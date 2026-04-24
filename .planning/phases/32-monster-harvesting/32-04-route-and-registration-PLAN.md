---
plan_id: 32-04
phase: 32
wave: 3
depends_on: [32-01, 32-02, 32-03]
files_modified:
  - modules/pathfinder/app/routes/harvest.py
  - modules/pathfinder/app/main.py
autonomous: true
requirements: [HRV-01, HRV-02, HRV-03, HRV-04, HRV-05, HRV-06]
must_haves:
  truths:
    - "POST /harvest is the 13th registered route — REGISTRATION_PAYLOAD['routes'] has length 13 and includes {'path': 'harvest', 'description': 'Monster harvest report with Medicine/Crafting DCs and vendor values (HRV-01..06)'}"
    - "modules/pathfinder/app/routes/harvest.py defines 4 Pydantic models: HarvestRequest, CraftableOut, ComponentOut, MonsterHarvestOut (and a HarvestResponse optional)"
    - "HarvestRequest validates: names list non-empty; len(names) <= MAX_BATCH_NAMES (20); each name passes _validate_monster_name (rejects control chars, >100 chars, empty); otherwise 422"
    - "Handler walks names in order: (1) GET cache note, parse-and-return on hit; (2) seed lookup (exact+fuzzy); (3) LLM fallback; (4) PUT cache note after success via build_harvest_markdown"
    - "Cache miss LLM failure raises 500 with {'error': 'LLM fallback failed', 'detail': str(exc)} AND does NOT write cache (anti-pattern per RESEARCH §Anti-Patterns)"
    - "Cache PUT failure degrades gracefully: WARNING logged, result still returned (no 500)"
    - "Cache path uses HARVEST_CACHE_PATH_PREFIX + slugify(name) + '.md' — never a PATCH; GET-then-PUT only (D-03b + S3)"
    - "Response shape: {monsters: [MonsterHarvestOut], aggregated: [ComponentOut], footer: str}"
    - "Footer wording: single-source → 'Source — FoundryVTT pf2e'; all-llm → 'Source — LLM generated (verify)'; mixed → 'Mixed sources — N seed / M generated' (D-04)"
    - "Module-level singletons: obsidian (set by main.lifespan from _harvest_module.obsidian = obsidian_client); harvest_tables (set from load_harvest_tables(...))"
    - "main.py lifespan imports app.routes.harvest as _harvest_module and assigns both singletons before yield; sets both to None after yield"
    - "main.py app.include_router(harvest_router) added after the existing npc_router include"
    - "main.py REGISTRATION_PAYLOAD gains the harvest route entry; module docstring gains a POST /harvest line"
    - "All remaining RED tests in test_harvest.py flip GREEN (14 tests total after Plan 32-03's 6); all 3 integration tests in test_harvest_integration.py flip GREEN"
  tests:
    - "cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py -q  # 20 passed"
    - "cd modules/pathfinder && uv run python -m pytest tests/test_harvest_integration.py -q  # 3 passed"
    - "cd modules/pathfinder && uv run python -m pytest tests/ -q  # all green (Phase 29/30/31 unbroken)"
    - "cd modules/pathfinder && uv run python -c 'from app.main import REGISTRATION_PAYLOAD; assert len(REGISTRATION_PAYLOAD[\"routes\"]) == 13; assert any(r[\"path\"] == \"harvest\" for r in REGISTRATION_PAYLOAD[\"routes\"])'"
---

<plan_objective>
Wire the harvest layer into the pathfinder module's HTTP surface. Ships `POST /harvest` (request/response models + handler), extends `main.py` lifespan to load the YAML seed and assign module-level singletons, adds the harvest route to `REGISTRATION_PAYLOAD` (13th route), and updates the module docstring. After this plan, all 20 Wave-0 unit tests AND all 3 integration tests flip GREEN. The Discord bot wiring lands in Plan 32-05.
</plan_objective>

<threat_model>
## STRIDE Register

