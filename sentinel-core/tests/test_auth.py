"""Tests for APIKeyMiddleware authentication (IFACE-06)."""
import os
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

from app.main import app

# Sentinel value used by teardown to distinguish "attribute was absent" from
# "attribute was set to None".
_MISSING = object()


async def test_auth_rejects_missing_key():
    """POST /message without X-Sentinel-Key returns 401 Unauthorized."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/message", json={"content": "hello", "user_id": "test"})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Unauthorized"}


async def test_auth_rejects_wrong_key():
    """POST /message with wrong X-Sentinel-Key returns 401 Unauthorized."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message",
            json={"content": "hello", "user_id": "test"},
            headers={"X-Sentinel-Key": "wrong-key"},
        )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Unauthorized"}


async def test_health_bypasses_auth():
    """GET /health without X-Sentinel-Key returns 200 (health is whitelisted)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_auth_accepts_valid_key():
    """POST /message with correct X-Sentinel-Key passes auth (not 401)."""
    import httpx
    from unittest.mock import AsyncMock
    from app.config import settings
    from app.clients.pi_adapter import PiAdapterClient

    from app.services.injection_filter import InjectionFilter

    _state_keys = (
        "vault",
        "context_window",
        "settings",
        "injection_filter",
        "output_scanner",
        "pi_adapter",
        "ai_provider",
        "message_processor",
    )
    # Save originals so we can restore them after the test.
    _orig = {k: getattr(app.state, k, _MISSING) for k in _state_keys}

    try:
        # Seed app.state so the route handler doesn't crash on state access
        mock_obsidian = AsyncMock()
        mock_obsidian.get_user_context.return_value = None
        mock_obsidian.get_recent_sessions.return_value = []
        mock_obsidian.write_session_summary.return_value = None
        app.state.vault = mock_obsidian
        app.state.context_window = 8192
        app.state.settings = settings
        app.state.injection_filter = InjectionFilter()
        mock_output_scanner = AsyncMock()
        mock_output_scanner.scan.return_value = (True, None)
        app.state.output_scanner = mock_output_scanner

        # Pi harness mock — connect error so route falls through to ai_provider
        def pi_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("not running in test")

        pi_http = httpx.AsyncClient(
            transport=httpx.MockTransport(pi_handler), base_url="http://pi-harness"
        )
        app.state.pi_adapter = PiAdapterClient(pi_http, "http://pi-harness")

        # AI provider mock — returns a response so route completes successfully
        mock_ai = AsyncMock()
        mock_ai.complete = AsyncMock(return_value="Auth test response")
        app.state.ai_provider = mock_ai

        # Build the processor against the just-installed test mocks. The route
        # now reads app.state.message_processor directly (no factory).
        from app.services.message_processing import MessageProcessor

        app.state.message_processor = MessageProcessor(
            vault=app.state.vault,
            ai_provider=app.state.ai_provider,
            injection_filter=app.state.injection_filter,
            output_scanner=app.state.output_scanner,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/message",
                json={"content": "hello", "user_id": "test"},
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )
        # Auth passed — downstream may 200, 422, or 503 but NOT 401
        assert resp.status_code != 401
    finally:
        # Restore every attribute to its pre-test value so mutations don't
        # bleed into subsequent tests running in the same process.
        for k, v in _orig.items():
            if v is _MISSING:
                try:
                    delattr(app.state, k)
                except AttributeError:
                    pass
            else:
                setattr(app.state, k, v)
