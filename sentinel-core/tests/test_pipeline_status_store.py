"""RED scaffold for ``app.services.pipeline_status_store`` (Phase 46, D-03a).

Wave 0 (Plan 46-01) pins the intended status-store API surface ahead of
Wave 3 landing the module. Function-scope import keeps pytest collection
green while ``app.services.pipeline_status_store`` does not exist yet --
this test FAILS at runtime (ModuleNotFoundError during the test body) until
Wave 3 lands it.

Mirrors ``tests/test_sweep_status_store.py`` exactly (PATTERNS.md
"pipeline_status_store.py" section -- a near-verbatim copy of
``sweep_status_store.py`` with `mode` + per-phase counts substituted for
the sweep fields, in its own independent in-memory dict -- YAGNI against
unifying the two stores).
"""
from __future__ import annotations


class _Report:
    """Minimal PipelineReport-shaped stand-in (D-03a field set)."""

    pipeline_id = "id-1"
    status = "running"
    mode = "pipeline"
    entries_total = 5
    entries_processed = 2
    reduced = 2
    hubs_touched = 1
    reweave_edits = 0
    verify_failed = 0
    verify_requeued = 0
    discarded_not_durable = 0
    absorbed_standalone = 0
    errors: list = []


class _ReportWithoutNewCounters:
    """PipelineReport-shaped stand-in that PREDATES ``discarded_not_durable``
    and ``absorbed_standalone`` -- must not raise (duck-typed, ``getattr``
    with default)."""

    pipeline_id = "id-2"
    status = "running"
    mode = "pipeline"
    entries_total = 5
    entries_processed = 2
    reduced = 2
    hubs_touched = 1
    reweave_edits = 0
    verify_failed = 0
    verify_requeued = 0
    errors: list = []


async def test_status_store_round_trips_pipeline_report():
    """set_pipeline_status_from_report -> get_pipeline_status round-trips
    mode + the per-phase counts (D-03a); reset returns to idle."""
    from app.services.pipeline_status_store import (
        get_pipeline_status,
        reset_pipeline_status,
        set_pipeline_status_from_report,
    )

    reset_pipeline_status()
    set_pipeline_status_from_report(_Report())

    current = get_pipeline_status()
    assert current["mode"] == "pipeline"
    assert current["status"] == "running"
    assert current["entries_processed"] == 2
    assert current["reduced"] == 2
    assert current["hubs_touched"] == 1

    reset_pipeline_status()
    reset = get_pipeline_status()
    assert reset["status"] == "idle"
    assert reset.get("pipeline_id") is None


async def test_status_store_surfaces_discarded_and_absorbed_counters():
    """2026-08-29 production incident: ``discarded_not_durable`` and
    ``absorbed_standalone`` exist on ``PipelineReport`` but were dropped at
    the status-store boundary, making 5 of 7 processed entries invisible
    through the status API. Both counters must round-trip."""
    from app.services.pipeline_status_store import (
        get_pipeline_status,
        reset_pipeline_status,
        set_pipeline_status_from_report,
    )

    class _ReportWithDiscards(_Report):
        discarded_not_durable = 3
        absorbed_standalone = 2

    reset_pipeline_status()
    set_pipeline_status_from_report(_ReportWithDiscards())

    current = get_pipeline_status()
    assert current["discarded_not_durable"] == 3
    assert current["absorbed_standalone"] == 2

    reset_pipeline_status()


async def test_status_store_report_missing_new_counters_does_not_raise():
    """Duck-typed read (module docstring): a report predating the new
    counters must not raise, and must surface a 0 default."""
    from app.services.pipeline_status_store import (
        get_pipeline_status,
        reset_pipeline_status,
        set_pipeline_status_from_report,
    )

    reset_pipeline_status()
    set_pipeline_status_from_report(_ReportWithoutNewCounters())

    current = get_pipeline_status()
    assert current["discarded_not_durable"] == 0
    assert current["absorbed_standalone"] == 0

    reset_pipeline_status()
