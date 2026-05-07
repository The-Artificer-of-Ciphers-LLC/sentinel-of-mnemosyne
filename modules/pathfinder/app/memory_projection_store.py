"""Memory projection store — per-player chat-map + NPC chat-history projections.

Two writers:

  * write_player_map_section: maintain mnemosyne/pf2e/players/{slug}.md with
    four canonical sections (## Voice Patterns, ## Notable Moments,
    ## Party Dynamics, ## Chat Timeline). GET-then-PUT; first write builds
    the file with all four headings so subsequent partial writes preserve
    the others (FCM-02).

  * append_npc_history_row: append a chat-history row under the NPC note's
    ## Foundry Chat History section (FCM-03). Two modes:
      - section already present (line-anchored regex match) -> patch_heading
        with operation='append'.
      - section missing -> GET-then-PUT with the new section appended at end.
    NPC note absent -> skipped sentinel, no writes.

Section detection regex is line-anchored (re.MULTILINE) so a mid-line literal
mention of "## Foundry Chat History" cannot trip the existing-section branch.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Canonical section order (FCM-02). First-write builds the file with all four
# empty so partial writes never lose the others.
_FOUR_SECTIONS: tuple[str, ...] = (
    "Voice Patterns",
    "Notable Moments",
    "Party Dynamics",
    "Chat Timeline",
)

_NPC_HISTORY_HEADING = "Foundry Chat History"
_NPC_HISTORY_SECTION_RE = re.compile(
    rf"^## {re.escape(_NPC_HISTORY_HEADING)}\b", re.MULTILINE
)

_PLAYER_MAP_PREFIX = "mnemosyne/pf2e/players"
_NPC_NOTE_PREFIX = "mnemosyne/pf2e/npcs"


# ---------------------------------------------------------------------------
# Player map (FCM-02)
# ---------------------------------------------------------------------------


def parse_player_map_sections(body: str) -> dict[str, list[str]]:
    """Split a player-map body into {section_name: [lines]} for the four canonical sections.

    Tolerant: if a heading is missing, its list is []. Lines are returned with
    trailing whitespace stripped; blank lines inside a section are dropped.
    Any pre-existing content above the first `## ` heading is discarded (the
    canonical layout has no preamble — title `# Player Map` is regenerated).
    """
    out: dict[str, list[str]] = {name: [] for name in _FOUR_SECTIONS}
    if not body:
        return out
    current: str | None = None
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            heading = match.group(1).strip()
            current = heading if heading in out else None
            continue
        if current is None:
            continue
        if not line.strip():
            continue
        out[current].append(line)
    return out


def build_player_map_markdown(sections: dict[str, list[str]]) -> str:
    """Emit the canonical player-map markdown.

    Always renders all four headings in canonical order, even if their lists
    are empty. Title `# Player Map` is regenerated each write.
    """
    parts: list[str] = ["# Player Map", ""]
    for name in _FOUR_SECTIONS:
        parts.append(f"## {name}")
        for line in sections.get(name, []):
            parts.append(line)
        parts.append("")
    body = "\n".join(parts)
    if not body.endswith("\n"):
        body += "\n"
    return body


async def write_player_map_section(
    slug: str,
    *,
    section: str,
    lines: list[str],
    obsidian: Any,
) -> None:
    """Append `lines` under `section` in the player's chat-map (GET-then-PUT)."""
    if section not in _FOUR_SECTIONS:
        raise ValueError(
            f"section must be one of {_FOUR_SECTIONS!r}, got {section!r}"
        )
    path = f"{_PLAYER_MAP_PREFIX}/{slug}.md"
    existing = await obsidian.get_note(path)
    sections = parse_player_map_sections(existing or "")
    sections[section] = list(sections.get(section, [])) + list(lines or [])
    await obsidian.put_note(path, build_player_map_markdown(sections))


# ---------------------------------------------------------------------------
# NPC chat history (FCM-03)
# ---------------------------------------------------------------------------


async def append_npc_history_row(
    npc_slug: str,
    *,
    row: str,
    obsidian: Any,
) -> str:
    """Append `row` under the NPC note's `## Foundry Chat History` section.

    Returns one of:
      - "appended" — section existed; patch_heading was used.
      - "created"  — section missing; GET-then-PUT was used.
      - "skipped (npc note missing)" — NPC note absent; no writes.
    """
    path = f"{_NPC_NOTE_PREFIX}/{npc_slug}.md"
    body = await obsidian.get_note(path)
    if body is None:
        logger.info(
            "append_npc_history_row: npc note %s missing, skipping", path
        )
        return "skipped (npc note missing)"

    if _NPC_HISTORY_SECTION_RE.search(body):
        await obsidian.patch_heading(
            path,
            _NPC_HISTORY_HEADING,
            row,
            operation="append",
        )
        return "appended"

    # Create the section at the end of the body.
    if not body.endswith("\n"):
        body += "\n"
    new_body = (
        body
        + f"\n## {_NPC_HISTORY_HEADING}\n"
        + (row if row.endswith("\n") else row + "\n")
    )
    await obsidian.put_note(path, new_body)
    return "created"
