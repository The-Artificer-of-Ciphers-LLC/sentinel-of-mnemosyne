"""Tests for POST /embeddings (Phase 43-02, D-06/EMB-01).

Thin passthrough to ctx.embedder — no /message pipeline reuse.
"""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

from app.errors import EmbeddingModelUnavailable
from app.main import app
from app.state import RouteContext

AUTH_HEADERS = {"X-Sentinel-Key": "test-key-for-pytest"}

_VALID_BODY = {"texts": ["hello", "world"]}

# Sentinel value distinguishing "attribute absent" from "attribute set to None".
_MISSING = object()


class _FakeSettings:
    embedding_model = "text-embedding-nomic-embed-text-v1.5"
    embedding_base_url = "http://secret-embed-host:1234/v1"
    embedding_api_key = "sk-super-secret-embed-key"


@pytest.fixture
def mock_embedder():
    return AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]])


@pytest.fixture(autouse=True)
def setup_app_state(mock_embedder):
    """Seed RouteContext.embedder before each test; restore after."""
    orig = getattr(app.state, "route_ctx", _MISSING)
    app.state.route_ctx = RouteContext(
        vault=AsyncMock(),
        embedder=mock_embedder,
        settings=_FakeSettings(),
    )
    yield
    if orig is _MISSING:
        try:
            delattr(app.state, "route_ctx")
        except AttributeError:
            pass
    else:
        app.state.route_ctx = orig


async def test_embeddings_success(mock_embedder):
    """200 with valid key + body returns one vector per text via ctx.embedder()."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/embeddings", json=_VALID_BODY, headers=AUTH_HEADERS)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["embeddings"] == [[0.1, 0.2], [0.3, 0.4]]
    assert body["model"] == "text-embedding-nomic-embed-text-v1.5"
    mock_embedder.assert_awaited_once_with(["hello", "world"])


async def test_embeddings_requires_auth():
    """No X-Sentinel-Key header -> 401 (existing global middleware, no new auth code)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/embeddings", json=_VALID_BODY)

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Unauthorized"}


async def test_embeddings_422_on_too_many_texts():
    """texts array exceeding _MAX_TEXTS is rejected by pydantic validation (422)."""
    too_many = {"texts": ["x"] * 201}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/embeddings", json=too_many, headers=AUTH_HEADERS)

    assert resp.status_code == 422


async def test_embeddings_422_on_text_too_long():
    """A single text exceeding _MAX_TEXT_LENGTH is rejected (422)."""
    too_long = {"texts": ["x" * 8001]}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/embeddings", json=too_long, headers=AUTH_HEADERS)

    assert resp.status_code == 422


async def test_embeddings_422_on_empty_texts():
    """Empty texts list is rejected (422)."""
    empty = {"texts": []}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/embeddings", json=empty, headers=AUTH_HEADERS)

    assert resp.status_code == 422


async def test_embeddings_503_on_backend_unavailable(mock_embedder):
    """EmbeddingModelUnavailable -> 503 with a generic detail; no secrets leaked."""
    mock_embedder.side_effect = EmbeddingModelUnavailable(
        "No embedding model loaded. Configured: openai/text-embedding-nomic-embed-text-v1.5. "
        "api_base=http://secret-embed-host:1234/v1 api_key=sk-super-secret-embed-key"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/embeddings", json=_VALID_BODY, headers=AUTH_HEADERS)

    assert resp.status_code == 503
    body_text = resp.text
    assert "secret-embed-host" not in body_text
    assert "sk-super-secret-embed-key" not in body_text
