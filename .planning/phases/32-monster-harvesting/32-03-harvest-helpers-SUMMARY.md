---
phase: 32-monster-harvesting
plan: 03
subsystem: pathfinder-helpers
tags: [harvest, pydantic, rapidfuzz, litellm, yaml, pure-transform, dc-clamp]

# Dependency graph
requires:
  - phase: 32-monster-harvesting
    provides: rapidfuzz 3.14.5 wheel (32-02), 160-monster harvest-tables.yaml seed (32-02), 24 RED test stubs (32-01)
provides:
  - modules/pathfinder/app/harvest.py — pure-transform helpers (4 Pydantic models + 4 constants + 7 helpers)
  - modules/pathfinder/app/llm.py extended with generate_harvest_fallback (DC clamp + stamps)
  - 6 Wave-0 RED tests flipped GREEN (test_format_price ×3, test_fuzzy_subset_matches, test_fuzzy_wolf_lord_falls_through, test_invalid_yaml_raises)
affects: [32-04-route-handler, 32-05-bot-dispatch]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-tier fuzzy seed lookup: exact normalized match -> head-noun anchor -> fuzz.ratio typo fallback (cutoff 85); deviates from RESEARCH.md's single-scorer token_set_ratio claim because token_set_ratio scores wolf-lord/wolf at 100 (subset), breaking the Pitfall 2 boundary test"
    - "Function-scope import (`from app.harvest import DC_BY_LEVEL` inside generate_harvest_fallback) to break app.llm -> app.harvest -> app.routes.npc -> app.llm module cycle"
    - "DC sanity clamp: post-parse overwrite of LLM-returned medicine_dc when level is known, logged WARNING — trust the table not the model"
    - "ORC attribution footer always emitted by build_harvest_markdown regardless of source (seed / cache / llm-generated)"
    - "Pure-transform discipline: no litellm, httpx, fastapi imports in app/harvest.py — I/O lives in app.routes.harvest (Plan 32-04) and app.llm (LLM layer)"

key-files:
  created:
    - modules/pathfinder/app/harvest.py (332 lines — Pydantic schema + YAML loader + fuzzy lookup + price formatter + markdown builder + aggregator + cache parser)
  modified:
    - modules/pathfinder/app/llm.py (+86 lines — generate_harvest_fallback + function-scope DC_BY_LEVEL import)

key-decisions:
  - "fuzz.ratio not fuzz.token_set_ratio — Rule 1 bug in plan's prescribed algorithm. token_set_ratio scores multi-word compounds where seed is a subset at 100 (e.g., 'wolf lord' vs 'wolf' = 100). fuzz.ratio's Levenshtein-derived score gives wolf-lord/wolf = 61.5 (below cutoff), satisfying the Pitfall 2 boundary."
  - "Head-noun anchor as Tier 2 before fuzz.ratio — catches 'alpha wolf' -> Wolf (head token exact match) before the conservative whole-string scorer runs, while still rejecting 'wolf lord' (head token 'lord' not in seeds)."
  - "DC_BY_LEVEL import inside function body — module-scope import deadlocks the app.llm/app.harvest/app.routes.npc cycle. Function-scope is the idiomatic Python cycle-break and keeps the plan's acceptance grep satisfied."
  - "slugify kept in __all__ of app.harvest — required by the plan's acceptance grep (`from app.routes.npc import slugify`) and signals that Plan 32-04 will call it from the same module for cache-path building."

requirements-completed: [HRV-01, HRV-02, HRV-03, HRV-04, HRV-05, HRV-06]

# Metrics
duration: ~12 min
completed: 2026-04-24
---

# Phase 32 Plan 03: Harvest Helpers + LLM Fallback Summary

**Pure-transform helper layer (app/harvest.py) and LLM fallback (app/llm.py::generate_harvest_fallback) shipped — 6 Wave-0 RED tests flipped GREEN; zero Phase 29/30/31 regressions; remaining 14 RED tests await Plan 32-04's route wiring.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 modified)
- **Total lines added:** 418 (332 harvest.py + 86 llm.py extension)

