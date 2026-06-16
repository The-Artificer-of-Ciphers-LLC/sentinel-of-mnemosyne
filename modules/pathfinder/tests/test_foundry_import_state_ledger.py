from __future__ import annotations

import json


def test_missing_state_file_returns_empty_buckets(tmp_path):
    from app.foundry_import_state_ledger import load_foundry_import_state

    state = load_foundry_import_state(tmp_path / ".foundry_chat_import_state.json")

    assert state.imported_keys == set()
    assert state.player_projection_keys == set()
    assert state.npc_projection_keys == set()


def test_legacy_state_file_preserves_imported_keys_with_empty_projection_sets(tmp_path):
    from app.foundry_import_state_ledger import load_foundry_import_state

    state_path = tmp_path / ".foundry_chat_import_state.json"
    state_path.write_text(
        json.dumps({"imported_keys": ["id:m1", "id:m2"]}),
        encoding="utf-8",
    )

    state = load_foundry_import_state(state_path)

    assert state.imported_keys == {"id:m1", "id:m2"}
    assert state.player_projection_keys == set()
    assert state.npc_projection_keys == set()


def test_malformed_state_file_returns_empty_buckets(tmp_path):
    from app.foundry_import_state_ledger import load_foundry_import_state

    state_path = tmp_path / ".foundry_chat_import_state.json"
    state_path.write_text("{not json", encoding="utf-8")

    state = load_foundry_import_state(state_path)

    assert state.imported_keys == set()
    assert state.player_projection_keys == set()
    assert state.npc_projection_keys == set()


def test_save_imported_keys_preserves_existing_projection_keys(tmp_path):
    from app.foundry_import_state_ledger import save_imported_keys

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    state_path = inbox / ".foundry_chat_import_state.json"
    state_path.write_text(
        json.dumps(
            {
                "imported_keys": ["old-import"],
                "player_projection_keys": ["player-key"],
                "npc_projection_keys": ["npc-key"],
            }
        ),
        encoding="utf-8",
    )

    save_imported_keys(inbox, {"new-import"})

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved == {
        "imported_keys": ["new-import"],
        "player_projection_keys": ["player-key"],
        "npc_projection_keys": ["npc-key"],
    }


def test_save_imported_keys_keeps_legacy_shape_without_projection_keys(tmp_path):
    from app.foundry_import_state_ledger import save_imported_keys

    inbox = tmp_path / "inbox"
    inbox.mkdir()

    save_imported_keys(inbox, {"id:m1"})

    state_path = inbox / ".foundry_chat_import_state.json"
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved == {"imported_keys": ["id:m1"]}


def test_save_projection_state_preserves_imported_keys(tmp_path):
    from app.foundry_import_state_ledger import save_projection_state

    state_path = tmp_path / ".foundry_chat_import_state.json"

    save_projection_state(
        state_path,
        imported_keys={"import-key"},
        player_keys={"player-key"},
        npc_keys={"npc-key"},
    )

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved == {
        "imported_keys": ["import-key"],
        "player_projection_keys": ["player-key"],
        "npc_projection_keys": ["npc-key"],
    }
