"""RED integration tests for ``app.services.migration_orchestrator`` (Phase
47, Plan 01 Wave 0, MIG-01/MIG-02).

Mirrors ``tests/test_pipeline_orchestrator.py`` + ``tests/test_vault_sweeper.
py``'s async fixture / fake-vault style, and their discipline of asserting
the FULL post-condition (e.g. "file exists under notes/{slug}.md AND the
flat-7 original is gone" -- RESEARCH.md's explicit Pitfall A warning sign)
rather than a shallow "did not raise" check.

Fails RED today with a ``ModuleNotFoundError`` -- ``app.services.migration_
orchestrator`` does not exist yet (Waves 2-4 land it). This is the intended
Wave 0 state.

Never mocks the real compliance/verification gate (``verify_note``/
``check_note_compliance``) to force a pass -- see [[phase46-pipeline-
coldstart-gap]]: mocking the gate is exactly the anti-pattern that shipped a
pipeline filing zero notes in production. Only the LLM/embedding boundary
(``reduce_entry``, ``propose_hub_slug``) is mocked, matching
``test_pipeline_orchestrator.py``'s own precedent.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from tests.fakes.vault import FakeVault


def _seed_flat7_vault() -> FakeVault:
    """FakeVault pre-populated with flat-7 content across all four legacy
    directories (D-01's two-track split: notes-bound learning/references,
    ops-bound journal/accomplishments)."""
    vault = FakeVault(
        notes={
            "learning/finished-course.md": (
                "---\ntopic: learning\n---\n\n"
                "# Finished Course\n\nCompleted the advanced Python course.\n"
            ),
            "references/pi-constant.md": (
                "---\ntopic: reference\n---\n\n"
                "# Pi Constant\n\nPi is approximately 3.14159.\n"
            ),
            "journal/2026-01-01-entry.md": (
                "---\ntopic: journal\n---\n\n"
                "# Journal Entry\n\nToday I worked on Phase 47.\n"
            ),
            "accomplishments/shipped-phase-46.md": (
                "---\ntopic: accomplishment\n---\n\n"
                "# Shipped Phase 46\n\nThe 6 Rs pipeline landed.\n"
            ),
        }
    )
    vault.dirs[""] = ["learning/", "references/", "journal/", "accomplishments/"]
    vault.dirs["learning"] = ["finished-course.md"]
    vault.dirs["references"] = ["pi-constant.md"]
    vault.dirs["journal"] = ["2026-01-01-entry.md"]
    vault.dirs["accomplishments"] = ["shipped-phase-46.md"]
    return vault


async def test_full_backfill_no_grandfathering():
    """MIG-01: every flat-7 original is gone; ops-bound files land under
    ops/{journal|accomplishments}/, notes-bound files land under
    notes/{claim-slug}.md carrying a _schema block and >=1 wikilink.

    Pitfall A warning sign: this asserts notes/{slug} existence, never
    inbox/{name} existence -- a bare relocate() into inbox/ would be
    invisible to the reused 6 Rs orchestrator and silently defeat MIG-01.
    """
    from app.services import migration_orchestrator
    from app.services.six_rs.reduce import ReduceResult

    fake_learning_result = ReduceResult(
        claim_title="Advanced Python Course Improves Async Fluency",
        body=(
            "Completing the advanced Python course improved async fluency.\n\n"
            "[[Python Fluency]]"
        ),
        schema_type="permanent",
    )
    fake_reference_result = ReduceResult(
        claim_title="Pi Approximates 3.14159",
        body="Pi is approximately 3.14159 to five decimal places.\n\n[[Pi Constant]]",
        schema_type="permanent",
    )

    vault = _seed_flat7_vault()

    with (
        patch(
            "app.services.pipeline_orchestrator.reduce_entry",
            new=AsyncMock(side_effect=[fake_learning_result, fake_reference_result]),
        ),
        patch(
            "app.services.six_rs.reflect.propose_hub_slug",
            new=AsyncMock(return_value="backfilled-concepts"),
        ),
    ):
        report = await migration_orchestrator.run(vault, dry_run=False)

    for path in (
        "learning/finished-course.md",
        "references/pi-constant.md",
        "journal/2026-01-01-entry.md",
        "accomplishments/shipped-phase-46.md",
    ):
        assert path not in vault.notes, f"flat-7 original {path} must be gone post-migration"

    journal_paths = [p for p in vault.notes if p.startswith("ops/journal/")]
    assert journal_paths, "expected the journal entry under ops/journal/{YYYY-MM-DD}/"
    accomplishment_paths = [p for p in vault.notes if p.startswith("ops/accomplishments/")]
    assert accomplishment_paths, "expected the accomplishment file under ops/accomplishments/"

    inbox_named_paths = [
        p
        for p in vault.notes
        if p.startswith("inbox/") and p != "inbox/_pending-classification.md"
    ]
    assert not inbox_named_paths, (
        "no legacy filename should survive under inbox/ -- Pitfall A: a bare "
        "relocate() into inbox/ is invisible to the reused pipeline orchestrator"
    )

    notes_paths = [p for p in vault.notes if p.startswith("notes/")]
    assert len(notes_paths) >= 2, "expected a notes/{slug}.md for each notes-bound legacy file"
    for path in notes_paths:
        body = vault.notes[path]
        assert "```_schema" in body, f"{path} missing a _schema block"
        assert "[[" in body, f"{path} missing a wikilink"

    assert report.status == "complete"


async def test_embedding_and_wikilink_preservation():
    """MIG-02: an ops-bound relocate preserves the note's own embedding
    frontmatter (untouched, no re-embed) AND the embedding sidecar's key is
    renamed old-path -> new-path with the embedding VALUE unchanged; a
    pre-existing [[old-title]] reference to the moved note still resolves
    (title unchanged, verify-then-trust, D-03)."""
    from app.services import migration_orchestrator
    from app.services.embedding_sidecar_index import EMBEDDING_INDEX_PATH

    src = "journal/2026-02-02-entry.md"
    embedding_b64 = "deadbeef=="
    vault = FakeVault(
        notes={
            src: (
                "---\n"
                "topic: journal\n"
                f"embedding_b64: {embedding_b64}\n"
                "embedding_model: nomic-embed-text-v1.5\n"
                "---\n\n"
                "# Journal Entry\n\nA day worth remembering.\n"
            ),
            "notes/hub.md": "# Hub\n\n[[Journal Entry]]\n",
            EMBEDDING_INDEX_PATH: json.dumps(
                {src: {"embedding_b64": embedding_b64, "embedding_model": "nomic-embed-text-v1.5"}}
            ),
        }
    )
    vault.dirs[""] = ["journal/"]
    vault.dirs["journal"] = ["2026-02-02-entry.md"]

    report = await migration_orchestrator.run(vault, dry_run=False)

    moved_paths = [p for p in vault.notes if p.startswith("ops/journal/")]
    assert len(moved_paths) == 1, "expected exactly one relocated journal entry"
    new_path = moved_paths[0]

    # Note's own embedding frontmatter travels unchanged -- no re-embed.
    assert embedding_b64 in vault.notes[new_path]

    # Sidecar key renamed, value unchanged (Pattern 2).
    index = json.loads(vault.notes[EMBEDDING_INDEX_PATH])
    assert src not in index, "stale sidecar key must not survive migration"
    assert index[new_path]["embedding_b64"] == embedding_b64

    # Pre-existing [[Journal Entry]] wikilink still resolves -- title unchanged.
    assert "[[Journal Entry]]" in vault.notes["notes/hub.md"]

    assert report.status == "complete"


async def test_dry_run_writes_nothing():
    """D-02: ``dry_run=True`` performs zero vault mutations; the returned
    report enumerates the planned moves for operator preview."""
    from app.services import migration_orchestrator

    vault = _seed_flat7_vault()
    pre_snapshot = dict(vault.notes)

    report = await migration_orchestrator.run(vault, dry_run=True)

    assert vault.notes == pre_snapshot, "dry_run must perform zero writes/deletes/relocates"
    assert report.planned_moves, "dry-run report must enumerate the planned moves"


async def test_hard_failure_triggers_atomic_rollback():
    """D-02/D-02a: a hard failure mid-run (relocate raises on the Nth call)
    triggers atomic rollback -- the vault is restored byte-identical to its
    pre-run snapshot and ``report.rolled_back`` is True."""
    from app.services import migration_orchestrator

    vault = _seed_flat7_vault()
    pre_snapshot = dict(vault.notes)

    original_relocate = vault.relocate
    call_count = {"n": 0}

    async def _flaky_relocate(src, dst, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated hard failure mid-run")
        return await original_relocate(src, dst, **kwargs)

    vault.relocate = _flaky_relocate  # type: ignore[assignment]

    report = await migration_orchestrator.run(vault, dry_run=False)

    assert report.rolled_back is True
    assert vault.notes == pre_snapshot, "vault must be restored byte-identical after rollback"


async def test_verify_failed_entry_does_not_rollback():
    """Open Question 1 RESOLVED: a non-empty ``report.verify_failed`` from
    the reused pipeline run (a dead-lettered entry, no hard exception) does
    NOT trigger rollback -- already-successful ops-bound moves are RETAINED
    and ``report.rolled_back`` is False. Drives a genuine dead-letter
    outcome (a Reduce result carrying no wikilink, so the REAL Verify gate
    fails it) -- never mocks ``verify_note``/``check_note_compliance`` to
    force the outcome."""
    from app.services import migration_orchestrator
    from app.services.six_rs.reduce import ReduceResult

    fake_reduce_result = ReduceResult(
        claim_title="A Claim With No Wikilink",
        body="This note deliberately carries no wikilink, so real Verify fails it.",
        schema_type="permanent",
    )

    vault = _seed_flat7_vault()

    with patch(
        "app.services.pipeline_orchestrator.reduce_entry",
        new=AsyncMock(return_value=fake_reduce_result),
    ):
        report = await migration_orchestrator.run(vault, dry_run=False)

    journal_paths = [p for p in vault.notes if p.startswith("ops/journal/")]
    assert journal_paths, "ops-bound moves must be retained despite the notes-bound dead-letter"

    assert report.verify_failed >= 1
    assert report.rolled_back is False
