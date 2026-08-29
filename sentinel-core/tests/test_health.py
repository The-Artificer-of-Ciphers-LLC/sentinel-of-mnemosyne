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


async def test_health_endpoint_probes_embedding_base_url_not_chat_base_url(monkeypatch):
    """Regression (43-05 live cutover): the /health embedding probe MUST be
    called with settings.embedding_base_url, NOT settings.lmstudio_base_url
    (the chat provider's URL). Missing this assertion is what let a third
    D-02 read-site regress to the chat URL undetected — the probe's return
    value was mocked but its call arguments were never inspected."""
    from app import main as main_module

    # Guarantee the two URLs are distinct so the assertion below is meaningful.
    monkeypatch.setattr(main_module.settings, "lmstudio_base_url", "http://chat-backend.test/v1")
    monkeypatch.setattr(main_module.settings, "embedding_base_url", "http://embedding-backend.test/v1")
    assert main_module.settings.embedding_base_url != main_module.settings.lmstudio_base_url

    calls = []

    async def _probe_spy(http_client, base_url, model_name):
        calls.append(base_url)
        return True

    monkeypatch.setattr(main_module, "probe_embedding_model_loaded", _probe_spy)

    app.state.http_client = object()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    assert len(calls) == 1, "probe_embedding_model_loaded must be called exactly once"
    assert calls[0] == main_module.settings.embedding_base_url, (
        f"probe_embedding_model_loaded must be called with settings.embedding_base_url, "
        f"got {calls[0]!r} (settings.lmstudio_base_url={main_module.settings.lmstudio_base_url!r})"
    )


async def test_health_endpoint_reports_profile_incomplete_with_stubs(monkeypatch):
    """/health reports profile="incomplete" when the canonical self/ files are
    still unfilled stubs (onboarding, GH #38)."""
    from app import main as main_module
    from app.services.recall import build_self_stub
    from app.services.self_profile import CANONICAL_PROFILE_PATHS
    from tests.fakes.vault import FakeVault

    async def _probe_loaded(*_args, **_kwargs):
        return True

    monkeypatch.setattr(main_module, "probe_embedding_model_loaded", _probe_loaded)

    app.state.http_client = object()
    app.state.vault = FakeVault(
        notes={p: build_self_stub(p) for p in CANONICAL_PROFILE_PATHS}
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["profile"] == "incomplete"


async def test_health_endpoint_reports_profile_complete_when_filled(monkeypatch):
    """/health reports profile="complete" when all canonical self/ files hold
    real (non-stub) content."""
    from app import main as main_module
    from app.services.self_profile import CANONICAL_PROFILE_PATHS
    from tests.fakes.vault import FakeVault

    async def _probe_loaded(*_args, **_kwargs):
        return True

    monkeypatch.setattr(main_module, "probe_embedding_model_loaded", _probe_loaded)

    app.state.http_client = object()
    app.state.vault = FakeVault(
        notes={p: f"# {p}\n\nReal content.\n" for p in CANONICAL_PROFILE_PATHS}
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["profile"] == "complete"


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
