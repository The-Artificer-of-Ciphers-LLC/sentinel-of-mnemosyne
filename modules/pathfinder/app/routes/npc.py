"""NPC CRUD endpoints for the pathfinder module.

Routes (all POST, proxied from sentinel-core at /modules/pathfinder/npc/{verb}):
  POST /npc/create  — create NPC note in Obsidian (NPC-01)
  POST /npc/update  — update NPC fields via GET-then-PUT (NPC-02)
  POST /npc/show    — query NPC and return parsed data (NPC-03)
  POST /npc/relate  — add relationship entry (NPC-04) — implemented in Plan 05
  POST /npc/import  — bulk import from Foundry JSON (NPC-05) — implemented in Plan 05

Architecture: D-27 — pathfinder calls Obsidian directly, not through sentinel-core.
Schema: D-15 through D-20 — split schema (frontmatter + ## Stats fenced block).

Module-level `obsidian` variable is set by main.py lifespan so tests can patch it directly.
"""
import base64
import json
import logging
import re
import uuid

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.dialogue import (
    apply_mood_delta,
    build_system_prompt,
    build_user_prompt,
    cap_history_turns,
    normalize_mood,
)
from app.llm import (
    build_mj_prompt,
    extract_npc_fields,
    generate_mj_description,
    generate_npc_reply,
    update_npc_fields,
)
from app.pdf import build_npc_pdf
from app.resolve_model import resolve_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/npc")

# Module-level ObsidianClient instance — set by main.py lifespan, patchable in tests.
obsidian = None

# NPC vault path prefix (D-16)
_NPC_PATH_PREFIX = "mnemosyne/pf2e/npcs"

# Token image vault path prefix — same parent as _NPC_PATH_PREFIX.
# Token images live at mnemosyne/pf2e/tokens/<slug>.png and are referenced
# from the NPC note's frontmatter `token_image:` field (token-image ext, PLAN.md).
_TOKEN_PATH_PREFIX = "mnemosyne/pf2e/tokens"

# Hard cap on uploaded image size — prevents memory exhaustion from a malicious
# or accidental huge attachment. Midjourney exports are ~1-3 MB, so 10 MB is
# generous. Matches the size check in /npc/import for consistency (T-29-04).
_MAX_IMAGE_BYTES = 10_000_000

# Valid relation types — closed enum (D-13)
VALID_RELATIONS = frozenset({"knows", "trusts", "hostile-to", "allied-with", "fears", "owes-debt"})


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

def _validate_npc_name(v: str) -> str:
    """Reject control characters in NPC name to prevent log injection and prompt injection (CR-02)."""
    v = v.strip()
    if not v:
        raise ValueError("name cannot be empty")
    if len(v) > 100:
        raise ValueError("name too long (max 100 chars)")
    if re.search(r"[\x00-\x1f\x7f]", v):
        raise ValueError("name contains invalid control characters")
    return v


class NPCCreateRequest(BaseModel):
    name: str
    description: str = ""
    user_id: str

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        return _validate_npc_name(v)


class NPCUpdateRequest(BaseModel):
    name: str
    correction: str
    user_id: str

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        return _validate_npc_name(v)


class NPCShowRequest(BaseModel):
    name: str
    user_id: str = ""  # Optional for backward compat; used for audit logging (WR-05)


class NPCRelateRequest(BaseModel):
    name: str
    relation: str
    target: str


class NPCImportRequest(BaseModel):
    actors_json: str  # raw JSON string fetched from Discord attachment URL
    user_id: str


class NPCOutputRequest(BaseModel):
    """Request model for /npc/{export-foundry,token,stat,pdf} (OUT-01..OUT-04)."""
    name: str

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        return _validate_npc_name(v)


class NPCTokenImageRequest(BaseModel):
    """Request model for /npc/token-image (PLAN.md token-image extension).

    image_b64: base64-encoded PNG bytes fetched from Discord attachment by bot layer.
    Content type is fixed to image/png per convention (Midjourney exports PNG).
    """
    name: str
    image_b64: str

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        return _validate_npc_name(v)


# ---------------------------------------------------------------------------
# Phase 31 — dialogue request/response models (D-24, DLG-01..03)
# ---------------------------------------------------------------------------


class TurnHistory(BaseModel):
    """One prior dialogue turn (D-11): user :pf npc say + bot's quote-block reply.

    Bot-sourced from thread.history walk; no field validation here (names already
    sanitised when the original message was issued).
    """
    party_line: str = ""
    replies: list[dict] = Field(default_factory=list)  # [{npc: str, reply: str}, ...]


