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
    assert result["invalid_count"] == 1
    assert result["class_counts"] == {"ic": 1, "roll": 1, "ooc": 1, "system": 0}
    assert result["note_path"].startswith("mnemosyne/pf2e/sessions/foundry-chat/")
    obsidian.put_note.assert_awaited_once()

    written_path, written_content = obsidian.put_note.await_args.args
    assert written_path == result["note_path"]
    assert "| ic | Valeros | We move at dawn. |" in written_content
    assert "| roll | System | Attack Roll: 22 |" in written_content
    assert "| ooc | GM | ((rules clarification)) |" in written_content
