---
phase: 32-monster-harvesting
plan: 04
subsystem: pathfinder-routes
tags: [harvest, fastapi, pydantic, apirouter, lifespan, registration, cache-aside]

# Dependency graph
requires:
  - phase: 32-monster-harvesting
    provides: app.harvest helpers (Plan 32-03), generate_harvest_fallback (Plan 32-03), harvest-tables.yaml seed (Plan 32-02), 17 RED tests scaffolded (Plan 32-01)
provides:
  - modules/pathfinder/app/routes/harvest.py — POST /harvest router + 4 Pydantic models + _validate_monster_name + cache-aside handler
  - modules/pathfinder/app/main.py — lifespan extended, harvest_router included, REGISTRATION_PAYLOAD grew to 13 routes, docstring updated
  - 17 additional Wave-0 RED tests flipped GREEN (14 route-level in test_harvest.py + 3 integration in test_harvest_integration.py)
  - 24/24 harvest tests GREEN (21 unit + 3 integration); Wave-0 progress: 24/31 stubs GREEN (7 remaining live in interfaces/discord — Plan 32-05)
affects: [32-05-bot-dispatch]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "POST route wired via APIRouter(prefix='/harvest') with a single `@router.post('')` handler (mirrors routes/npc.py §3 Analog B)"
    - "Module-level singletons `obsidian` and `harvest_tables` assigned by main.py lifespan, patched directly in tests via `patch('app.routes.harvest.*')` (PATTERNS.md §3 Analog D)"
    - "Cache-aside with anti-pattern guard: cache-miss LLM failure raises 500 AND does not write cache (RESEARCH §Anti-Patterns)"
    - "Cache PUT graceful degrade: put_note exception logged WARNING, result still returned 200 (D-03b)"
    - "Footer attribution wording: `Source — FoundryVTT pf2e` | `Source — LLM generated (verify)` | `Mixed sources — N seed / M generated` (D-04)"
    - "Single-Write discipline for main.py: Write whole file so imports + usages land atomically (ruff strips unpaired additions, hook re-ran once per Edit)"
    - "Plan 32-03 `patch_frontmatter_field` literal banned from route file — documented in-file as 'the PATCH frontmatter helper' to satisfy acceptance grep AND preserve the prohibition intent"

key-files:
  created:
    - modules/pathfinder/app/routes/harvest.py (225 lines — router, 4 Pydantic models, _validate_monster_name, _build_from_seed, _build_footer, async harvest handler)
    - .planning/phases/32-monster-harvesting/32-04-route-and-registration-SUMMARY.md (this file)
  modified:
    - modules/pathfinder/app/main.py (+22 / -4 lines — 4 imports, lifespan extension, REGISTRATION_PAYLOAD 13th entry, app.include_router(harvest_router), docstring line)

key-decisions:
  - "Route prefix is `/harvest` with a bare `@router.post('')` (NOT `/harvest/` with `@router.post('/harvest')`). FastAPI concatenates prefix + path literally — the NPC router uses `/npc` + `/create` etc., but `/harvest` is a single verb, so an empty path inside the router is idiomatic and matches the test client's `POST /harvest` expectation."
  - "Model resolution (`resolve_model('chat')`) runs ONCE per request, outside the per-name loop, because the task kind is identical for every monster in a batch. Reduces LM Studio model-discovery chatter on batch requests."
  - "`api_base = settings.litellm_api_base or None` — passes None when the env var is blank so litellm falls back to its own default; tests patch `generate_harvest_fallback` directly so this branch is never exercised in tests but still correct in production."
  - "`_harvest_module.harvest_tables = load_harvest_tables(Path(__file__).parent.parent / 'data' / 'harvest-tables.yaml')` uses an __file__-relative path rather than cwd-relative — resilient to container WORKDIR changes and test runners that chdir."
  - "AI Deferral Ban scan grep hits ONE line in the module docstring that literally explains the ban (`no TODO/pass/NotImplementedError`). Same documentation pattern Plan 32-03 established in app/harvest.py — accepted as documentation prose, not deferral."

requirements-completed: [HRV-01, HRV-02, HRV-03, HRV-04, HRV-05, HRV-06]

# Metrics
duration: ~18 min
completed: 2026-04-24
---

# Phase 32 Plan 04: Route + Registration Summary

