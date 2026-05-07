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
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from app import player_identity_resolver, player_vault_store
from app.vault_markdown import _parse_frontmatter, build_frontmatter_markdown

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
    """Request shape for POST /player/note (plan 08 widens behaviour).

    This slice ships the 503 + onboarding-gate surface only. Actual inbox.md
    writes land in plan 08 which extends this handler — keeping the route
    registered now lets the operational 503 test and the 409 gate test go
    GREEN at Wave 2, while the 'writes to inbox' test stays RED until plan 08.
    """

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
# POST /player/note — onboarding-gate + 503 surface only (plan 08 wires inbox)
# ---------------------------------------------------------------------------


@router.post("/note")
async def note(req: PlayerNoteRequest) -> JSONResponse:
    """Onboarding-gated note capture.

    Wave 2 ships only the 503 (obsidian missing) and 409 (not onboarded)
    surface; plan 08 adds the actual inbox.md GET-then-PUT write. Keeping the
    route registered now means the route table in REGISTRATION_PAYLOAD is
    stable across waves and the 503 test for /player/note can go GREEN.
    """
    _require_obsidian()
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
    # Plan 08 will replace this with append_to_inbox(slug, req.text). Until
    # that lands, the route accepts the request shape but performs no write —
    # the 'writes to inbox' RED test in plan-02 stays RED, by design.
    raise HTTPException(
        status_code=501,
        detail={"error": "note capture lands in plan 37-08"},
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
