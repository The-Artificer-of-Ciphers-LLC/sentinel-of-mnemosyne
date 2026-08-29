"""Tests for GET /self/profile/status and POST /self/profile (GH issue #38).

Mirrors ``tests/test_pipeline_routes.py``'s FastAPI TestClient + RouteContext
app-construction pattern. This is the exact HTTP contract the Discord-side
agent codes against.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.recall import build_self_stub
from app.services.self_profile import CANONICAL_PROFILE_PATHS
from app.state import RouteContext
from tests.fakes.vault import FakeVault


def _make_app(vault) -> FastAPI:
    app = FastAPI()
    app.state.vault = vault
    app.state.route_ctx = RouteContext(
        vault=vault,
        classify=AsyncMock(side_effect=AssertionError("classify must not be called")),
        embedder=AsyncMock(side_effect=AssertionError("embedder must not be called")),
    )
    from app.routes.self_profile import router as self_profile_router

    app.include_router(self_profile_router)
    return app


# --- GET /self/profile/status ---


def test_status_shape_matches_contract_exactly():
    vault = FakeVault(
        notes={p: build_self_stub(p) for p in CANONICAL_PROFILE_PATHS}
    )
    client = TestClient(_make_app(vault))

    resp = client.get("/self/profile/status")
    assert resp.status_code == 200
    data = resp.json()

    assert set(data.keys()) == {"complete", "paths", "unfilled"}
    assert data["complete"] is False
    assert set(data["paths"].keys()) == set(CANONICAL_PROFILE_PATHS)
    for path in CANONICAL_PROFILE_PATHS:
        assert data["paths"][path] == "stub"
    assert set(data["unfilled"]) == set(CANONICAL_PROFILE_PATHS)


def test_status_reports_complete_true_when_all_filled():
    vault = FakeVault(
        notes={p: f"# {p}\n\nReal content.\n" for p in CANONICAL_PROFILE_PATHS}
    )
    client = TestClient(_make_app(vault))

    resp = client.get("/self/profile/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["complete"] is True
    assert data["unfilled"] == []


# --- POST /self/profile ---


def test_post_admin_gated_403(monkeypatch):
    monkeypatch.setenv("SENTINEL_ADMIN_USER_IDS", "")
    vault = FakeVault()
    client = TestClient(_make_app(vault))

    resp = client.post(
        "/self/profile",
        json={"user_id": "789", "path": "self/identity.md", "content": "hi"},
    )
    assert resp.status_code == 403


def test_post_rejects_non_profile_path_422(monkeypatch):
    monkeypatch.setenv("SENTINEL_ADMIN_USER_IDS", "*")
    vault = FakeVault()
    client = TestClient(_make_app(vault))

    resp = client.post(
        "/self/profile",
        json={"user_id": "1", "path": "ops/sweeps/embedding-index.json", "content": "pwned"},
    )
    assert resp.status_code == 422
    # The arbitrary-write guard must never touch the vault.
    assert "ops/sweeps/embedding-index.json" not in vault.notes


def test_post_returns_409_on_filled_without_force(monkeypatch):
    monkeypatch.setenv("SENTINEL_ADMIN_USER_IDS", "*")
    path = "self/identity.md"
    vault = FakeVault(notes={path: "# Identity\n\nCurated real content.\n"})
    client = TestClient(_make_app(vault))

    resp = client.post(
        "/self/profile",
        json={"user_id": "1", "path": path, "content": "overwrite attempt"},
    )
    assert resp.status_code == 409
    assert resp.json() == {"written": False, "reason": "already filled"}
    # The original content must be untouched.
    assert vault.notes[path] == "# Identity\n\nCurated real content.\n"


def test_post_succeeds_with_force_on_filled(monkeypatch):
    monkeypatch.setenv("SENTINEL_ADMIN_USER_IDS", "*")
    path = "self/identity.md"
    vault = FakeVault(notes={path: "# Identity\n\nCurated real content.\n"})
    client = TestClient(_make_app(vault))

    resp = client.post(
        "/self/profile",
        json={"user_id": "1", "path": path, "content": "new content", "force": True},
    )
    assert resp.status_code == 200
    assert resp.json() == {"written": True, "path": path}
    assert vault.notes[path] == "new content"


def test_post_succeeds_on_stub_without_force():
    import os

    os.environ["SENTINEL_ADMIN_USER_IDS"] = "*"
    try:
        path = "self/goals.md"
        vault = FakeVault(notes={path: build_self_stub(path)})
        client = TestClient(_make_app(vault))

        resp = client.post(
            "/self/profile",
            json={"user_id": "1", "path": path, "content": "Ship onboarding."},
        )
        assert resp.status_code == 200
        assert resp.json() == {"written": True, "path": path}
        assert vault.notes[path] == "Ship onboarding."
    finally:
        os.environ.pop("SENTINEL_ADMIN_USER_IDS", None)
