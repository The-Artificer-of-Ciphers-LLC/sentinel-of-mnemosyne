"""Tests for CORSMiddleware configuration in Sentinel Core (Phase 28, MOD-02)."""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("CORS_ALLOW_ORIGINS", "http://localhost:30000")
os.environ.setdefault("CORS_ALLOW_ORIGIN_REGEX", r"https://.*\.forge-vtt\.com")

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import MagicMock

from app.main import app
from app.state import RouteContext

AUTH_HEADERS = {"X-Sentinel-Key": "test-key-for-pytest"}


@pytest.fixture(autouse=True)
def setup_app_state():
    app.state.module_registry = {}
    app.state.http_client = MagicMock()
    app.state.vault = MagicMock()
    app.state.ai_provider_name = "lmstudio"
    app.state.settings = MagicMock()
    app.state.settings.pi_harness_url = "http://pi-harness:3000"
    app.state.injection_filter = MagicMock()
    app.state.output_scanner = MagicMock()
    app.state.route_ctx = RouteContext(
        vault=app.state.vault,
        settings=app.state.settings,
        http_client=app.state.http_client,
        module_registry=app.state.module_registry,
        ai_provider_name=app.state.ai_provider_name,
    )


async def test_cors_preflight_returns_200():
    """OPTIONS preflight must return 200 with CORS headers — not 401 from APIKeyMiddleware."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.options(
            "/modules/pathfinder/healthz",
            headers={
                "Origin": "http://localhost:30000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Sentinel-Key",
            },
        )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers


async def test_cors_no_wildcard():
    """allow_origins must not contain '*' — breaks credential-bearing requests per D-04."""
    from app.config import settings
    origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
    assert "*" not in origins


async def test_cors_credential_origin_explicit():
    """allow_credentials=True header is present in preflight response."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:30000",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert "access-control-allow-credentials" in resp.headers


async def test_cors_regex_configured():
    """CORS_ALLOW_ORIGIN_REGEX default is the Forge VTT subdomain pattern (D-03)."""
    from app.config import settings
    assert "forge-vtt" in settings.cors_allow_origin_regex
