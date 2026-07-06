"""Pure wikilink-graph computation backing ``:graph``/``:stats`` (NOTE-03, SC-3).

Extracts wikilink targets from note bodies, resolves them to flat-``notes/``
paths by filename stem, and computes a ``GraphReport`` (note_count, orphans,
backlinks, hub_count, link_density) over an in-memory notes map. This module
performs NO vault I/O of its own — the route (Plan 45-06) and the links
sidecar (Plan 45-04) own the reads; this module is pure computation.

``NOTES_ROOT`` is the single canonical source of truth for the flat notes/
prefix (RESEARCH Pitfall 3 / T-45-DRIFT) — no other string literal in this
module (or its sibling ``moc_maintenance.py`` / ``links_sidecar_index.py``)
should redefine the notes-root prefix independently.

``resolve_wikilink`` pins research Open Question 2 (filename-stem
resolution, not title- or path-based) and activates the Wave-0 wikilink
fixture in ``tests/test_p45_invariants.py``.
"""
from __future__ import annotations

import re
from typing import Iterable

# Single canonical definition site for the flat notes/ root — Pitfall 3 SPOT.
# Every other module needing the notes-bound prefix must import this
# constant rather than repeat the string literal.
NOTES_ROOT = "notes"

_MD_EXT = ".md"

# Wikilink target extraction -- excludes the alias segment of
# [[Target|Alias]] and the heading-anchor segment of [[Target#Heading]].
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


def extract_wikilinks(body: str) -> set[str]:
    """Return the set of raw wikilink targets referenced in ``body``.

    Strips the alias portion of ``[[Target|Alias]]`` and the heading-anchor
    portion of ``[[Target#Heading]]``. Targets are returned unresolved (raw
    link text) — see ``resolve_wikilink`` for path resolution.
    """
    return {m.group(1).strip() for m in _WIKILINK_RE.finditer(body or "")}


def _slugify(text: str) -> str:
    """Normalize a wikilink target or filename stem for stem comparison.

    Lowercases and folds spaces/underscores to hyphens so a display-text
    wikilink target (e.g. ``Member One``) compares equal to its flat-notes
    filename stem (e.g. ``member-one``).
    """
    return (text or "").strip().lower().replace(" ", "-").replace("_", "-")


def resolve_wikilink(target: str, note_paths: Iterable[str]) -> str | None:
    """Resolve ``target`` to the flat-notes path whose filename stem matches.

    Matches by filename stem (research Open Question 2): a path resolves
    when its stem — case/separator-normalized — equals the normalized
    ``target``. The flat-``notes/`` invariant (Pattern 3) guarantees unique
    stems across the vault, so no ambiguity can arise. Returns ``None`` when
    no path matches.
    """
    target_slug = _slugify(target)
    for path in note_paths:
        stem = path.rsplit("/", 1)[-1]
        if stem.endswith(_MD_EXT):
            stem = stem[: -len(_MD_EXT)]
        if _slugify(stem) == target_slug:
            return path
    return None
