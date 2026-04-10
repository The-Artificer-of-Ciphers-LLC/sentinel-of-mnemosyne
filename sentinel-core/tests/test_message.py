"""Tests for POST /message endpoint (CORE-03) and MessageEnvelope validation."""
import os
import pytest
import httpx
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

from app.main import app
from app.clients.pi_adapter import PiAdapterClient
from app.config import settings

AUTH_HEADER = {"X-Sentinel-Key": "test-key-for-pytest"}


def _make_client(transport: httpx.MockTransport | None = None) -> httpx.AsyncClient:
    """Create an httpx.AsyncClient with an optional mock transport."""
    if transport is not None:
        return httpx.AsyncClient(transport=transport, base_url="http://pi-harness")
    return httpx.AsyncClient()


@pytest.fixture(autouse=True)
def default_obsidian_client():
    """
    Provide a default no-op ObsidianClient mock on app.state for all tests.
    Tests that need specific Obsidian behavior override app.state.obsidian_client directly.
    """
    from unittest.mock import AsyncMock

    mock = AsyncMock()
    mock.get_user_context.return_value = None
    mock.get_recent_sessions.return_value = []
    mock.write_session_summary.return_value = None
    mock.search_vault.return_value = []
    app.state.obsidian_client = mock
    return mock


@pytest.fixture
def pi_harness_mock():
    """Mock Pi harness returning a fixed response."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"content": "Hello from Pi"})
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "piAlive": True, "restarts": 0})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture
def pi_harness_down_mock():
    """Mock Pi harness that refuses connections."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    return httpx.MockTransport(handler)


