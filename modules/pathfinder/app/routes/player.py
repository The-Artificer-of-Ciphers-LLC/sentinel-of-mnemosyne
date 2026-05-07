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

import logging
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from app import player_identity_resolver, player_vault_store
from app.vault_markdown import _parse_frontmatter, build_frontmatter_markdown

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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/player", tags=["player"])

# Module-level ObsidianClient — set by main.py lifespan, patched by tests.
obsidian = None

VALID_STYLE_PRESETS = frozenset(
    {"Tactician", "Lorekeeper", "Cheerleader", "Rules-Lawyer Lite"}
)


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


async def _resolve_slug(user_id: str) -> str:
    """Derive slug, honouring the alias map when present."""
    try:
        alias_map = await player_identity_resolver.load_alias_map(obsidian)
    except Exception:
        alias_map = {}
    return player_identity_resolver.slug_from_discord_user_id(user_id, alias_map)


async def _read_profile(slug: str) -> dict:
    """Read profile.md and return its parsed frontmatter (or {})."""
    text = await player_vault_store.read_profile(slug, obsidian=obsidian)
    if not text:
        return {}
    return _parse_frontmatter(text)


# ---------------------------------------------------------------------------
# POST /player/onboard
# ---------------------------------------------------------------------------


@router.post("/onboard")
async def onboard(req: PlayerOnboardRequest) -> JSONResponse:
    """Create profile.md with onboarded:true (PVL-01).

    GET-then-PUT not required here — onboard is intentionally idempotent and
    always rewrites the profile with the latest onboarding form values.
    """
    _require_obsidian()
    slug = await _resolve_slug(req.user_id)
    profile = {
        "slug": slug,
        "onboarded": True,
        "character_name": req.character_name,
        "preferred_name": req.preferred_name,
        "style_preset": req.style_preset,
    }
    try:
        await player_vault_store.write_profile(slug, profile, obsidian=obsidian)
    except Exception as exc:
        logger.error("Obsidian write failed for player onboard %s: %s", slug, exc)
        raise HTTPException(
            status_code=503,
            detail={"error": "Obsidian write failed", "detail": str(exc)},
        )

    path = f"mnemosyne/pf2e/players/{slug}/profile.md"
    logger.info("Player onboarded: %s at %s", slug, path)
    return JSONResponse({"status": "onboarded", "slug": slug, "path": path})


# ---------------------------------------------------------------------------
# Capture-verb shared helpers (plan 37-08)
# ---------------------------------------------------------------------------


def _onboarding_gate_or_409(fm: dict) -> None:
    if not fm.get("onboarded"):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "player not onboarded",
                "hint": "Run :pf player start to onboard first.",
            },
        )


def _validate_free_text(value: str, *, max_len: int = _MAX_TEXT_LEN) -> str:
    """422 on empty/over-cap free-text fields (mirrors npc.py validators)."""
    try:
        return _sanitize_text(value, max_len=max_len)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)}) from exc