**POST /harvest wired end-to-end: new `app/routes/harvest.py` (225 lines) with cache-aside handler + 4 Pydantic models + input sanitiser; `app/main.py` lifespan extended to load the 160-monster seed and assign module singletons; REGISTRATION_PAYLOAD grown to 13 routes. All 17 remaining Wave-0 RED tests flipped GREEN (14 route unit + 3 integration); 84/84 pathfinder tests pass; no Phase 29/30/31 regressions.**

## Performance

- **Duration:** ~18 min
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 modified)
- **Total lines added:** 247 (225 harvest.py + 22 main.py net delta)

## Accomplishments

- `modules/pathfinder/app/routes/harvest.py` (NEW, 225 lines): `APIRouter(prefix="/harvest")`, 4 Pydantic models (`HarvestRequest`, `CraftableOut`, `ComponentOut`, `MonsterHarvestOut`), `_validate_monster_name` mirroring `_validate_npc_name` (control-char reject, 100-char cap), `_build_from_seed` + `_build_footer` route-local helpers, async `harvest(req)` handler implementing the full cache-aside flow (GET cache → seed lookup → LLM fallback → PUT cache).
- `modules/pathfinder/app/main.py` (+22 / -4): new imports (`Path`, `load_harvest_tables`, `harvest_router`, `_harvest_module`), lifespan assigns `_harvest_module.obsidian = obsidian_client` and `_harvest_module.harvest_tables = load_harvest_tables(__file__-relative path)` before yield (None after), `app.include_router(harvest_router)` added below the NPC router include, REGISTRATION_PAYLOAD gains the harvest entry (13th route), docstring gains the `POST /harvest` line.
- **17 Wave-0 RED tests flipped GREEN:**
  - 14 in `test_harvest.py`: `test_harvest_single_seed_hit`, `test_harvest_components_have_craftable`, `test_harvest_medicine_dc_present`, `test_harvest_batch_aggregated`, `test_harvest_fuzzy_match_returns_note`, `test_harvest_fuzzy_below_threshold_falls_to_llm`, `test_harvest_llm_fallback_marks_generated`, `test_harvest_cache_hit_skips_llm`, `test_harvest_cache_write_on_miss`, `test_harvest_cache_write_failure_degrades`, `test_harvest_empty_names_422`, `test_harvest_missing_names_key_422`, `test_harvest_invalid_name_control_char`, `test_harvest_batch_cap_enforced`
  - 3 in `test_harvest_integration.py`: `test_first_query_writes_cache_second_reads_cache`, `test_seed_hit_writes_cache_with_source_seed`, `test_batch_mixed_sources_footer`
- **Harvest test totals:** 21 unit + 3 integration = 24/24 GREEN (plan text cited "20 passed" — actual is 21 because `test_rapidfuzz_importable` counts as unit).
- **Full pathfinder suite:** 84/84 GREEN — zero Phase 29/30/31 regressions.

## Critical Gates Verified

### Cache-miss LLM failure anti-pattern guard
Reproduced and verified via standalone integration smoke:
- LLM raises `Exception("model down")`
- Handler raises `HTTPException(500, {"error": "LLM fallback failed", "detail": "model down"})`
- `obsidian.put_note.await_count == 0` (cache NOT written — retry on next call)

### Cache-write failure graceful degrade
Verified via `test_harvest_cache_write_failure_degrades`:
- `put_note` raises `Exception("obsidian down")`
- Handler still returns 200 with populated `monsters` payload
- WARNING log emitted mentioning "cache" or "harvest"

### Cache path format
Verified via `test_harvest_cache_write_on_miss`:
- `put_note` called once
- `call_args[0][0] == "mnemosyne/pf2e/harvest/boar.md"` (namespaced prefix + slugify)

### Seed-only vs LLM-only vs mixed footer
Verified via `test_harvest_llm_fallback_marks_generated` (footer contains "generated") and `test_batch_mixed_sources_footer` (footer contains `"1 seed"` and `"1 generated"`).

### Registration payload count
13 routes present with the harvest entry — verified via automated smoke:
```
SENTINEL_API_KEY=test uv run python -c "from app.main import REGISTRATION_PAYLOAD; assert len(REGISTRATION_PAYLOAD['routes']) == 13 and any(r['path'] == 'harvest' for r in REGISTRATION_PAYLOAD['routes']); print('REGISTRATION OK')"
→ REGISTRATION OK
```

### Live ASGI smoke against real 160-monster seed
```
SENTINEL_API_KEY=test ... POST /harvest {"names": ["Wolf"], "user_id": "u1"}
→ 200, monsters[0].source == "seed", monsters[0].level == 1, cache write logged
```

