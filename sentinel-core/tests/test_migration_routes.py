"""RED admin-gated route tests for /vault/migrate/* (Phase 47, Plan 01
Wave 0, T-47-01).

Mirrors ``tests/test_note_routes.py``'s sweep-route tests (admin-gate 403
rejection + dry-run vs. live request shape) against the not-yet-existing
``POST /vault/migrate/start`` / ``GET /vault/migrate/status`` routes
(``app.routes.migration``, landed Plan 05). Fails RED today with a
ModuleNotFoundError/ImportError -- this is the intended Wave 0 state.

Reuses the exact ``SENTINEL_ADMIN_USER_IDS`` admin-gate env-var setup from
``test_note_routes.py`` -- no new auth scaffolding invented.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.migration import router as migration_router
from app.state import RouteContext


class _FakeVault:
    """Minimal in-memory Vault double -- these route tests never reach the
    real migration orchestrator (admin gate rejects, or the background task
    is scheduled but not awaited within the request/response cycle)."""

    def __init__(self) -> None:
        self.notes: dict[str, str] = {}

    async def read_note(self, path: str) -> str:
        return self.notes.get(path, "")

    async def write_note(self, path: str, body: str) -> None:
        self.notes[path] = body

    async def delete_note(self, path: str) -> None:
        self.notes.pop(path, None)


def _make_app(vault: _FakeVault) -> FastAPI:
    app = FastAPI()
    app.state.vault = vault
    app.state.route_ctx = RouteContext(vault=vault)
    app.include_router(migration_router)
    return app


def test_migrate_start_requires_admin(monkeypatch):
    """T-47-01: a non-admin user_id gets 403 -- the destructive, vault-wide
    /vault/migrate/start mutation must be admin-gated identically to
    /vault/sweep/start (V4 Access Control)."""
    monkeypatch.setenv("SENTINEL_ADMIN_USER_IDS", "")
    client = TestClient(_make_app(_FakeVault()))

    resp = client.post("/vault/migrate/start", json={"user_id": "789", "dry_run": True})

    assert resp.status_code == 403
    assert resp.json()["detail"] == "admin only"


def test_migrate_start_dry_run(monkeypatch):
    """An admin user_id with dry_run=True gets a 200 ack (migration_id +
    status:"running") and the run is scheduled as a background task."""
    monkeypatch.setenv("SENTINEL_ADMIN_USER_IDS", "123,456")
    client = TestClient(_make_app(_FakeVault()))

    resp = client.post("/vault/migrate/start", json={"user_id": "123", "dry_run": True})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "migration_id" in data
    assert data["status"] == "running"


def test_migrate_status_shape():
    """GET /vault/migrate/status returns the status-store shape with a
    status field in the running/complete/blocked/error vocabulary."""
    client = TestClient(_make_app(_FakeVault()))

    resp = client.get("/vault/migrate/status")

    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] in {"idle", "running", "complete", "blocked", "error"}
