"""End-to-end Phase 37 integration tests (plan 37-14 closeout).

Exercises the full Foundry import → projection → idempotency loop AT THE ROUTE
LAYER (POST /foundry/messages/import). The first run writes; the second run
on the same inbox writes nothing new and reports zero updates.

Behavioral-Test-Only Rule: every assertion is on observable I/O — HTTP status,
response JSON, recorded obsidian call counts, or contents of the on-disk state
file. No source-grep, no `assert True`.
"""
from __future__ import annotations

import json
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


_HEADERS = {"X-Sentinel-Key": "test-key-for-pytest"}


def _make_inbox(tmp_path):
    """Build a fake nedb chatlog inbox with three records: one player, one NPC,
    one unknown. Returns the inbox dir Path.
    """
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    db = inbox / "chatlog-2026-05-07.db"
    records = [
        # Player line — Valeros maps to discord user u-player-1 in alias map below.
        {
            "_id": "rec-player-1",
            "type": 1,
            "speaker": {"alias": "Valeros"},
            "content": "<p>We move at dawn.</p>",
            "timestamp": 1710000000000,
        },
        # NPC line — Goblin Boss in npc_roster.
        {
            "_id": "rec-npc-1",
            "type": 1,
            "speaker": {"alias": "Goblin Boss"},
            "content": "<p>Surrender or die!</p>",
            "timestamp": 1710000001000,
        },
        # Unknown speaker — neither in alias map nor roster.
        {
            "_id": "rec-unknown-1",
            "type": 1,
            "speaker": {"alias": "Mystery Stranger"},
            "content": "<p>You shall not pass.</p>",
            "timestamp": 1710000002000,
        },
    ]
    db.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    return inbox


def _make_obsidian():
    """An obsidian client that:
      - returns the alias-map JSON on the canonical path so Valeros routes to a player;
      - returns an empty body for the goblin-boss NPC note so append_npc_history_row
        can build the section via GET-then-PUT;
      - returns None for player-map files (forces first-run write).
    """
    alias_doc = {
        "discord_id_to_slug": {},
        "foundry_actor_to_discord_id": {"Valeros": "u-player-1"},
    }
    npc_note_body = (
        "---\n"
        "name: Goblin Boss\n"
        "slug: goblin-boss\n"
        "---\n\n"
        "# Goblin Boss\n"
    )

    async def _get_note(path: str):
        if path == "mnemosyne/pf2e/players/_aliases.json":
            return json.dumps(alias_doc)
        if path == "mnemosyne/pf2e/npcs/goblin-boss.md":
            return npc_note_body
        return None

    obs = MagicMock()
    obs.get_note = AsyncMock(side_effect=_get_note)
    obs.put_note = AsyncMock(return_value=None)
    obs.patch_heading = AsyncMock(return_value=None)
    obs.list_directory = AsyncMock(return_value=[])
    return obs


def _patches(obs, npc_roster):
    """Build the patch context: obsidian singletons + session npc_roster_cache."""
    return [
        patch("app.main._register_with_retry", new=AsyncMock(return_value=None)),
        patch("app.routes.foundry.obsidian", obs),
        patch("app.routes.player.obsidian", obs),
        patch("app.routes.session.npc_roster_cache", npc_roster),
    ]


