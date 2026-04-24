---
phase: 32-monster-harvesting
plan: 01
subsystem: testing
tags: [pytest, pytest-asyncio, fastapi, rapidfuzz, discord.py, tdd, red-phase]

# Dependency graph
requires:
  - phase: 31-dialogue-engine
    provides: Wave-0 RED scaffolding pattern (31-01 — 26 stubs across 3 files, StatefulMockVault, import-protection rule)
  - phase: 28-pf2e-module-skeleton
    provides: ASGITransport+AsyncClient test harness, module-level obsidian singleton pattern, _register_with_retry patch
provides:
  - 21 unit stubs at modules/pathfinder/tests/test_harvest.py (HRV-01..06, D-02 fuzzy, D-03b cache, format_price, YAML schema, security caps)
  - 3 integration stubs at modules/pathfinder/tests/test_harvest_integration.py (StatefulMockVault round-trip; seed→cache; mixed-source footer)
  - 7 test_pf_harvest_* stubs in interfaces/discord/tests/test_subcommands.py (solo, batch, multi-word, trimmed commas, usage, embed shape, noun widen)
  - Test contract for Waves 1-3 — every symbol referenced (app.harvest.*, app.routes.harvest.*, app.llm.generate_harvest_fallback, bot.build_harvest_embed) is now documented by a failing test
affects: [32-02-dependency-seed-scaffold, 32-03-harvest-helpers, 32-04-route-handler, 32-05-bot-dispatch]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Import-protection rule — not-yet-existing symbols imported INSIDE test bodies so collection succeeds while run fails (inherits 31-01)"
    - "patch.object(bot._sentinel_client, \"post_to_module\", ...) — bot-layer dispatch test pattern (PATTERNS §10 Gotcha 1)"
    - "StatefulMockVault — in-memory vault for observing cache write-through round-trips (copied verbatim from 31 integration tests)"
    - "asyncio_mode=auto — bare `async def test_*` with no @pytest.mark.asyncio decorator"

key-files:
  created:
    - modules/pathfinder/tests/test_harvest.py (21 unit stubs)
    - modules/pathfinder/tests/test_harvest_integration.py (3 integration stubs)
  modified:
    - interfaces/discord/tests/test_subcommands.py (appended 7 test_pf_harvest_* stubs)

key-decisions:
  - "test_rapidfuzz_importable placed in test_harvest.py — will flip GREEN when Plan 32-02 adds the dep + uv sync runs"
  - "Cache-hit source assertion permits {\"cache\", \"seed\"} per PATTERNS §8 Gotcha 2 (planner picks source disposition in Plan 32-04)"
  - "test_invalid_yaml_raises asserts pytest.raises(Exception) rather than ValidationError specifically — allows Plan 32-03 to wrap Pydantic errors if desired without reworking the test"
  - "test_harvest_batch_cap_enforced uses 21 names (cap=20) — locks in MAX_BATCH_NAMES constant regardless of planner's choice of exactly-at-cap vs over-cap rejection boundary"

patterns-established:
  - "RED scaffolding first (Wave 0) → downstream waves implement against explicit test contract"
  - "Zero production code in Wave 0 — `git log --stat` diff is entirely under tests/"
  - "Stubs use substantive assertions (not `assert True` or `pass`) so each test diagnoses a specific missing behaviour when it flips GREEN"

requirements-completed: []

# Metrics
duration: ~15min
completed: 2026-04-24
---

# Phase 32 Plan 01: RED Test Stubs Summary

**31 failing test stubs scaffolding HRV-01..06 + D-02 fuzzy + D-03b cache + D-04 aggregation + security caps — every symbol Waves 1-3 must land is now documented by a named failing test.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-24T01:30:00Z
- **Completed:** 2026-04-24T01:45:21Z
- **Tasks:** 3
- **Files modified:** 3 (2 created, 1 appended)

## Accomplishments

- `modules/pathfinder/tests/test_harvest.py` — 21 unit stubs covering HRV-01..06, D-02 fuzzy boundary (Alpha Wolf vs Wolf Lord), D-03b cache hit/miss/degrade, format_price (single/mixed/empty), YAML schema validator, and security caps (empty names, missing key, control chars, batch cap 20)
- `modules/pathfinder/tests/test_harvest_integration.py` — 3 round-trip stubs with `StatefulMockVault` verbatim copy: first-query-writes-cache / second-query-reads-cache round trip, seed-hit writes `source: seed` frontmatter, batch mixed-sources footer (D-04)
- `interfaces/discord/tests/test_subcommands.py` — 7 `test_pf_harvest_*` stubs covering solo, batch, multi-word name preservation, trimmed-commas parsing, empty→usage string, embed-dict return shape, and noun-widen regression guard
- All 31 stubs collect cleanly (0 ImportError) and fail on run (31/31 RED) — honest signal for Waves 1-3

## Task Commits

Each task was committed atomically:

1. **Task 32-01-01:** Create test_harvest.py with 21 unit stubs — `e62d56c` (test)
2. **Task 32-01-02:** Create test_harvest_integration.py with 3 round-trip stubs — `563f191` (test)
3. **Task 32-01-03:** Append 7 test_pf_harvest_* stubs to test_subcommands.py — `8b38a25` (test)

## Files Created/Modified

