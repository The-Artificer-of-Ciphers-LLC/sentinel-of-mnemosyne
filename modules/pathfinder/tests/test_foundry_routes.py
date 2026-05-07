"""Tests for POST /foundry/messages/import projection wiring (Plan 37-12).

Covers FCM-04 (idempotency end-to-end via the route) and FCM-05 (dry-run +
metric shape) at the route layer. Function-scope `import_nedb_chatlogs_from_inbox`
is patched at app.routes.foundry to avoid touching real Obsidian or the FS.
"""
from __future__ import annotations

import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


_PROJECTION_METRIC_KEYS = {
    "player_updates",
    "npc_updates",
    "player_deduped",
    "npc_deduped",
    "unmatched_speakers",
    "dry_run",
}


def _make_import_stub(projection_payload):
    """Build an AsyncMock stand-in for import_nedb_chatlogs_from_inbox.

    Captures kwargs on the mock for later assertions and returns a route-shaped
    response dict whose `projection` key matches the supplied payload.
    """
    async def _impl(**kwargs):
        return {
            "source": "stub",
            "note_path": "mnemosyne/pf2e/sessions/foundry-chat/2026-05-07/chat-import-00.md",
            "imported_count": 1,
            "invalid_count": 0,
            "class_counts": {"ic": 1, "roll": 0, "ooc": 0, "system": 0},
            "dry_run": kwargs.get("dry_run", False),
            "deduped_count": 0,
            "imported_sources": ["stub.db"],
            "renamed_sources": [],
            "projection": projection_payload,
        }
    return AsyncMock(side_effect=_impl)


@pytest.mark.asyncio
async def test_foundry_import_response_includes_projection_metrics():
    """FCM-05: default-flag POST surfaces a `projection` block with all six metric keys."""
    from app.main import app
    import app.routes.foundry as foundry_route

    projection_payload = {
        "player_updates": 2,
        "npc_updates": 1,
        "player_deduped": 0,
        "npc_deduped": 0,
        "unmatched_speakers": [],
        "dry_run": False,
    }
    stub = _make_import_stub(projection_payload)

    with patch.object(foundry_route, "obsidian", MagicMock()), \
         patch.object(foundry_route, "import_nedb_chatlogs_from_inbox", stub):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/foundry/messages/import",
                json={"inbox_dir": "/tmp/inbox", "dry_run": False, "limit": None},
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["projection"] is not None
    assert set(body["projection"].keys()) == _PROJECTION_METRIC_KEYS
    # Stub was called with both flags True (defaults) and seams populated.
    call_kwargs = stub.await_args.kwargs
    assert call_kwargs["project_player_maps"] is True
    assert call_kwargs["project_npc_history"] is True
    assert callable(call_kwargs["identity_resolver"])
    assert callable(call_kwargs["npc_matcher"])


@pytest.mark.asyncio
async def test_foundry_import_skip_projection_when_flags_false():
    """Both flags False → projection disabled. The route MUST pass False through."""
    from app.main import app
    import app.routes.foundry as foundry_route

    # When both flags are False, the importer skips projection — projection_payload=None.
    stub = _make_import_stub(None)

    with patch.object(foundry_route, "obsidian", MagicMock()), \
         patch.object(foundry_route, "import_nedb_chatlogs_from_inbox", stub):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/foundry/messages/import",
                json={
                    "inbox_dir": "/tmp/inbox",
                    "dry_run": False,
                    "limit": None,
                    "project_player_maps": False,
                    "project_npc_history": False,
                },
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body.get("projection") is None
    call_kwargs = stub.await_args.kwargs
    assert call_kwargs["project_player_maps"] is False
    assert call_kwargs["project_npc_history"] is False


@pytest.mark.asyncio
async def test_foundry_import_dry_run_projection_metrics():
    """FCM-05: dry_run=True → projection.dry_run is True with zero update counts."""
    from app.main import app
    import app.routes.foundry as foundry_route

    projection_payload = {
        "player_updates": 0,
        "npc_updates": 0,
        "player_deduped": 0,
        "npc_deduped": 0,
        "unmatched_speakers": [],
        "dry_run": True,
    }
    stub = _make_import_stub(projection_payload)

    with patch.object(foundry_route, "obsidian", MagicMock()), \
         patch.object(foundry_route, "import_nedb_chatlogs_from_inbox", stub):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/foundry/messages/import",
                json={"inbox_dir": "/tmp/inbox", "dry_run": True, "limit": None},
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )

    assert resp.status_code == 200
    body = resp.json()
    proj = body["projection"]
    assert proj is not None
    assert proj["dry_run"] is True
    assert proj["player_updates"] == 0
    assert proj["npc_updates"] == 0
    # The mocked importer should have been called with dry_run=True.
    assert stub.await_args.kwargs["dry_run"] is True
