"""Cartosia archive importer orchestrator (260427-czb Task 3).

Walks an on-disk archive root, classifies each .md via
:mod:`app.pf_archive_router`, and writes the results into the vault under
``mnemosyne/pf2e/`` using the Phase 29 NPC frontmatter contract.

Behaviour summary (must_haves from PLAN.md):

* ``dry_run=True`` (default): produce a routing report at
  ``ops/sweeps/cartosia-dry-run-<ts>.md``; ZERO vault writes outside the
  report itself.
* ``dry_run=False`` (live): per file, GET-then-PUT through ObsidianClient.
  Existence check is skip-by-default; ``force=True`` overrides.
* ``limit=N``: cap file count (applied per-bucket as well — NPCs first,
  then everything else).
* ``confirm_large=False`` AND live mode AND >20 NPCs → raise
  :class:`ImportCostGuardError` BEFORE the first LLM call.
* Idempotency: re-running with default flags is a no-op (skipped_existing
  matches first-run npc_count).
* Two-NPC files: imported as a single record with the combined name
  preserved verbatim.
* Duplicate folder-trees (same NPC dir at two paths): one NPC record;
  dialogue files concatenated.
* Format B Secret block: preserved verbatim in the body markdown (no
  schema extension — Phase 29 contract is read-only).
* Homebrew destination: ``mnemosyne/pf2e/homebrew/`` (sibling of
  ``rulings/``) so the Phase 33 rules engine does not see a phantom
  ``homebrew`` topic.
"""
from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import yaml

from app.legendkeeper_image import download_token
from app.pf_archive_import_plan import (
    ImportCostGuardError,
    build_pf_archive_import_plan,
)
from app.pf_archive_router import RouteDecision, slugify
from app.pf_npc_extract import NpcExtractionError, extract_npc

logger = logging.getLogger(__name__)

__all__ = ["ImportCostGuardError", "ImportReport", "run_import"]


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class ImportReport:
    """Aggregated outcome of a single ``run_import`` invocation.

    Counters are observable outputs the Discord verb surfaces back to the
    operator; ``errors`` captures per-file extraction failures so the
    dry-run/live report can include them inline.
    """

    archive_root: str = ""
    dry_run: bool = True
    npc_count: int = 0
    location_count: int = 0
    homebrew_count: int = 0
    harvest_count: int = 0
    lore_count: int = 0
    session_count: int = 0
    arc_count: int = 0
    faction_count: int = 0
    dialogue_count: int = 0
    skip_count: int = 0
    skipped_existing: int = 0
    errors: list[str] = field(default_factory=list)
    proposed_writes: list[dict] = field(default_factory=list)
    report_path: str = ""

    def asdict(self) -> dict:
        return {
            "archive_root": self.archive_root,
            "dry_run": self.dry_run,
            "npc_count": self.npc_count,
            "location_count": self.location_count,
            "homebrew_count": self.homebrew_count,
            "harvest_count": self.harvest_count,
            "lore_count": self.lore_count,
            "session_count": self.session_count,
            "arc_count": self.arc_count,
            "faction_count": self.faction_count,
            "dialogue_count": self.dialogue_count,
            "skip_count": self.skip_count,
            "skipped_existing": self.skipped_existing,
            "errors": list(self.errors),
            "report_path": self.report_path,
        }


class _ObsidianLike(Protocol):
    async def get_note(self, path: str) -> str | None: ...
    async def put_note(self, path: str, content: str) -> None: ...
    async def put_binary(self, path: str, data: bytes, content_type: str) -> None: ...


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