- `modules/pathfinder/tests/test_harvest.py` (NEW, 514 lines) — 21 async unit tests + 5 pure-helper tests; env bootstrap; STUB_HARVEST_TABLE_DATA + CACHED_HARVEST_MD + _make_stub_tables fixtures
- `modules/pathfinder/tests/test_harvest_integration.py` (NEW, 195 lines) — 3 async integration tests; StatefulMockVault class copied verbatim from test_npc_say_integration.py
- `interfaces/discord/tests/test_subcommands.py` (MODIFIED, +146 lines) — 7 appended harvest dispatch tests; 27 pre-existing tests untouched

## Decisions Made

- **test_rapidfuzz_importable is a sync `def` (not `async def`)** because it exercises the Python import machinery, not the HTTP route — matches the scaffolding pattern for pure-helper tests (format_price, fuzzy_*, invalid_yaml).
- **test_harvest_cache_hit_skips_llm permits `source in {"cache", "seed"}`** — PATTERNS §8 Gotcha 2 notes the planner has latitude over whether Plan 32-04 returns "cache" or preserves the original frontmatter source. Test locks in the LLM-skip behaviour without over-constraining the field value.
- **test_pf_harvest_noun_recognised asserts via negation (`not result.startswith("Unknown pf category")`)** rather than asserting `post_to_module.called` — this lets the test flip GREEN the instant the noun widen lands, even before the full `harvest` branch is wired.
- **test_harvest_cache_write_failure_degrades uses caplog with permissive substring match** (`"cache" or "harvest"` in message) — lets Plan 32-04 choose its exact log wording without a test re-roll.

## Deviations from Plan

None — plan executed exactly as written. All 31 test names match 32-VALIDATION.md verbatim. All scaffolding contracts (env bootstrap, import-protection rule, patch targets, asyncio_mode bare `async def`) were honoured per PATTERNS §7, §8, §10.

## Issues Encountered

None — all three files collected and failed in a single iteration each. No auto-fixes required under Rules 1-3.

## Verification

### Collection (no ImportError)

```
cd modules/pathfinder && python -m pytest tests/test_harvest.py --collect-only -q
→ 21 tests collected in 0.08s

cd modules/pathfinder && python -m pytest tests/test_harvest_integration.py --collect-only -q
→ 3 tests collected in 0.03s

cd interfaces/discord && uv run --no-sync python -m pytest tests/test_subcommands.py -k 'harvest' --collect-only -q
→ 7/34 tests collected (27 deselected) in 0.01s
```

### RED (all 31 fail on run)

```
cd modules/pathfinder && python -m pytest tests/test_harvest.py tests/test_harvest_integration.py -q
→ 24 failed in 0.20s (21 unit + 3 integration)

cd interfaces/discord && uv run --no-sync python -m pytest tests/test_subcommands.py -k 'harvest' -q
→ 7 failed, 27 deselected in 0.15s
```

### Acceptance greps (per PLAN)

- `grep -cE '^(async )?def test_' tests/test_harvest.py` → 21 ✅
- `grep -c '^STUB_HARVEST_TABLE_DATA = '` → 1 ✅
- `grep -c '^CACHED_HARVEST_MD = '` → 1 ✅
- `grep -c '^def _make_stub_tables'` → 1 ✅
- `head -19 tests/test_harvest.py | grep -c "os.environ.setdefault"` → 6 ✅
- `grep -cE '^async def test_' tests/test_harvest_integration.py` → 3 ✅
- `grep -c 'class StatefulMockVault'` → 1 ✅
- `grep -cE '^async def test_pf_harvest_' tests/test_subcommands.py` → 7 ✅
- `grep -F "modules/pathfinder/harvest" tests/test_subcommands.py` → 3 matches ✅
- Pre-existing `test_pf_say_solo_dispatch` preserved → 1 ✅

**Failure reasons observed (honest RED):**
- `ModuleNotFoundError: No module named 'app.harvest'` (expected — Plan 32-03 lands this module)
- `AttributeError` on `app.routes.harvest.*` patch target (expected — Plan 32-04 lands this module)
- `"Unknown pf category \`harvest\`. Currently supported: \`npc\`."` (expected — Plan 32-05 widens the noun check)
- `test_rapidfuzz_importable` fails only if rapidfuzz wheel absent (will flip GREEN after Plan 32-02 `uv sync`)

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Wave 0 complete.** Waves 1-3 can now execute against an explicit test contract. Each downstream wave's "done" criterion is a subset of these 31 tests flipping GREEN:
  - **Plan 32-02** (rapidfuzz + seed YAML) flips `test_rapidfuzz_importable` GREEN.
  - **Plan 32-03** (app.harvest helpers) flips `test_format_price_*` (3), `test_fuzzy_*` (2), `test_invalid_yaml_raises` (1) GREEN.
  - **Plan 32-04** (route handler + integration) flips the remaining 15 route tests + 3 integration tests GREEN.
  - **Plan 32-05** (bot dispatch + embed) flips all 7 `test_pf_harvest_*` GREEN.
- **32-VALIDATION.md `wave_0_complete: true`** should be set after this plan merges (per VALIDATION.md note — human-editable field).

## Self-Check: PASSED

**Created files exist:**
- `modules/pathfinder/tests/test_harvest.py` — FOUND
- `modules/pathfinder/tests/test_harvest_integration.py` — FOUND
- `.planning/phases/32-monster-harvesting/32-01-red-test-stubs-SUMMARY.md` — FOUND (this file)

**Commits exist:**
- `e62d56c` — FOUND (test_harvest.py)
- `563f191` — FOUND (test_harvest_integration.py)
- `8b38a25` — FOUND (test_subcommands.py append)

---
*Phase: 32-monster-harvesting*
*Completed: 2026-04-24*
