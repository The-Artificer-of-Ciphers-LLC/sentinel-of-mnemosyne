"""Player identity resolver — Discord user_id -> player_slug, Foundry speaker classifier.

This module is the SINGLE place in the codebase that derives a slug from a Discord
user id. Every other component must import from here; do not re-derive elsewhere.

Slug contract (PVL-06):
  - Format: "p-{12 hex chars of sha256(user_id)}"  (total length 14)
  - Stable across processes (deterministic).
  - alias_map override returns the mapped slug verbatim (no hashing).

Foundry speaker resolution (FCM-01) precedence:
  1. foundry_alias_map  (Foundry actor name -> Discord user_id)
  2. npc_roster         (actor name -> npc slug)
  3. pc_character_names (actor name -> player slug)
  4. unknown            (return raw token)

Alias map JSON schema (mnemosyne/pf2e/players/_aliases.json):
  {
    "discord_id_to_slug": {"u-1": "p-custom"},
    "foundry_actor_to_discord_id": {"Valeros": "u-1"}
  }
Both keys are optional; missing file is treated as empty maps.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Literal

logger = logging.getLogger(__name__)

ALIAS_MAP_PATH = "mnemosyne/pf2e/players/_aliases.json"

_SLUG_PREFIX = "p-"
_SLUG_HEX_LEN = 12  # total slug length = len("p-") + 12 = 14


def slug_from_discord_user_id(
    user_id: str,
    alias_map: dict[str, str] | None = None,
) -> str:
    """Derive a deterministic player slug from a Discord user id.

    If alias_map contains user_id, returns the mapped slug verbatim (operator
    override for readable slugs). Otherwise returns "p-{12 hex chars}" of the
    sha256 of the user_id.
    """
    if not isinstance(user_id, str):
        raise TypeError(f"user_id must be str, got {type(user_id).__name__}")
    if not user_id:
        raise ValueError("user_id must be a non-empty string")
    if alias_map and user_id in alias_map:
        return alias_map[user_id]
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return f"{_SLUG_PREFIX}{digest[:_SLUG_HEX_LEN]}"


def resolve_foundry_speaker(
    *,
    actor: str,
    alias_map: dict[str, str],
    npc_roster: dict[str, str],
    pc_character_names: dict[str, str],
) -> tuple[Literal["player", "npc", "unknown"], str]:
    """Classify a Foundry actor name into (kind, identifier).

    Precedence (locked by FCM-01 RED tests):
      1. alias_map[actor] -> ("player", slug_from_discord_user_id(user_id))
      2. npc_roster[actor] -> ("npc", npc_slug)
      3. pc_character_names[actor] -> ("player", that_slug)
      4. fallthrough -> ("unknown", raw actor token)
    """
    if actor in alias_map:
        return ("player", slug_from_discord_user_id(alias_map[actor]))
    if actor in npc_roster:
        return ("npc", npc_roster[actor])
    if actor in pc_character_names:
        return ("player", pc_character_names[actor])
    return ("unknown", actor)


async def _load_alias_doc(obsidian: Any) -> dict[str, Any]:
    """Load and parse the alias JSON file. Returns {} on missing/invalid."""
    try:
        text = await obsidian.get_note(ALIAS_MAP_PATH)
    except Exception as exc:
        logger.warning("Failed to read alias map %s: %s", ALIAS_MAP_PATH, exc)
        return {}
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Alias map %s is not valid JSON: %s", ALIAS_MAP_PATH, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("Alias map %s is not a JSON object", ALIAS_MAP_PATH)
        return {}
    return data


async def load_alias_map(obsidian: Any) -> dict[str, str]:
    """Load `discord_id_to_slug` map. Returns {} if file or section missing."""
    doc = await _load_alias_doc(obsidian)
    section = doc.get("discord_id_to_slug", {})
    if not isinstance(section, dict):
        return {}
    return {str(k): str(v) for k, v in section.items()}


async def load_foundry_alias_map(obsidian: Any) -> dict[str, str]:
    """Load `foundry_actor_to_discord_id` map. Returns {} if file or section missing."""
    doc = await _load_alias_doc(obsidian)
    section = doc.get("foundry_actor_to_discord_id", {})
    if not isinstance(section, dict):
        return {}
    return {str(k): str(v) for k, v in section.items()}