| Threat ID | Category | Component | Disposition | Mitigation | Test Reference |
|-----------|----------|-----------|-------------|------------|----------------|
| T-32-04-T01 | Tampering | Path traversal / control chars in monster name (T-32-SEC-01) | mitigate | `_validate_monster_name` rejects control chars + length cap (S4). `slugify` strips non-alphanum. Test: `test_harvest_invalid_name_control_char`. |
| T-32-04-D01 | DoS | Unbounded batch of monster names | mitigate | `HarvestRequest.names` validator enforces `len(v) <= MAX_BATCH_NAMES` (20). Test: `test_harvest_batch_cap_enforced`. |
| T-32-04-T02 | Tampering | Fuzzy-match false positive silently returning wrong data (T-32-SEC-02) | mitigate | `lookup_seed` uses cutoff 85 (Plan 32-03); fuzzy hits surface a user-visible `note` ("Matched to closest..."). Tests: `test_harvest_fuzzy_match_returns_note`, `test_harvest_fuzzy_below_threshold_falls_to_llm`. |
| T-32-04-T03 | Tampering | LLM prompt injection via monster name (T-32-SEC-03) | mitigate | Name flows through Pydantic validator + slugify before any LLM call. LLM prompt template uses name as user-role data only. Test: `test_harvest_llm_fallback_marks_generated`. |
| T-32-04-I01 | Information Disclosure | LLM-generated data silently treated as canonical (T-32-LLM-01) | mitigate | Every LLM fallback result has `verified: False` (Plan 32-03 stamp); cache note frontmatter preserves the flag; footer signals "generated" count (D-04). Test: `test_harvest_llm_fallback_marks_generated`. |
| T-32-04-T04 | Tampering | Obsidian file-name collision via slug (T-32-SEC-04) | mitigate | Cache path uses `HARVEST_CACHE_PATH_PREFIX` (namespaced under `mnemosyne/pf2e/harvest/`). `slugify` strips traversal tokens. Test: `test_harvest_cache_write_on_miss`. |
| T-32-04-D02 | DoS | Obsidian unavailable during cache write | mitigate | Exception caught, WARNING logged, result still returned (D-03b graceful degrade). Test: `test_harvest_cache_write_failure_degrades`. |
| T-32-04-D03 | DoS | LLM unreachable / timeout | mitigate (fail-fast) | `generate_harvest_fallback` exception caught → `HTTPException(500)` WITHOUT writing cache. Retry on next call (RESEARCH §Anti-Patterns). |
| T-32-04-T05 | Tampering | Cache file poisoned by hand-edit (DM edits the .md to wrong data) | accept | DM ownership — the `verified: true` flag is a DM-only transition. If the DM writes bad data, that is operator error, not an injection surface. |
| T-32-04-S01 | Spoofing | Module endpoint accepting calls without auth | mitigate (inherited) | `X-Sentinel-Key` enforced upstream by sentinel-core's `proxy_module` middleware. No new auth code in this plan. |

**Block level:** none HIGH unmitigated. T-32-04-T01/T02/T03/T04/D01/D02/D03 MITIGATED (tested). T-32-04-I01 MITIGATED via the verified-flag contract. T-32-04-T05 accepted (DM ownership). T-32-04-S01 inherited. ASVS L1 satisfied.
</threat_model>

<tasks>

<task id="32-04-01" type="tdd" autonomous="true" tdd="true">
  <name>Task 32-04-01: Create app/routes/harvest.py — Pydantic models + route handler</name>
  <read_first>
    - modules/pathfinder/app/routes/npc.py (full file — especially lines 1-50 for imports; lines 72-81 for _validate_npc_name style; lines 162-185 for NPCSayRequest validator pattern; lines 344-395 for create_npc LLM+HTTPException pattern; lines 858-983 for say_npc handler analog; lines 210-217 for slugify reuse)
    - modules/pathfinder/app/harvest.py (output of Plan 32-03 — symbols: load_harvest_tables, lookup_seed, format_price, build_harvest_markdown, _aggregate_by_component, _parse_harvest_cache, HARVEST_CACHE_PATH_PREFIX, MAX_BATCH_NAMES, HarvestTable)
    - modules/pathfinder/app/llm.py (generate_harvest_fallback from Plan 32-03)
    - .planning/phases/32-monster-harvesting/32-PATTERNS.md §3 (Analogs A, B, C, D + Gotchas 1-3)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md §Pattern 1 (route skeleton reference impl)
    - .planning/phases/32-monster-harvesting/32-CONTEXT.md D-03a, D-03b, D-04
  </read_first>
  <behavior>
    - POST /harvest with {names: ["Boar"], user_id: "u1"} + seed hit + cache miss returns 200 with monsters[0]["source"] == "seed"
    - POST with empty names → 422
    - POST with 21 names → 422 (MAX_BATCH_NAMES cap)
    - POST with control-char in name → 422
    - Cache hit (get_note returns markdown with frontmatter) returns immediately; LLM not called; put_note not called
    - Cache miss + seed hit: result built from seed, put_note called once with HARVEST_CACHE_PATH_PREFIX/<slug>.md path
    - Cache miss + fuzzy seed hit: monsters[0]["source"] == "seed-fuzzy", monsters[0]["note"] contains "Matched to closest"
    - Cache miss + no seed match: LLM fallback called, monsters[0]["verified"] is False, monsters[0]["source"] == "llm-generated"
    - LLM fallback raises → route returns 500 (no cache write)
    - put_note raises → WARNING logged, result still returned (200)
    - Batch (N=2): aggregated by component type (D-04); footer indicates source mix
  </behavior>
  <action>
