"""Shared vault markdown utilities — frontmatter parse + build.

Extracted from routes/npc.py to avoid copy-paste between NPC code and the
new per-player code. routes/npc.py keeps its private copy until a follow-up
refactor migrates it (additive-only change for plan 37-06).
"""
from __future__ import annotations

import logging

import yaml

logger = logging.getLogger(__name__)


def _parse_frontmatter(note_text: str) -> dict:
    """Parse YAML frontmatter from a note string delimited by '---'.

    Returns empty dict if frontmatter cannot be parsed. Verbatim copy of
    routes/npc.py:_parse_frontmatter (lines 220-237) so the contract is
    identical.
    """
    try:
        if not note_text.startswith("---"):
            return {}
        end = note_text.find("---", 3)
        if end == -1:
            return {}
        frontmatter_text = note_text[3:end].strip()
        return yaml.safe_load(frontmatter_text) or {}
    except Exception as exc:
        logger.warning("Frontmatter parse failed: %s", exc)
        return {}


def build_frontmatter_markdown(frontmatter: dict, body: str = "") -> str:
    """Emit a markdown note with YAML frontmatter and an optional body.

    Uses yaml.safe_dump(default_flow_style=False, allow_unicode=True) — the
    same options routes/npc.py uses for NPC notes.
    """
    fm = yaml.safe_dump(
        frontmatter or {},
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    return f"---\n{fm}---\n{body}"
