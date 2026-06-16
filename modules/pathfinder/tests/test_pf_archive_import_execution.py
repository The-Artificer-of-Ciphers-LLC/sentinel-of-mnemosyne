"""Tests for PF Archive Import Execution."""

from __future__ import annotations

from pathlib import Path

from app.pf_archive_import_execution import execute_pf_archive_import_plan
from app.pf_archive_import_plan import PFArchiveImportEntry, PFArchiveImportPlan
from app.pf_archive_router import RouteDecision


class FakeObsidian:
    def __init__(self) -> None:
        self.notes: dict[str, str] = {}
        self.get_note_calls: list[str] = []
        self.put_note_calls: list[tuple[str, str]] = []
        self.put_binary_calls: list[tuple[str, bytes, str]] = []

    async def get_note(self, path: str) -> str | None:
        self.get_note_calls.append(path)
        return self.notes.get(path)

    async def put_note(self, path: str, content: str) -> None:
        self.put_note_calls.append((path, content))
        self.notes[path] = content

    async def put_binary(self, path: str, data: bytes, content_type: str) -> None:
        self.put_binary_calls.append((path, data, content_type))


async def _token_downloader(*args, **kwargs) -> str | None:
    raise AssertionError("token downloader should not be called")


def _plan(*, root: Path, dry_run: bool, entries: list[PFArchiveImportEntry]) -> PFArchiveImportPlan:
    return PFArchiveImportPlan(
        archive_root=root,
        dry_run=dry_run,
        subfolder="archive/test",
        entries=tuple(entries),
    )


def _entry(
    *,
    root: Path,
    source: str,
    content: str,
    decision: RouteDecision,
) -> PFArchiveImportEntry:
    return PFArchiveImportEntry(
        path=root / source,
        rel_source=source,
        content=content,
        decision=decision,
    )


async def test_execution_skips_existing_npc_without_extracting_or_writing(tmp_path):
    obsidian = FakeObsidian()
    obsidian.notes["mnemosyne/pf2e/npcs/existing.md"] = "already here"
    decision = RouteDecision(
        bucket="npc_a",
        slug="existing",
        dest="mnemosyne/pf2e/npcs/existing.md",
        reason="already imported",
    )

    report = await execute_pf_archive_import_plan(
        _plan(
            root=tmp_path,
            dry_run=False,
            entries=[
                _entry(
                    root=tmp_path,
                    source="Bestiary/Existing.md",
                    content="**Creature 1**\n\n**AC** 14\n",
                    decision=decision,
                )
            ],
        ),
        force=False,
        obsidian_client=obsidian,
        token_downloader=_token_downloader,
    )

    assert report.skipped_existing == 1
    assert report.npc_count == 0
    assert obsidian.get_note_calls == [
        "mnemosyne/pf2e/npcs/existing.md",
    ]
    assert [path for path, _ in obsidian.put_note_calls] == [
        report.report_path,
    ]


async def test_execution_consolidates_dialogue_and_writes_report(tmp_path):
    obsidian = FakeObsidian()
    decision = RouteDecision(
        bucket="npc_dialogue",
        slug="things-said",
        dest="mnemosyne/pf2e/npcs/fenn/dialogue.md",
        reason="dialogue filename; owner=fenn",
        owner_slug="fenn",
    )

    report = await execute_pf_archive_import_plan(
        _plan(
            root=tmp_path,
            dry_run=False,
            entries=[
                _entry(
                    root=tmp_path,
                    source="The NPCs/Fenn/Things Said.md",
                    content="Fenn remembers the bridge.",
                    decision=decision,
                )
            ],
        ),
        force=False,
        obsidian_client=obsidian,
        token_downloader=_token_downloader,
    )

    assert report.dialogue_count == 1
    assert obsidian.notes["mnemosyne/pf2e/npcs/fenn/dialogue.md"] == (
        "## From `The NPCs/Fenn/Things Said.md`\n\n"
        "Fenn remembers the bridge.\n"
    )
    assert report.report_path.startswith("ops/sweeps/archive-test-import-")
    assert report.report_path in obsidian.notes
