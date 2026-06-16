"""Execution for a planned Pathfinder archive import.

This module owns the live write policy behind a PF Archive Import Plan:
existence checks, per-bucket report counters, NPC note rendering, dialogue
consolidation, and report persistence.
"""

from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
import yaml

from app.pf_archive_import_plan import PFArchiveImportPlan
from app.pf_archive_router import RouteDecision, slugify
from app.pf_npc_extract import NpcExtractionError, extract_npc

logger = logging.getLogger(__name__)


@dataclass
class ImportReport:
    """Aggregated outcome of a single archive import execution."""

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


class ObsidianLike(Protocol):
    async def get_note(self, path: str) -> str | None: ...
    async def put_note(self, path: str, content: str) -> None: ...
    async def put_binary(self, path: str, data: bytes, content_type: str) -> None: ...


class TokenDownloader(Protocol):
    async def __call__(
        self,
        url: str,
        *,
        dest_slug: str,
        obsidian_client: ObsidianLike,
        http_client: httpx.AsyncClient,
    ) -> str | None: ...


_LEGENDKEEPER_RE = re.compile(
    r"!\[[^\]]*\]\((https://assets\.legendkeeper\.com/[^)\s]+)"
)
_FRONTMATTER_DELIM_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


async def execute_pf_archive_import_plan(
    plan: PFArchiveImportPlan,
    *,
    force: bool,
    obsidian_client: ObsidianLike,
    token_downloader: TokenDownloader,
) -> ImportReport:
    """Execute a PF Archive Import Plan against the Vault adapter."""
    report = ImportReport(
        archive_root=str(plan.archive_root),
        dry_run=plan.dry_run,
    )
    report.errors.extend(plan.errors)

    dialogue_buffers: dict[str, list[str]] = {}
    iso_now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    for entry in plan.entries:
        decision = entry.decision
        if decision.bucket == "skip":
            report.skip_count += 1
            continue

        if not plan.dry_run and decision.dest:
            existing = await obsidian_client.get_note(decision.dest)
            if existing is not None and not force:
                if decision.bucket in {"npc_a", "npc_b"}:
                    report.skipped_existing += 1
                continue

        if decision.bucket in {"npc_a", "npc_b"}:
            await _process_npc(
                content=entry.content,
                decision=decision,
                rel_source=entry.rel_source,
                iso_now=iso_now,
                dry_run=plan.dry_run,
                obsidian=obsidian_client,
                token_downloader=token_downloader,
                report=report,
                subfolder=plan.subfolder,
            )
            continue

        if decision.bucket == "npc_dialogue":
            _buffer_dialogue(report, dialogue_buffers, decision, entry.rel_source, entry.content)
            continue

        await _process_passthrough(
            content=entry.content,
            decision=decision,
            rel_source=entry.rel_source,
            iso_now=iso_now,
            dry_run=plan.dry_run,
            obsidian=obsidian_client,
            report=report,
            subfolder=plan.subfolder,
        )

    if not plan.dry_run:
        await _write_dialogue_buffers(
            dialogue_buffers,
            force=force,
            obsidian=obsidian_client,
        )

    report.report_path = _write_report(
        report,
        dry_run=plan.dry_run,
        iso_now=iso_now,
        subfolder=plan.subfolder,
    )
    await obsidian_client.put_note(
        report.report_path,
        _render_report(report, subfolder=plan.subfolder),
    )
    return report


def _record_proposed_write(
    report: ImportReport,
    *,
    rel_source: str,
    decision: RouteDecision,
) -> None:
    report.proposed_writes.append({
        "source": rel_source,
        "bucket": decision.bucket,
        "dest": decision.dest,
        "reason": decision.reason,
    })


async def _process_npc(
    *,
    content: str,
    decision: RouteDecision,
    rel_source: str,
    iso_now: str,
    dry_run: bool,
    obsidian: ObsidianLike,
    token_downloader: TokenDownloader,
    report: ImportReport,
    subfolder: str,
) -> None:
    report.npc_count += 1
    _record_proposed_write(report, rel_source=rel_source, decision=decision)
    if dry_run:
        return

    fmt = "A" if decision.bucket == "npc_a" else "B"
    try:
        fields = await extract_npc(content, rel_source, format=fmt)
    except NpcExtractionError as exc:
        report.errors.append(f"NPC extraction failed for {rel_source}: {exc}")
        return

    token_image = await _download_token_image(
        content,
        decision=decision,
        obsidian=obsidian,
        token_downloader=token_downloader,
    )
    await obsidian.put_note(
        decision.dest,
        _render_npc_note(
            content,
            fields=fields,
            decision=decision,
            rel_source=rel_source,
            iso_now=iso_now,
            subfolder=subfolder,
            token_image=token_image,
        ),
    )


