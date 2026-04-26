"""NPC listing and Foundry actor fetch endpoints (Phase 36 — FVT-04).

Routes (GET, proxied from sentinel-core at /modules/pathfinder/npcs/...):
  GET /npcs/                       — list all NPCs as [{name, slug, level, ancestry}]
  GET /npcs/{slug}/foundry-actor   — return PF2e actor JSON for a single NPC

Module-level `obsidian` variable is set by main.py lifespan so tests can patch it directly.
"""
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.routes.npc import (
    _NPC_PATH_PREFIX,
    _build_foundry_actor,
    _parse_frontmatter,
    _parse_stats_block,
    slugify,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/npcs")

# Module-level ObsidianClient instance — set by main.py lifespan, patchable in tests.
obsidian = None


@router.get("/")
async def list_npcs() -> JSONResponse:
    """Return [{name, slug, level, ancestry}] for all NPCs in the vault (FVT-04)."""
    paths = await obsidian.list_directory(_NPC_PATH_PREFIX)
    npcs = []
    for path in paths:
        if not path.endswith(".md"):
            continue
        note_text = await obsidian.get_note(path)
        if note_text is None:
            continue
        fields = _parse_frontmatter(note_text)
        name = fields.get("name")
        if not name:
            continue
        npcs.append({
            "name": name,
            "slug": slugify(name),
            "level": fields.get("level", 1),
            "ancestry": fields.get("ancestry", ""),
        })
    return JSONResponse(npcs)


@router.get("/{slug}/foundry-actor")
async def get_foundry_actor(slug: str) -> JSONResponse:
    """Return PF2e actor JSON for the NPC identified by slug (FVT-04).

    Returns 400 if slug contains path-traversal characters (T-PATH mitigation).
    Returns 404 if no NPC note exists for the slug.
    """
    # Path traversal guard — slugify strips to [a-z0-9-]; any other characters → 400
    safe_slug = slugify(slug)
    if safe_slug != slug:
        raise HTTPException(status_code=400, detail={"error": "invalid slug"})
    path = f"{_NPC_PATH_PREFIX}/{safe_slug}.md"
    note_text = await obsidian.get_note(path)
    if note_text is None:
        raise HTTPException(status_code=404, detail={"error": "NPC not found", "slug": slug})
    fields = _parse_frontmatter(note_text)
    stats = _parse_stats_block(note_text)
    actor = _build_foundry_actor(fields, stats)
    return JSONResponse(actor)
