"""Tests for POST /provider/complete (Phase 42-03, D-09/SC-6).

Thin passthrough to ctx.ai_provider.complete() — no /message pipeline reuse.
"""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

from app.errors import ProviderUnavailableError
from app.main import app
from app.state import RouteContext

AUTH_HEADERS = {"X-Sentinel-Key": "test-key-for-pytest"}

_VALID_BODY = {"messages": [{"role": "user", "content": "hello"}]}

# Sentinel value distinguishing "attribute absent" from "attribute set to None".
_MISSING = object()


@pytest.fixture
def mock_ai_provider():
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value="Hi there")
    return provider


@pytest.fixture(autouse=True)
def setup_app_state(mock_ai_provider):
    """Seed RouteContext.ai_provider before each test; restore after."""
    orig = getattr(app.state, "route_ctx", _MISSING)
    app.state.route_ctx = RouteContext(
        vault=AsyncMock(),
        ai_provider=mock_ai_provider,
        ai_provider_name="lmstudio",
    )
    yield
    if orig is _MISSING:
        try:
            delattr(app.state, "route_ctx")
        except AttributeError:
            pass
    else:
        app.state.route_ctx = orig


async def test_provider_complete_success(mock_ai_provider):
    """200 with valid key + body returns {content, model} via ctx.ai_provider.complete()."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=_VALID_BODY, headers=AUTH_HEADERS)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"content": "Hi there", "model": "lmstudio"}
    mock_ai_provider.complete.assert_awaited_once()
    call_args = mock_ai_provider.complete.call_args
    assert call_args.args[0] == [{"role": "user", "content": "hello"}]


async def test_provider_complete_requires_auth():
    """No X-Sentinel-Key header -> 401 (existing global middleware, no new auth code)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=_VALID_BODY)

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Unauthorized"}


async def test_provider_complete_no_provider_configured():
    """ctx.ai_provider is None -> 500 'ai_provider not configured'."""
    app.state.route_ctx = RouteContext(vault=AsyncMock(), ai_provider=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=_VALID_BODY, headers=AUTH_HEADERS)

    assert resp.status_code == 500
    assert resp.json() == {"detail": "ai_provider not configured"}


async def test_provider_complete_503_on_provider_unavailable(mock_ai_provider):
    """ProviderUnavailableError -> 503 with a generic detail; no secrets leaked (T-42-08)."""
    mock_ai_provider.complete = AsyncMock(
        side_effect=ProviderUnavailableError(
            "Both providers failed. api_base=http://secret-lmstudio-host:1234 api_key=sk-super-secret"
        )
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=_VALID_BODY, headers=AUTH_HEADERS)

    assert resp.status_code == 503
    body_text = resp.text
    assert "secret-lmstudio-host" not in body_text
    assert "sk-super-secret" not in body_text


async def test_provider_complete_422_on_too_many_messages():
    """messages array exceeding the cap is rejected by Pydantic validation (422)."""
    too_many = {"messages": [{"role": "user", "content": "x"}] * 51}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=too_many, headers=AUTH_HEADERS)

    assert resp.status_code == 422


async def test_provider_complete_422_on_content_too_long():
    """A single message exceeding the content-length cap is rejected (422)."""
    too_long = {"messages": [{"role": "user", "content": "x" * 32_001}]}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=too_long, headers=AUTH_HEADERS)

    assert resp.status_code == 422
