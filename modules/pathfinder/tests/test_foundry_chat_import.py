from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_import_nedb_chatlogs_from_inbox_live_writes_classified_markdown(tmp_path):
    from app.foundry_chat_import import import_nedb_chatlogs_from_inbox

    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir()
    db_path = inbox_dir / "chatlog-2026-05-06.db"
    records = [
        {
            "_id": "m1",
            "type": 1,
            "speaker": {"alias": "Valeros"},
            "content": "<p>We move at dawn.</p>",
            "timestamp": 1710000000000,
        },
        {
            "_id": "m2",
            "type": 5,
            "speaker": {"alias": "System"},
            "content": "<div><strong>Attack Roll:</strong> 22</div>",
            "timestamp": 1710000001000,
        },
        {
            "_id": "m3",
            "type": 0,
            "speaker": {"alias": "GM"},
            "content": "((rules clarification))",
            "timestamp": 1710000002000,
        },
        {
            "_id": "m4",
            "type": "base",
            "speaker": {"alias": "Merisiel"},
            "content": "<p>Scout ahead.</p>",
            "timestamp": 1710000002500,
        },
        {
            "_id": "junk",
            "type": 99,
            "speaker": {"alias": "System"},
            "content": "<p>ignore me</p>",
            "timestamp": 1710000003000,
        },
    ]
    db_path.write_text("\n".join(json.dumps(r) for r in records) + "\nnot-json\n", encoding="utf-8")

    obsidian = AsyncMock()

    result = await import_nedb_chatlogs_from_inbox(
        inbox_dir=str(inbox_dir),
        dry_run=False,
        limit=None,
        obsidian_client=obsidian,
    )

    assert result["source"].endswith("chatlog-2026-05-06.db")
    assert result["imported_count"] == 4
    assert result["deduped_count"] == 0
    assert result["invalid_count"] == 2
    assert result["class_counts"] == {"ic": 2, "roll": 1, "ooc": 1, "system": 0}
    assert result["note_path"].startswith("mnemosyne/pf2e/sessions/foundry-chat/")
    obsidian.put_note.assert_awaited_once()

    written_path, written_content = obsidian.put_note.await_args.args
    assert written_path == result["note_path"]
    assert "| ic | Valeros | We move at dawn. |" in written_content
    assert "| roll | System | Attack Roll: 22 |" in written_content
    assert "| ooc | GM | ((rules clarification)) |" in written_content
    assert "| ic | Merisiel | Scout ahead. |" in written_content
    assert (inbox_dir / "chatlog-2026-05-06.db_imported").exists()


@pytest.mark.asyncio
async def test_import_skips_already_imported_files_and_dedupes_by_state(tmp_path):
    from app.foundry_chat_import import import_nedb_chatlogs_from_inbox

    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir()

    old_file = inbox_dir / "old.db_imported"
    old_file.write_text('{"_id":"old","type":1,"speaker":{"alias":"A"},"content":"x"}\n', encoding="utf-8")

    db_path = inbox_dir / "new.db"
    records = [
        {"_id": "m1", "type": 1, "speaker": {"alias": "Valeros"}, "content": "Hi", "timestamp": 1},
        {"_id": "m2", "type": 1, "speaker": {"alias": "Valeros"}, "content": "Again", "timestamp": 2},
    ]
    db_path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    obsidian = AsyncMock()
    first = await import_nedb_chatlogs_from_inbox(
        inbox_dir=str(inbox_dir), dry_run=False, limit=None, obsidian_client=obsidian
    )
    assert first["imported_count"] == 2
    assert first["deduped_count"] == 0

    db_path_2 = inbox_dir / "new2.db"
    db_path_2.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    second = await import_nedb_chatlogs_from_inbox(
        inbox_dir=str(inbox_dir), dry_run=True, limit=None, obsidian_client=obsidian
    )
    assert second["imported_count"] == 0
    assert second["deduped_count"] == 2


