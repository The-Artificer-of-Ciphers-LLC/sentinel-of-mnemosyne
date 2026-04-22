---
phase: 28-pf2e-module-skeleton-cors
verified: 2026-04-22T02:00:00Z
status: passed
score: 12/12 must-haves verified
overrides_applied: 0
---

# Phase 28: pf2e-module Skeleton + CORS Verification Report

**Phase Goal:** Stand up the pf2e-module FastAPI container, register it with Sentinel Core via the module gateway, and enable CORS for Foundry VTT browser fetch() calls.
**Verified:** 2026-04-22T02:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | CORSMiddleware active; OPTIONS preflight to /modules/pathfinder/healthz returns 200 with Access-Control-Allow-Origin (not 401) | VERIFIED | test_cors_preflight_returns_200 passes; main.py line 194 adds CORSMiddleware after APIKeyMiddleware (LIFO = outermost = runs first) |
| 2 | allow_origins never contains '*' — credential headers can be sent cross-origin | VERIFIED | test_cors_no_wildcard passes; config.py line 84 defaults to "http://localhost:30000" |
| 3 | GET /modules returns a JSON list of registered modules | VERIFIED | list_modules() in routes/modules.py line 41; test_get_modules_list and test_get_modules_list_empty both pass |
| 4 | GET /modules/{name}/{path} proxies to registered module via shared httpx client | VERIFIED | get_proxy_module() in routes/modules.py line 58; uses request.app.state.http_client.get(); test_get_proxy_module passes |
| 5 | CORS_ALLOW_ORIGINS and CORS_ALLOW_ORIGIN_REGEX configurable from env vars via pydantic-settings | VERIFIED | config.py lines 83-85 define cors_allow_origins and cors_allow_origin_regex fields on Settings; test_cors_regex_configured passes |
| 6 | pf2e-module /healthz returns {"status": "ok", "module": "pathfinder"} | VERIFIED | modules/pathfinder/app/main.py line 87; test_healthz_returns_ok passes |
| 7 | pf2e-module calls POST /modules/register at startup with correct payload and retries 5 times with 1s/2s/4s/8s/16s backoff before exiting | VERIFIED | _register_with_retry() in pathfinder/app/main.py; delays = [1, 2, 4, 8, 16]; SystemExit(1) on full failure; all 4 registration tests pass |
| 8 | pf2e-module Docker image builds from python:3.12-slim with FastAPI, uvicorn, httpx installed | VERIFIED | Dockerfile line 1: FROM python:3.12-slim; lines 9-12 install fastapi, uvicorn[standard], httpx |
| 9 | modules/pathfinder/compose.yml declares service pf2e-module with profile pf2e and depends_on sentinel-core service_healthy | VERIFIED | compose.yml lines 11, 16-17, 23-25 — service name pf2e-module, profiles: [pf2e], depends_on sentinel-core condition: service_healthy |
| 10 | pf2e-module unit tests pass without a running sentinel-core | VERIFIED | 5 tests pass in modules/pathfinder/tests/ using mocked httpx client; no real sentinel-core required |
| 11 | docker-compose.yml has active (uncommented) modules/pathfinder/compose.yml include; sentinel.sh --pf2e flag activates pf2e profile; --pathfinder case removed | VERIFIED | docker-compose.yml line 14 active include; sentinel.sh line 12: --pf2e) PROFILES+=("pf2e"); no pathfinder case found |
| 12 | CORS_ALLOW_ORIGINS and CORS_ALLOW_ORIGIN_REGEX documented in .env.example with defaults and wildcard warning | VERIFIED | .env.example lines 53-58 with defaults http://localhost:30000 and https://.*\.forge-vtt\.com; wildcard WARNING comment present |

