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
import json
import logging
import re

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from app.llm import extract_npc_fields, update_npc_fields
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/npc")

# Module-level ObsidianClient instance — set by main.py lifespan, patchable in tests.
obsidian = None

# NPC vault path prefix (D-16)
_NPC_PATH_PREFIX = "mnemosyne/pf2e/npcs"

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


class NPCRelateRequest(BaseModel):
    name: str
    relation: str
    target: str


class NPCImportRequest(BaseModel):
    actors_json: str  # raw JSON string fetched from Discord attachment URL
    user_id: str


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
        # Find the closing --- delimiter
        end = note_text.index("---", 3)
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
    try:
        fields = await extract_npc_fields(
            name=req.name,
            description=req.description,
            model=settings.litellm_model,
            api_base=settings.litellm_api_base or None,
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
    try:
        changed = await update_npc_fields(
            current_note=note_text,
            correction=req.correction,
            model=settings.litellm_model,
            api_base=settings.litellm_api_base or None,
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
