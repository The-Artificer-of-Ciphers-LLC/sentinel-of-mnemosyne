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
from dataclasses import dataclass, field
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


@dataclass
class GraphReport:
    """Computed wikilink-graph report over an in-memory notes map."""

    note_count: int = 0
    orphans: list[str] = field(default_factory=list)
    backlinks: dict[str, list[str]] = field(default_factory=dict)
    hub_count: int = 0
    link_density: float = 0.0


def build_graph_report(notes: dict[str, str], hub_paths: set[str]) -> GraphReport:
    """Compute the ``GraphReport`` over an in-memory notes map.

    Pure computation — no vault I/O of its own. For each note, extracts and
    resolves its outbound wikilinks (via ``extract_wikilinks`` +
    ``resolve_wikilink``, self-links excluded), builds the backlinks map
    from resolved edges, marks a note an orphan when it has neither
    resolved inbound nor outbound edges (D-03b: a hub-pending singleton with
    no links yet is reported as an orphan — there is no separate pending
    state), sets ``hub_count`` from ``hub_paths``, and computes
    ``link_density`` as total resolved edges over ``note_count`` (0.0 for an
    empty vault, guarding the divide).
    """
    note_paths = list(notes.keys())
    outlinks: dict[str, set[str]] = {}
    backlinks: dict[str, list[str]] = {path: [] for path in notes}

    for path, body in notes.items():
        resolved: set[str] = set()
        for target in extract_wikilinks(body):
            resolved_path = resolve_wikilink(target, note_paths)
            if resolved_path is not None and resolved_path != path:
                resolved.add(resolved_path)
        outlinks[path] = resolved

    for src, targets in outlinks.items():
        for target_path in targets:
            backlinks[target_path].append(src)

    orphans = [
        path for path in notes if not outlinks[path] and not backlinks[path]
    ]

    total_edges = sum(len(v) for v in outlinks.values())
    note_count = len(notes)

    return GraphReport(
        note_count=note_count,
        orphans=orphans,
        backlinks=backlinks,
        hub_count=len(hub_paths),
        link_density=(total_edges / note_count) if note_count else 0.0,
    )
