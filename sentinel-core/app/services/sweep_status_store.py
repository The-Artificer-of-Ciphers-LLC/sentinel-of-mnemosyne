"""Operational sweep status store."""

from __future__ import annotations

_SWEEP_STATUS: dict[str, object] = {
    "sweep_id": None,
    "status": "idle",
    "files_processed": 0,
    "files_total": 0,
    "duplicates_moved": 0,
    "noise_moved": 0,
}


def get_sweep_status() -> dict:
    return dict(_SWEEP_STATUS)


def set_sweep_status_from_report(report) -> None:
    _SWEEP_STATUS.update(
        sweep_id=report.sweep_id,
        status=report.status,
        files_processed=report.files_processed,
        files_total=report.files_total,
        duplicates_moved=report.duplicates_moved,
        noise_moved=report.noise_moved,
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
    )