@pytest.mark.asyncio
async def test_foundry_import_idempotent_at_route_layer(tmp_path):
    """Two consecutive POST /foundry/messages/import calls on the same inbox.

    Run 1: projection.player_updates >= 1, npc_updates >= 1, unmatched >= 1.
    Run 2: projection.player_updates == 0, npc_updates == 0, deduped > 0,
           obsidian.put_note + patch_heading call counts unchanged.
    """
    inbox = _make_inbox(tmp_path)
    obs = _make_obsidian()
    # Roster uses the exact alias casing the resolver does strict dict lookups on.
    npc_roster = {"Goblin Boss": "goblin-boss"}

    patches = _patches(obs, npc_roster)
    for p in patches:
        p.start()
    try:
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r1 = await client.post(
                "/foundry/messages/import",
                json={
                    "inbox_dir": str(inbox),
                    "dry_run": False,
                    "limit": None,
                    "project_player_maps": True,
                    "project_npc_history": True,
                },
                headers=_HEADERS,
            )
            assert r1.status_code == 200, r1.text
            body1 = r1.json()
            proj1 = body1.get("projection")
            assert proj1 is not None, body1
            assert proj1["player_updates"] >= 1, proj1
            assert proj1["npc_updates"] >= 1, proj1
            assert len(proj1["unmatched_speakers"]) >= 1, proj1
            assert "Mystery Stranger" in proj1["unmatched_speakers"], proj1

            put_count_after_1 = obs.put_note.await_count
            patch_count_after_1 = obs.patch_heading.await_count

            # Re-create the source file (first call renamed it to *_imported);
            # the projection state file written under the same inbox dedupes
            # the per-record projection keys so Run 2 sees zero new projections.
            db = inbox / "chatlog-2026-05-07.db"
            if not db.exists():
                # First run renamed the file. Re-create with same records so
                # the importer reads them again and projection re-evaluates.
                records = [
                    {
                        "_id": "rec-player-1",
                        "type": 1,
                        "speaker": {"alias": "Valeros"},
                        "content": "<p>We move at dawn.</p>",
                        "timestamp": 1710000000000,
                    },
                    {
                        "_id": "rec-npc-1",
                        "type": 1,
                        "speaker": {"alias": "Goblin Boss"},
                        "content": "<p>Surrender or die!</p>",
                        "timestamp": 1710000001000,
                    },
                    {
                        "_id": "rec-unknown-1",
                        "type": 1,
                        "speaker": {"alias": "Mystery Stranger"},
                        "content": "<p>You shall not pass.</p>",
                        "timestamp": 1710000002000,
                    },
                ]
                db.write_text(
                    "\n".join(json.dumps(r) for r in records) + "\n",
                    encoding="utf-8",
                )

            r2 = await client.post(
                "/foundry/messages/import",
                json={
                    "inbox_dir": str(inbox),
                    "dry_run": False,
                    "limit": None,
                    "project_player_maps": True,
                    "project_npc_history": True,
                },
                headers=_HEADERS,
            )
            assert r2.status_code == 200, r2.text
            body2 = r2.json()
            proj2 = body2.get("projection")
            assert proj2 is not None, body2
            assert proj2["player_updates"] == 0, proj2
            assert proj2["npc_updates"] == 0, proj2
            assert (
                proj2["player_deduped"] + proj2["npc_deduped"]
            ) >= 1, proj2

            # No new projection writes on second run. The legacy importer's
            # foundry-chat-import note is a separate write path; we measure
            # only put_note calls hitting projection targets.
            projection_writes_after_2 = [
                c for c in obs.put_note.await_args_list
                if c.args
                and (
                    c.args[0].startswith("mnemosyne/pf2e/players/")
                    and c.args[0].endswith(".md")
                    and "/players/" in c.args[0]
                    and not c.args[0].endswith("/profile.md")
                )
            ]
            # Count distinct projection writes — Run 1 had >= 1; Run 2 must
            # not have added any.
            # We assert per-target: player-map writes after run 2 == after run 1,
            # and patch_heading calls (NPC history) unchanged.
            # Count player-map writes (path = mnemosyne/pf2e/players/{slug}.md).
            player_map_writes = [
                c for c in obs.put_note.await_args_list
                if c.args
                and c.args[0].startswith("mnemosyne/pf2e/players/")
                and c.args[0].count("/") == 3  # players/{slug}.md, no subdir
            ]
            # First run produced at least one player-map write; second run
            # produced none additional. Track by comparing against run 1's count.
            # We re-derive: total put_note count after run 2 vs after run 1
            # should differ ONLY by the legacy importer's note (one fixed write).
            # Strict assertion: patch_heading unchanged across run 2.
            assert obs.patch_heading.await_count == patch_count_after_1, (
                f"NPC history patch_heading should not fire on idempotent rerun; "
                f"after_1={patch_count_after_1} after_2={obs.patch_heading.await_count}"
            )
            # Strict assertion: projection-target put_note count unchanged.
            # The legacy importer ALSO calls put_note for its session note —
            # that path begins with mnemosyne/pf2e/sessions/ — so we filter.
            projection_puts_after_2 = [
                c for c in obs.put_note.await_args_list
                if c.args
                and c.args[0].startswith("mnemosyne/pf2e/players/")
            ]
            projection_puts_run_1_count = len([
                c for c in obs.put_note.await_args_list[:put_count_after_1]
                if c.args
                and c.args[0].startswith("mnemosyne/pf2e/players/")
            ])
            assert (
                len(projection_puts_after_2) == projection_puts_run_1_count
            ), (
                "projection put_note writes should be unchanged on idempotent rerun; "
                f"run1={projection_puts_run_1_count} run2_total={len(projection_puts_after_2)}"
            )
    finally:
        for p in reversed(patches):
            p.stop()


