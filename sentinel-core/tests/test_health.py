"""Tests for the GET /health endpoint.

Behavioral coverage for 260502-1zv D-02: the /health response must include
an ``embedding_model`` field reporting "loaded" or "not_loaded", and the
existing ``status`` and ``obsidian`` fields must remain present (backwards
compat — multiple operator dashboards already key on those fields).
"""
from __future__ import annotations

import os

from httpx import ASGITransport, AsyncClient

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

from app.main import app  # noqa: E402


async def test_health_endpoint_reports_embedding_status_loaded(monkeypatch):
    """When the embedding probe returns True, /health returns
    embedding_model="loaded". Other fields preserved."""
    from app import main as main_module

    async def _probe_loaded(*_args, **_kwargs):
        return True

    monkeypatch.setattr(
        main_module, "probe_embedding_model_loaded", _probe_loaded
    )

    # Seed app.state.http_client — ASGITransport bypasses lifespan so the
    # state attr is unset; without it the /health probe call errors out
    # before the monkeypatched function fires (args evaluated first).
    app.state.http_client = object()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "obsidian" in body  # backwards compat
    assert body["embedding_model"] == "loaded"


async def test_health_endpoint_reports_embedding_status_not_loaded(monkeypatch):
    """When the embedding probe returns False, /health returns
    embedding_model="not_loaded"."""
    from app import main as main_module

    async def _probe_not_loaded(*_args, **_kwargs):
        return False

    monkeypatch.setattr(
        main_module, "probe_embedding_model_loaded", _probe_not_loaded
    )

    # Seed app.state.http_client — ASGITransport bypasses lifespan so the
    # state attr is unset; without it the /health probe call errors out
    # before the monkeypatched function fires (args evaluated first).
    app.state.http_client = object()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["embedding_model"] == "not_loaded"


async def test_health_endpoint_graceful_degrade_when_probe_raises(monkeypatch):
    """Even if the probe raises, /health must return 200 with
    embedding_model="not_loaded" — graceful degrade rule."""
    from app import main as main_module

    async def _probe_raises(*_args, **_kwargs):
        raise RuntimeError("simulated probe crash")

    monkeypatch.setattr(
        main_module, "probe_embedding_model_loaded", _probe_raises
    )

    # Seed app.state.http_client — ASGITransport bypasses lifespan so the
    # state attr is unset; without it the /health probe call errors out
    # before the monkeypatched function fires (args evaluated first).
    app.state.http_client = object()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["embedding_model"] == "not_loaded"
