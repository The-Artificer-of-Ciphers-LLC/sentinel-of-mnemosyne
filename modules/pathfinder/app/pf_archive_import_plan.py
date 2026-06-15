"""Side-effect-free planning for Pathfinder archive imports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.pf_archive_router import RouteDecision, route, slugify

_LARGE_NPC_THRESHOLD = 20


class ImportCostGuardError(Exception):
    """Raised when a live import would touch >20 NPCs without confirm_large."""


@dataclass(frozen=True)
class PFArchiveImportEntry:
    """One archive note after routing and pre-execution import policy."""

    path: Path
    rel_source: str
    content: str
    decision: RouteDecision


@dataclass(frozen=True)
class PFArchiveImportPlan:
    """Pure plan for a Pathfinder archive import."""

    archive_root: Path
    dry_run: bool
    subfolder: str
    entries: tuple[PFArchiveImportEntry, ...]
    errors: tuple[str, ...] = ()


def build_pf_archive_import_plan(
    *,
    archive_root: str,
    dry_run: bool,
    limit: int | None,
    confirm_large: bool,
    subfolder: str = "archive/cartosia",
) -> PFArchiveImportPlan:
    """Walk, route, cost-guard, limit, and dedupe an archive without Vault I/O."""
    root = Path(archive_root).resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(
            f"archive_root does not exist or is not a directory: {root}"
        )

    all_md_files = sorted(p for p in root.rglob("*.md") if p.is_file())
    known_npc_slugs = build_known_npc_slugs(all_md_files, root)

    entries: list[PFArchiveImportEntry] = []
    errors: list[str] = []
    for fp in all_md_files:
        try:
            content = fp.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"unreadable file (non-utf8): {fp}")
            continue
        decision = route(fp, content, archive_root=root, known_npc_slugs=known_npc_slugs)
        entries.append(
            PFArchiveImportEntry(
                path=fp,
                rel_source=str(fp.relative_to(root)),
                content=content,
                decision=decision,
            )
        )

    distinct_npc_slugs = {
        entry.decision.slug
        for entry in entries
        if entry.decision.bucket in {"npc_a", "npc_b"}
    }
    if (
        not dry_run
        and not confirm_large
        and len(distinct_npc_slugs) > _LARGE_NPC_THRESHOLD
    ):
        raise ImportCostGuardError(
            f"refusing to live-import {len(distinct_npc_slugs)} NPCs "
            f"(>{_LARGE_NPC_THRESHOLD}); pass confirm_large=True to proceed"
        )

    if limit is not None and limit > 0:
        npc_entries = [
            entry for entry in entries if entry.decision.bucket in {"npc_a", "npc_b"}
        ]
        rest_entries = [
            entry for entry in entries if entry.decision.bucket not in {"npc_a", "npc_b"}
        ]
        entries = (npc_entries + rest_entries)[:limit]

    entries = dedupe_npcs(entries)
    return PFArchiveImportPlan(
        archive_root=root,
        dry_run=dry_run,
        subfolder=subfolder,
        entries=tuple(entries),
        errors=tuple(errors),
    )


def dedupe_npcs(
    entries: list[PFArchiveImportEntry],
) -> list[PFArchiveImportEntry]:
    """Collapse duplicate NPC slugs to one record, preferring npc_a."""
    seen: dict[str, PFArchiveImportEntry] = {}
    out: list[PFArchiveImportEntry] = []
    for entry in entries:
        if entry.decision.bucket not in {"npc_a", "npc_b"}:
            out.append(entry)
            continue
        prior = seen.get(entry.decision.slug)
        if prior is None:
            seen[entry.decision.slug] = entry
            continue
        if entry.decision.bucket == "npc_a" and prior.decision.bucket == "npc_b":
            seen[entry.decision.slug] = entry
    out.extend(seen.values())
    return out


def build_known_npc_slugs(
    all_md_files: Iterable[Path], root: Path
) -> frozenset[str]:
    """Cheap first pass used by route() to resolve dialogue owners."""
    slugs: set[str] = set()
    for fp in all_md_files:
        rel = fp.relative_to(root)
        for part in rel.parts[:-1]:
            if part.lower() in {"the npcs", "the npc"}:
                continue
            slugs.add(slugify(part.replace('"', "").replace("“", "").replace("”", "")))
        head = re.split(r"\s+(?:-|—|–)\s+", fp.stem, maxsplit=1)[0]
        slugs.add(slugify(head.replace('"', "")))
    return frozenset(s for s in slugs if s)
