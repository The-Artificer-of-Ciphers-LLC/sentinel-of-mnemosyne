"""Vault inventory: answers "what is in my second brain?"-shaped meta-questions.

Warm recall (``Recall._warm_search``) is *relevance search* -- it ranks notes
against a query. A meta-question about vault CONTENTS ("what topics do you
have?") has no single relevant note to retrieve, so warm recall returns
nothing and the model confabulates (verified in production).

This module detects that question shape (``is_inventory_query``, pure) and,
when detected, renders a compact summary of the links-graph sidecar
(``format_inventory``, pure) via a single vault read (``load_inventory``).

Reads the sidecar built by ``links_sidecar_index.py`` (``ops/graph/links-index.json``)
rather than re-implementing decoding or hardcoding the path -- this module is
purely a presentation layer over that existing index.
"""
from __future__ import annotations

import logging
import re

from app.services.links_sidecar_index import LINKS_INDEX_PATH, decode_index_body

logger = logging.getLogger(__name__)

__all__ = [
    "INVENTORY_QUERY_PATTERNS",
    "is_inventory_query",
    "format_inventory",
    "load_inventory",
]

# ---------------------------------------------------------------------------
# is_inventory_query
# ---------------------------------------------------------------------------

# Conservative, deliberately narrow set of patterns for "what does the vault
# CONTAIN" questions -- as opposed to "what do you know about <subject>"
# questions, which are ordinary warm-recall queries and must NOT match here.
# A false positive here wastes context on every message that trips it, so
# each pattern is anchored to a specific, real, observed phrasing rather than
# a broad keyword match (e.g. bare "topics" or "vault" would be too loose).
INVENTORY_QUERY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bwhat('?s| is) in (my )?second brain\b"),
    re.compile(r"\bwhat('?s| is) in (it|my vault|the vault)\b"),
    re.compile(r"\bwhat do you have on me\b"),
    re.compile(r"\bsummary of (the |my )?topics\b"),
    re.compile(r"\bwhat topics\b"),
    re.compile(r"\blist the topics\b"),
    re.compile(r"\bwhat subjects\b"),
    re.compile(r"\bwhat do you know about me\b"),
    re.compile(r"\bwhat have you got\b"),
    re.compile(r"\bcontents of (my )?vault\b"),
    re.compile(r"\btable of contents\b"),
    re.compile(r"\boverview of (my )?notes\b"),
    re.compile(r"\bwhat notes do you have\b"),
    # Validated against real observed queries pulled from the production
    # inbox queue and live Discord transcript (2026-08-29): "show me a
    # summary of my notes", "give me a summary of my second brain status".
    # Add future patterns the same way -- against a real, verbatim query,
    # not an imagined phrasing.
    re.compile(r"\b(summary|overview|rundown) of (my |the )?(notes|vault|second brain)\b"),
    re.compile(r"\bsecond brain (status|contents)\b"),
)


def is_inventory_query(text: str) -> bool:
    """Return True when ``text`` asks what the vault CONTAINS, not a subject.

    Pure, no I/O. Matches case-insensitively against normalised whitespace
    using the conservative pattern set in ``INVENTORY_QUERY_PATTERNS``.

    Deliberately returns False for ordinary subject questions (e.g. "what do
    you know about creative resets?", "what is a memory palace?", "what's in
    the music module?") -- those are warm-recall queries, not inventory
    queries. A false positive here wastes one of the scarce context slots on
    every affected message, so the pattern set stays narrow and specific
    rather than matching loosely on words like "topics" or "vault" alone.
    """
    if not text:
        return False
    normalised = " ".join(text.split()).lower()
    return any(p.search(normalised) for p in INVENTORY_QUERY_PATTERNS)


# ---------------------------------------------------------------------------
# format_inventory
# ---------------------------------------------------------------------------


def _title_from_path(path: str) -> str:
    """Derive a human-readable title from a vault-relative note path.

    Strips the ``.md`` suffix, keeps only the filename stem, replaces
    hyphens with spaces, and capitalises the first character.
    """
    stem = path.rsplit("/", 1)[-1]
    if stem.endswith(".md"):
        stem = stem[: -len(".md")]
    stem = stem.replace("-", " ")
    if not stem:
        return stem
    return stem[0].upper() + stem[1:]


def format_inventory(index: dict[str, dict], *, max_notes: int = 60) -> str:
    """Render a compact, token-bounded plain-text inventory of ``index``.

    Pure, no I/O. Groups notes by ``schema.type`` -- ``"hub"`` entries first
    (these are topic clusters), then every other type (including untyped
    entries, grouped under ``"untyped"``). Each note is rendered as its
    human-readable title (see ``_title_from_path``). Truncates to
    ``max_notes`` total entries across all groups, appending an explicit
    "... and N more" line so the block can never blow the context budget.

    Returns "" for an empty index.
    """
    if not index:
        return ""

    groups: dict[str, list[str]] = {}
    for path, entry in sorted(index.items()):
        schema = entry.get("schema") if isinstance(entry, dict) else None
        note_type = None
        if isinstance(schema, dict):
            note_type = schema.get("type")
        if not note_type:
            note_type = "untyped"
        groups.setdefault(note_type, []).append(path)

    total = sum(len(paths) for paths in groups.values())

    # Hub entries first (topic clusters), then every other type, sorted by
    # type name for deterministic output.
    ordered_types = sorted(groups.keys(), key=lambda t: (t != "hub", t))

    lines: list[str] = [f"Vault inventory: {total} notes."]
    remaining = max_notes
    truncated_count = 0

    for note_type in ordered_types:
        paths = groups[note_type]
        if remaining <= 0:
            truncated_count += len(paths)
            continue

        lines.append("")
        lines.append(f"{note_type} ({len(paths)}):")

        take = paths[:remaining]
        overflow = paths[remaining:]
        remaining -= len(take)
        truncated_count += len(overflow)

        for path in take:
            lines.append(f"- {_title_from_path(path)}")

    if truncated_count:
        lines.append("")
        lines.append(f"... and {truncated_count} more")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# load_inventory
# ---------------------------------------------------------------------------


async def load_inventory(vault) -> str:
    """Read the links sidecar index and return ``format_inventory`` of it.

    ONE ``read_note`` call -- no per-note REST fan-out. Fails soft: any
    read or decode failure returns "" and logs at debug/warning; this must
    never raise into ``Recall``.
    """
    try:
        raw = await vault.read_note(LINKS_INDEX_PATH)
    except Exception as exc:
        logger.warning(
            "load_inventory: failed to read index at %r: %r", LINKS_INDEX_PATH, exc
        )
        return ""

    if not raw or not raw.strip():
        logger.debug("load_inventory: index at %r is empty or absent", LINKS_INDEX_PATH)
        return ""

    try:
        index = decode_index_body(raw)
    except Exception as exc:
        logger.warning(
            "load_inventory: failed to decode index at %r: %r", LINKS_INDEX_PATH, exc
        )
        return ""

    if not isinstance(index, dict):
        logger.warning(
            "load_inventory: index at %r has unexpected type %r (expected dict)",
            LINKS_INDEX_PATH, type(index).__name__,
        )
        return ""

    return format_inventory(index)