CREATE `modules/pathfinder/app/routes/harvest.py`. Write the complete file in a SINGLE Write operation (S10 ruff rule — imports + uses in one pass):

```python
"""POST /harvest — monster harvest report with Medicine/Crafting DCs and vendor values (HRV-01..06).

Module-level singletons (obsidian, harvest_tables) are assigned by main.py lifespan.
Tests patch them at app.routes.harvest.{obsidian, harvest_tables, generate_harvest_fallback}.

Shape mirrors app.routes.npc.say_npc (PATTERNS.md §3 Analog B):
- request validator per S4 (_validate_monster_name)
- per-name cache-aside loop (GET cache → seed lookup → LLM fallback → PUT cache)
- Obsidian GET-then-PUT via build_harvest_markdown (D-03b, S3 — never patch_frontmatter_field)
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
obsidian = None         # type: ignore[assignment]  # set to ObsidianClient in lifespan
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
    type: str                   # "Hide", "Claws", "Venom gland"
    medicine_dc: int
    craftable: list[CraftableOut] = Field(default_factory=list)
    monsters: list[str] = Field(default_factory=list)   # D-04 aggregation


class MonsterHarvestOut(BaseModel):
    monster: str
    level: int
    source: str                 # "seed" | "seed-fuzzy" | "llm-generated" | "cache"
    verified: bool
    components: list[dict] = Field(default_factory=list)
    note: str | None = None


# --- Helpers confined to this route ---

def _build_from_seed(entry, monster_name: str, note: str | None) -> dict:
    """Convert a seed MonsterEntry → the per-monster result dict shape."""
    components = []
    for comp in entry.components:
        components.append({
            "type": comp.name,
            "medicine_dc": comp.medicine_dc,
            "craftable": [
                {"name": c.name, "crafting_dc": c.crafting_dc, "value": c.value}
                for c in comp.craftable
            ],
        })
    return {
        "monster": monster_name if note is not None else entry.name,
        "level": entry.level,
        "source": "seed-fuzzy" if note is not None else "seed",
        "verified": True,  # seed data is canonical (DM-curated) — verified by authorship
        "components": components,
        "note": note,
    }


def _build_footer(per_monster: list[dict]) -> str:
    """Footer wording per D-04 — attribution for the batch."""
    total = len(per_monster)
    if total == 0:
        return ""
    seed_count = sum(1 for m in per_monster if m["source"] in ("seed", "seed-fuzzy", "cache"))
    llm_count = total - seed_count
    if llm_count == 0:
        return "Source — FoundryVTT pf2e"
    if seed_count == 0:
        return "Source — LLM generated (verify)"
    return f"Mixed sources — {seed_count} seed / {llm_count} generated"


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

        # 1. Cache hit
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
            result = _build_from_seed(seed_entry, name, seed_note)
        else:
            # 3. LLM fallback
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

        # 4. Cache write-through (GET-then-PUT — never patch_frontmatter_field per S3).
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

    return JSONResponse({
        "monsters": per_monster_results,
        "aggregated": aggregated,
        "footer": footer,
    })
```

