"""RED scaffold for ``app.services.pipeline_orchestrator`` (Phase 46, PIPE-02/03/06).

Wave 0 (Plan 46-01) pins the intended orchestrator API surface ahead of
Wave 3 landing the module. Function-scope imports keep pytest collection
green while ``app.services.pipeline_orchestrator`` does not exist yet
(STATE Phase 33-01 / 45-01 precedent) -- these tests FAIL at runtime
(ModuleNotFoundError during the test body) until Wave 3 lands ``run``.

Intended contract (RESEARCH.md Architecture Patterns / PATTERNS.md
"pipeline_orchestrator.py" section, cloning ``vault_sweeper.run_sweep``):

    async def run(
        vault, *, mode: str, status_callback: Callable[[PipelineReport], None] | None = None,
    ) -> PipelineReport

``mode`` in {"ralph", "pipeline", "reweave", "rethink"}. ``PipelineReport``
carries explicit per-phase counts (D-03a): ``entries_total``,
``entries_processed``, ``reduced``, ``hubs_touched``, ``reweave_edits``,
``verify_failed``, ``verify_requeued``, plus ``status`` and ``mode``.

Concurrency (D-04/Pitfall 8): the shared sweep lock (``vault.acquire_sweep_lock``)
is acquired BEFORE any inbox read -- a lock already held by a concurrent
sweep or pipeline run must raise ``SweepInProgressError`` with zero inbox
reads, mirroring ``run_sweep()``'s lock-before-walk ordering exactly.
"""
from __future__ import annotations


class _ImmediateTaskRunner:
    """Synchronous task runner -- records coroutines, caller awaits run_all().

    Mirrors tests/test_note_sweep_runner.py's fixture exactly (PATTERNS.md
    Testing pattern) so Wave 3's ``start_pipeline`` background-task wrapper
    can reuse this same shape once it lands.
    """

    def __init__(self):
        self._scheduled: list = []

    def schedule(self, coro):
        self._scheduled.append(coro)

    async def run_all(self):
        for coro in self._scheduled:
            await coro
        self._scheduled.clear()


def _make_vault(*, retry_count: int = 0):
    """FakeVault pre-populated with one pending inbox entry (Reduce input).

    ``retry_count`` lets Verify-failure tests seed an entry that is already
    partway (or fully) through the bounded requeue cap (PIPE-07) without
    inventing a second fixture-building helper.
    """
    from app.services.inbox import append_entry
    from app.services.note_classifier import ClassificationResult
    from tests.fakes.vault import FakeVault

    vault = FakeVault()
    vault.dirs[""] = []
    result = ClassificationResult(
        topic="reference", confidence=0.8, title_slug="cosine-floor-note", reasoning="r"
    )
    body = append_entry(
        "", "raw captured text about the cosine floor", result, retry_count=retry_count
    )
    from app.services.inbox import INBOX_PATH

    vault.notes[INBOX_PATH] = body
    return vault


async def test_ralph_mode_reduce_and_reflect():
    """mode="ralph" runs Reduce + Reflect per inbox entry (PIPE-02).

    Asserts a notes/{slug}.md was written for the inbox entry and the
    reflect/hub path was invoked; the returned report shows `reduced` and
    `hubs_touched` counts.
    """
    from unittest.mock import AsyncMock, patch

    from app.services import pipeline_orchestrator
    from app.services.six_rs.reduce import ReduceResult

    fake_reduce_result = ReduceResult(
        claim_title="Cosine Floor Governs Hub Attachment",
        body="The hub-lookup floor is reused verbatim from RecallConfig.\n\n[[Recall Hub]]",
        schema_type="permanent",
    )

    vault = _make_vault()

    with (
        patch(
            "app.services.pipeline_orchestrator.reduce_entry",
            new=AsyncMock(return_value=fake_reduce_result),
        ),
        patch(
            "app.services.pipeline_orchestrator.find_and_attach_hub",
            new=AsyncMock(return_value="notes/recall-hub.md"),
        ),
    ):
        report = await pipeline_orchestrator.run(vault, mode="ralph")

    assert report.mode == "ralph"
    assert report.reduced >= 1
    assert report.hubs_touched >= 1
    written_note_paths = [p for p in vault.notes if p.startswith("notes/") and p != "notes/recall-hub.md"]
    assert written_note_paths, "expected a notes/{slug}.md write for the reduced entry"


