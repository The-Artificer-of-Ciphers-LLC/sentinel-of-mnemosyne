"""Tests for pf2e-module /healthz endpoint."""
import os
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")

from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch


async def test_healthz_returns_ok():
    """GET /healthz returns {"status": "ok", "module": "pathfinder"}."""
    # Import inside test to allow env vars to be set first
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "module": "pathfinder"}