## Accomplishments

- `modules/pathfinder/app/harvest.py` (NEW, 332 lines): 4 Pydantic models (HarvestTable, MonsterEntry, HarvestComponent, CraftableItem), 4 module constants (FUZZY_SCORE_CUTOFF=85.0, HARVEST_CACHE_PATH_PREFIX, DC_BY_LEVEL keys 0-25, MAX_BATCH_NAMES=20), 7 helpers (load_harvest_tables, normalize_name, lookup_seed, format_price, build_harvest_markdown, _aggregate_by_component, _parse_harvest_cache).
- `modules/pathfinder/app/llm.py` (+86 lines): `generate_harvest_fallback` appended. Signature matches S2 (`model`, `api_base: str | None = None`). System prompt embeds the full DC-by-level table (levels 0-25, every level) + sample equipment vendor values. Post-parse stamps `source='llm-generated'` + `verified=False` and clamps mismatched `medicine_dc` against DC_BY_LEVEL[level].
- 6 Wave-0 RED tests flipped GREEN:
  - `test_format_price_single_denom`
  - `test_format_price_mixed_currency`
  - `test_format_price_empty_dict`
  - `test_fuzzy_subset_matches` (alpha wolf -> Wolf with "Matched to closest" note)
  - `test_fuzzy_wolf_lord_falls_through` (wolf lord -> None, below cutoff)
  - `test_invalid_yaml_raises` (Pydantic ValidationError on malformed YAML)
- Zero Phase 29/30/31 regressions (60 non-harvest tests green).

## Public Surface Exported by app.harvest

**Pydantic models:** `HarvestTable`, `MonsterEntry`, `HarvestComponent`, `CraftableItem`

**Constants:**
- `FUZZY_SCORE_CUTOFF: float = 85.0`
- `HARVEST_CACHE_PATH_PREFIX: str = "mnemosyne/pf2e/harvest"`
- `MAX_BATCH_NAMES: int = 20`
- `DC_BY_LEVEL: dict[int, int]` (26 entries, keys 0-25)

**Helpers:**
- `load_harvest_tables(path: Path) -> HarvestTable` — fail-fast YAML loader
- `normalize_name(raw: str) -> str` — lowercase + strip articles
- `lookup_seed(query, tables, threshold=85.0) -> tuple[MonsterEntry | None, str | None]` — two-tier fuzzy seed lookup
- `format_price(value: dict | None) -> str` — Foundry price dict -> "N gp M sp K cp"
- `build_harvest_markdown(result: dict) -> str` — Obsidian cache note with ORC footer
- `_aggregate_by_component(per_monster: list[dict]) -> list[dict]` — cross-monster component grouping
- `_parse_harvest_cache(note_text: str, name: str) -> dict | None` — log-and-degrade cache reader

**Re-exported:** `slugify` (from app.routes.npc) via `__all__`

## LLM Fallback Contract (app.llm.generate_harvest_fallback)

**Signature:** `async def generate_harvest_fallback(monster_name: str, model: str, api_base: str | None = None) -> dict`

**System prompt grounds the LLM in:**
- Full DC-by-level table (levels 0-25 verbatim — every level listed as "Level N: DC X")
- Sample craftable vendor values (Leather armor 2 gp, Dagger 2 sp, Torch 1 cp, Healing potion 12 gp, Antidote 10 gp, Poison 12 gp)
- JSON-only output contract with fixed keys (monster, level, components[])

**Post-parse processing:**
1. `parsed["source"] = "llm-generated"` — SC-4 / T-32-LLM-01 mitigation
2. `parsed["verified"] = False` — signals DM must confirm before finalising
3. DC sanity clamp: for each component, if parsed `level` is in DC_BY_LEVEL and `medicine_dc != DC_BY_LEVEL[level]`, log WARNING and overwrite (Pitfall 4)
4. Raises `json.JSONDecodeError` on malformed output — Plan 32-04's route catches and returns 500 (no salvage)

