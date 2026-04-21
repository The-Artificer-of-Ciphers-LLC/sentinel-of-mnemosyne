---
phase: 27-architecture-pivot
verified: 2026-04-21T02:00:00Z
status: human_needed
score: 12/12 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run `cd sentinel-core && pytest tests/test_modules.py -v` to confirm all 5 module gateway tests pass"
    expected: "5 passed, 0 failed"
    why_human: "Cannot run pytest in this environment; code review pass (7291637) may have introduced changes after the green run at 8e6d5df"
  - test: "Run `cd interfaces/discord && python -m pytest tests/ -q` to confirm all 8 Discord tests pass"
    expected: "8 passed, 0 failed"
    why_human: "Cannot run pytest; test files were modified in 2fc1e84 along with bot.py rename"
  - test: "Run `docker compose config` to confirm base stack starts without pi-harness"
    expected: "Exits 0, no pi-harness service in resolved config output"
    why_human: "Cannot run docker compose in this environment"
---

# Phase 27: Architecture Pivot Verification Report

**Phase Goal:** Architecture Pivot — remove Pi as a required dependency, implement Path B module gateway, rename /sentask to /sen, update all architecture documentation to Path B.
**Verified:** 2026-04-21T02:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | test_modules.py exists with 5 pytest-collectable async test stubs | ✓ VERIFIED | `grep -c "async def test_"` returns 5 at sentinel-core/tests/test_modules.py |
| 2 | POST /modules/register returns `{"status": "registered"}` (modules.py implements it) | ✓ VERIFIED | `router.post("/modules/register")` present in modules.py line 29; stores in module_registry |
| 3 | POST /modules/{name}/{path} proxies to registered module | ✓ VERIFIED | `@router.post("/modules/{name}/{path:path}")` present; `{path:path}` Starlette converter confirmed |
| 4 | Proxy returns 503 on ConnectError | ✓ VERIFIED | `except httpx.ConnectError:` raises HTTPException(status_code=503) in modules.py |
| 5 | Proxy returns 404 for unregistered module | ✓ VERIFIED | `if name not in registry: raise HTTPException(status_code=404)` in modules.py |
| 6 | modules router wired into main.py with module_registry in lifespan | ✓ VERIFIED | `from app.routes.modules import router as modules_router` (line 28), `app.state.module_registry = {}` (line 174), `app.include_router(modules_router)` (line 194) |
| 7 | Pi harness removed from base compose stack | ✓ VERIFIED | `grep "pi-harness" docker-compose.yml` returns 0 matches; no active include path |
| 8 | sentinel-core/compose.yml has no depends_on pi-harness | ✓ VERIFIED | `grep "depends_on" sentinel-core/compose.yml` returns 0 matches |
| 9 | pi-harness/compose.yml has profiles: [pi] | ✓ VERIFIED | `profiles: [pi]` present at line 5 of pi-harness/compose.yml |
| 10 | sentinel.sh has --pi flag wiring pi profile | ✓ VERIFIED | `--pi)         PROFILES+=("pi") ;;` at line 17, before `*)` catch-all at line 18 |
| 11 | Discord slash command registered as /sen (not /sentask) | ✓ VERIFIED | `@bot.tree.command(name="sen", ...)` at line 367; `name="sentask"` returns 0 matches |
| 12 | ARCHITECTURE-Core.md and PRD reflect Path B; no Pi-as-brain language | ✓ VERIFIED | `Pi.*brain\|brain.*Pi\|primary AI layer` returns 0 matches in both docs; `LiteLLM-direct` found in both; `POST /modules/register` in ARCHITECTURE-Core.md (5 matches); Path B ASCII diagram confirmed (`INTERFACE LAYER`, `MODULE CONTAINERS` present) |

