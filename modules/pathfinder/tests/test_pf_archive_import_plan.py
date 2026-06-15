"""Tests for the side-effect-free Pathfinder archive import plan."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.pf_archive_import_plan import (
    ImportCostGuardError,
    build_pf_archive_import_plan,
)

FIXTURES = Path(__file__).parent / "fixtures" / "cartosia"


def test_plan_applies_npc_first_limit_without_vault_io():
    plan = build_pf_archive_import_plan(
        archive_root=str(FIXTURES),
        dry_run=True,
        limit=2,
        confirm_large=False,
    )

    assert len(plan.entries) == 2
    assert {entry.decision.bucket for entry in plan.entries} <= {"npc_a", "npc_b"}
    assert plan.errors == ()


def test_plan_cost_guard_blocks_large_live_run_before_execution(tmp_path):
    archive = tmp_path / "cartosia"
    npcs_dir = archive / "The NPCs"
    npcs_dir.mkdir(parents=True)
    for i in range(25):
        (npcs_dir / f"NPC {i:02d}.md").write_text(
            f"# NPC {i}\n\n**Creature 1**\n\n**AC** 14\n**HP** 10\n\n"
            f"Body text long enough to clear the skip threshold {'x' * 220}\n",
            encoding="utf-8",
        )

    with pytest.raises(ImportCostGuardError):
        build_pf_archive_import_plan(
            archive_root=str(archive),
            dry_run=False,
            limit=None,
            confirm_large=False,
        )