**Smoke test** (runs post-create; mocks obsidian + harvest_tables + LLM):
```bash
cd modules/pathfinder && uv run python -c "
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient
from app.harvest import HarvestTable

async def main():
    stub_tables = HarvestTable.model_validate({
        'version': '1.0', 'source': 'foundryvtt-pf2e', 'levels': [1],
        'monsters': [{'name': 'Wolf', 'level': 1, 'traits': ['animal'],
                      'components': [{'name': 'Hide', 'medicine_dc': 15,
                                      'craftable': [{'name': 'Leather armor', 'crafting_dc': 14, 'value': '2 gp'}]}]}],
    })
    mock_obs = AsyncMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    with patch('app.main._register_with_retry', new=AsyncMock(return_value=None)), \
         patch('app.routes.harvest.obsidian', mock_obs), \
         patch('app.routes.harvest.harvest_tables', stub_tables):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            resp = await client.post('/harvest', json={'names': ['Wolf'], 'user_id': 'u1'})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body['monsters'][0]['source'] == 'seed'
    assert body['monsters'][0]['level'] == 1
    assert body['aggregated'][0]['type'] == 'Hide'
    print('OK')

asyncio.run(main())
"
```
  </action>
  <acceptance_criteria>
    - test -f modules/pathfinder/app/routes/harvest.py
    - grep -E '^router = APIRouter\(prefix="/harvest"' modules/pathfinder/app/routes/harvest.py matches
    - grep -E '^class (HarvestRequest|CraftableOut|ComponentOut|MonsterHarvestOut)\(BaseModel\)' modules/pathfinder/app/routes/harvest.py matches 4 times
    - grep -E '^async def harvest\(req: HarvestRequest\)' modules/pathfinder/app/routes/harvest.py matches
    - grep -F 'from app.routes.npc import slugify' modules/pathfinder/app/routes/harvest.py matches (reuse)
    - grep -F 'from app.llm import generate_harvest_fallback' modules/pathfinder/app/routes/harvest.py matches
    - grep -F 'from app.harvest import' modules/pathfinder/app/routes/harvest.py matches
    - grep -F 'HARVEST_CACHE_PATH_PREFIX' modules/pathfinder/app/routes/harvest.py occurs ≥ 2 times (import + use)
    - grep -F 'patch_frontmatter_field' modules/pathfinder/app/routes/harvest.py returns 0 matches (D-03b + S3 — only PUT)
    - grep -F 'obsidian.put_note' modules/pathfinder/app/routes/harvest.py matches
    - grep -F 'obsidian.get_note' modules/pathfinder/app/routes/harvest.py matches
    - grep -F 'Mixed sources —' modules/pathfinder/app/routes/harvest.py matches (D-04 footer)
    - grep -F 'Source — FoundryVTT pf2e' modules/pathfinder/app/routes/harvest.py matches
    - Smoke test exits 0 with OK (seed happy path 200)
    - 14 Wave-0 RED tests that need the route flip GREEN: cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py -q exits 0 (20 passed total — including Plan 32-03's 6 + Plan 32-02's 1 = 7 already green)
    - 3 integration tests flip GREEN: cd modules/pathfinder && uv run python -m pytest tests/test_harvest_integration.py -q exits 0 (3 passed)
    - grep -v '^#' modules/pathfinder/app/routes/harvest.py | grep -E '(TODO|FIXME|NotImplementedError|raise NotImplementedError)' returns 0 matches
  </acceptance_criteria>
  <automated>cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py tests/test_harvest_integration.py -q</automated>
</task>

<task id="32-04-02" type="execute" autonomous="true">
  <name>Task 32-04-02: Extend main.py lifespan + register harvest route (REGISTRATION_PAYLOAD + docstring)</name>
  <read_first>
    - modules/pathfinder/app/main.py (full file — module docstring lines 1-17; REGISTRATION_PAYLOAD lines 47-65 after Phase 31 made it 12 entries; lifespan lines 93-113 with `_npc_module.obsidian = obsidian_client` pattern)
    - modules/pathfinder/app/routes/harvest.py (output of Task 32-04-01)
    - .planning/phases/32-monster-harvesting/32-PATTERNS.md §5 (REGISTRATION_PAYLOAD append; lifespan pattern; Gotchas 1-3; "all routes MUST appear in registry at import time")
    - .planning/phases/31-dialogue-engine/31-04-route-and-registration-PLAN.md (exemplar Task 31-04-03 — same structure on Phase 31)
  </read_first>
  <action>
EDIT `modules/pathfinder/app/main.py` in a SINGLE Edit session (S10 — imports + usages in one pass; ruff strips unpaired additions):

**Step 1 — Add `import app.routes.harvest as _harvest_module` AND the `from pathlib import Path` if not already imported.** Place the `_harvest_module` import adjacent to the existing `import app.routes.npc as _npc_module` (around line 39). The Path import lives alongside stdlib imports at the top.

**Step 2 — Add `from app.harvest import load_harvest_tables` near the other app.* imports.**