**Smoke test proves clamp fires:** input `{level: 15, medicine_dc: 33}` -> output `medicine_dc: 34` (DC_BY_LEVEL[15] = 34), WARNING logged.

## Task Commits

Each task was committed atomically on main:

1. **Task 32-03-01** (feat): `42d7dda` — add app/harvest.py pure-transform helpers
2. **Task 32-03-02** (feat): `e1bde6f` — add generate_harvest_fallback to app/llm.py

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] RESEARCH.md's fuzzy-match recommendation was factually wrong**
- **Found during:** Task 32-03-01 smoke-testing rapidfuzz scorer behavior before writing `lookup_seed`.
- **Issue:** The plan (via RESEARCH §Fuzzy-Match Recommendation lines 226-237) prescribes `fuzz.token_set_ratio` with `score_cutoff=85.0` and claims `token_set_ratio("wolf lord", "wolf") ≈ 80` (below cutoff) and `token_set_ratio("goblin", "hobgoblin") = 77`. These claims are factually incorrect. Actual rapidfuzz 3.14.5 scores: `token_set_ratio("wolf", "wolf lord") = 100` (exact subset match), `token_set_ratio("goblin", "hobgoblin") = 80`. Under the prescribed scorer, `test_fuzzy_wolf_lord_falls_through` is unreachable — every variant `X wolf` matches Wolf at 100. **Every single rapidfuzz scorer tested** (ratio, partial_ratio, token_sort_ratio, token_set_ratio, WRatio, QRatio, partial_token_sort_ratio, partial_token_set_ratio) gave identical scores for `alpha wolf/wolf` and `wolf lord/wolf`, so no single scorer + cutoff can distinguish them.
- **Fix:** Implemented a two-tier policy inside `lookup_seed`:
  1. Exact normalized-name match -> (entry, None).
  2. Head-noun anchor: if the last whitespace-separated token of the query (after normalisation) is exactly a seed name, return that seed with a "Matched to closest" note. Rationale: in English compound nouns the head noun is last — "alpha wolf" has head "wolf" (matches); "wolf lord" has head "lord" (no seed named "lord", fails).
  3. Typo-tolerant fallback: `fuzz.ratio` (not `token_set_ratio`) on the whole normalised query at cutoff 85. `fuzz.ratio` is Levenshtein-derived and penalises insertions, so `wolfe->wolf = 88.9` (matches, catches typos) while `wolf lord->wolf = 61.5` (rejected) and `hobgoblin->goblin = 80.0` (rejected).
- **Files modified:** `modules/pathfinder/app/harvest.py` — `lookup_seed` docstring documents the deviation inline.
- **Commit:** `42d7dda`
- **Tests affected:** The deviation is precisely what flips `test_fuzzy_subset_matches` and `test_fuzzy_wolf_lord_falls_through` from RED to GREEN simultaneously — the RED tests pin the correct behavior, which the plan's prescribed algorithm could not produce.

**2. [Rule 3 — Blocking] app.llm -> app.harvest -> app.routes.npc -> app.llm circular import**
- **Found during:** Task 32-03-02 smoke test after landing the module-level `from app.harvest import DC_BY_LEVEL` in app/llm.py.
- **Issue:** Module load order deadlocked:
  1. `import app.llm` starts
  2. `app.llm` executes `from app.harvest import DC_BY_LEVEL`
  3. `app.harvest` executes `from app.routes.npc import slugify`
  4. `app.routes.npc` executes `from app.llm import build_mj_prompt, extract_npc_fields, ...`
  5. `app.llm` is still partially initialised -> `ImportError: cannot import name 'build_mj_prompt'`
- **Fix:** Moved `from app.harvest import DC_BY_LEVEL` inside the `generate_harvest_fallback` function body. Idiomatic Python cycle-break. Import cost is negligible (post-first-call, the import is cached in `sys.modules`). Plan's acceptance grep still matches (the string is present in the file).
- **Files modified:** `modules/pathfinder/app/llm.py`
- **Commit:** `e1bde6f` (both the function body and the cycle-break land in the same commit)

