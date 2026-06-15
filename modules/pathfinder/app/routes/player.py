"""Per-player FastAPI routes for Phase 37 (PVL-01..05, PVL-07 isolation).

Wave 2 slice ships three routes:
  POST /player/onboard  — create profile.md (PVL-01)
  POST /player/style    — list / set style preset (PVL-05)
  GET  /player/state    — read profile state (PVL-01)

Plans 08/09/10 add /player/note, /player/ask, /player/npc, /player/todo,
/player/recall, /player/canonize. The onboarding-gate 503 helper and
module-level `obsidian` singleton are shared across all routes.

Route handlers delegate write/read mechanics to player_vault_store, slug
derivation to player_identity_resolver, and frontmatter shape to
vault_markdown — keeping the route layer thin per PATTERNS.md analog with
routes/npc.py.
"""
from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from app.player_interaction_orchestrator import (
    VALID_OUTCOMES as VALID_CANONIZE_OUTCOMES,
    VALID_STYLE_PRESETS,
    PlayerInteractionRequest,
    PlayerInteractionResult,
    handle_player_interaction_with_obsidian,
)
from app.vault_markdown import build_frontmatter_markdown

# Free-text caps + control-char filter mirror routes/npc.py validators.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_MAX_TEXT_LEN = 2000
_MAX_NPC_NAME_LEN = 100


def _sanitize_text(value: str, *, max_len: int = _MAX_TEXT_LEN) -> str:
    """Strip control chars + enforce length cap; raise ValueError on empty/over-cap."""
    cleaned = _CONTROL_CHAR_RE.sub("", value or "").strip()
    if not cleaned:
        raise ValueError("text must be non-empty after sanitisation")
    if len(cleaned) > max_len:
        raise ValueError(f"text exceeds {max_len}-char limit")
    return cleaned

router = APIRouter(prefix="/player", tags=["player"])

# Module-level ObsidianClient — set by main.py lifespan, patched by tests.
obsidian = None

_MAX_QUESTION_ID_LEN = 100
_MAX_RULE_TEXT_LEN = 2000


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class PlayerOnboardRequest(BaseModel):
    user_id: str
    character_name: str
    preferred_name: str
    style_preset: str

    @field_validator("style_preset")
    @classmethod
    def check_preset(cls, v: str) -> str:
        if v not in VALID_STYLE_PRESETS:
            raise ValueError(
                f"invalid style_preset {v!r}; valid: {sorted(VALID_STYLE_PRESETS)}"
            )
        return v


class PlayerNoteRequest(BaseModel):
    """Request shape for POST /player/note — appends to per-player inbox.md."""

    user_id: str
    text: str


class PlayerAskRequest(BaseModel):
    """Request shape for POST /player/ask.

    v1 contract: store-only. The question is appended to questions.md and NO
    LLM/external HTTP call is issued. LLM-answered ask is deferred to v2.
    """

    user_id: str
    text: str


class PlayerNpcRequest(BaseModel):
    """Request shape for POST /player/npc — writes per-player NPC knowledge.

    Per PVL-07: writes land at players/{slug}/npcs/{npc_slug}.md, NEVER at the
    global mnemosyne/pf2e/npcs/{npc_slug}.md path.
    """

    user_id: str
    npc_name: str
    note: str


class PlayerTodoRequest(BaseModel):
    """Request shape for POST /player/todo — appends to per-player todo.md."""

    user_id: str
    text: str


class PlayerRecallRequest(BaseModel):
    """Request shape for POST /player/recall — deterministic per-player recall.

    v1 contract (CONTEXT lock): keyword-match + recency only. No LLM, no
    embeddings. The query is optional; an empty/missing query returns the
    most-recent notes under the requesting player's namespace.
    """

    user_id: str
    query: str | None = ""


class PlayerCanonizeRequest(BaseModel):
    """Request shape for POST /player/canonize (PVL-04).

    Records a yellow→green or yellow→red rule outcome in the requesting
    player's canonization.md with provenance back to the originating
    question_id. v1: NO timeout-based auto-resolution (see Open Question 4
    in CONTEXT.md).
    """

    user_id: str
    outcome: str
    question_id: str
    rule_text: str

    @field_validator("outcome")
    @classmethod
    def check_outcome(cls, v: str) -> str:
        if v not in VALID_CANONIZE_OUTCOMES:
            raise ValueError(
                f"invalid outcome {v!r}; valid: {sorted(VALID_CANONIZE_OUTCOMES)}"
            )
        return v

    @field_validator("question_id")
    @classmethod
    def check_question_id(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if not cleaned:
            raise ValueError("question_id must be non-empty")
        if len(cleaned) > _MAX_QUESTION_ID_LEN:
            raise ValueError(
                f"question_id exceeds {_MAX_QUESTION_ID_LEN}-char limit"
            )
        if _CONTROL_CHAR_RE.search(cleaned):
            raise ValueError("question_id contains control characters")
        return cleaned


class PlayerStyleRequest(BaseModel):
    user_id: str
    action: Literal["list", "set"]
    preset: str | None = None

    @field_validator("preset")
    @classmethod
    def check_preset(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in VALID_STYLE_PRESETS:
            raise ValueError(
                f"invalid preset {v!r}; valid: {sorted(VALID_STYLE_PRESETS)}"
            )
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_obsidian() -> None:
    """Raise 503 if the lifespan singleton was never set."""
    if obsidian is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "obsidian client not initialised"},
        )