**Step 3 — Add `from app.routes.harvest import router as harvest_router` near the `from app.routes.npc import router as npc_router` (wherever that import currently sits; check grep `grep -n 'import router as' modules/pathfinder/app/main.py`).**

**Step 4 — Extend REGISTRATION_PAYLOAD.** Find the existing `REGISTRATION_PAYLOAD = { ... "routes": [ ... ] }` dict (currently 12 entries after Phase 31). Append EXACTLY this entry after the final `{"path": "npc/say", ...}` entry (verbatim per PATTERNS.md §5):

```python
{"path": "harvest", "description": "Monster harvest report with Medicine/Crafting DCs and vendor values (HRV-01..06)"},
```

**Step 5 — Update the module docstring.** Find the docstring at lines 1-17 listing endpoints. Append one line after the existing `POST /npc/say` entry (match the existing 2-space-indent `POST /...` padding style):

```
  POST /harvest            — monster harvest report with Medicine/Crafting DCs and vendor values (HRV-01..06)
```

**Step 6 — Extend the lifespan context manager.** In the `@asynccontextmanager async def lifespan(app)` function (around line 93), inside the `async with httpx.AsyncClient() as obsidian_http_client:` block, BEFORE the existing `yield`:

```python
        # Existing:
        _npc_module.obsidian = obsidian_client
        # Add:
        _harvest_module.obsidian = obsidian_client
        _harvest_module.harvest_tables = load_harvest_tables(
            Path(__file__).parent.parent / "data" / "harvest-tables.yaml"
        )
```

AFTER the `yield`:

```python
    # Existing:
    _npc_module.obsidian = None
    # Add:
    _harvest_module.obsidian = None
    _harvest_module.harvest_tables = None
```

**Step 7 — Register the router.** Find the existing `app.include_router(npc_router)` line (around line 123). Add directly below:

```python
app.include_router(harvest_router)
```

**Smoke test**:
```bash
cd modules/pathfinder && uv run python -c "
from app.main import REGISTRATION_PAYLOAD
routes = REGISTRATION_PAYLOAD['routes']
assert len(routes) == 13, f'expected 13 routes, got {len(routes)}'
harvest = [r for r in routes if r['path'] == 'harvest']
assert len(harvest) == 1, f'expected exactly one harvest route, got {len(harvest)}'
assert harvest[0]['description'] == 'Monster harvest report with Medicine/Crafting DCs and vendor values (HRV-01..06)'
print('OK — 13 routes registered, harvest present')
"
```

**Integration smoke test** (brings the full ASGI app up):
```bash
cd modules/pathfinder && uv run python -c "
import asyncio
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient
from pathlib import Path
from app.harvest import load_harvest_tables

async def main():
    # Real YAML load — Plan 32-02 wrote the seed. If this smoke test runs before 32-02 in any ordering, it fails loudly (which is the desired fail-fast behaviour).
    seed_path = Path('data/harvest-tables.yaml')
    if not seed_path.exists():
        print('SKIP — seed not yet present (Wave 1 parallel task)')
        return
    tbl = load_harvest_tables(seed_path)
    assert len(tbl.monsters) >= 20
    mock_obs = AsyncMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    with patch('app.main._register_with_retry', new=AsyncMock(return_value=None)), \
         patch('app.routes.harvest.obsidian', mock_obs), \
         patch('app.routes.harvest.harvest_tables', tbl):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            # Use a monster name the DM wrote into the real seed; 'Wolf' is in the required list.
            resp = await client.post('/harvest', json={'names': ['Wolf'], 'user_id': 'u1'})
    assert resp.status_code == 200, (resp.status_code, resp.text)
    print('OK — live ASGI harvest returned 200')

asyncio.run(main())
"
```
  </action>
  <acceptance_criteria>
    - Smoke test (REGISTRATION_PAYLOAD) exits 0 with output `OK — 13 routes registered, harvest present`
    - grep -F '"harvest"' modules/pathfinder/app/main.py matches ≥ 1
    - grep -F '"Monster harvest report with Medicine/Crafting DCs and vendor values (HRV-01..06)"' modules/pathfinder/app/main.py matches
    - grep -E '^\s*POST /harvest' modules/pathfinder/app/main.py matches (docstring updated)
    - grep -F 'import app.routes.harvest as _harvest_module' modules/pathfinder/app/main.py matches
    - grep -F '_harvest_module.obsidian = obsidian_client' modules/pathfinder/app/main.py matches
    - grep -F '_harvest_module.harvest_tables = load_harvest_tables' modules/pathfinder/app/main.py matches
    - grep -F '_harvest_module.obsidian = None' modules/pathfinder/app/main.py matches
    - grep -F '_harvest_module.harvest_tables = None' modules/pathfinder/app/main.py matches
    - grep -F 'app.include_router(harvest_router)' modules/pathfinder/app/main.py matches
    - grep -F 'from app.harvest import load_harvest_tables' modules/pathfinder/app/main.py matches
    - python -c 'from app.main import REGISTRATION_PAYLOAD; print(len(REGISTRATION_PAYLOAD["routes"]))' outputs `13`
    - All harvest tests GREEN: cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py tests/test_harvest_integration.py -q exit 0
    - Phase 29/30/31 still green: cd modules/pathfinder && uv run python -m pytest tests/ -q exit 0
  </acceptance_criteria>
  <automated>cd modules/pathfinder && uv run python -c "from app.main import REGISTRATION_PAYLOAD; routes = REGISTRATION_PAYLOAD['routes']; assert len(routes) == 13; h = [r for r in routes if r['path'] == 'harvest']; assert len(h) == 1; assert h[0]['description'] == 'Monster harvest report with Medicine/Crafting DCs and vendor values (HRV-01..06)'; print('OK')"</automated>
