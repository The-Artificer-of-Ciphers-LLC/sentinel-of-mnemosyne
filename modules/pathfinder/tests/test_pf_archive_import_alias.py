"""Alias-parity / subfolder-parametric tests for the importer (260427-cui).

Pins:
  - `imported_from` reflects the `subfolder` argument dynamically (was the
    hardcoded literal `cartosia-archive` pre-refactor).
  - Report path slug derives from the subfolder (was `ops/sweeps/cartosia-…`).
  - Default subfolder = `archive/cartosia` for backward compat.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.pf_archive_import import ImportReport, run_import


# ---------------------------------------------------------------------------
# Minimal in-memory Obsidian double (mirrors the integration test FakeObsidian
# but kept local so this file is self-contained).
# ---------------------------------------------------------------------------


class _FakeObsidian:
    def __init__(self) -> None:
        self.put_note_calls: list[tuple[str, str]] = []
        self.notes: dict[str, str] = {}

    async def get_note(self, path: str) -> str | None:
        return self.notes.get(path)

    async def put_note(self, path: str, content: str) -> None:
        self.put_note_calls.append((path, content))
        self.notes[path] = content

    async def put_binary(self, path: str, data: bytes, content_type: str) -> None:
        pass


def _make_archive(root: Path, subdir: str) -> Path:
    """Build a tiny archive at `root/<subdir>` with one Format-A NPC."""
    archive = root / subdir
    archive.mkdir(parents=True)
    npc = archive / "Bestiary" / "Test Goblin.md"
    npc.parent.mkdir(parents=True)
    npc.write_text(
        "# Test Goblin\n\n**Creature 1**\n\n**AC** 14; **HP** 12\n\n"
        + ("filler body text " * 30)
    )
    return archive


# ---------------------------------------------------------------------------
# Subfolder threads through to imported_from frontmatter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_imported_from_uses_subfolder_argument_for_npc(tmp_path):
    """Live import with subfolder='archive/classes' must write
    `imported_from: archive/classes` into the NPC frontmatter — NOT the
    pre-refactor literal `cartosia-archive`.
    """
    archive = _make_archive(tmp_path, "archive/classes")
    obs = _FakeObsidian()

    async def _llm_response(*args, **kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"name":"Test Goblin","ancestry":"Goblin",'
                            '"class":"Warrior","level":1,"mood":"neutral",'
                            '"personality":"Hostile.","backstory":"Lives in caves.",'
                            '"traits":["goblin","humanoid"]}'
                        )
                    }
                }
            ]
        }

    with patch("app.pf_npc_extract.acompletion_with_profile",
               new=AsyncMock(side_effect=_llm_response)), \
         patch("app.pf_archive_import.download_token",
               new=AsyncMock(return_value=None)):
        report = await run_import(
            archive_root=str(archive),
            subfolder="archive/classes",
            dry_run=False,
            limit=None,
            force=False,
            confirm_large=False,
            obsidian_client=obs,
        )

    assert isinstance(report, ImportReport)
    npc_writes = [(p, c) for p, c in obs.put_note_calls
                  if p == "mnemosyne/pf2e/npcs/test-goblin.md"]
    assert len(npc_writes) == 1, f"expected one NPC write, got {npc_writes}"
    _, content = npc_writes[0]
    assert "imported_from: archive/classes" in content
    assert "cartosia-archive" not in content


@pytest.mark.asyncio
async def test_imported_from_uses_subfolder_argument_for_passthrough(tmp_path):
    """Same contract for passthrough buckets (location/lore/homebrew/etc):
    `imported_from` reflects the subfolder.
    """
    archive = tmp_path / "archive" / "lorepack"
    archive.mkdir(parents=True)
    lore = archive / "Locations" / "Some Place.md"
    lore.parent.mkdir(parents=True)
    lore.write_text("# Some Place\n\n" + ("descriptive prose " * 50))

    obs = _FakeObsidian()
    with patch("app.pf_npc_extract.acompletion_with_profile", new=AsyncMock()), \
         patch("app.pf_archive_import.download_token",
               new=AsyncMock(return_value=None)):
        await run_import(
            archive_root=str(archive),
            subfolder="archive/lorepack",
            dry_run=False,
            limit=None,
            force=False,
            confirm_large=False,
            obsidian_client=obs,
        )

    lore_writes = [(p, c) for p, c in obs.put_note_calls
                   if p.startswith("mnemosyne/pf2e/lore/")]
    assert lore_writes, f"expected lore write, got {[p for p, _ in obs.put_note_calls]}"
    _, content = lore_writes[0]
    assert "imported_from: archive/lorepack" in content
    assert "cartosia-archive" not in content


# ---------------------------------------------------------------------------
# Report path slug derives from subfolder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_report_path_slug_derives_from_subfolder(tmp_path):
    """A subfolder like 'archive/classes/wizard' must produce a report path
    `ops/sweeps/archive-classes-wizard-dry-run-<ts>.md` — NOT `cartosia-…`.
    """
    archive = _make_archive(tmp_path, "archive/classes/wizard")
    obs = _FakeObsidian()

    with patch("app.pf_npc_extract.acompletion_with_profile", new=AsyncMock()), \
         patch("app.pf_archive_import.download_token",
               new=AsyncMock(return_value=None)):
        report = await run_import(
            archive_root=str(archive),
            subfolder="archive/classes/wizard",
            dry_run=True,
            limit=None,
            force=False,
            confirm_large=False,
            obsidian_client=obs,
        )

    assert re.match(
        r"^ops/sweeps/archive-classes-wizard-dry-run-.+\.md$",
        report.report_path,
    ), f"unexpected report path: {report.report_path}"
    assert "cartosia" not in report.report_path


@pytest.mark.asyncio
async def test_default_subfolder_is_archive_cartosia(tmp_path):
    """Backward-compat: calling run_import without subfolder defaults to
    `archive/cartosia` (so the cartosia alias produces a report at
    `ops/sweeps/archive-cartosia-…`).
    """
    archive = _make_archive(tmp_path, "any/path")
    obs = _FakeObsidian()

    with patch("app.pf_npc_extract.acompletion_with_profile", new=AsyncMock()), \
         patch("app.pf_archive_import.download_token",
               new=AsyncMock(return_value=None)):
        report = await run_import(
            archive_root=str(archive),
            dry_run=True,
            limit=None,
            force=False,
            confirm_large=False,
            obsidian_client=obs,
        )

    # Default subfolder slug is 'archive-cartosia'.
    assert "archive-cartosia-dry-run-" in report.report_path
