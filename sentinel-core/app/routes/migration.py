"""Routes for the flat-7 -> ops//notes/ migration cutover (Phase 47,
MIG-01/MIG-02, T-47-01).

Endpoints:
  POST /vault/migrate/start  — admin-gated; spawns a migration task and
                                returns migration_id + status
  GET  /vault/migrate/status — current migration progress

Mirrors ``routes/note.py``'s sweep routes (``/vault/sweep/start``,
``/vault/sweep/status``, lines 119-196) verbatim: the SAME
``_is_admin_route`` gate is reused (imported, not re-implemented) as
defense-in-depth alongside the Discord bot-layer gate (T-47-01). Unlike
the sweep route, migration does NOT build the embedding/classifier
"safe_to_mutate" probe — the migration orchestrator reuses
``pipeline_orchestrator``'s own internal calls, which already carry that
guard (per 47-PATTERNS.md).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.routes.note import _is_admin_route
from app.services import migration_status_store
from app.services.migration_orchestrator import start_migration
from app.state import get_route_context

logger = logging.getLogger(__name__)
router = APIRouter()


class MigrateStartRequest(BaseModel):
    user_id: str
    dry_run: bool = False  # preview the migration without mutating the vault


@router.post("/vault/migrate/start")
async def vault_migrate_start(req: MigrateStartRequest, request: Request):
    if not _is_admin_route(req.user_id):
        raise HTTPException(status_code=403, detail="admin only")

    ctx = get_route_context(request)

    return await start_migration(
        vault=ctx.vault,
        dry_run=req.dry_run,
        embedder=ctx.embedder,
        settings=ctx.settings,
    )


@router.get("/vault/migrate/status")
async def vault_migrate_status():
    return migration_status_store.get_status()