class NPCSayRequest(BaseModel):
    """Request shape for POST /npc/say (D-24).

    party_line == "" is the SCENE ADVANCE signal (D-02).
    history is bot-assembled from Discord thread (D-11..D-14); empty when first turn.
    """
    names: list[str]
    party_line: str = ""
    history: list[TurnHistory] = Field(default_factory=list)
    user_id: str

    @field_validator("names")
    @classmethod
    def sanitize_names(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("at least one NPC name required")
        return [_validate_npc_name(n) for n in v]

    @field_validator("party_line")
    @classmethod
    def check_party_length(cls, v: str) -> str:
        if len(v) > 2000:
            raise ValueError("party_line too long (max 2000 chars)")
        return v


class NPCReply(BaseModel):
    """One NPC's response within a /npc/say turn (D-24)."""
    npc: str
    reply: str
    mood_delta: int
    new_mood: str


class NPCSayResponse(BaseModel):
    """Response shape for POST /npc/say (D-24).

    Per Patterns S6, the route returns JSONResponse({...}) directly rather than
    setting response_model — kept for documentation/typing consistency.
    """
    replies: list[NPCReply]
    warning: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    """Convert NPC name to a stable lowercase filename slug (D-18).

    Examples: 'Baron Aldric' -> 'baron-aldric', 'Varek' -> 'varek'.
    Uses stdlib re — no external dependency (RESEARCH.md Don't Hand-Roll).
    Strips path traversal chars — '../' becomes '' (T-29-01 mitigation).
    """
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _parse_frontmatter(note_text: str) -> dict:
    """Parse YAML frontmatter from a note string delimited by '---'.

    Returns empty dict if frontmatter cannot be parsed.
    Safe to call on machine-generated notes (Sentinel always writes valid YAML).
    """
    try:
        if not note_text.startswith("---"):
            return {}
        # Find the closing --- delimiter (use find to avoid ValueError on malformed notes)
        end = note_text.find("---", 3)
        if end == -1:
            return {}
        frontmatter_text = note_text[3:end].strip()
        return yaml.safe_load(frontmatter_text) or {}
    except Exception as exc:
        logger.warning("Frontmatter parse failed: %s", exc)
        return {}


def _parse_stats_block(note_text: str) -> dict:
    """Extract the ## Stats fenced yaml block from note body (D-17).

    Returns empty dict if stats block is absent (D-22: stats omitted if missing).
    """
    try:
        # Match: ## Stats\n```yaml\n<content>\n```
        match = re.search(r"## Stats\n```yaml\n(.*?)```", note_text, re.DOTALL)
        if not match:
            return {}
        return yaml.safe_load(match.group(1)) or {}
    except Exception as exc:
        logger.warning("Stats block parse failed: %s", exc)
        return {}


def build_npc_markdown(fields: dict, stats: dict | None = None) -> str:
    """Build the full markdown content for an NPC note (D-15, D-16, D-17).

    fields: frontmatter fields dict (name, level, ancestry, class, traits,
            personality, backstory, mood, relationships, imported_from).
    stats: optional stats dict (ac, hp, fortitude, reflex, will, speed, skills).
           If None, the ## Stats block is omitted (identity-only NPC).
    """
    frontmatter = yaml.dump(fields, default_flow_style=False, allow_unicode=True)
    body = f"---\n{frontmatter}---\n"
    if stats:
        stats_yaml = yaml.dump(stats, default_flow_style=False, allow_unicode=True)
        body += f"\n## Stats\n```yaml\n{stats_yaml}```\n"
    return body


def _build_foundry_actor(fields: dict, stats: dict) -> dict:
    """Build a PF2e Remaster-compatible Foundry VTT actor dict (OUT-01, D-04).

    Uses uuid.uuid4().hex[:16] for _id (16 hex chars per Foundry convention, Pitfall 4).
    Does NOT include system.details.alignment — removed in 2023 Remaster.
    NPCs with no stats block default all numeric fields to 0 (D-05).
    """
    actor_id = uuid.uuid4().hex[:16]
    return {
        "_id": actor_id,
        "name": fields.get("name", "Unknown"),
        "type": "npc",
        "img": "icons/svg/mystery-man.svg",
        "items": [],
        "effects": [],
        "folder": None,
        "flags": {},
        "ownership": {"default": 0},
        "prototypeToken": {
            "name": fields.get("name", "Unknown"),
            "texture": {"src": "icons/svg/mystery-man.svg"},
        },
        "system": {
            "traits": {
                "value": fields.get("traits") or [],
                "rarity": "common",
                "size": {"value": "med"},
            },
            "abilities": {
                "str": {"mod": 0}, "dex": {"mod": 0}, "con": {"mod": 0},
                "int": {"mod": 0}, "wis": {"mod": 0}, "cha": {"mod": 0},
            },
            "attributes": {
                "ac": {"value": stats.get("ac", 0), "details": ""},
                "adjustment": None,
                "hp": {
                    "value": stats.get("hp", 0),
                    "max": stats.get("hp", 0),
                    "temp": 0,
                    "details": "",
                },
                "speed": {
                    "value": stats.get("speed", 25),
                    "otherSpeeds": [],
                    "details": "",
                },
                "allSaves": {"value": ""},
            },
            "perception": {"mod": stats.get("perception", 0)},
            "skills": {},
            "initiative": {"statistic": "perception"},
            "details": {
                "level": {"value": fields.get("level", 1)},
                "blurb": (fields.get("personality") or "")[:100],
                "publicNotes": fields.get("backstory") or "",
                "privateNotes": "",
                "publication": {"title": "", "authors": "", "license": "ORC"},
            },
            "saves": {
                "fortitude": {"value": stats.get("fortitude", 0), "saveDetail": ""},
                "reflex": {"value": stats.get("reflex", 0), "saveDetail": ""},
                "will": {"value": stats.get("will", 0), "saveDetail": ""},
            },
            "resources": {"focus": {"value": 0, "max": 0}},
        },
    }


# ---------------------------------------------------------------------------
# Route handlers — use module-level `obsidian` (set in main.py lifespan)
# ---------------------------------------------------------------------------

@router.post("/create")
async def create_npc(req: NPCCreateRequest) -> JSONResponse:
    """Create an NPC note in Obsidian (NPC-01).

    Uses GET-before-write collision check (D-19).
    LLM extracts all frontmatter fields from description (D-06, D-07).
    """
    slug = slugify(req.name)
    path = f"{_NPC_PATH_PREFIX}/{slug}.md"

    # Collision check — D-19: return 409 with existing path, never silently overwrite
    existing = await obsidian.get_note(path)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": "NPC already exists", "path": path},
        )

    # LLM field extraction — D-06, D-07
    # Task kind "structured" — requires function-calling-capable model for reliable JSON
    try:
        fields = await extract_npc_fields(
            name=req.name,
            description=req.description,
            model=await resolve_model("structured"),
            api_base=settings.litellm_api_base or None,
            profile=await resolve_model_profile("structured"),
        )
    except Exception as exc:
        logger.error("LLM extraction failed for NPC %s: %s", req.name, exc)
        raise HTTPException(status_code=500, detail={"error": "LLM extraction failed", "detail": str(exc)})

    # Ensure required fields with defaults (D-16, D-20)
    fields["name"] = req.name  # canonical — use user-provided name
    fields.setdefault("level", 1)
    fields.setdefault("mood", "neutral")
    fields["relationships"] = []
    fields["imported_from"] = None

    content = build_npc_markdown(fields, stats=None)
    try:
        await obsidian.put_note(path, content)
    except Exception as exc:
        logger.error("Obsidian write failed for NPC %s: %s", req.name, exc)
        raise HTTPException(status_code=503, detail={"error": "Obsidian write failed", "detail": str(exc)})

    logger.info("NPC created: %s at %s", req.name, path)
    return JSONResponse({
        "status": "created",
        "slug": slug,
        "path": path,
        **{k: fields.get(k) for k in ("name", "level", "ancestry", "class", "traits", "personality", "backstory", "mood")},
    })