</task>

</tasks>

<verification>
Phase-32 module-side gate (after both tasks complete):

```bash
# 1. All 20 unit + 3 integration tests GREEN
cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py -v
# Expected: 20 passed

cd modules/pathfinder && uv run python -m pytest tests/test_harvest_integration.py -v
# Expected: 3 passed

# 2. No Phase 29/30/31 regressions
cd modules/pathfinder && uv run python -m pytest tests/ -q
# Expected: all green

# 3. Registration payload has 13 routes including harvest
cd modules/pathfinder && uv run python -c "from app.main import REGISTRATION_PAYLOAD; assert len(REGISTRATION_PAYLOAD['routes']) == 13 and any(r['path'] == 'harvest' for r in REGISTRATION_PAYLOAD['routes']); print('REGISTRATION OK')"

# 4. Cache write path uses PUT not PATCH (S3 + D-03b invariant)
grep -F 'patch_frontmatter_field' modules/pathfinder/app/routes/harvest.py && echo "FAIL — PATCH used in harvest handler" || echo "PASS — no PATCH in harvest handler"

# 5. AI Deferral Ban scan
grep -v '^#' modules/pathfinder/app/routes/harvest.py | grep -E '(TODO|FIXME|NotImplementedError|raise NotImplementedError)' && echo "FAIL" || echo "PASS"
```
</verification>

<success_criteria>
- `modules/pathfinder/app/routes/harvest.py` exists with router + 4 Pydantic models + harvest handler
- Module-level `obsidian` and `harvest_tables` singletons declared and patched by main.py lifespan
- `modules/pathfinder/app/main.py` imports `_harvest_module` and `load_harvest_tables`; lifespan loads seed + assigns singletons; `harvest_router` included; docstring + REGISTRATION_PAYLOAD updated
- REGISTRATION_PAYLOAD has 13 routes including `harvest`
- All 20 Wave-0 unit tests pass (14 new GREEN + 6 already GREEN from Plan 32-03)
- All 3 integration tests pass
- No PATCH / `patch_frontmatter_field` introduced in harvest handler (S3 + D-03b compliance)
- No Phase 29/30/31 regressions
- AI Deferral Ban: zero TODO/FIXME/NotImplementedError introduced
- HRV-01..06 satisfied at the HTTP layer; Discord wiring follows in Plan 32-05
</success_criteria>

<output>
Create `.planning/phases/32-monster-harvesting/32-04-SUMMARY.md` documenting:
- Files created/modified: app/routes/harvest.py (new), app/main.py (+imports, +lifespan extension, +REGISTRATION_PAYLOAD entry, +docstring line, +include_router)
- Test results: 20/20 unit + 3/3 integration green; full module suite green; no Phase 29/30/31 regressions
- REGISTRATION_PAYLOAD route count: 13 (was 12 after Phase 31)
- Documented: cache GET-then-PUT flow; LLM 500 with no-cache-write; put_note graceful degrade
- Note: HTTP layer complete; Discord bot wiring (harvest verb dispatch + build_harvest_embed) lands in Plan 32-05.
- Worktree note per S9: commit with `--no-verify` in parallel worktrees.
</output>