async def _download_token_image(
    content: str,
    *,
    decision: RouteDecision,
    obsidian: ObsidianLike,
    token_downloader: TokenDownloader,
) -> str | None:
    match = _LEGENDKEEPER_RE.search(content)
    if not match:
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http_client:
            return await token_downloader(
                match.group(1),
                dest_slug=decision.slug,
                obsidian_client=obsidian,
                http_client=http_client,
            )
    except Exception as exc:
        logger.warning("token download failed for %s: %s", decision.slug, exc)
        return None


def _render_npc_note(
    content: str,
    *,
    fields: dict[str, Any],
    decision: RouteDecision,
    rel_source: str,
    iso_now: str,
    subfolder: str,
    token_image: str | None,
) -> str:
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
    return _render_note(frontmatter, _strip_existing_frontmatter(content))


async def _process_passthrough(
    *,
    content: str,
    decision: RouteDecision,
    rel_source: str,
    iso_now: str,
    dry_run: bool,
    obsidian: ObsidianLike,
    report: ImportReport,
    subfolder: str,
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
    _record_proposed_write(report, rel_source=rel_source, decision=decision)
    if dry_run:
        return

    frontmatter = {
        "imported_from": subfolder,
        "imported_at": iso_now,
        "source_path": rel_source,
        "bucket": decision.bucket,
    }
    await obsidian.put_note(
        decision.dest,
        _render_note(frontmatter, _strip_existing_frontmatter(content)),
    )


def _buffer_dialogue(
    report: ImportReport,
    dialogue_buffers: dict[str, list[str]],
    decision: RouteDecision,
    rel_source: str,
    content: str,
) -> None:
    owner = decision.owner_slug or "_orphan-dialogue"
    dialogue_buffers.setdefault(owner, []).append(
        f"## From `{rel_source}`\n\n{content.strip()}\n"
    )
    report.dialogue_count += 1
    _record_proposed_write(report, rel_source=rel_source, decision=decision)


async def _write_dialogue_buffers(
    dialogue_buffers: dict[str, list[str]],
    *,
    force: bool,
    obsidian: ObsidianLike,
) -> None:
    for owner_slug, chunks in dialogue_buffers.items():
        dest = f"mnemosyne/pf2e/npcs/{owner_slug}/dialogue.md"
        existing = await obsidian.get_note(dest)
        if existing is not None and not force:
            merged = existing.rstrip() + "\n\n---\n\n" + "\n\n".join(chunks)
        else:
            merged = "\n\n".join(chunks)
        await obsidian.put_note(dest, merged)


def _render_note(frontmatter: dict[str, Any], body: str) -> str:
    return (
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
        + "---\n\n"
        + body
    )


def _strip_existing_frontmatter(content: str) -> str:
    if content.startswith("---"):
        match = _FRONTMATTER_DELIM_RE.match(content)
        if match:
            return content[match.end() :].lstrip("\n")
    return content


def _write_report(
    report: ImportReport, *, dry_run: bool, iso_now: str, subfolder: str
) -> str:
    ts = iso_now.replace(":", "-").replace("+00-00", "Z")
    kind = "dry-run" if dry_run else "import"
    sub_slug = slugify(subfolder)
    return f"ops/sweeps/{sub_slug}-{kind}-{ts}.md"


def _render_report(report: ImportReport, *, subfolder: str) -> str:
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
    for proposed_write in report.proposed_writes:
        lines.append(
            f"| {proposed_write['bucket']} | `{proposed_write['source']}` | "
            f"`{proposed_write['dest']}` | {proposed_write['reason']} |"
        )
    if report.errors:
        lines.append("")
        lines.append("## Errors")
        lines.append("")
        for err in report.errors:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"
