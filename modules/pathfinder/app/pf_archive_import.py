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
from typing import Iterable, Protocol

import yaml

from app.pf_npc_extract import NpcExtractionError, extract_npc
from app.pf_archive_router import RouteDecision, route, slugify
from app.legendkeeper_image import download_token

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class ImportCostGuardError(Exception):
    """Raised when a live import would touch >20 NPCs without confirm_large."""


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


_LARGE_NPC_THRESHOLD = 20  # research §LLM cost guard
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
    root = Path(archive_root).resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"archive_root does not exist or is not a directory: {root}")

    report = ImportReport(archive_root=str(root), dry_run=dry_run)

    # 1. Walk archive, collect all .md files.
    all_md_files = sorted(p for p in root.rglob("*.md") if p.is_file())

    # 2. First pass: build known_npc_slugs from files that sniff as NPC OR
    #    are an NPC-as-folder envelope (a dir whose name appears as a slug
    #    in dialogue children).
    known_npc_slugs = _build_known_npc_slugs(all_md_files, root)

    # 3. Second pass: classify everything.
    classifications: list[tuple[Path, str, RouteDecision]] = []
    for fp in all_md_files:
        try:
            content = fp.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            report.errors.append(f"unreadable file (non-utf8): {fp}")
            continue
        decision = route(fp, content, archive_root=root, known_npc_slugs=known_npc_slugs)
        classifications.append((fp, content, decision))

    # 4. Cost guard — count distinct NPC slugs (after dedupe by slug).
    distinct_npc_slugs: set[str] = {
        d.slug for _, _, d in classifications if d.bucket in {"npc_a", "npc_b"}
    }
    if (
        not dry_run
        and not confirm_large
        and len(distinct_npc_slugs) > _LARGE_NPC_THRESHOLD
    ):
        raise ImportCostGuardError(
            f"refusing to live-import {len(distinct_npc_slugs)} NPCs (>{_LARGE_NPC_THRESHOLD}); "
            f"pass confirm_large=True to proceed"
        )

    # 5. Apply limit if set — preserve a stable order: NPCs first (so the
    #    operator can sample LLM extraction quality with --limit 5), then
    #    everything else.
    if limit is not None and limit > 0:
        npc_class = [c for c in classifications if c[2].bucket in {"npc_a", "npc_b"}]
        rest_class = [c for c in classifications if c[2].bucket not in {"npc_a", "npc_b"}]
        classifications = (npc_class + rest_class)[:limit]

    # 6. Dedupe NPCs by slug — when two paths produce the same slug, prefer
    #    the one with bucket==npc_a (PF2e stat block) for the body. Both
    #    files' dialogue children stay separate (handled by route() — they
    #    classify independently).
    classifications = _dedupe_npcs(classifications)

    # 7. Process per file.
    dialogue_buffers: dict[str, list[str]] = {}  # owner_slug → list of body chunks
    iso_now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    for fp, content, decision in classifications:
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

        rel_source = str(fp.relative_to(root))

        if decision.bucket in {"npc_a", "npc_b"}:
            await _process_npc(
                fp=fp,
                content=content,
                decision=decision,
                rel_source=rel_source,
                iso_now=iso_now,
                dry_run=dry_run,
                obsidian=obsidian_client,
                report=report,
                subfolder=subfolder,
            )
        elif decision.bucket == "npc_dialogue":
            owner = decision.owner_slug or "_orphan-dialogue"
            dialogue_buffers.setdefault(owner, []).append(
                f"## From `{rel_source}`\n\n{content.strip()}\n"
            )
            report.dialogue_count += 1
            report.proposed_writes.append({
                "source": rel_source,
                "bucket": decision.bucket,
                "dest": decision.dest,
                "reason": decision.reason,
            })
        else:
            await _process_passthrough(
                content=content,
                decision=decision,
                rel_source=rel_source,
                iso_now=iso_now,
                dry_run=dry_run,
                obsidian=obsidian_client,
                report=report,
                subfolder=subfolder,
            )

    # 8. Flush dialogue buffers (live mode only).
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

    # 9. Write the report file.
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
# Internals — dedupe + helpers.
# ---------------------------------------------------------------------------


def _dedupe_npcs(
    classifications: list[tuple[Path, str, RouteDecision]],
) -> list[tuple[Path, str, RouteDecision]]:
    """Collapse duplicate NPC slugs to one record, preferring npc_a (stat block).

    Non-NPC entries pass through unchanged.
    """
    seen: dict[str, tuple[Path, str, RouteDecision]] = {}
    out: list[tuple[Path, str, RouteDecision]] = []
    for fp, content, decision in classifications:
        if decision.bucket not in {"npc_a", "npc_b"}:
            out.append((fp, content, decision))
            continue
        prior = seen.get(decision.slug)
        if prior is None:
            seen[decision.slug] = (fp, content, decision)
            continue
        # If new is npc_a and prior is npc_b, the new wins.
        if decision.bucket == "npc_a" and prior[2].bucket == "npc_b":
            seen[decision.slug] = (fp, content, decision)
        # Otherwise keep the first.
    out.extend(seen.values())
    return out


def _build_known_npc_slugs(
    all_md_files: Iterable[Path], root: Path
) -> frozenset[str]:
    """Cheap first pass — slugs of any file that *might* be an NPC, plus
    NPC-as-folder dir slugs. Used by ``route()`` to resolve dialogue owners.
    """
    slugs: set[str] = set()
    for fp in all_md_files:
        rel = fp.relative_to(root)
        # Any directory named the same as a sibling .md file → NPC envelope.
        # Plus all dirs whose parent is "The NPCs" / "the npcs".
        for part in rel.parts[:-1]:
            if part.lower() in {"the npcs", "the npc"}:
                continue
            slugs.add(slugify(part.replace('"', "").replace("“", "").replace("”", "")))
        # File stems too.
        head = re.split(r"\s+(?:-|—|–)\s+", fp.stem, maxsplit=1)[0]
        slugs.add(slugify(head.replace('"', "")))
    return frozenset(s for s in slugs if s)


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
