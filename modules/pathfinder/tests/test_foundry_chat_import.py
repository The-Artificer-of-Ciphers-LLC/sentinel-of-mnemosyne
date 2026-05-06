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
    assert result["imported_count"] == 3
    assert result["deduped_count"] == 0
    assert result["invalid_count"] == 2
    assert result["class_counts"] == {"ic": 1, "roll": 1, "ooc": 1, "system": 0}
    assert result["note_path"].startswith("mnemosyne/pf2e/sessions/foundry-chat/")
    obsidian.put_note.assert_awaited_once()

    written_path, written_content = obsidian.put_note.await_args.args
    assert written_path == result["note_path"]
    assert "| ic | Valeros | We move at dawn. |" in written_content
    assert "| roll | System | Attack Roll: 22 |" in written_content
    assert "| ooc | GM | ((rules clarification)) |" in written_content
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