## Task Commits

Each task was committed atomically on main:

1. **Task 32-04-01** (feat): `69fd7e1` — add app/routes/harvest.py — POST /harvest handler + 4 Pydantic models
2. **Task 32-04-02** (feat): `c7ed378` — wire POST /harvest into main.py lifespan + REGISTRATION_PAYLOAD

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Acceptance Compliance] `patch_frontmatter_field` literal appeared in two docstring/comment lines**
- **Found during:** Task 32-04-01 acceptance grep (`grep -F 'patch_frontmatter_field' ... returns 0 matches`).
- **Issue:** The initial file contained the literal string `patch_frontmatter_field` twice — once in the module docstring and once in an inline comment — both stating the prohibition ("never patch_frontmatter_field"). The plan's acceptance rule is a strict grep-equals-0 check, which does not distinguish code use from documentation prose that mentions the banned symbol.
- **Fix:** Reworded both mentions to "the PATCH frontmatter helper" / "the PATCH helper". Prohibition intent preserved (the docstring still explicitly forbids the PATCH route); literal grep now returns 0.
- **Files modified:** `modules/pathfinder/app/routes/harvest.py` (pre-commit, same commit as the initial Write).
- **Commit:** `69fd7e1`

**2. [Rule 3 — Blocking] Post-Edit hook stripped unpaired main.py imports**
- **Found during:** Task 32-04-02 initial Edit that added imports without simultaneously wiring them into usage.
- **Issue:** A post-Edit ruff hook reformatted `app/main.py` immediately after my first Edit landed the new imports (`Path`, `load_harvest_tables`, `harvest_router`, `_harvest_module`). Because my first Edit only added the imports and the docstring — not the actual lifespan wiring or `include_router` call — ruff's unused-import rule removed all four new imports silently. This is the exact scenario PATTERNS.md §5 Gotcha 2 anticipates ("ruff strips unpaired additions"). 32-03's SUMMARY documented the identical behaviour on app/llm.py.
- **Fix:** Replaced the file with a single `Write` call that contained imports + lifespan bindings + `include_router` + REGISTRATION_PAYLOAD entry + docstring line atomically. One-pass landing keeps ruff from seeing an unused-import window.
- **Files modified:** `modules/pathfinder/app/main.py`
- **Commit:** `c7ed378`

### Text-consistency Note (not a deviation)

- Plan smoke test text states "20 passed" for `test_harvest.py`; actual count is 21 because `test_rapidfuzz_importable` is a unit test collected from the same file. Plan text appears to have undercounted by excluding rapidfuzz smoke (which was the first Wave-0 stub, flipped GREEN in Plan 32-02). No impact on acceptance — all 21 are GREEN.

## Authentication Gates

None — all execution was local (pytest + ruff against host venv; integration smoke patched the registration call).

## Issues Encountered

None that required human intervention. Both auto-fixes were inline Rule 1 / Rule 3 resolutions.

## Verification

### Plan verification block (5/5 PASS)

```
=== 1. all 21 unit tests GREEN ===               21 passed
=== 2. all 3 integration tests GREEN ===          3 passed
=== 3. full pathfinder suite (no regressions) === 84 passed
=== 4. REGISTRATION_PAYLOAD has 13 routes +harvest === REGISTRATION OK
=== 5. No PATCH in harvest handler ===            PASS — no `patch_frontmatter_field` in harvest handler
=== 6. AI Deferral Ban ===                        PASS (one doc-prose mention of the rule; zero TODO/FIXME/NotImplementedError as code)
```

### Acceptance greps (Task 32-04-01)

- `grep -E '^router = APIRouter\(prefix="/harvest"' app/routes/harvest.py` → 1 match
- `grep -cE '^class (HarvestRequest|CraftableOut|ComponentOut|MonsterHarvestOut)\(BaseModel\)' app/routes/harvest.py` → 4
- `grep -E '^async def harvest\(req: HarvestRequest\)' app/routes/harvest.py` → 1 match
- `grep -F 'from app.routes.npc import slugify' app/routes/harvest.py` → 1 match
- `grep -F 'from app.llm import generate_harvest_fallback' app/routes/harvest.py` → 1 match
- `grep -F 'from app.harvest import' app/routes/harvest.py` → 1 match
- `grep -cF 'HARVEST_CACHE_PATH_PREFIX' app/routes/harvest.py` → 2 (import + use)
- `grep -cF 'patch_frontmatter_field' app/routes/harvest.py` → 0
- `grep -F 'obsidian.put_note' app/routes/harvest.py` → 1 match
- `grep -F 'obsidian.get_note' app/routes/harvest.py` → 1 match
- `grep -F 'Mixed sources —' app/routes/harvest.py` → 1 match
- `grep -F 'Source — FoundryVTT pf2e' app/routes/harvest.py` → 1 match