async def _run_player_interaction(
    request: PlayerInteractionRequest,
) -> PlayerInteractionResult:
    """Run the Pathfinder Player Interaction module from the HTTP adapter."""
    _require_obsidian()
    try:
        result = await handle_player_interaction_with_obsidian(
            request,
            obsidian_client=obsidian,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "Obsidian interaction failed", "detail": str(exc)},
        ) from exc
    if result.requires_onboarding:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "player not onboarded",
                "hint": "Run :pf player start to onboard first.",
            },
        )
    return result


# ---------------------------------------------------------------------------
# POST /player/onboard
# ---------------------------------------------------------------------------


@router.post("/onboard")
async def onboard(req: PlayerOnboardRequest) -> JSONResponse:
    """Create profile.md with onboarded:true (PVL-01).

    GET-then-PUT not required here — onboard is intentionally idempotent and
    always rewrites the profile with the latest onboarding form values.
    """
    result = await _run_player_interaction(
        PlayerInteractionRequest(
            verb="start",
            user_id=req.user_id,
            character_name=req.character_name,
            preferred_name=req.preferred_name,
            style_preset=req.style_preset,
        )
    )
    return JSONResponse(
        {
            "status": "onboarded",
            "slug": result.slug,
            "path": result.data["path"],
        }
    )


# ---------------------------------------------------------------------------
# Capture-verb shared helpers (plan 37-08)
# ---------------------------------------------------------------------------


def _validate_free_text(value: str, *, max_len: int = _MAX_TEXT_LEN) -> str:
    """422 on empty/over-cap free-text fields (mirrors npc.py validators)."""
    try:
        return _sanitize_text(value, max_len=max_len)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)}) from exc


# ---------------------------------------------------------------------------
# POST /player/note — append to per-player inbox.md (PVL-02)
# ---------------------------------------------------------------------------


@router.post("/note")
async def note(req: PlayerNoteRequest) -> JSONResponse:
    """Append `text` to mnemosyne/pf2e/players/{slug}/inbox.md (PVL-02).

    Onboarding-gated. 503 if obsidian client is unset; 409 if profile.md does
    not yet have onboarded:true. Per-player isolation enforced by
    player_vault_store._resolve_player_path.
    """
    text = _validate_free_text(req.text)
    result = await _run_player_interaction(
        PlayerInteractionRequest(verb="note", user_id=req.user_id, text=text)
    )
    return JSONResponse({"ok": True, "slug": result.slug, "path": result.data["path"]})


# ---------------------------------------------------------------------------
# POST /player/ask — append to per-player questions.md (PVL-02)
#
# v1 contract: STORE-ONLY. No LLM call. The question persists for later
# canonization (plan 37-10). Behavioural-Test-Only Rule: any LLM POST during
# this handler is a regression — covered by test_post_ask_stores_question_no_llm.
# ---------------------------------------------------------------------------


@router.post("/ask")
async def ask(req: PlayerAskRequest) -> JSONResponse:
    """Append a question to mnemosyne/pf2e/players/{slug}/questions.md.

    v1 contract: store-only. NO LLM call is issued — the question is queued
    for later canonization. LLM-answered ask is deferred to v2.
    """
    text = _validate_free_text(req.text)
    result = await _run_player_interaction(
        PlayerInteractionRequest(verb="ask", user_id=req.user_id, text=text)
    )
    return JSONResponse({"ok": True, "slug": result.slug, "path": result.data["path"]})


# ---------------------------------------------------------------------------
# POST /player/npc — write per-player NPC knowledge (PVL-07 isolation)
# ---------------------------------------------------------------------------


@router.post("/npc")
async def npc(req: PlayerNpcRequest) -> JSONResponse:
    """Write per-player NPC knowledge at players/{slug}/npcs/{npc_slug}.md.

    PVL-07: this MUST NOT touch the global mnemosyne/pf2e/npcs/{npc_slug}.md
    path. Per-player isolation is enforced by player_vault_store, which
    constrains every resolved path under players/{slug}/.
    """
    name = _validate_free_text(req.npc_name, max_len=_MAX_NPC_NAME_LEN)
    note_text = _validate_free_text(req.note)
    result = await _run_player_interaction(
        PlayerInteractionRequest(
            verb="npc",
            user_id=req.user_id,
            npc_name=name,
            note=note_text,
        )
    )
    return JSONResponse({"ok": True, "slug": result.slug, "path": result.data["path"]})