**Score:** 12/12 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `sentinel-core/tests/test_modules.py` | 5 test stubs (RED gate) | ✓ VERIFIED | 5 async test functions; exists and substantive |
| `sentinel-core/app/routes/modules.py` | Module gateway router | ✓ VERIFIED | ModuleRegistration, ModuleRoute, register_module, proxy_module all present |
| `sentinel-core/app/main.py` | Wired module router + registry | ✓ VERIFIED | Import, lifespan init, include_router all confirmed |
| `docker-compose.yml` | Base compose without pi-harness include | ✓ VERIFIED | 0 active pi-harness references |
| `sentinel-core/compose.yml` | No depends_on pi-harness | ✓ VERIFIED | 0 depends_on or PI_HARNESS_URL matches |
| `pi-harness/compose.yml` | profiles: [pi] declared | ✓ VERIFIED | profiles: [pi] at line 5 |
| `sentinel.sh` | --pi flag present | ✓ VERIFIED | Line 17, before catch-all |
| `interfaces/discord/bot.py` | /sen command (not /sentask) | ✓ VERIFIED | name="sen" at line 367 |
| `docs/ARCHITECTURE-Core.md` | Path B canonical architecture doc | ✓ VERIFIED | LiteLLM-direct (6 matches), module contract (5+ matches), ASCII diagram present, 0 Pi-as-brain |
| `docs/PRD-Sentinel-of-Mnemosyne.md` | PRD with Path B AI layer description | ✓ VERIFIED | LiteLLM-direct present, Pi API call / Pi-as-brain: 0 matches |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| sentinel-core/app/main.py lifespan | app.state.module_registry | `app.state.module_registry = {}` | ✓ WIRED | Line 174 in main.py |
| sentinel-core/app/main.py | app/routes/modules.py | `app.include_router(modules_router)` | ✓ WIRED | Line 194 in main.py |
| sentinel.sh --pi flag | pi-harness/compose.yml profiles: [pi] | `PROFILES+=("pi")` → `docker compose --profile pi` | ✓ WIRED | sentinel.sh line 17 |
| bot.py @bot.tree.command | Discord API registration | `name="sen"` in tree.sync() | ✓ WIRED | Verified structurally; runtime sync is human-testable |
| docs/ARCHITECTURE-Core.md | sentinel-core/app/routes/modules.py | documents POST /modules/register contract | ✓ WIRED | 5+ occurrences of POST /modules/register in doc |

### Data-Flow Trace (Level 4)

Not applicable — this phase implements an API gateway (no data rendering). The module registry is in-memory by design. Tests verify the data flow at the unit level.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| test_modules.py has 5 tests | `grep -c "async def test_" sentinel-core/tests/test_modules.py` | 5 | ✓ PASS |
| modules.py exports ModuleRegistration | file exists with class def | confirmed | ✓ PASS |
| main.py wires module_registry | grep confirmed 3 insertion points | all 3 found | ✓ PASS |
| pi-harness removed from base stack | grep docker-compose.yml | 0 matches | ✓ PASS |
| Discord /sen registered | grep bot.py name="sen" | 1 match at line 367 | ✓ PASS |
| pytest test suite (full) | Cannot run without environment | N/A | ? SKIP |
| discord tests | Cannot run without environment | N/A | ? SKIP |

### Requirements Coverage

No REQUIREMENTS.md IDs were declared in any of the 5 plan frontmatter files for this phase (all plans have `requirements: []`). Phase 27 is an architecture pivot — the requirements it satisfies (removing Pi as a dependency, Path B gateway) were not pre-assigned requirement IDs in the REQUIREMENTS.md tracking system.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| sentinel-core/app/routes/modules.py | SSRF surface: `base_url` accepted from caller, used in outbound httpx proxy | ℹ️ Info | Accepted per T-27-03-01 — X-Sentinel-Key gates registration; local-network personal system; v1.0 CIDR validation flagged |

No TODO/FIXME/placeholder comments found in phase artifacts. No empty implementations. No stub anti-patterns.

### Human Verification Required

#### 1. Full pytest suite — sentinel-core

**Test:** `cd sentinel-core && pytest tests/test_modules.py -v && pytest -x`
**Expected:** 5 tests pass in test_modules.py; full suite exits 0 (131+ tests)
**Why human:** Cannot execute pytest in this verification environment. The code review commit `7291637` landed after the green run documented in 27-03-SUMMARY.md; need to confirm no regressions were introduced.

#### 2. Discord test suite

**Test:** `cd interfaces/discord && python -m pytest tests/ -q`
**Expected:** 8 tests pass, 0 failed
**Why human:** Cannot execute pytest. test_subcommands.py and test_thread_persistence.py were both modified in commit 2fc1e84 (sys.path fix + patch target fix); need runtime confirmation they pass.

#### 3. docker compose config baseline

**Test:** `docker compose config 2>&1 | grep -c "pi-harness"` from project root
**Expected:** 0 (pi-harness service absent from default resolved config)
**Why human:** Cannot run Docker Compose in this environment.

### Gaps Summary

No gaps found. All 12 observable truths verified against actual codebase artifacts. The three items routed to human verification are operational/runtime checks that cannot be performed programmatically in this environment — they are not code deficiencies.

---

_Verified: 2026-04-21T02:00:00Z_
_Verifier: Claude (gsd-verifier)_