### Additional Notes

- **Post-write formatter interaction:** A ruff hook reformatted `app/llm.py` between edits, stripping unused module-scope imports. The fix was to land the function body AND the import in a single Write operation so ruff saw the import as used. This is the exact scenario the plan anticipated ("If the import lands alone, ruff strips it").
- **`# noqa` / `# type: ignore` count:** 0 in both files. Plan's Blocker-1 invariant honoured.
- **AI Deferral Ban scan:** The only grep hit on "TODO|FIXME|NotImplementedError" in either file is a docstring line in `app/harvest.py` that literally explains the AI Deferral Ban rule ("no TODO/pass/NotImplementedError") — documentation prose, not suppression or deferral.

## Authentication Gates

None — execution was entirely local (pytest + ruff against host venv).

## Issues Encountered

None that required human intervention. Both deviations were auto-fixed inline under Rule 1 / Rule 3.

## Verification

### 7-step plan verification (from `<verification>` block)

```
=== 1. All new symbols importable ===       all symbols OK (len(DC_BY_LEVEL)=26)
=== 2. 6 Wave-0 unit tests flip GREEN ===   6 passed, 15 deselected
=== 3. Remaining RED tests still fail ===   14 failed, 7 passed (target)
=== 4. AI Deferral Ban scan ===             PASS (only docstring mention)
=== 5. No # noqa / # type: ignore ===       0 / 0
=== 6. Pure-transform discipline ===        grep -cE '^(from|import) (litellm|httpx|fastapi)' = 0
=== 7. No Phase 29/30/31 regressions ===    60 passed, 24 deselected
```

### Acceptance greps (Task 32-03-01)

- `grep -E '^class HarvestTable\(BaseModel\)' app/harvest.py` -> 1 match
- `grep -cE '^class (MonsterEntry|HarvestComponent|CraftableItem)\(BaseModel\)' app/harvest.py` -> 3
- `grep -F 'FUZZY_SCORE_CUTOFF: float = 85.0' app/harvest.py` -> 1 match
- `grep -F 'HARVEST_CACHE_PATH_PREFIX: str = "mnemosyne/pf2e/harvest"' app/harvest.py` -> 1 match
- `grep -F 'MAX_BATCH_NAMES: int = 20' app/harvest.py` -> 1 match
- `grep -F 'from app.routes.npc import slugify' app/harvest.py` -> 1 match
- `grep -F 'yaml.safe_load' app/harvest.py` -> 2 matches (loader + cache parser); zero bare `yaml.load(`
- `grep -E '^def (normalize_name|lookup_seed|build_harvest_markdown|_aggregate_by_component|_parse_harvest_cache)\(' app/harvest.py` -> 5 matches
- `grep -F 'process.extractOne' app/harvest.py` -> 1 match (rapidfuzz used)
- `grep -F 'score_cutoff=threshold' app/harvest.py` -> 1 match
- `grep -F 'datetime.datetime.now(datetime.UTC)' app/harvest.py` -> 1 match (non-deprecated)
- `grep -F '⚠ Generated' app/harvest.py` -> 1 match
- `grep -F 'Matched to closest entry:' app/harvest.py` -> 1 match
- `grep -F 'ORC license' app/harvest.py` -> 1 match; `grep -F 'FoundryVTT pf2e system' app/harvest.py` -> 1 match (Info 1 footer)
- `grep -cE '# (noqa|type: ignore)' app/harvest.py` -> 0
- `grep -cE '^(from|import) (litellm|httpx|fastapi)' app/harvest.py` -> 0

### Acceptance greps (Task 32-03-02)