def _wrap_obsidian_write(action: str, slug: str):
    """Context-manager-like helper for uniform 503-on-write-failure handling."""
    # Returns a closure that wraps a coroutine; kept as a small helper so the
    # four capture handlers stay readable.
    pass  # pragma: no cover — intentionally a marker; handlers use try/except inline


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
    _require_obsidian()
    text = _validate_free_text(req.text)
    slug = await _resolve_slug(req.user_id)
    fm = await _read_profile(slug)
    _onboarding_gate_or_409(fm)
    try:
        await player_vault_store.append_to_inbox(slug, text, obsidian=obsidian)
    except Exception as exc:
        logger.error("Obsidian write failed for /player/note %s: %s", slug, exc)
        raise HTTPException(
            status_code=503,
            detail={"error": "Obsidian write failed", "detail": str(exc)},
        )
    path = f"mnemosyne/pf2e/players/{slug}/inbox.md"
    logger.info("Player note captured: slug=%s path=%s", slug, path)
    return JSONResponse({"ok": True, "slug": slug, "path": path})


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
    _require_obsidian()
    text = _validate_free_text(req.text)
    slug = await _resolve_slug(req.user_id)
    fm = await _read_profile(slug)
    _onboarding_gate_or_409(fm)
    try:
        await player_vault_store.append_to_questions(slug, text, obsidian=obsidian)
    except Exception as exc:
        logger.error("Obsidian write failed for /player/ask %s: %s", slug, exc)
        raise HTTPException(
            status_code=503,
            detail={"error": "Obsidian write failed", "detail": str(exc)},
        )
    path = f"mnemosyne/pf2e/players/{slug}/questions.md"
    logger.info("Player question stored (no LLM): slug=%s path=%s", slug, path)
    return JSONResponse({"ok": True, "slug": slug, "path": path})


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
    _require_obsidian()
    # Lazy import keeps app.routes.npc out of player.py module-load — avoids
    # the circular-import risk Phase 32 documented for cross-route imports.
    from app.routes.npc import slugify  # noqa: PLC0415

    name = _validate_free_text(req.npc_name, max_len=_MAX_NPC_NAME_LEN)
    note_text = _validate_free_text(req.note)
    npc_slug = slugify(name)
    if not npc_slug:
        raise HTTPException(
            status_code=422,
            detail={"error": "npc_name produced an empty slug after sanitisation"},
        )
    slug = await _resolve_slug(req.user_id)
    fm = await _read_profile(slug)
    _onboarding_gate_or_409(fm)
    # Build a minimal markdown body so the per-player NPC note is human-readable
    # in Obsidian. Frontmatter records the npc identity; body holds the note.
    content = (
        f"---\n"
        f"npc_slug: {npc_slug}\n"
        f"npc_name: {name}\n"
        f"player_slug: {slug}\n"
        f"---\n\n"
        f"{note_text}\n"
    )
    try:
        await player_vault_store.write_npc_knowledge(
            slug, npc_slug, content, obsidian=obsidian
        )
    except Exception as exc:
        logger.error("Obsidian write failed for /player/npc %s: %s", slug, exc)
        raise HTTPException(
            status_code=503,
            detail={"error": "Obsidian write failed", "detail": str(exc)},
        )
    path = f"mnemosyne/pf2e/players/{slug}/npcs/{npc_slug}.md"
    logger.info("Player NPC knowledge written: slug=%s npc=%s path=%s", slug, npc_slug, path)
    return JSONResponse({"ok": True, "slug": slug, "path": path})


# ---------------------------------------------------------------------------
# POST /player/todo — append to per-player todo.md (PVL-02)
# ---------------------------------------------------------------------------


@router.post("/todo")
async def todo(req: PlayerTodoRequest) -> JSONResponse:
    """Append `text` to mnemosyne/pf2e/players/{slug}/todo.md."""
    _require_obsidian()
    text = _validate_free_text(req.text)
    slug = await _resolve_slug(req.user_id)
    fm = await _read_profile(slug)
    _onboarding_gate_or_409(fm)
    try:
        await player_vault_store.append_to_todo(slug, text, obsidian=obsidian)
    except Exception as exc:
        logger.error("Obsidian write failed for /player/todo %s: %s", slug, exc)
        raise HTTPException(
            status_code=503,
            detail={"error": "Obsidian write failed", "detail": str(exc)},
        )
    path = f"mnemosyne/pf2e/players/{slug}/todo.md"
    logger.info("Player todo captured: slug=%s path=%s", slug, path)
    return JSONResponse({"ok": True, "slug": slug, "path": path})


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
    _require_obsidian()
    if req.action == "list":
        presets = sorted(VALID_STYLE_PRESETS)
        return JSONResponse({"presets": presets})

    # action == "set" — preset must be present.
    if req.preset is None:
        raise HTTPException(
            status_code=422,
            detail={"error": "preset required when action=set"},
        )

    slug = await _resolve_slug(req.user_id)
    fm = await _read_profile(slug)
    if not fm.get("onboarded"):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "player not onboarded",
                "hint": "Run :pf player start to onboard first.",
            },
        )

    fm["style_preset"] = req.preset
    try:
        await player_vault_store.write_profile(slug, fm, obsidian=obsidian)
    except Exception as exc:
        logger.error("Obsidian write failed for /player/style %s: %s", slug, exc)
        raise HTTPException(
            status_code=503,
            detail={"error": "Obsidian write failed", "detail": str(exc)},
        )

    path = f"mnemosyne/pf2e/players/{slug}/profile.md"
    logger.info("Player style preset updated: %s -> %s", slug, req.preset)
    return JSONResponse(
        {"status": "set", "slug": slug, "path": path, "style_preset": req.preset}
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
    _require_obsidian()
    slug = await _resolve_slug(user_id)
    fm = await _read_profile(slug)
    return JSONResponse(
        {
            "slug": slug,
            "onboarded": bool(fm.get("onboarded")),
            "style_preset": fm.get("style_preset"),
            "character_name": fm.get("character_name"),
            "preferred_name": fm.get("preferred_name"),
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