**Score:** 12/12 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `sentinel-core/app/config.py` | CORS settings fields | VERIFIED | cors_allow_origins (line 84), cors_allow_origin_regex (line 85) |
| `sentinel-core/app/main.py` | CORSMiddleware wiring | VERIFIED | Import line 19, add_middleware lines 194-201, LIFO ordering confirmed (line 192 APIKey, line 194 CORS) |
| `sentinel-core/app/routes/modules.py` | GET /modules list + GET proxy route | VERIFIED | list_modules() line 41, get_proxy_module() line 58, both before POST proxy |
| `sentinel-core/tests/test_cors.py` | CORS middleware unit tests | VERIFIED | 4 tests: preflight_200, no_wildcard, credentials_header, regex_configured |
| `sentinel-core/tests/test_modules.py` | GET /modules and GET proxy unit tests | VERIFIED | 10 tests total including test_get_modules_list, test_get_proxy_module and 3 variants |
| `modules/pathfinder/app/main.py` | /healthz endpoint + lifespan startup registration with retry | VERIFIED | /healthz at line 81, _register_with_retry at line 39 |
| `modules/pathfinder/compose.yml` | Docker Compose service definition | VERIFIED | pf2e-module service, profile pf2e, service_healthy dependency |
| `modules/pathfinder/Dockerfile` | Container image build instructions | VERIFIED | python:3.12-slim base, curl installed, FastAPI/uvicorn/httpx deps |
| `modules/pathfinder/pyproject.toml` | Project dependencies and pytest config | VERIFIED | asyncio_mode = "auto" at line 19 |
| `modules/pathfinder/tests/test_healthz.py` | /healthz unit tests | VERIFIED | test_healthz_returns_ok present and passing |
| `modules/pathfinder/tests/test_registration.py` | startup registration retry unit tests | VERIFIED | test_registration_succeeds_on_first_attempt, test_registration_exits_after_all_failures, plus retries_on_failure and payload_correct |
| `docker-compose.yml` | Active pathfinder module include | VERIFIED | Line 14: - path: modules/pathfinder/compose.yml (uncommented) |
| `sentinel.sh` | Updated profile flags | VERIFIED | --pf2e case line 12; ALL_KNOWN_PROFILES contains pf2e line 29; no pathfinder case |
| `.env.example` | CORS env var documentation | VERIFIED | CORS_ALLOW_ORIGINS and CORS_ALLOW_ORIGIN_REGEX with wildcard warning |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| sentinel-core/app/main.py | CORSMiddleware | app.add_middleware(CORSMiddleware, ...) after APIKeyMiddleware | WIRED | Line 192 adds APIKeyMiddleware (call 1, innermost), lines 194-201 add CORSMiddleware (call 2, outermost). LIFO confirmed. |
| sentinel-core/app/config.py | main.py CORS settings | settings.cors_allow_origins and settings.cors_allow_origin_regex | WIRED | main.py lines 193, 197-198 reference settings fields directly |
| sentinel-core/app/routes/modules.py | app.state.http_client | request.app.state.http_client.get(target_url, ...) | WIRED | Line 72 in get_proxy_module() |
| modules/pathfinder/app/main.py lifespan | http://sentinel-core:8000/modules/register | httpx.AsyncClient.post() with REGISTRATION_PAYLOAD and X-Sentinel-Key header | WIRED | Lines 47-53 in _register_with_retry(); header forwarded at line 50 |
| modules/pathfinder/compose.yml | sentinel-core service | depends_on: sentinel-core: condition: service_healthy | WIRED | compose.yml lines 23-25 |
| docker-compose.yml include | modules/pathfinder/compose.yml | path: modules/pathfinder/compose.yml | WIRED | docker-compose.yml line 14, active and uncommented |
| sentinel.sh --pf2e | PROFILES array | PROFILES+=("pf2e") | WIRED | sentinel.sh line 12 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| GET /modules list_modules() | registry.values() | app.state.module_registry dict (populated by POST /modules/register) | Yes — returns live in-memory registry | FLOWING |
| GET /modules/{name}/{path} get_proxy_module() | resp from http_client.get() | app.state.http_client (real httpx.AsyncClient in production) | Yes — proxies real upstream response | FLOWING |
| GET /healthz healthz() | static dict | hardcoded {"status": "ok", "module": "pathfinder"} | Yes — correct for a health endpoint | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| sentinel-core CORS + modules tests (14 tests) | `cd sentinel-core && python -m pytest tests/test_cors.py tests/test_modules.py -q` | 14 passed | PASS |
| pf2e-module unit tests (5 tests) | `cd modules/pathfinder && python -m pytest tests/ -q` | 5 passed | PASS |
| docker compose config validation | `docker compose config --quiet` | exits 0 | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| MOD-01 | 28-02, 28-03 | PF2e module delivered as Docker Compose include (Path B reference implementation) | SATISFIED | modules/pathfinder/ skeleton with Dockerfile, compose.yml (profile pf2e), docker-compose.yml active include, sentinel.sh --pf2e flag |
| MOD-02 | 28-01 | CORS middleware added to Sentinel Core to allow Foundry browser fetch() calls with X-Sentinel-Key | SATISFIED | CORSMiddleware in main.py, no wildcard, allow_credentials=True, CORS env vars in config.py and .env.example |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| modules/pathfinder/app/main.py | 27 | `SENTINEL_API_KEY = os.getenv("SENTINEL_API_KEY", "")` module-level capture | Info | Not a runtime stub — the actual registration call reads os.getenv() at call time (line 50), not this module-level constant. Constant is unused in registration path. No runtime impact. |

No blockers or warnings found.

### Human Verification Required

**1. CORS preflight smoke test against running server**

**Test:** Start sentinel-core and run: `curl -X OPTIONS -H "Origin: http://localhost:30000" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: X-Sentinel-Key" -v http://localhost:8000/modules/pathfinder/healthz 2>&1 | grep -i "access-control"`
**Expected:** `access-control-allow-origin: http://localhost:30000` in response
**Why human:** Requires a running server; automated unit tests cover this via ASGITransport but cannot confirm production server behavior.

**2. pf2e-module Docker build**

**Test:** `cd /Users/trekkie/projects/sentinel-of-mnemosyne && docker build -f modules/pathfinder/Dockerfile modules/pathfinder/`
**Expected:** Image builds successfully with python:3.12-slim, curl, fastapi, uvicorn, httpx
**Why human:** Docker build requires Docker daemon; not runnable in automated checks.

**3. Full stack startup with --pf2e profile**

**Test:** `./sentinel.sh --pf2e up` (requires sentinel-core healthy first)
**Expected:** pf2e-module starts, registers with sentinel-core, GET /modules returns pathfinder entry
**Why human:** Requires running Docker stack, Obsidian, and LM Studio.

### Gaps Summary

No gaps. All 12 must-haves verified against actual codebase.

**Pre-existing defect (not a phase gap):** `test_ai_agnostic_guardrail.py::test_no_vendor_ai_imports_or_hardcoded_models` fails due to `from litellm import` in `app/routes/message.py`. This failure pre-dates Phase 28 (present on base commit cae28d9). Not introduced by or related to this phase.

---

_Verified: 2026-04-22T02:00:00Z_
_Verifier: Claude (gsd-verifier)_