_LEGENDKEEPER_RE = re.compile(
    r"!\[[^\]]*\]\((https://assets\.legendkeeper\.com/[^)\s]+)"
)
_FRONTMATTER_DELIM_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_import(
    *,
    archive_root: str,
    dry_run: bool,
    limit: int | None,
    force: bool,
    confirm_large: bool,
    obsidian_client: _ObsidianLike,
    subfolder: str = "archive/cartosia",
) -> ImportReport:
    """Run the PF2e archive importer over ``archive_root``.

    ``subfolder`` is the logical archive identifier — used for the
    ``imported_from`` frontmatter field and as the slug prefix for the
    report path. Defaults to ``archive/cartosia`` for backward compat
    with the original cartosia-only importer.
    """
    plan = build_pf_archive_import_plan(
        archive_root=archive_root,
        dry_run=dry_run,
        limit=limit,
        confirm_large=confirm_large,
        subfolder=subfolder,
    )
    root = plan.archive_root
    report = ImportReport(archive_root=str(root), dry_run=dry_run)
    report.errors.extend(plan.errors)

    dialogue_buffers: dict[str, list[str]] = {}  # owner_slug → list of body chunks
    iso_now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    for entry in plan.entries:
        content = entry.content
        decision = entry.decision
        if decision.bucket == "skip":
            report.skip_count += 1
            continue

        # Common existence check (live mode only).
        if not dry_run and decision.dest:
            existing = await obsidian_client.get_note(decision.dest)
            if existing is not None and not force:
                if decision.bucket in {"npc_a", "npc_b"}:
                    report.skipped_existing += 1
                continue

        if decision.bucket in {"npc_a", "npc_b"}:
            await _process_npc(
                fp=entry.path,
                content=content,
                decision=decision,
                rel_source=entry.rel_source,
                iso_now=iso_now,
                dry_run=dry_run,
                obsidian=obsidian_client,
                report=report,
                subfolder=subfolder,
            )
        elif decision.bucket == "npc_dialogue":
            owner = decision.owner_slug or "_orphan-dialogue"
            dialogue_buffers.setdefault(owner, []).append(
                f"## From `{entry.rel_source}`\n\n{content.strip()}\n"
            )
            report.dialogue_count += 1
            report.proposed_writes.append({
                "source": entry.rel_source,
                "bucket": decision.bucket,
                "dest": decision.dest,
                "reason": decision.reason,
            })
        else:
            await _process_passthrough(
                content=content,
                decision=decision,
                rel_source=entry.rel_source,
                iso_now=iso_now,
                dry_run=dry_run,
                obsidian=obsidian_client,
                report=report,
                subfolder=subfolder,
            )

    if not dry_run:
        for owner_slug, chunks in dialogue_buffers.items():
            dest = f"mnemosyne/pf2e/npcs/{owner_slug}/dialogue.md"
            existing = await obsidian_client.get_note(dest)
            if existing is not None and not force:
                # Append by GET-then-PUT (project_obsidian_patch_constraint:
                # don't try to PATCH a field that may not exist).
                merged = existing.rstrip() + "\n\n---\n\n" + "\n\n".join(chunks)
            else:
                merged = "\n\n".join(chunks)
            await obsidian_client.put_note(dest, merged)

    report_path = _write_report(report, dry_run=dry_run, iso_now=iso_now, subfolder=subfolder)
    report.report_path = report_path
    if not dry_run or True:  # always write the report (dry-run too)
        await obsidian_client.put_note(report_path, _render_report(report, subfolder=subfolder))

    return report


# ---------------------------------------------------------------------------
# Internals — NPC processing
# ---------------------------------------------------------------------------


async def _process_npc(
    *,
    fp: Path,
    content: str,
    decision: RouteDecision,
    rel_source: str,
    iso_now: str,
    dry_run: bool,
    obsidian: _ObsidianLike,
    report: ImportReport,
    subfolder: str = "archive/cartosia",
) -> None:
    report.npc_count += 1
    report.proposed_writes.append({
        "source": rel_source,
        "bucket": decision.bucket,
        "dest": decision.dest,
        "reason": decision.reason,
    })
    if dry_run:
        return

    fmt = "A" if decision.bucket == "npc_a" else "B"
    try:
        fields = await extract_npc(content, rel_source, format=fmt)
    except NpcExtractionError as exc:
        report.errors.append(f"NPC extraction failed for {rel_source}: {exc}")
        return

    # LegendKeeper image (Format B has them most often, but Format A may too).
    token_image = None
    match = _LEGENDKEEPER_RE.search(content)
    if match:
        url = match.group(1)
        try:
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http_client:
                token_image = await download_token(
                    url,
                    dest_slug=decision.slug,
                    obsidian_client=obsidian,
                    http_client=http_client,
                )
        except Exception as exc:  # network / Pillow / vault — don't fail the NPC
            logger.warning("token download failed for %s: %s", decision.slug, exc)

    # Compose Phase 29 frontmatter — DO NOT add new fields. Format B's
    # Age/Location/height/eye color stay in the body markdown.
    frontmatter = {
        "name": fields["name"],
        "ancestry": fields["ancestry"],
        "class": fields["class"],
        "level": fields["level"],
        "mood": fields["mood"],
        "personality": fields["personality"],
        "backstory": fields["backstory"],
        "traits": list(fields["traits"]),
        "relationships": [],
        "imported_from": subfolder,
        "imported_at": iso_now,
        "source_path": rel_source,
        "token_image": token_image,
    }
    body = _strip_existing_frontmatter(content)
    note = (
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
        + "---\n\n"
        + body
    )
    await obsidian.put_note(decision.dest, note)


