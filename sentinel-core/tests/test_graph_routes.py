"""Tests for /vault/graph, /vault/stats, /vault/check routes (Plan 45-06, NOTE-03).

Mirrors ``test_note_routes.py``'s FastAPI TestClient + RouteContext app-
construction pattern, but uses the shared ``FakeVault`` test double (which
already implements ``list_under``/``read_note``/``write_note`` against an
in-memory ``notes``/``dirs`` store) so the sidecar rebuild the routes trigger
has something real to walk.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.graph import router as graph_router
from app.services.links_sidecar_index import LINKS_INDEX_PATH
from app.state import RouteContext
from tests.fakes.vault import FakeVault


def _vault_with_notes(notes: dict[str, str]) -> FakeVault:
    """Build a FakeVault pre-populated with a flat notes/ dir listing + bodies."""
    vault = FakeVault(notes=dict(notes))
    filenames = [path.rsplit("/", 1)[-1] for path in notes if path.startswith("notes/")]
    vault.dirs[""] = ["notes/"]
    vault.dirs["notes"] = filenames
    return vault


def _make_app(vault: FakeVault, *, classify=None, embedder=None) -> FastAPI:
    app = FastAPI()
    app.state.vault = vault
    app.state.route_ctx = RouteContext(
        vault=vault,
        classify=classify or AsyncMock(side_effect=AssertionError("classify must not be called")),
        embedder=embedder or AsyncMock(side_effect=AssertionError("embedder must not be called")),
    )
    app.include_router(graph_router)
    return app


_HUB_BODY = (
    "# Topic Hub\n\n[[Note A]]\n\n"
    "```_schema\n"
    "type: hub\n"
    "```\n"
)

_NOTE_A_BODY = (
    "# A Note About Something\n\n"
    "See [[Note B]] and [[Topic Hub]].\n\n"
    "```_schema\n"
    "type: reference\n"
    "```\n"
)

_NOTE_B_BODY = "no schema, no title, no links here\n"


def _seeded_vault() -> FakeVault:
    return _vault_with_notes(
        {
            "notes/topic-hub.md": _HUB_BODY,
            "notes/note-a.md": _NOTE_A_BODY,
            "notes/note-b.md": _NOTE_B_BODY,
        }
    )


# --- GET /vault/graph ---


def test_vault_graph_returns_200_with_modeled_json():
    vault = _seeded_vault()
    client = TestClient(_make_app(vault))

    resp = client.get("/vault/graph")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["note_count"] == 3
    assert data["hub_count"] == 1
    assert set(data["backlinks"].keys()) == {
        "notes/topic-hub.md",
        "notes/note-a.md",
        "notes/note-b.md",
    }
    assert data["caveat"] is None


def test_vault_graph_invokes_hybrid_freshness_and_persists_sidecar():
    vault = _seeded_vault()
    client = TestClient(_make_app(vault))

    assert LINKS_INDEX_PATH not in vault.notes
    resp = client.get("/vault/graph")
    assert resp.status_code == 200
    # Hybrid freshness rebuild wrote the sidecar (D-04a).
    assert LINKS_INDEX_PATH in vault.notes


# --- GET /vault/stats ---


def test_vault_stats_returns_200_with_modeled_json():
    vault = _seeded_vault()
    client = TestClient(_make_app(vault))

    resp = client.get("/vault/stats")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["note_count"] == 3
    assert data["hub_count"] == 1
    assert data["orphan_count"] == 0
    assert data["avg_notes_per_hub"] == 3.0
    assert data["caveat"] is None


def test_vault_stats_zero_hubs_avoids_divide_by_zero():
    vault = _vault_with_notes({"notes/lonely.md": "# Lonely Note\n\nno links\n"})
    client = TestClient(_make_app(vault))

    resp = client.get("/vault/stats")

    assert resp.status_code == 200
    data = resp.json()
    assert data["hub_count"] == 0
    assert data["avg_notes_per_hub"] == 0.0
    assert data["orphan_count"] == 1


# --- GET /vault/check ---


def test_vault_check_returns_200_with_modeled_json():
    vault = _seeded_vault()
    client = TestClient(_make_app(vault))

    resp = client.get("/vault/check")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["note_count"] == 3
    by_path = {r["path"]: r for r in data["results"]}
    assert by_path["notes/topic-hub.md"]["has_schema"] is True
    assert by_path["notes/note-b.md"]["has_schema"] is False
    assert "missing _schema block" in by_path["notes/note-b.md"]["failures"]
    assert "missing wikilink" in by_path["notes/note-b.md"]["failures"]
    assert data["compliant_count"] >= 1


def test_vault_check_makes_zero_llm_or_embedding_calls():
    vault = _seeded_vault()
    classify = AsyncMock(side_effect=AssertionError("classify must not be called"))
    embedder = AsyncMock(side_effect=AssertionError("embedder must not be called"))
    client = TestClient(_make_app(vault, classify=classify, embedder=embedder))

    resp = client.get("/vault/check")

    assert resp.status_code == 200, resp.text
    classify.assert_not_called()
    embedder.assert_not_called()


# --- No admin gate (parity with sweep-route admin test, inverted) ---


def test_non_admin_caller_receives_normal_200_from_all_three_routes(monkeypatch):
    # Deliberately configure NO admin users — a caller that would be denied
    # by /vault/sweep/start's _is_admin_route gate must still get a plain 200
    # from all three of these read-only routes (T-45-ACL).
    monkeypatch.setenv("SENTINEL_ADMIN_USER_IDS", "")
    vault = _seeded_vault()
    client = TestClient(_make_app(vault))

    for path in ("/vault/graph", "/vault/stats", "/vault/check"):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} -> {resp.status_code}: {resp.text}"


# --- Stale-index caveat degrade path ---


def test_vault_graph_degrades_to_existing_index_when_sweep_lock_held():
    """rebuild_links_index_if_stale (D-04a) already absorbs SweepInProgressError
    internally and degrades to the existing (possibly stale) index without
    raising to its caller (Pitfall 2) — so the route's own defensive
    SweepInProgressError guard never actually fires in current behavior; this
    characterizes that the route stays a plain 200 with the pre-lock data
    rather than a 500, which is the load-bearing contract here.
    """
    from datetime import datetime, timezone

    vault = _seeded_vault()

    async def _seed_index():
        from app.services.links_sidecar_index import build_links_index, encode_index_body

        idx = await build_links_index(vault, existing={})
        vault.notes[LINKS_INDEX_PATH] = encode_index_body(idx)
        return idx

    import asyncio

    existing = asyncio.run(_seed_index())

    # Hold the sweep lock so a would-be rebuild (triggered by a path-set
    # change below) is forced to degrade rather than raise.
    asyncio.run(vault.acquire_sweep_lock(now=datetime.now(timezone.utc)))
    vault.notes["notes/note-c.md"] = "# Note C\n"
    vault.dirs["notes"].append("note-c.md")

    client = TestClient(_make_app(vault))
    resp = client.get("/vault/graph")

    assert resp.status_code == 200
    data = resp.json()
    assert data["note_count"] == len(existing)