@pytest.mark.asyncio
async def test_foundry_import_dry_run_then_live_writes_once(tmp_path):
    """dry_run=True writes nothing; first live writes everything; second live
    writes nothing new. Idempotency holds across the dry-run boundary.
    """
    inbox = _make_inbox(tmp_path)
    obs = _make_obsidian()
    npc_roster = {"Goblin Boss": "goblin-boss"}
    patches = _patches(obs, npc_roster)
    for p in patches:
        p.start()
    try:
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # 1) dry run
            r_dry = await client.post(
                "/foundry/messages/import",
                json={
                    "inbox_dir": str(inbox),
                    "dry_run": True,
                    "project_player_maps": True,
                    "project_npc_history": True,
                },
                headers=_HEADERS,
            )
            assert r_dry.status_code == 200, r_dry.text
            assert obs.put_note.await_count == 0, (
                "dry_run must perform zero writes; "
                f"saw put_note count={obs.put_note.await_count}"
            )
            assert obs.patch_heading.await_count == 0
            proj_dry = r_dry.json()["projection"]
            assert proj_dry["dry_run"] is True
            # Dry-run still reports counts (identical metric shape).
            assert proj_dry["player_updates"] >= 1
            assert proj_dry["npc_updates"] >= 1

            # 2) first live (the original .db file is intact since dry_run did
            # not rename it).
            r_live_1 = await client.post(
                "/foundry/messages/import",
                json={
                    "inbox_dir": str(inbox),
                    "dry_run": False,
                    "project_player_maps": True,
                    "project_npc_history": True,
                },
                headers=_HEADERS,
            )
            assert r_live_1.status_code == 200, r_live_1.text
            put_count_live_1 = obs.put_note.await_count
            patch_count_live_1 = obs.patch_heading.await_count
            assert put_count_live_1 >= 1
            proj_live_1 = r_live_1.json()["projection"]
            assert proj_live_1["player_updates"] >= 1
            assert proj_live_1["npc_updates"] >= 1

            # 3) second live — recreate the renamed source so importer reads
            # again, then assert ZERO new projection writes.
            db = inbox / "chatlog-2026-05-07.db"
            if not db.exists():
                records = [
                    {"_id": "rec-player-1", "type": 1,
                     "speaker": {"alias": "Valeros"},
                     "content": "<p>We move at dawn.</p>",
                     "timestamp": 1710000000000},
                    {"_id": "rec-npc-1", "type": 1,
                     "speaker": {"alias": "Goblin Boss"},
                     "content": "<p>Surrender or die!</p>",
                     "timestamp": 1710000001000},
                    {"_id": "rec-unknown-1", "type": 1,
                     "speaker": {"alias": "Mystery Stranger"},
                     "content": "<p>You shall not pass.</p>",
                     "timestamp": 1710000002000},
                ]
                db.write_text(
                    "\n".join(json.dumps(r) for r in records) + "\n",
                    encoding="utf-8",
                )

            r_live_2 = await client.post(
                "/foundry/messages/import",
                json={
                    "inbox_dir": str(inbox),
                    "dry_run": False,
                    "project_player_maps": True,
                    "project_npc_history": True,
                },
                headers=_HEADERS,
            )
            assert r_live_2.status_code == 200, r_live_2.text
            proj_live_2 = r_live_2.json()["projection"]
            assert proj_live_2["player_updates"] == 0, proj_live_2
            assert proj_live_2["npc_updates"] == 0, proj_live_2
            # patch_heading is the load-bearing NPC-history-write signal.
            assert obs.patch_heading.await_count == patch_count_live_1, (
                f"NPC history must not re-patch on idempotent rerun; "
                f"live1={patch_count_live_1} live2={obs.patch_heading.await_count}"
            )
            # Player-map projection puts unchanged.
            projection_puts_live_2 = [
                c for c in obs.put_note.await_args_list
                if c.args and c.args[0].startswith("mnemosyne/pf2e/players/")
            ]
            projection_puts_live_1 = [
                c for c in obs.put_note.await_args_list[:put_count_live_1]
                if c.args and c.args[0].startswith("mnemosyne/pf2e/players/")
            ]
            assert (
                len(projection_puts_live_2) == len(projection_puts_live_1)
            ), (
                "projection put_note writes must be unchanged on idempotent live rerun"
            )
    finally:
        for p in reversed(patches):
            p.stop()


@pytest.mark.asyncio
async def test_state_file_extended_in_place(tmp_path):
    """After first live import, the state JSON has all three arrays and
    imported_keys is non-empty (legacy importer behavior preserved).
    """
    inbox = _make_inbox(tmp_path)
    obs = _make_obsidian()
    npc_roster = {"Goblin Boss": "goblin-boss"}
    patches = _patches(obs, npc_roster)
    for p in patches:
        p.start()
    try:
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/foundry/messages/import",
                json={
                    "inbox_dir": str(inbox),
                    "dry_run": False,
                    "project_player_maps": True,
                    "project_npc_history": True,
                },
                headers=_HEADERS,
            )
            assert r.status_code == 200, r.text

        state_path = inbox / ".foundry_chat_import_state.json"
        assert state_path.exists(), (
            f"state file should be created at {state_path}; "
            f"dir contents: {list(inbox.iterdir())}"
        )
        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        for key in (
            "imported_keys",
            "player_projection_keys",
            "npc_projection_keys",
        ):
            assert key in data, f"state file missing array {key!r}: {data!r}"
            assert isinstance(data[key], list), (
                f"{key!r} must be a list; got {type(data[key]).__name__}"
            )
        # Legacy importer behavior: imported_keys non-empty after a live run.
        assert len(data["imported_keys"]) >= 1, (
            f"imported_keys should be populated after live import; data={data!r}"
        )
        # Per-target projection arrays — at least one of player/npc populated
        # (we have one player record + one npc record, so both should be > 0).
        assert len(data["player_projection_keys"]) >= 1, data
        assert len(data["npc_projection_keys"]) >= 1, data
    finally:
        for p in reversed(patches):
            p.stop()
