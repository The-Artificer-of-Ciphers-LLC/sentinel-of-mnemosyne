"""Tests for POST /modules/register and POST /modules/{name}/{path} endpoints (Phase 27 SC-1–SC-4)."""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.routes.modules import ModuleRegistration

AUTH_HEADERS = {"X-Sentinel-Key": "test-key-for-pytest"}

_VALID_REGISTRATION = {
    "name": "test-module",
    "base_url": "http://test-module:9000",
    "routes": [{"path": "/run", "description": "Run the module"}],
}


@pytest.fixture
def mock_http_client():
    m = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json = MagicMock(return_value={"result": "ok"})
    m.post = AsyncMock(return_value=mock_resp)
    return m


@pytest.fixture(autouse=True)
def setup_app_state(mock_http_client):
    """Reset module registry and inject mock http client before each test."""
    app.state.module_registry = {}
    app.state.http_client = mock_http_client
    # Minimal other state required by middleware/lifespan
    app.state.obsidian_client = MagicMock()
    app.state.ai_provider_name = "lmstudio"
    app.state.settings = MagicMock()
    app.state.settings.pi_harness_url = "http://pi-harness:3000"


async def test_register_module():
    """SC-1: POST /modules/register returns {"status": "registered"} and stores entry."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/modules/register", json=_VALID_REGISTRATION, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert resp.json() == {"status": "registered"}
    assert "test-module" in app.state.module_registry


async def test_proxy_module():
    """SC-2: POST /modules/{name}/{path} proxies request to registered module and returns response."""
    # Pre-register the module
    app.state.module_registry["test-module"] = ModuleRegistration(**_VALID_REGISTRATION)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/modules/test-module/run",
            json={"input": "hello"},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 200
    assert resp.json() == {"result": "ok"}


async def test_proxy_module_unavailable():
    """SC-3: POST /modules/{name}/{path} returns 503 when module base_url is unreachable."""
    app.state.module_registry["test-module"] = ModuleRegistration(**_VALID_REGISTRATION)
    app.state.http_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/modules/test-module/run",
            json={},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 503
    assert resp.json()["detail"] == {"error": "module unavailable"}


async def test_proxy_unknown_module():
    """SC-4: POST /modules/{name}/{path} returns 404 when module is not registered."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/modules/nonexistent/run",
            json={},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 404


async def test_register_requires_auth():
    """POST /modules/register without X-Sentinel-Key returns 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/modules/register", json=_VALID_REGISTRATION)

    assert resp.status_code in (401, 403)