async def test_pipeline_mode_full_sequence():
    """mode="pipeline" exercises Reduce, Verify, Reflect, Reweave, and a
    single end-of-run Rethink, with per-phase counts populated (PIPE-03)."""
    from unittest.mock import AsyncMock, patch

    from app.services import pipeline_orchestrator
    from app.services.six_rs.reduce import ReduceResult

    fake_reduce_result = ReduceResult(
        claim_title="Cosine Floor Governs Hub Attachment",
        body="The hub-lookup floor is reused verbatim from RecallConfig.\n\n[[Recall Hub]]",
        schema_type="permanent",
    )

    vault = _make_vault()

    with (
        patch(
            "app.services.pipeline_orchestrator.reduce_entry",
            new=AsyncMock(return_value=fake_reduce_result),
        ),
        patch(
            "app.services.pipeline_orchestrator.find_and_attach_hub",
            new=AsyncMock(return_value="notes/recall-hub.md"),
        ),
        patch(
            "app.services.pipeline_orchestrator.reweave_note",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.pipeline_orchestrator.verify_note",
            new=AsyncMock(return_value={"passed": True, "requeued": False, "retry_count": 0}),
        ),
        patch(
            "app.services.pipeline_orchestrator.triage_observations",
            new=AsyncMock(return_value=[{"path": "ops/observations/x.md", "disposition": "KEEP"}]),
        ) as rethink_mock,
    ):
        report = await pipeline_orchestrator.run(vault, mode="pipeline")

    assert report.mode == "pipeline"
    assert report.reduced >= 1
    assert report.hubs_touched >= 1
    assert report.verify_failed == 0
    # Rethink runs once per full-pipeline run (end-of-run), never per entry.
    rethink_mock.assert_awaited_once()


async def test_pipeline_mode_verify_failure_below_cap_requeues_with_incremented_retry():
    """Verify-failure with ``retry_count`` below ``VERIFY_RETRY_CAP`` deletes the
    draft note and requeues the entry to inbox/ with ``retry_count`` incremented
    by one (PIPE-07); ``verify_failed``/``verify_requeued`` both move.

    Mirrors ``test_pipeline_mode_full_sequence``'s mocking style but makes
    ``verify_note`` return a failing/below-cap outcome instead of the
    happy-path ``passed=True`` used there.
    """
    from unittest.mock import AsyncMock, patch

    from app.services import pipeline_orchestrator
    from app.services.inbox import INBOX_PATH, parse_inbox
    from app.services.six_rs.reduce import ReduceResult
    from app.services.six_rs.verify import VERIFY_RETRY_CAP

    fake_reduce_result = ReduceResult(
        claim_title="Cosine Floor Governs Hub Attachment",
        body="The hub-lookup floor is reused verbatim from RecallConfig.\n\n[[Recall Hub]]",
        schema_type="permanent",
    )

    below_cap_retry_count = VERIFY_RETRY_CAP - 1
    vault = _make_vault(retry_count=below_cap_retry_count)

    failing_outcome = {
        "passed": False,
        "requeued": True,
        "retry_count": below_cap_retry_count + 1,
        "needs_attention": False,
        "compliance": {"failures": ["missing wikilink"]},
    }

    with (
        patch(
            "app.services.pipeline_orchestrator.reduce_entry",
            new=AsyncMock(return_value=fake_reduce_result),
        ),
        patch(
            "app.services.pipeline_orchestrator.verify_note",
            new=AsyncMock(return_value=failing_outcome),
        ),
        patch(
            "app.services.pipeline_orchestrator.find_and_attach_hub",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.pipeline_orchestrator.triage_observations",
            new=AsyncMock(return_value=[]),
        ),
    ):
        report = await pipeline_orchestrator.run(vault, mode="pipeline")

    assert report.verify_failed == 1
    assert report.verify_requeued == 1

    # D-02: a failing note never stays in notes/.
    written_note_paths = [p for p in vault.notes if p.startswith("notes/")]
    assert not written_note_paths, "a Verify-failed note must be deleted from notes/"

    entries = parse_inbox(vault.notes[INBOX_PATH])
    assert len(entries) == 1, "the failed entry must be requeued, not dropped"
    requeued_entry = entries[0]
    assert requeued_entry.retry_count == below_cap_retry_count + 1
    assert requeued_entry.needs_attention is False


