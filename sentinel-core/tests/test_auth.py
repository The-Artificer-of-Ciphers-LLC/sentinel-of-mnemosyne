"""Tests for APIKeyMiddleware authentication (IFACE-06)."""
import os
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

from app.main import app


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

    # Seed app.state so the route handler doesn't crash on state access
    mock_obsidian = AsyncMock()
    mock_obsidian.get_user_context.return_value = None
    mock_obsidian.get_recent_sessions.return_value = []
    mock_obsidian.write_session_summary.return_value = None
    app.state.obsidian_client = mock_obsidian
    app.state.context_window = 8192
    app.state.settings = settings

    # Pi harness mock — connect error so route falls through to ai_provider
    def pi_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("not running in test")

    pi_http = httpx.AsyncClient(transport=httpx.MockTransport(pi_handler), base_url="http://pi-harness")
    app.state.pi_adapter = PiAdapterClient(pi_http, "http://pi-harness")

    # AI provider mock — returns a response so route completes successfully
    mock_ai = AsyncMock()
    mock_ai.complete = AsyncMock(return_value="Auth test response")
    app.state.ai_provider = mock_ai

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message",
            json={"content": "hello", "user_id": "test"},
            headers={"X-Sentinel-Key": "test-key-for-pytest"},
        )
    # Auth passed — downstream may 200, 422, or 503 but NOT 401
    assert resp.status_code != 401
