"""Routes for the 6 Rs pipeline (Phase 46, PIPE-06).

Endpoints:
  POST /vault/pipeline/start   -- admin-gated; spawns a pipeline run and
                                   returns an immediate {pipeline_id, status,
                                   mode} ack (D-03 always-async + poll).
  GET  /vault/pipeline/status  -- ungated; returns the PipelineReport dict
                                   shape (mirrors /vault/sweep/status).

``_is_admin_route`` is IMPORTED from ``app.routes.note`` -- never duplicated
(T-46-01, Open Question 3): a single source of truth for the admin gate.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.routes.note import _is_admin_route
from app.services.pipeline_orchestrator import get_status, start_pipeline
from app.state import get_route_context

router = APIRouter()

_VALID_MODES: frozenset[str] = frozenset({"ralph", "pipeline", "reweave", "rethink"})


class PipelineStartRequest(BaseModel):
    user_id: str
    mode: str


@router.post("/vault/pipeline/start")
async def vault_pipeline_start(req: PipelineStartRequest, request: Request):
    if not _is_admin_route(req.user_id):
        raise HTTPException(status_code=403, detail="admin only")

    if req.mode not in _VALID_MODES:
        raise HTTPException(status_code=422, detail=f"invalid mode: {req.mode!r}")

    ctx = get_route_context(request)
    return await start_pipeline(
        vault=ctx.vault,
        embedder=ctx.embedder,
        settings=ctx.settings,
        mode=req.mode,
    )


@router.get("/vault/pipeline/status")
async def vault_pipeline_status():
    return get_status()