@router.post("/update")
async def update_npc(req: NPCUpdateRequest) -> JSONResponse:
    """Update NPC fields via GET-then-PUT (NPC-02, D-10).

    Reads the existing note, sends to LLM with correction to extract changed fields,
    merges changes into frontmatter, rebuilds full markdown, and PUTs back.
    Stats block preserved if present; replaced only if correction mentions stats.
    """
    slug = slugify(req.name)
    path = f"{_NPC_PATH_PREFIX}/{slug}.md"

    # Read existing note — must exist
    note_text = await obsidian.get_note(path)
    if note_text is None:
        raise HTTPException(status_code=404, detail={"error": "NPC not found", "slug": slug})

    # LLM extracts changed fields from correction string (D-10)
    # Task kind "structured" — same JSON-extraction profile as /create
    try:
        changed = await update_npc_fields(
            current_note=note_text,
            correction=req.correction,
            model=await resolve_model("structured"),
            api_base=settings.litellm_api_base or None,
            profile=await resolve_model_profile("structured"),
        )
    except Exception as exc:
        logger.error("LLM update extraction failed for NPC %s: %s", req.name, exc)
        raise HTTPException(status_code=500, detail={"error": "LLM update failed", "detail": str(exc)})

    # Merge changed fields into existing frontmatter
    current_fields = _parse_frontmatter(note_text)
    current_stats = _parse_stats_block(note_text)
    current_fields.update(changed)

    # Rebuild and PUT full note
    content = build_npc_markdown(current_fields, stats=current_stats if current_stats else None)
    try:
        await obsidian.put_note(path, content)
    except Exception as exc:
        logger.error("Obsidian write failed for NPC %s: %s", req.name, exc)
        raise HTTPException(status_code=503, detail={"error": "Obsidian write failed", "detail": str(exc)})

    logger.info("NPC updated: %s, changed: %s", req.name, list(changed.keys()))
    return JSONResponse({
        "status": "updated",
        "slug": slug,
        "path": path,
        "changed_fields": list(changed.keys()),
    })


