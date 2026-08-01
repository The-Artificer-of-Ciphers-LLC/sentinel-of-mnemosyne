from app.services.sweep_status_store import (
    get_sweep_status,
    patch_sweep_status,
    reset_sweep_status,
    set_sweep_status_from_report,
)


class _Report:
    sweep_id = "id-1"
    status = "running"
    files_processed = 1
    files_total = 5
    duplicates_moved = 2
    noise_moved = 3


class _ReportNoReportPath:
    """Mirrors note_sweep_runner._new_status — has topic_moves but NO
    report_path attribute at all (the shape used for the live-sweep
    start-of-run status object)."""

    sweep_id = "id-2"
    status = "running"
    files_processed = 0
    files_total = 0
    duplicates_moved = 0
    noise_moved = 0
    topic_moves = 0


def test_sweep_status_store_set_get_reset():
    reset_sweep_status()
    set_sweep_status_from_report(_Report())

    current = get_sweep_status()
    assert current["sweep_id"] == "id-1"
    assert current["status"] == "running"
    assert current["files_processed"] == 1

    reset_sweep_status()
    reset = get_sweep_status()
    assert reset["status"] == "idle"
    assert reset["sweep_id"] is None
    assert reset["topic_moves"] == 0
    assert reset["report_path"] is None


def test_new_sweep_status_does_not_retain_previous_run_topic_moves_and_report_path():
    """Regression for fix-score-local-model-capabilities Task 3: a previous
    dry-run's ``topic_moves``/``report_path`` must NOT leak into a later
    (live) sweep's status — a zero-move live sweep must never look like it
    moved N files from a stale prior dry-run.
    """
    reset_sweep_status()

    # Simulate a completed dry-run that populated topic_moves + report_path
    # via patch_sweep_status, exactly as note_sweep_runner._dry_runner does.
    patch_sweep_status(
        status="dry-run-complete",
        report_path="ops/sweeps/dry-run-2026-08-01T18-11-40Z.md",
        topic_moves=22,
        noise_moved=4,
        duplicates_moved=1,
        files_processed=26,
        files_total=26,
    )
    stale = get_sweep_status()
    assert stale["topic_moves"] == 22
    assert stale["report_path"] == "ops/sweeps/dry-run-2026-08-01T18-11-40Z.md"

    # A NEW sweep starts — note_sweep_runner._set_status(_new_status(...)) is
    # the very first call for any new sweep, live or dry-run.
    set_sweep_status_from_report(_ReportNoReportPath())

    fresh = get_sweep_status()
    assert fresh["sweep_id"] == "id-2"
    assert fresh["topic_moves"] == 0, "stale topic_moves from the previous run must not leak"
    assert fresh["report_path"] is None, "stale report_path from the previous run must not leak"

    # And the live sweep's own final report (no report_path attribute, real
    # topic_moves=0 since nothing was actually moved) must also not resurrect
    # the stale values.
    set_sweep_status_from_report(_Report())
    final = get_sweep_status()
    assert final["report_path"] is None
    assert final["topic_moves"] == 0
