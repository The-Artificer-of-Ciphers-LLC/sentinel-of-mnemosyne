"""Integration tests for the cartosia importer orchestrator (260427-czb Task 3).

Drives the full walk → route → extract → write pipeline against the
fixture archive at tests/fixtures/cartosia/. All external dependencies
are faked:
  * ObsidianClient → in-memory recorder (no network).
  * LLM → patched AsyncMock with deterministic JSON responses.
  * LegendKeeper CDN → unused in these tests (token download is exercised
    in test_legendkeeper_image.py; here we patch download_token to a no-op
    so we don't bind tests to network behaviour).

Per CLAUDE.md Behavioral-Test-Only Rule, every assertion is on observable
output: ImportReport fields, recorded fake-Obsidian put_note calls, and
the actual content of put_note bodies (frontmatter shape, body
preservation).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.pf_archive_import import (
    ImportCostGuardError,
    ImportReport,
    run_import,
)


FIXTURES = Path(__file__).parent / "fixtures" / "cartosia"


# ---------------------------------------------------------------------------
# Fake Obsidian client — records every call.
# ---------------------------------------------------------------------------


class FakeObsidian:
    def __init__(self) -> None:
        self.notes: dict[str, str] = {}
        self.binaries: dict[str, tuple[bytes, str]] = {}
        self.put_note_calls: list[tuple[str, str]] = []
        self.get_note_calls: list[str] = []
        self.put_binary_calls: list[tuple[str, bytes, str]] = []

    async def get_note(self, path: str) -> str | None:
        self.get_note_calls.append(path)
        return self.notes.get(path)

    async def put_note(self, path: str, content: str) -> None:
        self.put_note_calls.append((path, content))
        self.notes[path] = content

    async def put_binary(self, path: str, data: bytes, content_type: str) -> None:
        self.put_binary_calls.append((path, data, content_type))
        self.binaries[path] = (data, content_type)


# ---------------------------------------------------------------------------
# Helpers — deterministic fake LLM
# ---------------------------------------------------------------------------


def _make_llm_response(name: str, level: int = 1, klass: str = "Commoner") -> dict:
    payload = {
        "name": name,
        "ancestry": "Human",
        "class": klass,
        "level": level,
        "mood": "neutral",
        "personality": f"{name} keeps to themselves.",
        "backstory": f"{name} grew up in the Ember District.",
        "traits": [],
    }
    return {"choices": [{"message": {"content": json.dumps(payload), "reasoning_content": ""}}]}


def _llm_dispatcher(call_log: list[dict]):
    """Return an AsyncMock side_effect that derives the response from the
    user prompt's source filename (so tests don't have to interleave order).
    """

    async def _side_effect(*args, **kwargs):
        messages = kwargs.get("messages") or []
        user = next((m for m in messages if m["role"] == "user"), {"content": ""})
        call_log.append({"messages": messages})
        text = user["content"]
        if "Fenn the Beggar" in text:
            return _make_llm_response("Fenn the Beggar", level=4, klass="Scout")
        if "Veela and Tarek" in text:
            return _make_llm_response("Veela and Tarek", level=2, klass="Rogue")
        if "Alice Twoorb" in text:
            return _make_llm_response("Alice Twoorb", level=1, klass="Trapper")
        return _make_llm_response("Unknown", level=1, klass="Commoner")

    return _side_effect


# ---------------------------------------------------------------------------
# Test 1: dry-run produces a report and writes ZERO NPC notes.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_writes_only_report_and_returns_bucket_counts():
    obs = FakeObsidian()
    with patch(
        "app.pf_npc_extract.acompletion_with_profile", new=AsyncMock(return_value=None)
    ) as mock_llm:
        report = await run_import(
            archive_root=str(FIXTURES),
            dry_run=True,
            limit=None,
            force=False,
            confirm_large=False,
            obsidian_client=obs,
        )

    assert isinstance(report, ImportReport)
    # Dry-run must not call the LLM.
    assert mock_llm.await_count == 0
    # Dry-run only writes the dry-run report itself — no NPC notes.
    npc_writes = [p for p, _ in obs.put_note_calls if p.startswith("mnemosyne/pf2e/")]
    assert npc_writes == [], f"dry-run leaked vault writes: {npc_writes}"
    # The report itself must have been written.
    report_writes = [p for p, _ in obs.put_note_calls if "ops/sweeps/cartosia-dry-run-" in p]
    assert len(report_writes) == 1, "exactly one dry-run report file expected"
    # Bucket counts must be > 0 across the fixture set.
    assert report.npc_count >= 2  # Fenn + Veela&Tarek + Alice Twoorb
    assert report.location_count >= 1
    assert report.homebrew_count >= 1
    assert report.harvest_count >= 1
    assert report.lore_count >= 1
    assert report.session_count == 1


# ---------------------------------------------------------------------------
# Test 2: live run with limit=2 processes exactly 2 NPC files.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_run_with_limit_caps_npc_writes():
    obs = FakeObsidian()
    call_log: list = []
    with patch(
        "app.pf_npc_extract.acompletion_with_profile",
        new=AsyncMock(side_effect=_llm_dispatcher(call_log)),
    ), patch(
        "app.pf_archive_import.download_token", new=AsyncMock(return_value=None)
    ):
        report = await run_import(
            archive_root=str(FIXTURES),
            dry_run=False,
            limit=2,
            force=False,
            confirm_large=True,  # bypass the >20 NPC guard for the test
            obsidian_client=obs,
        )

    npc_writes = [p for p, _ in obs.put_note_calls if p.startswith("mnemosyne/pf2e/npcs/")
                  and "/dialogue.md" not in p]
    assert len(npc_writes) == 2, f"limit=2 must cap NPC writes: {npc_writes}"
    assert report.npc_count == 2


# ---------------------------------------------------------------------------
# Test 3: idempotency — re-running over the same archive is a no-op by default.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerun_skips_existing_npcs_by_default():
    obs = FakeObsidian()
    call_log: list = []
    with patch(
        "app.pf_npc_extract.acompletion_with_profile",
        new=AsyncMock(side_effect=_llm_dispatcher(call_log)),
    ), patch(
        "app.pf_archive_import.download_token", new=AsyncMock(return_value=None)
    ):
        first = await run_import(
            archive_root=str(FIXTURES),
            dry_run=False,
            limit=None,
            force=False,
            confirm_large=True,
            obsidian_client=obs,
        )
        # Reset put_note_calls but KEEP obs.notes so existence checks see them.
        obs.put_note_calls.clear()
        second = await run_import(
            archive_root=str(FIXTURES),
            dry_run=False,
            limit=None,
            force=False,
            confirm_large=True,
            obsidian_client=obs,
        )

    # Second run must skip every previously-written NPC.
    assert second.skipped_existing >= first.npc_count
    # No NPC was overwritten.
    npc_overwrites = [
        p for p, _ in obs.put_note_calls
        if p.startswith("mnemosyne/pf2e/npcs/") and "/dialogue.md" not in p
    ]
    assert npc_overwrites == [], f"second run must not overwrite NPCs: {npc_overwrites}"


# ---------------------------------------------------------------------------
# Test 4: force=True overwrites existing NPCs.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_force_overwrites_existing_npcs():
    obs = FakeObsidian()
    # Pre-populate one NPC dest so the importer sees it as existing.
    obs.notes["mnemosyne/pf2e/npcs/fenn-the-beggar.md"] = "---\nname: stale\n---\n"

    call_log: list = []
    with patch(
        "app.pf_npc_extract.acompletion_with_profile",
        new=AsyncMock(side_effect=_llm_dispatcher(call_log)),
    ), patch(
        "app.pf_archive_import.download_token", new=AsyncMock(return_value=None)
    ):
        report = await run_import(
            archive_root=str(FIXTURES),
            dry_run=False,
            limit=None,
            force=True,
            confirm_large=True,
            obsidian_client=obs,
        )

    overwrites = [
        (p, c) for p, c in obs.put_note_calls
        if p == "mnemosyne/pf2e/npcs/fenn-the-beggar.md"
    ]
    assert len(overwrites) == 1
    _, content = overwrites[0]
    assert "stale" not in content
    assert "Fenn the Beggar" in content


# ---------------------------------------------------------------------------
# Test 5: cost guard rejects live import of >20 NPCs without confirm_large.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_guard_blocks_large_live_run_without_confirm(tmp_path):
    """Synthesise a 25-NPC archive on disk; live mode without confirm_large
    must raise ImportCostGuardError BEFORE any LLM call or vault write.
    """
    big = tmp_path / "cartosia"
    npcs_dir = big / "The NPCs"
    npcs_dir.mkdir(parents=True)
    for i in range(25):
        (npcs_dir / f"NPC {i:02d}.md").write_text(
            f"# NPC {i}\n\n**Creature 1**\n\n**AC** 14\n**HP** 10\n\n## Notes\n\n"
            f"Body text long enough to clear the 200-char skip threshold {'x' * 220}\n"
        )

    obs = FakeObsidian()
    with patch(
        "app.pf_npc_extract.acompletion_with_profile", new=AsyncMock()
    ) as mock_llm, patch(
        "app.pf_archive_import.download_token", new=AsyncMock(return_value=None)
    ):
        with pytest.raises(ImportCostGuardError):
            await run_import(
                archive_root=str(big),
                dry_run=False,
                limit=None,
                force=False,
                confirm_large=False,
                obsidian_client=obs,
            )

    assert mock_llm.await_count == 0
    assert obs.put_note_calls == []


# ---------------------------------------------------------------------------
# Test 6: two-NPC file (Veela and Tarek) → single record with combined name.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_npc_file_imports_as_single_combined_record():
    obs = FakeObsidian()
    call_log: list = []
    with patch(
        "app.pf_npc_extract.acompletion_with_profile",
        new=AsyncMock(side_effect=_llm_dispatcher(call_log)),
    ), patch(
        "app.pf_archive_import.download_token", new=AsyncMock(return_value=None)
    ):
        await run_import(
            archive_root=str(FIXTURES),
            dry_run=False,
            limit=None,
            force=False,
            confirm_large=True,
            obsidian_client=obs,
        )

    veela_writes = [
        (p, c) for p, c in obs.put_note_calls
        if p == "mnemosyne/pf2e/npcs/veela-and-tarek.md"
    ]
    assert len(veela_writes) == 1
    _, content = veela_writes[0]
    assert "Veela and Tarek" in content


# ---------------------------------------------------------------------------
# Test 7: Format B Secret block preserved in body.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_format_b_secret_block_preserved_in_body():
    obs = FakeObsidian()
    call_log: list = []
    with patch(
        "app.pf_npc_extract.acompletion_with_profile",
        new=AsyncMock(side_effect=_llm_dispatcher(call_log)),
    ), patch(
        "app.pf_archive_import.download_token", new=AsyncMock(return_value=None)
    ):
        await run_import(
            archive_root=str(FIXTURES),
            dry_run=False,
            limit=None,
            force=False,
            confirm_large=True,
            obsidian_client=obs,
        )

    alice_writes = [
        (p, c) for p, c in obs.put_note_calls
        if p == "mnemosyne/pf2e/npcs/alice-twoorb.md"
    ]
    assert len(alice_writes) == 1
    _, content = alice_writes[0]
    # Both the Secret line AND the original body markers must survive.
    assert "Secret" in content
    assert "Information that only admins can see." in content
    assert "**Age: 32**" in content
    assert "Otari" in content


# ---------------------------------------------------------------------------
# Test 8: mis-placed Adventure Hooks lands under lore/arcs/, NOT npcs/.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adventure_hooks_routes_to_lore_arcs_not_npcs():
    obs = FakeObsidian()
    call_log: list = []
    with patch(
        "app.pf_npc_extract.acompletion_with_profile",
        new=AsyncMock(side_effect=_llm_dispatcher(call_log)),
    ), patch(
        "app.pf_archive_import.download_token", new=AsyncMock(return_value=None)
    ):
        await run_import(
            archive_root=str(FIXTURES),
            dry_run=False,
            limit=None,
            force=False,
            confirm_large=True,
            obsidian_client=obs,
        )

    # Adventure Hooks landed under lore/arcs/.
    arc_writes = [p for p, _ in obs.put_note_calls if "lore/arcs/" in p]
    assert any("adventure-hooks" in p for p in arc_writes), arc_writes
    # And NOT under npcs/.
    npc_paths = [p for p, _ in obs.put_note_calls if p.startswith("mnemosyne/pf2e/npcs/")]
    assert not any("adventure-hooks" in p for p in npc_paths)


# ---------------------------------------------------------------------------
# Test 9: NPC frontmatter shape — Phase 29 contract.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_npc_frontmatter_includes_phase29_required_fields():
    obs = FakeObsidian()
    call_log: list = []
    with patch(
        "app.pf_npc_extract.acompletion_with_profile",
        new=AsyncMock(side_effect=_llm_dispatcher(call_log)),
    ), patch(
        "app.pf_archive_import.download_token", new=AsyncMock(return_value=None)
    ):
        await run_import(
            archive_root=str(FIXTURES),
            dry_run=False,
            limit=None,
            force=False,
            confirm_large=True,
            obsidian_client=obs,
        )

    fenn_writes = [
        (p, c) for p, c in obs.put_note_calls
        if p == "mnemosyne/pf2e/npcs/fenn-the-beggar.md"
    ]
    assert len(fenn_writes) == 1
    _, content = fenn_writes[0]
    assert content.startswith("---\n"), "must have YAML frontmatter"
    # Required Phase 29 fields all present.
    for field in (
        "name:",
        "ancestry:",
        "class:",
        "level:",
        "mood:",
        "personality:",
        "backstory:",
        "traits:",
        "relationships:",
        "imported_from:",
        "imported_at:",
    ):
        assert field in content, f"missing frontmatter field: {field}"
    assert "imported_from: cartosia-archive" in content
    # Original body markers preserved.
    assert "Fenn the Beggar" in content
    assert "Roleplaying Notes" in content


# ---------------------------------------------------------------------------
# Test 10: dialogue files concatenate per owner.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dialogue_files_concatenate_per_owner():
    obs = FakeObsidian()
    call_log: list = []
    with patch(
        "app.pf_npc_extract.acompletion_with_profile",
        new=AsyncMock(side_effect=_llm_dispatcher(call_log)),
    ), patch(
        "app.pf_archive_import.download_token", new=AsyncMock(return_value=None)
    ):
        await run_import(
            archive_root=str(FIXTURES),
            dry_run=False,
            limit=None,
            force=False,
            confirm_large=True,
            obsidian_client=obs,
        )

    # Ashen Gorl has dialogue at two paths in the fixture tree (root NPC dir
    # AND the deeply-nested duplicate). They must concatenate into ONE file
    # at npcs/ashen-gorl-the-singed/dialogue.md.
    gorl_dialogue_path = "mnemosyne/pf2e/npcs/ashen-gorl-the-singed/dialogue.md"
    gorl_writes = [c for p, c in obs.put_note_calls if p == gorl_dialogue_path]
    assert len(gorl_writes) >= 1
    # The final concatenated content must include both dialogue snippets.
    final = obs.notes[gorl_dialogue_path]
    assert "Party Acknowledgment" in final
    assert "Things Said" in final


# ---------------------------------------------------------------------------
# Test 11: homebrew lands at sibling, not under rulings/.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_homebrew_lands_at_sibling_of_rulings():
    obs = FakeObsidian()
    call_log: list = []
    with patch(
        "app.pf_npc_extract.acompletion_with_profile",
        new=AsyncMock(side_effect=_llm_dispatcher(call_log)),
    ), patch(
        "app.pf_archive_import.download_token", new=AsyncMock(return_value=None)
    ):
        await run_import(
            archive_root=str(FIXTURES),
            dry_run=False,
            limit=None,
            force=False,
            confirm_large=True,
            obsidian_client=obs,
        )

    homebrew_paths = [p for p, _ in obs.put_note_calls if "/homebrew/" in p]
    assert any("movement-rules" in p for p in homebrew_paths), homebrew_paths
    # CRITICAL: NOT under rulings/
    rulings_homebrew = [p for p, _ in obs.put_note_calls if "rulings/homebrew" in p]
    assert rulings_homebrew == [], (
        "homebrew must be sibling of rulings/, not a sub-topic — "
        "would surface a phantom 'homebrew' topic in :pf rule list"
    )