- `grep -E '^async def generate_harvest_fallback\(' app/llm.py` -> 1 match
- `grep -F 'from app.harvest import DC_BY_LEVEL' app/llm.py` -> 1 match
- `grep -F 'timeout": 60.0' app/llm.py` -> 4 occurrences (non-zero across functions)
- `grep -F 'kwargs["api_base"] = api_base' app/llm.py` -> 4 occurrences (S2 conditional pattern)
- `grep -F '_strip_code_fences' app/llm.py` -> 5 occurrences
- Full DC table 0-25 verbatim:
  - `grep -F 'Level 0: DC 14' app/llm.py` -> 1
  - `grep -F 'Level 10: DC 27' app/llm.py` -> 1
  - `grep -F 'Level 15: DC 34' app/llm.py` -> 1
  - `grep -F 'Level 20: DC 40' app/llm.py` -> 1
  - `grep -F 'Level 25: DC 50' app/llm.py` -> 1
  - `grep -F 'Level 10: DC 27, Level 11: DC 28' app/llm.py` -> 1 (adjacency — continuous 0-25 chain)
- `grep -F 'parsed["source"] = "llm-generated"' app/llm.py` -> 1 match
- `grep -F 'parsed["verified"] = False' app/llm.py` -> 1 match
- `grep -F 'DC_BY_LEVEL[level]' app/llm.py` -> 1 match (clamp)

### Structural sanity checks

- `app/harvest.py` line count: 332
- `app/llm.py` line count: 306 (was 221, +85 net — the function body + its cycle-break import + one blank line)
- Ruff check on both files: **All checks passed**

## User Setup Required

None — no external services, no new env vars, no migrations. Plan 32-04 will wire the route handler and register the harvest module in app/main.py.

## Next Phase Readiness

- **Plan 32-04 (route handler + integration) unblocked.** All helpers it needs (`load_harvest_tables`, `lookup_seed`, `format_price`, `build_harvest_markdown`, `_aggregate_by_component`, `_parse_harvest_cache`, `HARVEST_CACHE_PATH_PREFIX`, `MAX_BATCH_NAMES`, `generate_harvest_fallback`) are now exported.
- **Wave-0 progress:** 7 of 31 RED tests GREEN (1 from 32-02 rapidfuzz + 6 from 32-03). Remaining 24 RED tests distribute as:
  - 14 route-level tests in `test_harvest.py` (Plan 32-04)
  - 3 integration tests in `test_harvest_integration.py` (Plan 32-04)
  - 7 bot-dispatch tests in `test_subcommands.py` (Plan 32-05)
- **No container rebuild needed** — the rapidfuzz wheel was already pulled in by Plan 32-02's `uv sync`. Plan 32-04's route wiring will hit `docker compose build pf2e-module` once only if it introduces new deps.

## Self-Check: PASSED

**Created files exist:**
- `modules/pathfinder/app/harvest.py` — FOUND (332 lines)
- `.planning/phases/32-monster-harvesting/32-03-harvest-helpers-SUMMARY.md` — FOUND (this file)

**Modified files verified:**
- `modules/pathfinder/app/llm.py` — MODIFIED (+85 lines; `generate_harvest_fallback` present at line 227; cycle-break import at function body)

**Commits exist:**
- `42d7dda` — FOUND (feat(32-03): add app/harvest.py pure-transform helpers)
- `e1bde6f` — FOUND (feat(32-03): add generate_harvest_fallback to app/llm.py)

## TDD Gate Compliance

This plan is `type: tdd` with both tasks marked `tdd="true"`. The RED tests were scaffolded by Plan 32-01 (`test_harvest.py`, 21 unit stubs); Plan 32-03 executes the GREEN phase — 6 previously-RED tests flip GREEN as proof the implementation matches the contract. No REFACTOR commit required — the helpers land complete in their initial form (single-Write discipline per Blocker 1).

**Gate sequence in git log:**
- RED commit: `e62d56c` (Plan 32-01 — test(32-01): scaffold test_harvest.py with 21 RED stubs)
- GREEN commits: `42d7dda` + `e1bde6f` (Plan 32-03, this plan)

---
*Phase: 32-monster-harvesting*
*Completed: 2026-04-24*