@pytest.mark.asyncio
async def test_dedupe_foundry_import_note_removes_duplicate_rows():
    from app.foundry_chat_import import dedupe_foundry_import_note

    note = """# Foundry Chat Import

| class | speaker | content |
| --- | --- | --- |
| ic | Valeros | Hi | 
| ic | Valeros | Hi | 
| ooc | GM | Rules | 
"""
    deduped, removed = dedupe_foundry_import_note(note)
    assert removed == 1
    assert deduped.count("| ic | Valeros | Hi |") == 1


@pytest.mark.asyncio
async def test_import_nedb_chatlogs_from_leveldb_shards(tmp_path, monkeypatch):
    import app.foundry_chat_import as mod

    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir()
    (inbox_dir / "CURRENT").write_text("MANIFEST-000001\n", encoding="utf-8")
    (inbox_dir / "001000.ldb").write_bytes(b"not used")

    monkeypatch.setattr(
        mod,
        "_load_nedb_records_from_leveldb_dir",
        lambda _inbox, _limit: [
            {
                "_id": "m-leveldb",
                "type": 1,
                "speaker": {"alias": "Merisiel"},
                "content": "<p>Quiet now.</p>",
                "timestamp": 1710000010000,
            }
        ],
    )

    obsidian = AsyncMock()
    result = await mod.import_nedb_chatlogs_from_inbox(
        inbox_dir=str(inbox_dir),
        dry_run=False,
        limit=None,
        obsidian_client=obsidian,
    )

    assert result["source"].startswith("leveldb://")
    assert result["imported_count"] == 1
    assert result["class_counts"]["ic"] == 1
    written_path, written_content = obsidian.put_note.await_args.args
    assert written_path == result["note_path"]
    assert "| ic | Merisiel | Quiet now. |" in written_content


