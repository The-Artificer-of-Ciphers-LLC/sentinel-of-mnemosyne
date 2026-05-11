"""Routes for the 2nd-brain note-import + inbox flow (260427-vl1).

Endpoints:
  POST /note/classify           — classify content; file directly or inbox or drop
  GET  /inbox                   — list pending entries with discord-rendered string
  POST /inbox/classify          — file an existing inbox entry under a topic
  POST /inbox/discard           — drop an entry from inbox without filing
  POST /vault/sweep/start       — admin-gated; spawns a sweep task and returns sweep_id
  GET  /vault/sweep/status      — current sweep progress (idle/running/complete)

All Obsidian I/O goes through ``request.app.state.route_ctx`` — a single
dataclass that bundles every dependency (Q4(b) consolidation).
"""
from __future__ import annotations

import logging
import os
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.errors import EntryNotFound, InboxChangedConflict
from app.services.inbox import INBOX_PATH, parse_inbox, render_for_discord
from app.services.note_classifier import classify_note  # noqa: F401 — re-exported for test patching
from app.services.note_intake import NoteIntake
from app.state import get_route_context

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Request / response models ---


class ClassifyRequest(BaseModel):
    content: str
    topic: str | None = None


class ClassifyResponse(BaseModel):
    action: str  # filed | inboxed | dropped
    path: str | None = None
    topic: str | None = None
    confidence: float | None = None
    reason: str | None = None
    entry_n: int | None = None


class InboxClassifyRequest(BaseModel):
    entry_n: int
    topic: str


class InboxDiscardRequest(BaseModel):
    entry_n: int


# --- Helpers ---


# --- Routes ---


@router.post("/note/classify", response_model=ClassifyResponse)
async def classify_and_file(req: ClassifyRequest, request: Request) -> ClassifyResponse:
    ctx = get_route_context(request)
    intake = NoteIntake(ctx.vault, ctx.classify)
    result = await intake.classify_and_apply(req.content, req.topic)
    return ClassifyResponse(**result)


@router.get("/inbox")
async def get_inbox(request: Request):
    ctx = get_route_context(request)
    vault = ctx.vault
    body = await vault.read_note(INBOX_PATH)
    entries = parse_inbox(body)
    rendered = render_for_discord(entries)
    return {
        "entries": [e.model_dump() for e in entries],
        "rendered": rendered,
    }


@router.post("/inbox/classify")
async def inbox_classify(req: InboxClassifyRequest, request: Request):
    ctx = get_route_context(request)
    intake = NoteIntake(ctx.vault, ctx.classify)
    try:
        return await intake.inbox_classify(req.entry_n, req.topic)
    except EntryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InboxChangedConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/inbox/discard")
async def inbox_discard(req: InboxDiscardRequest, request: Request):
    ctx = get_route_context(request)
    intake = NoteIntake(ctx.vault, ctx.classify)
    try:
        return await intake.inbox_discard(req.entry_n)
    except EntryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InboxChangedConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))


# --- 260427-vl1 Task 7: vault sweeper routes ---


from app.services.note_sweep_runner import start_sweep
from app.services.vault_sweeper import get_status, reset_status_for_tests  # noqa: F401


class SweepStartRequest(BaseModel):
    user_id: str
    force_reclassify: bool = False
    dry_run: bool = False  # preview moves without modifying the vault
    source_folder: str = ""  # restrict sweep to a specific vault folder; "" = whole vault


def _is_admin_route(user_id: str) -> bool:
    """Defense-in-depth admin gate at the route layer (Task 8 also gates at bot)."""
    raw = os.environ.get("SENTINEL_ADMIN_USER_IDS", "")
    if raw.strip() == "*":
        return True
    allowed = {u.strip() for u in raw.split(",") if u.strip()}
    return bool(allowed) and user_id in allowed


@router.post("/vault/sweep/start")
async def vault_sweep_start(req: SweepStartRequest, request: Request):
    if not _is_admin_route(req.user_id):
        raise HTTPException(status_code=403, detail="admin only")

    ctx = get_route_context(request)
    vault = ctx.vault
    classifier = ctx.classify
    embedder = ctx.embedder

    return await start_sweep(
        vault=vault,
        classifier=classifier,
        embedder=embedder,
        force_reclassify=req.force_reclassify,
        dry_run=req.dry_run,
        source_folder=req.source_folder,
    )


@router.get("/vault/sweep/status")
async def vault_sweep_status():
    return get_status()
