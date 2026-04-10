"""Tests for POST /message endpoint (CORE-03)."""
import os
import pytest
import httpx
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

from app.main import app
from app.clients.pi_adapter import PiAdapterClient
from app.config import settings


def _make_client(transport: httpx.MockTransport | None = None) -> httpx.AsyncClient:
    """Create an httpx.AsyncClient with an optional mock transport."""
    if transport is not None:
        return httpx.AsyncClient(transport=transport, base_url="http://pi-harness")
    return httpx.AsyncClient()


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

        resp = await client.post("/message", json={"content": "hello", "user_id": "test"})

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

        resp = await client.post("/message", json={"content": "hello", "user_id": "test"})

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

        resp = await client.post("/message", json={"content": short_message, "user_id": "test"})

    assert resp.status_code == 422
    detail = resp.json().get("detail", "")
    assert "too long" in detail.lower() or "tokens" in detail.lower()