@router.post("/show")
async def show_npc(req: NPCShowRequest) -> JSONResponse:
    """Return parsed NPC data dict (NPC-03, D-21, D-22).

    Returns frontmatter fields + stats dict (or empty dict if stats block absent).
    Bot formats the discord embed from this structured response.
    """
    slug = slugify(req.name)
    path = f"{_NPC_PATH_PREFIX}/{slug}.md"

    note_text = await obsidian.get_note(path)
    if note_text is None:
        raise HTTPException(status_code=404, detail={"error": "NPC not found", "slug": slug})

    fields = _parse_frontmatter(note_text)
    stats = _parse_stats_block(note_text)

    return JSONResponse({
        "slug": slug,
        "path": path,
        **fields,
        "stats": stats if stats else {},
    })


@router.post("/relate")
async def relate_npc(req: NPCRelateRequest) -> JSONResponse:
    """Add a relationship entry to an NPC's relationships list (NPC-04, D-12 through D-14).

    Uses GET-then-PATCH:
    1. Validate relation type against VALID_RELATIONS (D-13) before any I/O
    2. GET current note — NPC must exist (404 if missing)
    3. Parse frontmatter → read existing relationships list
    4. Append new entry → PATCH /vault/{slug}.md Target: relationships (Pattern 2)

    PATCH targets the single `relationships` field per Obsidian v3 API semantics.
    The body is the complete updated list (Operation: replace), not an append (D-29).
    """
    slug = slugify(req.name)
    path = f"{_NPC_PATH_PREFIX}/{slug}.md"

    # Validate relation type — closed enum (D-13); fail fast before any Obsidian I/O
    if req.relation not in VALID_RELATIONS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": f"Invalid relation type: {req.relation!r}",
                "valid_options": sorted(VALID_RELATIONS),
            },
        )

    # Read current note — NPC must exist
    note_text = await obsidian.get_note(path)
    if note_text is None:
        raise HTTPException(status_code=404, detail={"error": "NPC not found", "slug": slug})

    # Parse existing relationships list from frontmatter
    fields = _parse_frontmatter(note_text)
    relationships = fields.get("relationships") or []
    if not isinstance(relationships, list):
        relationships = []

    # Append new relationship entry (D-14 format)
    relationships.append({"target": req.target, "relation": req.relation})

    # PATCH single field — replace entire relationships list
    try:
        await obsidian.patch_frontmatter_field(path, "relationships", relationships)
    except Exception as exc:
        logger.error("PATCH relationships failed for %s: %s", req.name, exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to update relationships", "detail": str(exc)},
        )

    logger.info("NPC relate: %s %s %s", req.name, req.relation, req.target)
    return JSONResponse({
        "status": "related",
        "slug": slug,
        "path": path,
        "relation": req.relation,
        "target": req.target,
        "relationships": relationships,
    })


# ---------------------------------------------------------------------------
# Foundry bulk import helpers (NPC-05, D-23 through D-26)
# ---------------------------------------------------------------------------