# ---------------------------------------------------------------------------
# POST /player/todo — append to per-player todo.md (PVL-02)
# ---------------------------------------------------------------------------


@router.post("/todo")
async def todo(req: PlayerTodoRequest) -> JSONResponse:
    """Append `text` to mnemosyne/pf2e/players/{slug}/todo.md."""
    text = _validate_free_text(req.text)
    result = await _run_player_interaction(
        PlayerInteractionRequest(verb="todo", user_id=req.user_id, text=text)
    )
    return JSONResponse({"ok": True, "slug": result.slug, "path": result.data["path"]})


# ---------------------------------------------------------------------------
# POST /player/recall — deterministic per-player recall (PVL-03 / PVL-07)
#
# v1 contract: keyword-match + recency only via app.player_recall_engine.recall.
# Onboarding-gated. Reads ONLY under mnemosyne/pf2e/players/{slug}/ — the
# engine's defensive prefix guard plus list_directory's slug-bound prefix arg
# make cross-player leakage impossible.
# ---------------------------------------------------------------------------


@router.post("/recall")
async def recall(req: PlayerRecallRequest) -> JSONResponse:
    """Return ranked recall results scoped to the requesting player's namespace."""
    result = await _run_player_interaction(
        PlayerInteractionRequest(
            verb="recall",
            user_id=req.user_id,
            query=req.query or "",
        )
    )
    return JSONResponse(
        {"ok": True, "slug": result.slug, "results": result.data["results"]}
    )


# ---------------------------------------------------------------------------
# POST /player/canonize — record yellow→green/red rule outcome (PVL-04)
#
# Yellow rule outcomes get canonized to green or red and appended to
# canonization.md with provenance back to the originating question_id.
# v1: NO timeout-based auto-resolution — every canonization is operator-driven.
# ---------------------------------------------------------------------------


@router.post("/canonize")
async def canonize(req: PlayerCanonizeRequest) -> JSONResponse:
    """Append a canonization entry to players/{slug}/canonization.md (PVL-04).

    Onboarding-gated. The persisted bullet embeds {outcome, timestamp,
    question_id, rule_text} so a downstream reader can trace any green/red
    decision back to the original yellow question.
    """
    rule_text = _validate_free_text(req.rule_text, max_len=_MAX_RULE_TEXT_LEN)
    result = await _run_player_interaction(
        PlayerInteractionRequest(
            verb="canonize",
            user_id=req.user_id,
            outcome=req.outcome,
            question_id=req.question_id,
            rule_text=rule_text,
        )
    )
    return JSONResponse(
        {
            "ok": True,
            "slug": result.slug,
            "path": result.data["path"],
            "outcome": result.data["outcome"],
            "question_id": result.data["question_id"],
        }
    )


# ---------------------------------------------------------------------------
# POST /player/style
# ---------------------------------------------------------------------------


@router.post("/style")
async def style(req: PlayerStyleRequest) -> JSONResponse:
    """List or set the style preset (PVL-05).

    action=list  — read-only; returns the four canonical presets, no put_note.
    action=set   — gated by onboarding; GET-then-PUT profile.md frontmatter
                   so style_preset persists alongside the existing fields.
    """
    if req.action == "list":
        result = await _run_player_interaction(
            PlayerInteractionRequest(
                verb="style",
                user_id=req.user_id,
                action="list",
            )
        )
        return JSONResponse({"presets": result.presets})

    # action == "set" — preset must be present.
    if req.preset is None:
        raise HTTPException(
            status_code=422,
            detail={"error": "preset required when action=set"},
        )

    result = await _run_player_interaction(
        PlayerInteractionRequest(
            verb="style",
            user_id=req.user_id,
            action="set",
            preset=req.preset,
        )
    )
    return JSONResponse(
        {
            "status": "set",
            "slug": result.slug,
            "path": result.data["path"],
            "style_preset": result.data["style_preset"],
        }
    )


# ---------------------------------------------------------------------------
# GET /player/state
# ---------------------------------------------------------------------------


@router.get("/state")
async def state(user_id: str = Query(...)) -> JSONResponse:
    """Return onboarding/style state from profile.md frontmatter.

    200 even when not onboarded — clients use the `onboarded` flag to decide
    whether to prompt the user to run :pf player start.
    """
    result = await _run_player_interaction(
        PlayerInteractionRequest(verb="state", user_id=user_id)
    )
    data = result.data or {}
    return JSONResponse(
        {
            "slug": result.slug,
            "onboarded": data.get("onboarded"),
            "style_preset": data.get("style_preset"),
            "character_name": data.get("character_name"),
            "preferred_name": data.get("preferred_name"),
        }
    )


# Surface build_frontmatter_markdown re-export for downstream routes/tests
# that use the same vault formatting.
__all__ = [
    "router",
    "obsidian",
    "VALID_STYLE_PRESETS",
    "build_frontmatter_markdown",
]
