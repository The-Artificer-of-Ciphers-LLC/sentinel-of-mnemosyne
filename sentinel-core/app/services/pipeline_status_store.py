"""Operational pipeline status store (6 Rs pipeline, D-03a / D-04).

Near-verbatim clone of ``sweep_status_store.py`` with the sweep field set
substituted for the ``PipelineReport`` per-phase counts. Kept as a fully
separate in-memory dict from the sweep store -- the sweep lockfile handles
mutual-exclusion (D-04), this store handles progress reporting; the two
concerns are orthogonal and intentionally NOT unified (YAGNI).
"""

from __future__ import annotations

_PIPELINE_STATUS: dict[str, object] = {
    "pipeline_id": None,
    "status": "idle",
    "mode": None,
    "entries_total": 0,
    "entries_processed": 0,
    "reduced": 0,
    "hubs_touched": 0,
    "reweave_edits": 0,
    "verify_failed": 0,
    "verify_requeued": 0,
    "errors": [],
}


def get_pipeline_status() -> dict:
    return dict(_PIPELINE_STATUS)


def set_pipeline_status_from_report(report) -> None:
    """Read D-03a fields off ``report`` duck-typed -- no PipelineReport import."""
    _PIPELINE_STATUS.update(
        pipeline_id=report.pipeline_id,
        status=report.status,
        mode=report.mode,
        entries_total=report.entries_total,
        entries_processed=report.entries_processed,
        reduced=report.reduced,
        hubs_touched=report.hubs_touched,
        reweave_edits=report.reweave_edits,
        verify_failed=report.verify_failed,
        verify_requeued=report.verify_requeued,
        errors=list(report.errors),
    )


def patch_pipeline_status(**kwargs) -> None:
    """Update individual fields in the live status store."""
    _PIPELINE_STATUS.update(kwargs)


def reset_pipeline_status() -> None:
    _PIPELINE_STATUS.update(
        pipeline_id=None,
        status="idle",
        mode=None,
        entries_total=0,
        entries_processed=0,
        reduced=0,
        hubs_touched=0,
        reweave_edits=0,
        verify_failed=0,
        verify_requeued=0,
        errors=[],
    )


def _new_status(pipeline_id: str, status: str, mode: str) -> dict:
    """Initial 'running' status dict for a freshly-started pipeline run.

    Called by the Wave-3 runner (mirrors vault_sweeper's analogous factory)
    to seed the store before the background task produces its first
    ``PipelineReport``.
    """
    return {
        "pipeline_id": pipeline_id,
        "status": status,
        "mode": mode,
        "entries_total": 0,
        "entries_processed": 0,
        "reduced": 0,
        "hubs_touched": 0,
        "reweave_edits": 0,
        "verify_failed": 0,
        "verify_requeued": 0,
        "errors": [],
    }