def parse_foundry_actor(actor: dict) -> dict | None:
    """Extract identity fields from a Foundry VTT actor dict (D-24, D-25).

    Returns None if actor has no name — that actor is silently skipped by import_npcs.
    Defensively ignores unknown JSON keys — PF2e Foundry schema changes are non-breaking.
    The 'system.details.*' path follows Foundry PF2e system data structure (assumed; low
    confidence). Phase 30 derives the canonical schema from a live export; this is identity-only.
    """
    name = actor.get("name") or actor.get("data", {}).get("name")
    if not name:
        logger.debug("Skipping actor with no name: keys=%s", list(actor.keys()))
        return None

    # Log unrecognized top-level keys for Phase 30 schema derivation (CONTEXT.md specifics)
    recognized_keys = {"name", "type", "system", "data", "flags", "_id", "img", "items", "prototypeToken"}
    unknown_keys = set(actor.keys()) - recognized_keys
    if unknown_keys:
        logger.info("Foundry actor %r has unrecognized keys: %s", name, sorted(unknown_keys))

    system = actor.get("system", {})
    details = system.get("details", {})

    level_raw = details.get("level", 1)
    level = level_raw.get("value", 1) if isinstance(level_raw, dict) else level_raw

    ancestry_raw = details.get("ancestry", "")
    ancestry = ancestry_raw.get("value", "") if isinstance(ancestry_raw, dict) else ancestry_raw

    class_raw = details.get("class", "")
    class_val = class_raw.get("value", "") if isinstance(class_raw, dict) else class_raw

    traits_raw = system.get("traits", {})
    traits = traits_raw.get("value", []) if isinstance(traits_raw, dict) else []

    return {
        "name": name,
        "level": level,
        "ancestry": ancestry,
        "class": class_val,
        "traits": traits,
        "imported_from": "foundry",  # flag for Phase 30 enrichment (CONTEXT.md specifics)
    }


@router.post("/import")
async def import_npcs(req: NPCImportRequest) -> JSONResponse:
    """Bulk import NPCs from a Foundry VTT actor list JSON string (NPC-05, D-23 through D-26).

    actors_json: JSON string of a Foundry actor list array (fetched from Discord attachment
                 by bot.py _pf_dispatch before this endpoint is called).
    No LLM call — identity fields only (name, level, ancestry, class, traits).
    Stats block is left empty (Phase 30 derives canonical PF2e Foundry schema).
    """
    # Parse actors JSON — size-check before parsing to prevent memory exhaustion (T-29-04)
    if len(req.actors_json) > 10_000_000:
        raise HTTPException(status_code=413, detail={"error": "actors_json too large (>10MB)"})

    try:
        actors = json.loads(req.actors_json)
        if not isinstance(actors, list):
            raise HTTPException(status_code=400, detail={"error": "actors_json must be a JSON array"})
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail={"error": "Invalid JSON", "detail": str(exc)})

    imported: list[str] = []
    skipped: list[str] = []

    for actor in actors:
        if not isinstance(actor, dict):
            continue  # skip non-object entries

        parsed = parse_foundry_actor(actor)
        if parsed is None:
            continue  # skip actors with no name

        name = parsed["name"]
        slug = slugify(name)
        path = f"{_NPC_PATH_PREFIX}/{slug}.md"

        # Collision check — D-19 (same check as create)
        existing = await obsidian.get_note(path)
        if existing is not None:
            logger.info("Import skip (collision): %s at %s", name, path)
            skipped.append(name)
            continue

        # Build identity-only note — no stats block (D-24)
        fields = {
            "name": parsed["name"],
            "level": parsed.get("level", 1),
            "ancestry": parsed.get("ancestry", ""),
            "class": parsed.get("class", ""),
            "traits": parsed.get("traits", []),
            "personality": "",
            "backstory": "",
            "mood": "neutral",
            "relationships": [],
            "imported_from": "foundry",
        }
        content = build_npc_markdown(fields, stats=None)

        try:
            await obsidian.put_note(path, content)
            imported.append(name)
            logger.info("Import created: %s at %s", name, path)
        except Exception as exc:
            logger.error("Import failed for %s: %s", name, exc)
            skipped.append(name)

    logger.info(
        "Import complete: %d created, %d skipped (req user_id=%s)",
        len(imported),
        len(skipped),
        req.user_id,
    )
    return JSONResponse({
        "status": "imported",
        "imported_count": len(imported),
        "imported": imported,
        "skipped": skipped,
    })


# ---------------------------------------------------------------------------
# NPC output endpoints (OUT-01 through OUT-04, Plan 30-02)
# ---------------------------------------------------------------------------


