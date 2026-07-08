"""Pure wikilink-orphan checker, vendored from sentinel-core (MUS-05, D-08/D-10).

Module containers cannot import ``sentinel-core`` at runtime, so the orphan
rule — ``orphan iff no outlinks and no backlinks``, resolved strictly by
filename stem — lives here once instead of drifting per-module. This is a
behavior-preserving vendor of
``sentinel-core/app/services/graph_analysis.py``'s ``extract_wikilinks``,
``_slugify``, ``resolve_wikilink``, ``GraphReport``, and
``build_graph_report``, with the Core-only ``hub_paths`` parameter and
``hub_count`` field dropped (module self-checks do not classify hubs).

Pure computation — no vault I/O, no ``sentinel-core`` import. Any module
(music, and future modules per the 6-module PRD) can import this to prove its
own zero-orphan compliance against the exact rule Core uses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

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
    wikilink target (e.g. ``Member One``) compares equal to its filename
    stem (e.g. ``member-one``). Slashes are preserved, so a full-path target
    like ``dir/x`` never equals a bare stem like ``x``.
    """
    return (text or "").strip().lower().replace(" ", "-").replace("_", "-")


def resolve_wikilink(target: str, note_paths: Iterable[str]) -> str | None:
    """Resolve ``target`` to the note path whose filename stem matches.

    Matches by filename stem: a path resolves when its stem — case/separator
    -normalized — equals the normalized ``target``. Returns ``None`` when no
    path matches (including when ``target`` carries a directory prefix that
    does not match any bare stem).
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
    link_density: float = 0.0


def build_graph_report(notes: dict[str, str]) -> GraphReport:
    """Compute the ``GraphReport`` over an in-memory notes map.

    Pure computation — no I/O. For each note, extracts and resolves its
    outbound wikilinks (via ``extract_wikilinks`` + ``resolve_wikilink``,
    self-links excluded), builds the backlinks map from resolved edges,
    marks a note an orphan when it has neither resolved inbound nor outbound
    edges (a hub-pending singleton with no links yet is reported as an
    orphan — there is no separate pending state), and computes
    ``link_density`` as total resolved edges over ``note_count`` (0.0 for an
    empty notes map, guarding the divide).
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
        link_density=(total_edges / note_count) if note_count else 0.0,
    )
