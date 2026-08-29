"""Routes for self-profile onboarding status + writes (GH issue #38, core half).

Endpoints:
  GET  /self/profile/status  -- ungated; mirrors /vault/pipeline/status.
  POST /self/profile         -- admin-gated; writes one canonical profile path.

``_is_admin_route`` is IMPORTED from ``app.routes.note`` -- never duplicated,
same single-source-of-truth convention as ``app.routes.pipeline``.

This is the exact HTTP contract the Discord-side agent codes against; do not
change response shapes without updating that contract.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.routes.note import _is_admin_route
from app.services.self_profile import CANONICAL_PROFILE_PATHS, is_unfilled, profile_status
from app.state import get_route_context

router = APIRouter()


class ProfileWriteRequest(BaseModel):
    user_id: str
    path: str
    content: str
    force: bool = False


@router.get("/self/profile/status")
async def self_profile_status(request: Request):
    ctx = get_route_context(request)
    status = await profile_status(ctx.vault)
    return {
        "complete": status.complete,
        "paths": status.paths,
        "unfilled": status.unfilled,
    }


@router.post("/self/profile")
async def write_self_profile(req: ProfileWriteRequest, request: Request):
    if not _is_admin_route(req.user_id):
        raise HTTPException(status_code=403, detail="admin only")

    # NEVER let this route write an arbitrary vault path — it is an
    # admin-gated arbitrary-write primitive otherwise. Validate against the
    # canonical profile allowlist before touching the vault.
    if req.path not in CANONICAL_PROFILE_PATHS:
        raise HTTPException(
            status_code=422, detail=f"not a known profile path: {req.path!r}"
        )

    ctx = get_route_context(request)
    vault = ctx.vault

    if not req.force:
        try:
            existing = await vault.read_note(req.path)
        except Exception:
            existing = ""
        if not is_unfilled(req.path, existing):
            # CRITICAL SAFETY: never silently overwrite a filled profile file.
            # Losing a curated identity.md is far worse than never onboarding.
            return JSONResponse(
                {"written": False, "reason": "already filled"}, status_code=409
            )

    await vault.write_note(req.path, req.content)
    return {"written": True, "path": req.path}