@pytest.fixture
def lmstudio_available_mock(mock_lmstudio_models_response):
    """Mock LM Studio returning 8192 context window."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/v0/models/" in request.url.path:
            return httpx.Response(200, json=mock_lmstudio_models_response)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def test_post_message_returns_response_envelope(pi_harness_mock, lmstudio_available_mock):
    """POST /message with valid content returns ResponseEnvelope with content and model fields."""
    # Set up app state directly — lifespan runs when entering AsyncClient context
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Inject mocked Pi adapter into app state (lifespan has already set app.state)
        pi_http = _make_client(pi_harness_mock)
        app.state.pi_adapter = PiAdapterClient(pi_http, "http://pi-harness")
        app.state.context_window = 8192
        app.state.settings = settings

        resp = await client.post(
            "/message",
            json={"content": "hello", "user_id": "test"},
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "content" in data
    assert "model" in data


async def test_post_message_503_when_pi_unavailable(pi_harness_down_mock):
    """POST /message returns 503 when Pi harness is unreachable."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        pi_http = _make_client(pi_harness_down_mock)
        app.state.pi_adapter = PiAdapterClient(pi_http, "http://pi-harness")
        app.state.context_window = 8192
        app.state.settings = settings

        resp = await client.post(
            "/message",
            json={"content": "hello", "user_id": "test"},
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 503
    assert resp.json().get("detail") == "AI backend not ready"


async def test_post_message_422_when_message_too_long():
    """POST /message returns 422 when token count exceeds context window."""
    # Use a short message (passes Pydantic max_length) but set context_window=5
    # so token guard fires (even "hello" costs ~9 tokens with overhead+priming).
    short_message = "hello world"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        app.state.context_window = 5  # guaranteed to reject any real message
        app.state.settings = settings

        resp = await client.post(
            "/message",
            json={"content": short_message, "user_id": "test"},
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 422
    detail = resp.json().get("detail", "")
    assert "too long" in detail.lower() or "tokens" in detail.lower()


def test_user_id_rejects_path_traversal():
    """MessageEnvelope.user_id must reject path traversal characters."""
    from pydantic import ValidationError
    from app.models import MessageEnvelope

    with pytest.raises(ValidationError):
        MessageEnvelope(content="hi", user_id="../../etc/passwd")


def test_user_id_accepts_valid_chars():
    """MessageEnvelope.user_id accepts alphanumeric, hyphens, and underscores."""
    from app.models import MessageEnvelope

    env = MessageEnvelope(content="hi", user_id="trekkie_01-a")
    assert env.user_id == "trekkie_01-a"


# ---------------------------------------------------------------------------
# Wave 2 tests — Phase 2 memory-aware POST /message flow
# ---------------------------------------------------------------------------
from unittest.mock import AsyncMock


@pytest.fixture
def obsidian_with_context():
    """Mock ObsidianClient that returns user context and no sessions."""
    mock = AsyncMock()
    mock.get_user_context.return_value = "# User: trekkie\n\nI am a developer."
    mock.get_recent_sessions.return_value = []
    mock.write_session_summary.return_value = None
    mock.search_vault.return_value = []
    return mock


@pytest.fixture
def obsidian_no_context():
    """Mock ObsidianClient where user file does not exist."""
    mock = AsyncMock()
    mock.get_user_context.return_value = None
    mock.get_recent_sessions.return_value = []
    mock.write_session_summary.return_value = None
    mock.search_vault.return_value = []
    return mock


@pytest.fixture
def obsidian_write_fails():
    """Mock ObsidianClient where write raises an exception."""
    mock = AsyncMock()
    mock.get_user_context.return_value = None
    mock.get_recent_sessions.return_value = []
    mock.write_session_summary.side_effect = Exception("Obsidian write failed")
    mock.search_vault.return_value = []
    return mock


async def test_context_injected_when_file_exists(pi_harness_mock, obsidian_with_context):
    """When Obsidian returns user context, Pi receives a 3-message messages array."""
    captured_body = {}

    def capturing_handler(request: httpx.Request) -> httpx.Response:
        import json

        if request.url.path == "/prompt":
            captured_body.update(json.loads(request.content))
            return httpx.Response(200, json={"content": "Hello from Pi"})
        return httpx.Response(404)

    capturing_transport = httpx.MockTransport(capturing_handler)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        pi_http = _make_client(capturing_transport)
        app.state.pi_adapter = PiAdapterClient(pi_http, "http://pi-harness")
        app.state.obsidian_client = obsidian_with_context
        app.state.context_window = 8192
        app.state.settings = settings

        resp = await client.post(
            "/message",
            json={"content": "hello", "user_id": "trekkie"},
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert "messages" in captured_body
    messages = captured_body["messages"]
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert "trekkie" in messages[0]["content"].lower() or "developer" in messages[0]["content"].lower()
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Understood."
    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == "hello"


async def test_no_injection_when_user_file_missing(obsidian_no_context):
    """When Obsidian returns None (no user file), Pi receives single-message array."""
    captured_body = {}

    def capturing_handler(request: httpx.Request) -> httpx.Response:
        import json

        if request.url.path == "/prompt":
            captured_body.update(json.loads(request.content))
            return httpx.Response(200, json={"content": "Hello from Pi"})
        return httpx.Response(404)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        pi_http = _make_client(httpx.MockTransport(capturing_handler))
        app.state.pi_adapter = PiAdapterClient(pi_http, "http://pi-harness")
        app.state.obsidian_client = obsidian_no_context
        app.state.context_window = 8192
        app.state.settings = settings

        resp = await client.post(
            "/message",
            json={"content": "hello", "user_id": "new_user"},
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    messages = captured_body.get("messages", [])
    assert len(messages) == 1
    assert messages[0]["content"] == "hello"


async def test_no_injection_when_obsidian_down(pi_harness_mock):
    """When Obsidian is unreachable, response is still 200 (graceful degrade per D-3)."""
    obsidian_down = AsyncMock()
    obsidian_down.get_user_context.return_value = None  # graceful — returns None not raises
    obsidian_down.get_recent_sessions.return_value = []
    obsidian_down.write_session_summary.return_value = None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        pi_http = _make_client(pi_harness_mock)
        app.state.pi_adapter = PiAdapterClient(pi_http, "http://pi-harness")
        app.state.obsidian_client = obsidian_down
        app.state.context_window = 8192
        app.state.settings = settings

        resp = await client.post(
            "/message",
            json={"content": "hello", "user_id": "trekkie"},
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200


async def test_response_succeeds_when_write_fails(pi_harness_mock, obsidian_write_fails):
    """Session summary write failure does not affect the HTTP response (D-2 failure handling)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        pi_http = _make_client(pi_harness_mock)
        app.state.pi_adapter = PiAdapterClient(pi_http, "http://pi-harness")
        app.state.obsidian_client = obsidian_write_fails
        app.state.context_window = 8192
        app.state.settings = settings

        resp = await client.post(
            "/message",
            json={"content": "hello", "user_id": "trekkie"},
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert resp.json()["content"] == "Hello from Pi"


async def test_token_guard_fires_on_inflated_context(pi_harness_mock):
    """Token guard raises 422 when context-injected messages exceed context_window."""
    huge_context = AsyncMock()
    huge_context.get_user_context.return_value = "word " * 5000  # ~5000 tokens
    huge_context.get_recent_sessions.return_value = []
    huge_context.write_session_summary.return_value = None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        pi_http = _make_client(pi_harness_mock)
        app.state.pi_adapter = PiAdapterClient(pi_http, "http://pi-harness")
        app.state.obsidian_client = huge_context
        app.state.context_window = 10  # tiny window — truncation overhead alone exceeds this
        app.state.settings = settings

        resp = await client.post(
            "/message",
            json={"content": "hello", "user_id": "trekkie"},
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 422


async def test_context_truncated_to_budget(pi_harness_mock):
    """Context exceeding 25% of context_window is truncated before token guard runs."""
    # context_window=400 tokens → 25% budget = 100 tokens
    # 500-word context will exceed the 100-token budget and must be truncated
    long_context = AsyncMock()
    long_context.get_user_context.return_value = "word " * 500
    long_context.get_recent_sessions.return_value = []
    long_context.write_session_summary.return_value = None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        pi_http = _make_client(pi_harness_mock)
        app.state.pi_adapter = PiAdapterClient(pi_http, "http://pi-harness")
        app.state.obsidian_client = long_context
        app.state.context_window = 400  # 25% budget = 100 tokens
        app.state.settings = settings

        resp = await client.post(
            "/message",
            json={"content": "hello", "user_id": "trekkie"},
            headers=AUTH_HEADER,
        )

    # After truncation the full array fits within 400 tokens → 200 response
    assert resp.status_code == 200


async def test_send_messages_sends_array():
    """PiAdapterClient.send_messages() POSTs {messages: [...]} to bridge /prompt."""
    import json

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            captured.update(json.loads(request.content))
            return httpx.Response(200, json={"content": "ok"})
        return httpx.Response(404)

    async with AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test") as client:
        adapter = PiAdapterClient(client, "http://test")
        messages = [
            {"role": "user", "content": "ctx"},
            {"role": "assistant", "content": "Understood."},
            {"role": "user", "content": "hello"},
        ]
        result = await adapter.send_messages(messages)

    assert result == "ok"
    assert "messages" in captured
    assert captured["messages"] == messages
    assert "message" not in captured  # must NOT send legacy field