# ---------------------------------------------------------------------------
# Internals — passthrough buckets (location, lore, homebrew, harvest, ...).
# ---------------------------------------------------------------------------


async def _process_passthrough(
    *,
    content: str,
    decision: RouteDecision,
    rel_source: str,
    iso_now: str,
    dry_run: bool,
    obsidian: _ObsidianLike,
    report: ImportReport,
    subfolder: str = "archive/cartosia",
) -> None:
    counter_map = {
        "location": "location_count",
        "homebrew": "homebrew_count",
        "harvest": "harvest_count",
        "lore": "lore_count",
        "session": "session_count",
        "arc": "arc_count",
        "faction": "faction_count",
    }
    attr = counter_map.get(decision.bucket)
    if attr:
        setattr(report, attr, getattr(report, attr) + 1)
    report.proposed_writes.append({
        "source": rel_source,
        "bucket": decision.bucket,
        "dest": decision.dest,
        "reason": decision.reason,
    })
    if dry_run:
        return

    body = _strip_existing_frontmatter(content)
    fm = {
        "imported_from": subfolder,
        "imported_at": iso_now,
        "source_path": rel_source,
        "bucket": decision.bucket,
    }
    note = (
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
        + "---\n\n"
        + body
    )
    await obsidian.put_note(decision.dest, note)


# ---------------------------------------------------------------------------
# Internals — helpers.
# ---------------------------------------------------------------------------


def _strip_existing_frontmatter(content: str) -> str:
    if content.startswith("---"):
        m = _FRONTMATTER_DELIM_RE.match(content)
        if m:
            return content[m.end() :].lstrip("\n")
    return content


def _write_report(
    report: ImportReport, *, dry_run: bool, iso_now: str, subfolder: str = "archive/cartosia"
) -> str:
    ts = iso_now.replace(":", "-").replace("+00-00", "Z")
    kind = "dry-run" if dry_run else "import"
    sub_slug = slugify(subfolder)
    return f"ops/sweeps/{sub_slug}-{kind}-{ts}.md"


def _render_report(report: ImportReport, *, subfolder: str = "archive/cartosia") -> str:
    kind_word = "Dry-Run" if report.dry_run else "Import"
    lines = [
        f"# PF2e Archive {kind_word} Report ({subfolder})",
        "",
        f"- archive_root: `{report.archive_root}`",
        f"- npc_count: {report.npc_count}",
        f"- location_count: {report.location_count}",
        f"- homebrew_count: {report.homebrew_count}",
        f"- harvest_count: {report.harvest_count}",
        f"- lore_count: {report.lore_count}",
        f"- session_count: {report.session_count}",
        f"- arc_count: {report.arc_count}",
        f"- faction_count: {report.faction_count}",
        f"- dialogue_count: {report.dialogue_count}",
        f"- skip_count: {report.skip_count}",
        f"- skipped_existing: {report.skipped_existing}",
        f"- errors: {len(report.errors)}",
        "",
        "## Proposed writes",
        "",
        "| bucket | source | dest | reason |",
        "| --- | --- | --- | --- |",
    ]
    for pw in report.proposed_writes:
        lines.append(
            f"| {pw['bucket']} | `{pw['source']}` | `{pw['dest']}` | {pw['reason']} |"
        )
    if report.errors:
        lines.append("")
        lines.append("## Errors")
        lines.append("")
        for err in report.errors:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"
