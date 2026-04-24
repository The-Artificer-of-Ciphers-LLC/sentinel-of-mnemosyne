"""POST /harvest — monster harvest report with Medicine/Crafting DCs and vendor values (HRV-01..06).

Module-level singletons (obsidian, harvest_tables) are assigned by main.py lifespan.
Tests patch them at app.routes.harvest.{obsidian, harvest_tables, generate_harvest_fallback}.

Shape mirrors app.routes.npc.say_npc (PATTERNS.md §3 Analog B):
- request validator per S4 (_validate_monster_name)
- per-name cache-aside loop (GET cache → seed lookup → LLM fallback → PUT cache)
- Obsidian GET-then-PUT via build_harvest_markdown (D-03b, S3 — never the PATCH frontmatter helper)
- LLM failure → 500 WITHOUT cache write; cache PUT failure → degrade gracefully
- Aggregation grouped by component type (D-04) returned in `aggregated` field

Per CLAUDE.md AI Deferral Ban: every helper completes its job; no TODO/pass/NotImplementedError.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.harvest import (
    HARVEST_CACHE_PATH_PREFIX,
    MAX_BATCH_NAMES,
    HarvestTable,
    _aggregate_by_component,
    _parse_harvest_cache,
    build_harvest_markdown,
    lookup_seed,
)
from app.llm import generate_harvest_fallback
from app.resolve_model import resolve_model
from app.routes.npc import slugify  # Don't Hand-Roll — reuse the existing slug fn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/harvest", tags=["harvest"])

# Module-level singletons — set by main.py lifespan, patchable in tests (PATTERNS.md §3 Analog D).
obsidian = None  # type: ignore[assignment]  # set to ObsidianClient in lifespan
harvest_tables: HarvestTable | None = None


# --- Input sanitiser (S4 — mirrors _validate_npc_name) ---


def _validate_monster_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("monster name cannot be empty")
    if len(v) > 100:
        raise ValueError("monster name too long (max 100 chars)")
    if re.search(r"[\x00-\x1f\x7f]", v):
        raise ValueError("monster name contains invalid control characters")
    # CR-01: slug must be non-empty so cache keys don't collide. Names like
    # "测试龙", "🐺", "...", "!@#$%" all slugify to "" and would otherwise share
    # the same cache path mnemosyne/pf2e/harvest/.md, cross-contaminating data.
    if not slugify(v):
        raise ValueError(
            "monster name must contain at least one ASCII alphanumeric character"
        )
    return v


# --- Pydantic models (PATTERNS.md §3 Analog A) ---


class HarvestRequest(BaseModel):
    """Request shape for POST /harvest (HRV-01, HRV-06)."""

    names: list[str]
    user_id: str = ""

    @field_validator("names")
    @classmethod
    def sanitize_names(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("at least one monster name required")
        if len(v) > MAX_BATCH_NAMES:
            raise ValueError(f"too many monsters (max {MAX_BATCH_NAMES})")
        return [_validate_monster_name(n) for n in v]


class CraftableOut(BaseModel):
    name: str
    crafting_dc: int
    value: str  # "2 gp" | "5 sp" | "3 cp" | "2 gp 5 sp"


class ComponentOut(BaseModel):
    type: str  # "Hide", "Claws", "Venom gland"
    medicine_dc: int
    craftable: list[CraftableOut] = Field(default_factory=list)
    monsters: list[str] = Field(default_factory=list)  # D-04 aggregation


class MonsterHarvestOut(BaseModel):
    monster: str
    level: int
    source: str  # "seed" | "seed-fuzzy" | "llm-generated" | "cache"
    verified: bool
    components: list[dict] = Field(default_factory=list)
    note: str | None = None


# --- Helpers confined to this route ---


def _build_from_seed(entry, monster_name: str, note: str | None) -> dict:
    """Convert a seed MonsterEntry → the per-monster result dict shape."""
    components = []
    for comp in entry.components:
        components.append(
            {
                "type": comp.name,
                "medicine_dc": comp.medicine_dc,
                "craftable": [
                    {"name": c.name, "crafting_dc": c.crafting_dc, "value": c.value}
                    for c in comp.craftable
                ],
            }
        )
    return {
        "monster": monster_name if note is not None else entry.name,
        "level": entry.level,
        "source": "seed-fuzzy" if note is not None else "seed",
        "verified": True,  # seed data is canonical (DM-curated) — verified by authorship
        "components": components,
        "note": note,
    }


def _build_footer(per_monster: list[dict]) -> str:
    """Footer wording per D-04 — attribution for the batch.

    IN-02: ORC license attribution is a legal requirement, not cosmetic.
    All three branches (all-seed / all-generated / mixed) now carry the
    FoundryVTT pf2e + Paizo + ORC attribution, so a DM inspecting a batch
    composed entirely of LLM-generated data still sees the upstream source
    citation.
    """
    total = len(per_monster)
    if total == 0:
        return ""
    seed_count = sum(
        1 for m in per_monster if m["source"] in ("seed", "seed-fuzzy", "cache")
    )
    llm_count = total - seed_count
    if llm_count == 0:
        return "Source — FoundryVTT pf2e (Paizo, ORC license)"
    if seed_count == 0:
        return (
            "Source — LLM generated (verify). "
            "Seed reference: FoundryVTT pf2e (Paizo, ORC license)"
        )
    return (
        f"Mixed sources — {seed_count} seed / {llm_count} generated. "
        f"Seed reference: FoundryVTT pf2e (Paizo, ORC license)"
    )


# --- Route handler ---


@router.post("")
async def harvest(req: HarvestRequest) -> JSONResponse:
    """Single or batch monster harvest lookup (HRV-01..06, D-02, D-03b, D-04).

    Per-name flow:
      1. Cache hit → parse and return (skip LLM + skip cache re-write).
      2. Seed lookup (exact → fuzzy via rapidfuzz cutoff 85).
      3. LLM fallback (Plan 32-03 generate_harvest_fallback) on miss.
      4. Cache write-through via build_harvest_markdown + put_note (GET-then-PUT).
    """
    if obsidian is None or harvest_tables is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "harvest subsystem not initialised"},
        )

    per_monster_results: list[dict] = []
    model_chat = await resolve_model("chat")
    api_base = settings.litellm_api_base or None

    for name in req.names:
        slug = slugify(name)
        cache_path = f"{HARVEST_CACHE_PATH_PREFIX}/{slug}.md"

        # 1. Cache hit (query-slug path — fast path for exact and LLM-fallback repeats).
        cached_text = await obsidian.get_note(cache_path)
        if cached_text is not None:
            parsed = _parse_harvest_cache(cached_text, name)
            if parsed is not None:
                per_monster_results.append(parsed)
                continue
            # Malformed cache: log and fall through to re-fetch.
            logger.warning("Harvest cache malformed for %s; re-fetching", name)

        # 2. Seed lookup
        seed_entry, seed_note = lookup_seed(name, harvest_tables)
        if seed_entry is not None:
            # WR-05: canonicalise fuzzy-match cache path to the seed's slug so
            # every variant that resolves to the same seed (Alpha Wolf, Wolves,
            # wolfe) shares a single cache file. DM hand-edits to the canonical
            # file then propagate to every future alias lookup. Exact-match
            # queries also cache under the seed slug — idempotent.
            canonical_slug = slugify(seed_entry.name)
            canonical_cache_path = f"{HARVEST_CACHE_PATH_PREFIX}/{canonical_slug}.md"
            # Re-check cache at canonical path when it differs from the query
            # slug — a prior fuzzy/exact hit may have already seeded it.
            if canonical_cache_path != cache_path:
                canonical_cached = await obsidian.get_note(canonical_cache_path)
                if canonical_cached is not None:
                    parsed = _parse_harvest_cache(canonical_cached, name)
                    if parsed is not None:
                        per_monster_results.append(parsed)
                        continue
            result = _build_from_seed(seed_entry, name, seed_note)
            cache_path = canonical_cache_path
        else:
            # 3. LLM fallback — failure MUST NOT write cache (RESEARCH §Anti-Patterns).
            # LLM-fallback continues to cache under the query slug (there is no
            # canonical entity to canonicalise against).
            try:
                result = await generate_harvest_fallback(
                    monster_name=name,
                    model=model_chat,
                    api_base=api_base,
                )
            except Exception as exc:
                logger.error("LLM harvest fallback failed for %s: %s", name, exc)
                raise HTTPException(
                    status_code=500,
                    detail={"error": "LLM fallback failed", "detail": str(exc)},
                )
            # Ensure the dict shape is consistent with seed results downstream.
            result.setdefault("note", None)

        # 4. Cache write-through (GET-then-PUT — never the PATCH helper per S3).
        try:
            cache_md = build_harvest_markdown(result)
            await obsidian.put_note(cache_path, cache_md)
            logger.info("Harvest cached: %s (source=%s)", name, result.get("source"))
        except Exception as exc:
            logger.warning("Harvest cache write failed for %s: %s", name, exc)
            # Degrade per D-03b — still return the result; next call retries cache.

        per_monster_results.append(result)

    # 5. Aggregate by component type (D-04)
    aggregated = _aggregate_by_component(per_monster_results)
    footer = _build_footer(per_monster_results)

    return JSONResponse(
        {
            "monsters": per_monster_results,
            "aggregated": aggregated,
            "footer": footer,
        }
    )