@router.post("/export-foundry")
async def export_foundry(req: NPCOutputRequest) -> JSONResponse:
    """Export NPC as Foundry VTT PF2e actor JSON (OUT-01).

    Returns {"actor": {...}, "filename": "{slug}.json", "slug": slug}.
    Bot layer serializes actor dict to JSON bytes and wraps in discord.File (D-03).
    NPCs with no stats block export with all numeric fields defaulting to 0 (D-05).
    """
    slug = slugify(req.name)
    path = f"{_NPC_PATH_PREFIX}/{slug}.md"
    note_text = await obsidian.get_note(path)
    if note_text is None:
        raise HTTPException(status_code=404, detail={"error": "NPC not found", "slug": slug})
    fields = _parse_frontmatter(note_text)
    stats = _parse_stats_block(note_text)
    actor = _build_foundry_actor(fields, stats)
    return JSONResponse({
        "actor": actor,
        "filename": f"{slug}.json",
        "slug": slug,
    })


@router.post("/token")
async def token_prompt(req: NPCOutputRequest) -> JSONResponse:
    """Generate Midjourney /imagine prompt for NPC token art (OUT-02).

    Hybrid composition: constrained LLM call fills visual description slot;
    fixed template anchors style/framing/MJ params (D-08, D-09).
    Returns plain text prompt in {"prompt": "..."} — bot returns as-is (D-12).
    """
    slug = slugify(req.name)
    path = f"{_NPC_PATH_PREFIX}/{slug}.md"
    note_text = await obsidian.get_note(path)
    if note_text is None:
        raise HTTPException(status_code=404, detail={"error": "NPC not found", "slug": slug})
    fields = _parse_frontmatter(note_text)
    # Task kind "fast" — max_tokens=40, prefers smaller/cheaper model above 4K ctx
    description = await generate_mj_description(
        fields=fields,
        model=await resolve_model("fast"),
        api_base=settings.litellm_api_base or None,
        profile=await resolve_model_profile("fast"),
    )
    prompt = build_mj_prompt(fields, description)
    return JSONResponse({"prompt": prompt, "slug": slug})


@router.post("/stat")
async def stat_block(req: NPCOutputRequest) -> JSONResponse:
    """Return structured stat block data for Discord embed rendering (OUT-03).

    Bot layer constructs discord.Embed from the returned dict (D-13 through D-17).
    Returns {"fields": frontmatter_dict, "stats": stats_dict_or_empty, "slug": slug, "path": path}.
    stats is {} if no ## Stats block present (D-16).
    """
    slug = slugify(req.name)
    path = f"{_NPC_PATH_PREFIX}/{slug}.md"
    note_text = await obsidian.get_note(path)
    if note_text is None:
        raise HTTPException(status_code=404, detail={"error": "NPC not found", "slug": slug})
    fields = _parse_frontmatter(note_text)
    stats = _parse_stats_block(note_text)
    return JSONResponse({
        "fields": fields,
        "stats": stats if stats else {},
        "slug": slug,
        "path": path,
    })


@router.post("/pdf")
async def pdf_export(req: NPCOutputRequest) -> JSONResponse:
    """Generate PDF stat card for NPC (OUT-04).

    Binary bytes encoded as base64 inside JSON wrapper — required because
    sentinel-core proxy always calls resp.json() (binary transport constraint,
    RESEARCH.md Pattern 1). Bot decodes data_b64 and wraps in discord.File.
    Returns {"data_b64": "...", "filename": "{slug}-stat-card.pdf", "slug": slug}.

    If the NPC has a `token_image:` frontmatter field pointing to a vault path,
    the referenced image is fetched and embedded in the PDF header (token-image
    extension, PLAN.md). Missing/unreadable images fall back to header-only PDF.
    """
    slug = slugify(req.name)
    path = f"{_NPC_PATH_PREFIX}/{slug}.md"
    note_text = await obsidian.get_note(path)
    if note_text is None:
        raise HTTPException(status_code=404, detail={"error": "NPC not found", "slug": slug})
    fields = _parse_frontmatter(note_text)
    stats = _parse_stats_block(note_text)

    # Fetch token image if frontmatter references one — get_binary returns None
    # on 404 or any error, so PDF falls back to header-only rendering.
    token_image_bytes: bytes | None = None
    token_path = fields.get("token_image")
    if isinstance(token_path, str) and token_path:
        token_image_bytes = await obsidian.get_binary(token_path)

    pdf_bytes = build_npc_pdf(fields, stats, token_image_bytes=token_image_bytes)
    return JSONResponse({
        "data_b64": base64.b64encode(pdf_bytes).decode("ascii"),
        "filename": f"{slug}-stat-card.pdf",
        "slug": slug,
    })