async def test_pipeline_mode_verify_failure_at_cap_flags_needs_attention():
    """Verify-failure once ``retry_count`` has reached ``VERIFY_RETRY_CAP`` is
    NOT requeued again -- the orchestrator stops incrementing and flags the
    entry ``needs_attention`` instead (PIPE-07 bounded-retry discipline).
    """
    from unittest.mock import AsyncMock, patch

    from app.services import pipeline_orchestrator
    from app.services.inbox import INBOX_PATH, parse_inbox
    from app.services.six_rs.reduce import ReduceResult
    from app.services.six_rs.verify import VERIFY_RETRY_CAP

    fake_reduce_result = ReduceResult(
        claim_title="Cosine Floor Governs Hub Attachment",
        body="The hub-lookup floor is reused verbatim from RecallConfig.\n\n[[Recall Hub]]",
        schema_type="permanent",
    )

    vault = _make_vault(retry_count=VERIFY_RETRY_CAP)

    failing_outcome_at_cap = {
        "passed": False,
        "requeued": False,
        "retry_count": VERIFY_RETRY_CAP,
        "needs_attention": True,
        "compliance": {"failures": ["missing wikilink"]},
    }

    with (
        patch(
            "app.services.pipeline_orchestrator.reduce_entry",
            new=AsyncMock(return_value=fake_reduce_result),
        ),
        patch(
            "app.services.pipeline_orchestrator.verify_note",
            new=AsyncMock(return_value=failing_outcome_at_cap),
        ),
        patch(
            "app.services.pipeline_orchestrator.find_and_attach_hub",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.pipeline_orchestrator.triage_observations",
            new=AsyncMock(return_value=[]),
        ),
    ):
        report = await pipeline_orchestrator.run(vault, mode="pipeline")

    assert report.verify_failed == 1
    # requeued is False at the cap -- verify_requeued must NOT move.
    assert report.verify_requeued == 0

    written_note_paths = [p for p in vault.notes if p.startswith("notes/")]
    assert not written_note_paths, "a Verify-failed note must be deleted from notes/"

    entries = parse_inbox(vault.notes[INBOX_PATH])
    assert len(entries) == 1, "an at-cap entry stays in inbox/ (never silently dropped)"
    flagged_entry = entries[0]
    assert flagged_entry.retry_count == VERIFY_RETRY_CAP
    assert flagged_entry.needs_attention is True


async def test_concurrent_pipeline_and_sweep_refused():
    """Pitfall 8: lock acquisition strictly precedes any inbox read.

    Pre-acquiring the shared sweep lock on the vault must make a concurrent
    pipeline run raise SweepInProgressError BEFORE any `parse_inbox`/inbox
    read occurs (PIPE-06, D-04).
    """
    from app.errors import SweepInProgressError
    from app.services import pipeline_orchestrator
    from app.services.inbox import INBOX_PATH

    vault = _make_vault()
    await vault.acquire_sweep_lock()

    read_paths: list[str] = []
    original_read_note = vault.read_note

    async def _spying_read_note(path: str) -> str:
        read_paths.append(path)
        return await original_read_note(path)

    vault.read_note = _spying_read_note  # type: ignore[assignment]

    raised = False
    try:
        await pipeline_orchestrator.run(vault, mode="ralph")
    except SweepInProgressError:
        raised = True

    assert raised, "a concurrent run must raise SweepInProgressError"
    assert INBOX_PATH not in read_paths, (
        "lock acquisition must strictly precede any inbox read -- "
        f"but read_note was called with: {read_paths}"
    )
