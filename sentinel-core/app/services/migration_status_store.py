"""Operational migration status store (Phase 47 migration cutover, MIG-01/MIG-02).

Near-verbatim clone of ``pipeline_status_store.py`` with the migration
report field set substituted for the pipeline's per-phase counts. Kept as
a fully separate in-memory dict from the pipeline/sweep stores — mutual
exclusion across sweeper/pipeline/migration is handled by the shared
``vault.acquire_sweep_lock()`` (D-04 precedent); this store only handles
progress reporting for ``GET /vault/migrate/status``, an orthogonal
concern (YAGNI: not unified with the other two status stores).
"""

from __future__ import annotations

_MIGRATION_STATUS: dict[str, object] = {
    "migration_id": None,
    "status": "idle",
    "mode": None,
    "dry_run": False,
    "planned_moves": [],
    "ops_moved": [],
    "notes_backfilled": 0,
    "verify_failed": 0,
    "new_orphans": 0,
    "rolled_back": False,
    "errors": [],
}


def get_status() -> dict:
    return dict(_MIGRATION_STATUS)


def set_status(report) -> None:
    """Read ``MigrationReport`` fields off ``report`` duck-typed — no
    ``migration_orchestrator`` import (mirrors
    ``pipeline_status_store.set_pipeline_status_from_report``)."""
    _MIGRATION_STATUS.update(
        migration_id=report.migration_id,
        status=report.status,
        dry_run=report.dry_run,
        planned_moves=list(report.planned_moves),
        ops_moved=list(report.ops_moved),
        notes_backfilled=report.notes_backfilled,
        verify_failed=report.verify_failed,
        new_orphans=report.new_orphans,
        rolled_back=report.rolled_back,
        errors=list(report.errors),
    )


def patch_status(**kwargs) -> None:
    """Update individual fields in the live status store."""
    _MIGRATION_STATUS.update(kwargs)


def reset_status() -> None:
    _MIGRATION_STATUS.update(
        migration_id=None,
        status="idle",
        mode=None,
        dry_run=False,
        planned_moves=[],
        ops_moved=[],
        notes_backfilled=0,
        verify_failed=0,
        new_orphans=0,
        rolled_back=False,
        errors=[],
    )


def new_status(migration_id: str, status: str, mode: str) -> dict:
    """Initial status dict for a freshly-started migration run.

    Called by ``start_migration`` to seed the store before the background
    task produces its first ``MigrationReport`` (mirrors
    ``pipeline_status_store._new_status``).
    """
    return {
        "migration_id": migration_id,
        "status": status,
        "mode": mode,
        "dry_run": mode == "dry_run",
        "planned_moves": [],
        "ops_moved": [],
        "notes_backfilled": 0,
        "verify_failed": 0,
        "new_orphans": 0,
        "rolled_back": False,
        "errors": [],
    }