### Acceptance greps (Task 32-04-02)

- `grep -F '"harvest"' app/main.py` → 1 match (REGISTRATION_PAYLOAD entry)
- `grep -cF '"Monster harvest report with Medicine/Crafting DCs and vendor values (HRV-01..06)"' app/main.py` → 1
- `grep -E '^\s*POST /harvest' app/main.py` → 1 match (docstring)
- `grep -F 'import app.routes.harvest as _harvest_module' app/main.py` → 1 match
- `grep -F '_harvest_module.obsidian = obsidian_client' app/main.py` → 1 match
- `grep -F '_harvest_module.harvest_tables = load_harvest_tables' app/main.py` → 1 match
- `grep -F '_harvest_module.obsidian = None' app/main.py` → 1 match
- `grep -F '_harvest_module.harvest_tables = None' app/main.py` → 1 match
- `grep -F 'app.include_router(harvest_router)' app/main.py` → 1 match
- `grep -F 'from app.harvest import load_harvest_tables' app/main.py` → 1 match
- `grep -F 'from app.routes.harvest import router as harvest_router' app/main.py` → 1 match

### Structural sanity checks

- `app/routes/harvest.py` line count: 225
- `app/main.py` line count: 150 (was 136, +14 net after imports, docstring line, REGISTRATION entry, lifespan 3-line extension, include_router line)
- `uv run ruff check app/routes/harvest.py app/main.py` → All checks passed!

## User Setup Required

None — the 160-monster YAML is already present at `modules/pathfinder/data/harvest-tables.yaml` (Plan 32-02); all deps (rapidfuzz, pyyaml, pydantic, fastapi) are in `uv.lock` (Plan 32-02 / 32-03). Plan 32-05 will wire the Discord bot side.

## Next Phase Readiness

- **Plan 32-05 (bot dispatch + embed) unblocked.** The HTTP layer is complete; Discord wiring (verb dispatch for `:pf harvest <name>[, <name>...]` + `build_harvest_embed` + noun-widen regression guard) is the last piece. The 7 `test_pf_harvest_*` stubs in `interfaces/discord/tests/test_subcommands.py` remain RED awaiting Plan 32-05.
- **Wave-0 progress:** 24/31 stubs GREEN (rapidfuzz + format_price ×3 + fuzzy ×2 + invalid_yaml + 14 route + 3 integration). The remaining 7 all live in the discord interface and flip with Plan 32-05.
- **No container rebuild needed for Plan 32-05** — no new dependencies were added in this plan; the pf2e-module container already includes rapidfuzz from Plan 32-02.

## Self-Check: PASSED

**Created files exist:**
- `modules/pathfinder/app/routes/harvest.py` — FOUND (225 lines)
- `.planning/phases/32-monster-harvesting/32-04-route-and-registration-SUMMARY.md` — FOUND (this file)

**Modified files verified:**
- `modules/pathfinder/app/main.py` — MODIFIED (+22 / -4 lines; REGISTRATION_PAYLOAD length 13; harvest router included)

**Commits exist:**
- `69fd7e1` — FOUND (feat(32-04): add app/routes/harvest.py — POST /harvest handler + 4 Pydantic models)
- `c7ed378` — FOUND (feat(32-04): wire POST /harvest into main.py lifespan + REGISTRATION_PAYLOAD)

## TDD Gate Compliance

This plan has Task 32-04-01 marked `tdd="true"`. The RED tests were scaffolded by Plan 32-01 (17 route + integration tests); this plan lands GREEN for all 17 simultaneously. No separate REFACTOR commit was required — the route handler lands correct on its first commit and survives the main.py wiring without modification.

**Gate sequence in git log:**
- RED commits: `e62d56c` + `563f191` (Plan 32-01 — test_harvest.py + test_harvest_integration.py stubs)
- GREEN commits: `69fd7e1` + `c7ed378` (this plan)

---
*Phase: 32-monster-harvesting*
*Completed: 2026-04-24*
