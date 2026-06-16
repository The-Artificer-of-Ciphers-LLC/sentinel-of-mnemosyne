"""Foundry import/projection state ledger.

Owns the ``.foundry_chat_import_state.json`` file shared by Foundry chat import
dedupe and Foundry memory projection idempotency. Missing, malformed, and
legacy one-array files are tolerated so existing inboxes keep importing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STATE_FILE_NAME = ".foundry_chat_import_state.json"


@dataclass(frozen=True)
class FoundryImportState:
    imported_keys: set[str]
    player_projection_keys: set[str]
    npc_projection_keys: set[str]


def state_path_for_inbox(inbox: Path) -> Path:
    return inbox / STATE_FILE_NAME


def load_foundry_import_state(path: Path) -> FoundryImportState:
    out = FoundryImportState(
        imported_keys=set(),
        player_projection_keys=set(),
        npc_projection_keys=set(),
    )
    if not path.exists():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(data, dict):
        return out
    return FoundryImportState(
        imported_keys=_string_set(data.get("imported_keys")),
        player_projection_keys=_string_set(data.get("player_projection_keys")),
        npc_projection_keys=_string_set(data.get("npc_projection_keys")),
    )


def load_imported_keys(inbox: Path) -> set[str]:
    return load_foundry_import_state(state_path_for_inbox(inbox)).imported_keys


def load_projection_state_dict(path: Path) -> dict[str, set[str]]:
    state = load_foundry_import_state(path)
    return {
        "imported_keys": state.imported_keys,
        "player_projection_keys": state.player_projection_keys,
        "npc_projection_keys": state.npc_projection_keys,
    }


def save_imported_keys(inbox: Path, keys: set[str]) -> None:
    path = state_path_for_inbox(inbox)
    existing = load_foundry_import_state(path)
    if existing.player_projection_keys or existing.npc_projection_keys:
        _write_state(
            path,
            imported_keys=keys,
            player_keys=existing.player_projection_keys,
            npc_keys=existing.npc_projection_keys,
            include_projection_keys=True,
        )
        return
    _write_state(
        path,
        imported_keys=keys,
        player_keys=set(),
        npc_keys=set(),
        include_projection_keys=False,
    )


def save_projection_state(
    path: Path,
    *,
    imported_keys: set[str],
    player_keys: set[str],
    npc_keys: set[str],
) -> None:
    _write_state(
        path,
        imported_keys=imported_keys,
        player_keys=player_keys,
        npc_keys=npc_keys,
        include_projection_keys=True,
    )


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value}


def _write_state(
    path: Path,
    *,
    imported_keys: set[str],
    player_keys: set[str],
    npc_keys: set[str],
    include_projection_keys: bool,
) -> None:
    payload: dict[str, Any] = {"imported_keys": sorted(imported_keys)}
    if include_projection_keys:
        payload["player_projection_keys"] = sorted(player_keys)
        payload["npc_projection_keys"] = sorted(npc_keys)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
