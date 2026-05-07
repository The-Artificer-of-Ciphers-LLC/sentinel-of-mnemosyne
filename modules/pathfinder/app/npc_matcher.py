"""NPC matcher — alias -> npc slug, with vault-probe fallback.

First tries the npc_roster dict (lowercase alias -> slug), then falls back to
slugify(alias) plus an Obsidian get_note probe at mnemosyne/pf2e/npcs/{slug}.md.
Returns the slug if a note exists, else None.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_NPC_PATH_PREFIX = "mnemosyne/pf2e/npcs"


async def match_npc_speaker(
    alias: str,
    *,
    obsidian_client: Any,
    npc_roster: dict[str, str] | None = None,
) -> str | None:
    """Resolve a Foundry/chat alias to an NPC slug, or None if no NPC exists.

    Roster lookup is case-insensitive (matches both "Goblin" and "goblin"
    keys). The vault probe issues a single get_note() call against the
    canonical Phase 29 NPC path; returns None on miss.
    """
    if not isinstance(alias, str) or not alias.strip():
        return None
    if npc_roster:
        # Case-insensitive lookup against roster keys.
        lowered = alias.lower()
        for key, value in npc_roster.items():
            if key.lower() == lowered:
                return value
    # Function-scope import: routes/npc.py pulls in heavy modules (LLM, etc.)
    # at module load — defer until actually needed so test collection stays cheap.
    from app.routes.npc import slugify  # noqa: PLC0415

    candidate = slugify(alias)
    if not candidate:
        return None
    note = await obsidian_client.get_note(f"{_NPC_PATH_PREFIX}/{candidate}.md")
    if note is None:
        return None
    return candidate