@pytest.mark.asyncio
async def test_npc_projection_runs_and_persists_after_session_note_write(tmp_path):
    """Regression test: NPC history projection must run AND write to the NPC note
    even when the session-note put_note precedes it in the call order.

    Root cause guarded: if put_note for the session note raises (e.g. ReadTimeout
    on large imports), projection is never reached and NPC notes never get history.
    This test exercises the happy path end-to-end to verify:
      1. result["npc_updates"] >= 1  (projection ran)
      2. obsidian received a put_note targeting mnemosyne/pf2e/npcs/goblin.md
         (the write actually persisted — not merely queued or counted)
    """
    from app.foundry_chat_import import import_nedb_chatlogs_from_inbox

    # --- Stage NeDB inbox with Goblin speaker records ---
    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir()
    db_path = inbox_dir / "chatlog-goblin-session.db"
    records = [
        {
            "_id": "g1",
            "type": 1,
            "speaker": {"alias": "Goblin"},
            "content": "<p>Goblins attack!</p>",
            "timestamp": 1710001000000,
        },
        {
            "_id": "g2",
            "type": 1,
            "speaker": {"alias": "Goblin"},
            "content": "<p>Flee, tiny ones!</p>",
            "timestamp": 1710001001000,
        },
        {
            "_id": "g3",
            "type": 1,
            "speaker": {"alias": "Goblin"},
            "content": "<p>Mine, mine, mine!</p>",
            "timestamp": 1710001002000,
        },
    ]
    db_path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    # --- Recording fake obsidian client ---
    # Tracks every (path, content) pair passed to put_note so we can assert
    # the NPC note path received a write.  get_note returns a stub note body
    # for the NPC path (no ## Foundry Chat History section yet) so
    # append_npc_history_row uses the GET-then-PUT "created" branch.
    put_note_calls: list[tuple[str, str]] = []
    get_note_calls: list[str] = []

    async def fake_put_note(path: str, content: str) -> None:
        put_note_calls.append((path, content))

    async def fake_get_note(path: str) -> str | None:
        get_note_calls.append(path)
        if path.startswith("mnemosyne/pf2e/npcs/"):
            # Existing NPC note without the history section → triggers "created" branch.
            return "# Goblin\n\nA small but fierce creature.\n"
        return None

    class FakeObsidian:
        put_note = staticmethod(fake_put_note)
        get_note = staticmethod(fake_get_note)

    obsidian = FakeObsidian()

    # --- Resolvers: every speaker "Goblin" → npc, slug returned by npc_matcher ---
    def identity_resolver(speaker_token: str):
        if speaker_token == "Goblin":
            return ("npc", None)  # slug left to npc_matcher as fallback
        return ("unknown", speaker_token)

    async def npc_matcher(speaker_token: str) -> str | None:
        if speaker_token == "Goblin":
            return "goblin"
        return None

    # --- Run the import with projection enabled ---
    result = await import_nedb_chatlogs_from_inbox(
        inbox_dir=str(inbox_dir),
        dry_run=False,
        limit=None,
        obsidian_client=obsidian,
        project_npc_history=True,
        project_player_maps=False,
        identity_resolver=identity_resolver,
        npc_matcher=npc_matcher,
    )

    # Assertion 1: projection ran and counted NPC updates.
    assert result["projection"] is not None, "projection result must not be None"
    assert result["projection"]["npc_updates"] >= 1, (
        f"expected npc_updates >= 1, got {result['projection']['npc_updates']}; "
        "projection may have been skipped due to session-note write failure"
    )

    # Assertion 2: the NPC note path received a real write through obsidian.
    # append_npc_history_row calls get_note then put_note (created branch) or
    # patch_heading (appended branch). We assert at least one put_note targeted
    # the NPC slug path, proving the persistence call reached obsidian.
    npc_write_paths = [
        path for path, _ in put_note_calls
        if path.startswith("mnemosyne/pf2e/npcs/")
    ]
    assert npc_write_paths, (
        f"expected a put_note call targeting mnemosyne/pf2e/npcs/ but got "
        f"put_note calls to: {[p for p, _ in put_note_calls]}"
    )
    # Verify the correct NPC slug was targeted.
    assert any("goblin" in p for p in npc_write_paths), (
        f"expected 'goblin' in NPC note path, got: {npc_write_paths}"
    )
    # Verify the written content contains the chat history section marker.
    npc_written_content = next(
        content for path, content in put_note_calls
        if path.startswith("mnemosyne/pf2e/npcs/")
    )
    assert "Foundry Chat History" in npc_written_content, (
        "NPC note write must include the ## Foundry Chat History section"
    )
    # Goblin was matched, so it must NOT appear in unmatched_speakers.
    assert "Goblin" not in result["projection"].get("unmatched_speakers", [])


def test_state_file_backcompat_missing_projection_keys(tmp_path):
    """Wave 0 RED: ADDITIVE backcompat test for the projection state-file shape.

    A pre-Phase-37 state JSON contains only ``imported_keys`` (no projection
    arrays). The Wave 6 loader ``_load_projection_state`` must handle this
    legacy shape by returning empty sets for the projection key buckets — no
    exception, no key-error.

    This test fails RED on ImportError until Wave 6 lands the loader symbol.
    """
    from app.foundry_chat_import import _load_projection_state  # noqa: function-scope

    state_path = tmp_path / ".foundry_chat_import_state.json"
    state_path.write_text(
        json.dumps({"imported_keys": ["abc"]}),
        encoding="utf-8",
    )

    state = _load_projection_state(state_path)

    # Tolerate either dict-of-sets or a small dataclass — assert on the
    # observable contract: three buckets, two of them empty, one preserved.
    if hasattr(state, "imported_keys"):
        imported = state.imported_keys
        player = state.player_projection_keys
        npc = state.npc_projection_keys
    else:
        imported = state["imported_keys"]
        player = state["player_projection_keys"]
        npc = state["npc_projection_keys"]

    assert set(imported) == {"abc"}
    assert set(player) == set()
    assert set(npc) == set()
