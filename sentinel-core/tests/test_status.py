"""Tests for GET /status and GET /context/{user_id} endpoints (RD-05)."""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock

from app.main import app

AUTH_HEADERS = {"X-Sentinel-Key": "test-key-for-pytest"}


@pytest.fixture
def mock_obsidian():
    m = MagicMock()
    m.check_health = AsyncMock(return_value=True)
    m.get_recent_sessions = AsyncMock(return_value=["session1"])
    m.read_self_context = AsyncMock(return_value="context content")
    return m


@pytest.fixture
def mock_http_client():
    m = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    m.get = AsyncMock(return_value=mock_resp)
    return m


@pytest.fixture(autouse=True)
def setup_app_state(mock_obsidian, mock_http_client):
    app.state.obsidian_client = mock_obsidian
    app.state.http_client = mock_http_client
    app.state.ai_provider_name = "lmstudio"
    app.state.settings = MagicMock()
    app.state.settings.pi_harness_url = "http://pi-harness:3000"


async def test_status_all_up(mock_obsidian, mock_http_client):
    """When obsidian up and pi /health=200, returns status=ok."""
    mock_obsidian.check_health.return_value = True
    mock_http_client.get.return_value.status_code = 200

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/status", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


async def test_status_obsidian_down(mock_obsidian, mock_http_client):
    """When obsidian.check_health()=False, returns status=degraded with obsidian=unreachable."""
    mock_obsidian.check_health.return_value = False
    mock_http_client.get.return_value.status_code = 200

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/status", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["obsidian"] == "unreachable"


async def test_status_pi_down(mock_obsidian, mock_http_client):
    """When pi /health request fails, returns status=ok with pi_harness=unreachable (Pi is not a health gate)."""
    mock_obsidian.check_health.return_value = True
    mock_http_client.get.side_effect = Exception("connection refused")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/status", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["pi_harness"] == "unreachable"


async def test_status_includes_ai_provider(mock_obsidian, mock_http_client):
    """Response includes ai_provider key with a non-empty string value."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/status", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert "ai_provider" in data
    assert isinstance(data["ai_provider"], str)
    assert len(data["ai_provider"]) > 0


async def test_status_requires_auth():
    """GET /status without X-Sentinel-Key returns 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/status")

    assert resp.status_code in (401, 403)


async def test_context_returns_user_id():
    """GET /context/testuser returns JSON with user_id=testuser."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/context/testuser", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "testuser"


async def test_context_includes_recent_sessions_count():
    """Response includes recent_sessions_count as an integer."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/context/testuser", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert "recent_sessions_count" in data
    assert isinstance(data["recent_sessions_count"], int)


async def test_context_requires_auth():
    """GET /context/testuser without X-Sentinel-Key returns 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/context/testuser")

    assert resp.status_code in (401, 403)
