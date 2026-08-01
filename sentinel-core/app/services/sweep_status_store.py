"""Operational sweep status store."""

from __future__ import annotations

_SWEEP_STATUS: dict[str, object] = {
    "sweep_id": None,
    "status": "idle",
    "files_processed": 0,
    "files_total": 0,
    "duplicates_moved": 0,
    "noise_moved": 0,
    "topic_moves": 0,
    "report_path": None,
}


def get_sweep_status() -> dict:
    return dict(_SWEEP_STATUS)


def set_sweep_status_from_report(report) -> None:
    """Overwrite the live status store from a fresh ``report``/status object.

    ``topic_moves`` and ``report_path`` are ALWAYS included here (not just
    the original 6 fields) so that every call to this function — including
    the start-of-sweep placeholder status object built in
    ``note_sweep_runner._new_status`` (which has no ``report_path``
    attribute) — resets them. Without this, a PREVIOUS run's dry-run
    ``report_path``/``topic_moves`` values leaked into a later live sweep's
    status (a zero-move live sweep looked like it moved N files from the
    prior dry-run). ``getattr(..., default)`` handles status objects (like
    ``_new_status``) that don't define these attributes at all.
    """
    _SWEEP_STATUS.update(
        sweep_id=report.sweep_id,
        status=report.status,
        files_processed=report.files_processed,
        files_total=report.files_total,
        duplicates_moved=report.duplicates_moved,
        noise_moved=report.noise_moved,
        topic_moves=getattr(report, "topic_moves", 0),
        report_path=getattr(report, "report_path", None),
    )


def patch_sweep_status(**kwargs) -> None:
    """Update individual fields in the live status store."""
    _SWEEP_STATUS.update(kwargs)


def reset_sweep_status() -> None:
    _SWEEP_STATUS.update(
        sweep_id=None,
        status="idle",
        files_processed=0,
        files_total=0,
        duplicates_moved=0,
        noise_moved=0,
        topic_moves=0,
        report_path=None,
    )