@router.post("/token-image")
async def upload_token_image(req: NPCTokenImageRequest) -> JSONResponse:
    """Upload Midjourney-generated token image for an NPC (PLAN.md token-image ext).

    Closes the Midjourney loop: user runs :pf npc token → Midjourney → downloads
    PNG → :pf npc token-image <name> with attachment. Bot base64-encodes the
    attachment bytes and POSTs here. We:
      1. Verify the NPC note exists (404 if not).
      2. Decode base64 (400 if malformed).
      3. PUT the binary to {_TOKEN_PATH_PREFIX}/{slug}.png.
      4. PATCH the note's frontmatter `token_image` field so /npc/pdf picks it up.
    Subsequent /npc/pdf calls embed the image in the PDF header.
    """
    slug = slugify(req.name)
    note_path = f"{_NPC_PATH_PREFIX}/{slug}.md"
    token_path = f"{_TOKEN_PATH_PREFIX}/{slug}.png"

    # NPC must exist — 404 before any vault writes (mirrors update/show/relate)
    note_text = await obsidian.get_note(note_path)
    if note_text is None:
        raise HTTPException(status_code=404, detail={"error": "NPC not found", "slug": slug})

    # Decode image bytes — 400 on malformed base64 (client contract violation)
    try:
        image_bytes = base64.b64decode(req.image_b64, validate=True)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "Invalid base64 image data", "detail": str(exc)},
        )

    # Size check AFTER decode — the base64 string is ~4/3 the size of decoded bytes,
    # but the bot enforces a soft cap on the wire side. Server is the source of truth.
    if len(image_bytes) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error": f"Image too large (max {_MAX_IMAGE_BYTES // 1_000_000} MB)"},
        )

    # Write binary to vault
    try:
        await obsidian.put_binary(token_path, image_bytes, "image/png")
    except Exception as exc:
        logger.error("put_binary failed for %s: %s", token_path, exc)
        raise HTTPException(
            status_code=503,
            detail={"error": "Obsidian binary write failed", "detail": str(exc)},
        )

    # Record path in frontmatter so /npc/pdf can pick it up.
    # GET-then-PUT (not PATCH): Obsidian REST API v3 PATCH with Operation=replace
    # returns 400 when the target frontmatter key doesn't already exist, and
    # NPCs created before this feature lack a `token_image` field. Rebuilding
    # the full note via build_npc_markdown is the proven pattern (see update_npc).
    current_fields = _parse_frontmatter(note_text)
    current_stats = _parse_stats_block(note_text)
    current_fields["token_image"] = token_path
    updated_note = build_npc_markdown(
        current_fields, stats=current_stats if current_stats else None
    )
    try:
        await obsidian.put_note(note_path, updated_note)
    except Exception as exc:
        logger.error("put_note for token_image failed for %s: %s", note_path, exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to update token_image frontmatter", "detail": str(exc)},
        )

    logger.info("Token image saved: %s -> %s (%d bytes)", req.name, token_path, len(image_bytes))
    return JSONResponse({
        "status": "saved",
        "slug": slug,
        "note_path": note_path,
        "token_path": token_path,
        "size_bytes": len(image_bytes),
    })


# ---------------------------------------------------------------------------
# Phase 31 — NPC dialogue endpoint (DLG-01..03, D-07, D-09, D-18, D-19, D-27, D-29)
# ---------------------------------------------------------------------------


@router.post("/say")
async def say_npc(req: NPCSayRequest) -> JSONResponse:
    """In-character NPC dialogue with mood tracking and multi-NPC scenes (DLG-01..03).

    - Solo or scene mode (>=2 names) determined by len(req.names).
    - Empty req.party_line == "" triggers SCENE ADVANCE framing (D-02).
    - First missing NPC fails fast with 404 (D-29) before any LLM call.
    - Mood writes use GET-then-PUT via build_npc_markdown (D-09) — only when mood changes.
    - Soft warning when >=5 NPCs (D-18).
    """
    # Step 1: Load each NPC in order; fail fast on first missing (D-29).
    npcs_data: list[dict] = []
    for name in req.names:
        slug = slugify(name)
        path = f"{_NPC_PATH_PREFIX}/{slug}.md"
        note_text = await obsidian.get_note(path)
        if note_text is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "NPC not found", "slug": slug, "name": name},
            )
        fields = _parse_frontmatter(note_text)
        stats = _parse_stats_block(note_text)
        npcs_data.append({
            "name": name,
            "slug": slug,
            "path": path,
            "fields": fields,
            "stats": stats,
        })

    # Step 2: Cap thread-scoped history (D-14).
    capped_history = cap_history_turns([h.model_dump() for h in req.history])

    # Step 3: Scene roster in canonical order.
    scene_roster = [n["name"] for n in npcs_data]
    scene_name_set_lower = {n.lower() for n in scene_roster}

    # Step 3b: Debug-only scene_id (RESEARCH.md Recommended Defaults — logged only, not user-visible).
    scene_id = "-".join(sorted(slugify(n) for n in scene_roster))
    logger.info(
        "npc/say scene_id=%s names=%s party_line_len=%d history_turns=%d",
        scene_id, scene_roster, len(req.party_line), len(capped_history),
    )

    # Step 4: Resolve chat-tier model and profile (D-27). Single call up front; same model used per turn.
    model = await resolve_model("chat")
    profile_chat = await resolve_model_profile("chat")
    api_base = settings.litellm_api_base or None

    # Step 5: Serial round-robin (D-19) — each NPC sees prior NPCs' replies in this turn.
    this_turn_replies: list[dict] = []
    response_replies: list[dict] = []
    for npc in npcs_data:
        # Filter relationship edges to scene members only (Pitfall 7 / RESEARCH Finding 7).
        all_rels = npc["fields"].get("relationships") or []
        scene_rels = [
            r for r in all_rels
            if isinstance(r, dict)
            and str(r.get("target", "")).lower() in scene_name_set_lower
        ]

        sys_prompt = build_system_prompt(npc["fields"], scene_roster, scene_rels)
        usr_prompt = build_user_prompt(
            history=capped_history,
            this_turn_replies=this_turn_replies,
            party_line=req.party_line,
            npc_name=npc["name"],
        )

        llm_result = await generate_npc_reply(
            system_prompt=sys_prompt,
            user_prompt=usr_prompt,
            model=model,
            api_base=api_base,
            profile=profile_chat,
        )

        # Mood math (D-07): zero or clamped no-op skips the vault write.
        # WR-04: if the stored mood value is invalid (hand-edited or corrupted),
        # normalize_mood silently promotes it to 'neutral'. On a delta=0 turn
        # new_mood == current_mood == 'neutral', so the existing write-elision
        # would leave the invalid value in the vault indefinitely. Track the raw
        # stored value: if it differs from the normalised one, force a self-
        # healing write even when no delta write is otherwise queued.
        raw_mood = npc["fields"].get("mood") or "neutral"
        current_mood = normalize_mood(raw_mood)
        new_mood = apply_mood_delta(current_mood, llm_result["mood_delta"])
        needs_normalization_repair = raw_mood != current_mood and new_mood == current_mood

        if new_mood != current_mood or needs_normalization_repair:
            updated_fields = dict(npc["fields"])
            updated_fields["mood"] = new_mood
            new_content = build_npc_markdown(
                updated_fields,
                stats=npc["stats"] if npc["stats"] else None,
            )
            try:
                await obsidian.put_note(npc["path"], new_content)
                if needs_normalization_repair:
                    logger.info(
                        "NPC mood self-healed: %s invalid=%r -> %s",
                        npc["name"], raw_mood, new_mood,
                    )
                else:
                    logger.info(
                        "NPC mood updated: %s %s -> %s",
                        npc["name"], current_mood, new_mood,
                    )
            except Exception as exc:
                logger.error("Mood write failed for %s: %s", npc["name"], exc)
                # Degrade per RESEARCH.md lines 1007-1012: keep reply, revert reported mood.
                new_mood = current_mood

        this_turn_replies.append({"npc": npc["name"], "reply": llm_result["reply"]})
        response_replies.append({
            "npc": npc["name"],
            "reply": llm_result["reply"],
            "mood_delta": llm_result["mood_delta"],
            "new_mood": new_mood,
        })

    # Step 6: Soft cap warning (D-18) — exact string per CONTEXT.md D-18.
    warning = None
    if len(scene_roster) >= 5:
        warning = f"⚠ {len(scene_roster)} NPCs in scene — consider splitting for clarity."

    return JSONResponse({"replies": response_replies, "warning": warning})
