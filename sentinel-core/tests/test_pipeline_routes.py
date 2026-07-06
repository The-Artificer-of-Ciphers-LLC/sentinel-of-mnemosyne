"""RED scaffold for ``app.routes.pipeline`` (Phase 46, PIPE-06).

Wave 0 (Plan 46-01) pins the intended route contract ahead of Wave 3
landing the module. Function-scope imports keep pytest collection green
while ``app.routes.pipeline`` does not exist yet -- these tests FAIL at
runtime (ModuleNotFoundError during the test body) until Wave 3 lands it.

Mirrors ``tests/test_graph_routes.py``'s FastAPI TestClient + RouteContext
app-construction pattern and ``tests/test_note_routes.py``'s
``test_sweep_start_admin_only`` shape (PATTERNS.md "routes/pipeline.py"
section):

    POST /vault/pipeline/start   -- admin-gated via _is_admin_route (403 on non-admin)
    GET  /vault/pipeline/status  -- ungated, returns the PipelineReport dict shape
"""
from __future__ import annotations

from unittest.mock import AsyncMock


def _make_app(vault, *, classify=None, embedder=None):
    from fastapi import FastAPI

    from app.state import RouteContext

    app = FastAPI()
    app.state.vault = vault
    app.state.route_ctx = RouteContext(
        vault=vault,
        classify=classify or AsyncMock(side_effect=AssertionError("classify must not be called")),
        embedder=embedder or AsyncMock(side_effect=AssertionError("embedder must not be called")),
    )
    from app.routes.pipeline import router as pipeline_router

    app.include_router(pipeline_router)
    return app


async def test_pipeline_start_admin_gated_403(monkeypatch):
    """A non-admin user_id gets 403 from POST /vault/pipeline/start."""
    from fastapi.testclient import TestClient

    from tests.fakes.vault import FakeVault

    monkeypatch.setenv("SENTINEL_ADMIN_USER_IDS", "")
    vault = FakeVault()
    client = TestClient(_make_app(vault))

    resp = client.post("/vault/pipeline/start", json={"user_id": "789", "mode": "ralph"})
    assert resp.status_code == 403


async def test_pipeline_status_returns_report_shape():
    """GET /vault/pipeline/status is ungated and returns the report dict shape."""
    from fastapi.testclient import TestClient

    from tests.fakes.vault import FakeVault

    vault = FakeVault()
    client = TestClient(_make_app(vault))

    resp = client.get("/vault/pipeline/status")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("status", "mode"):
        assert key in data, f"expected {key!r} in pipeline status response: {data}"
