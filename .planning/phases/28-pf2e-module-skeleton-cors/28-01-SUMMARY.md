---
phase: 28-pf2e-module-skeleton-cors
plan: "01"
subsystem: sentinel-core
tags: [cors, modules, gateway, fastapi, middleware]
dependency_graph:
  requires: []
  provides: [cors-middleware, get-modules-list, get-proxy-module]
  affects: [sentinel-core/app/main.py, sentinel-core/app/config.py, sentinel-core/app/routes/modules.py]
tech_stack:
  added: [fastapi.middleware.cors.CORSMiddleware]
  patterns: [LIFO middleware ordering, pydantic-settings CORS config, TDD RED/GREEN]
key_files:
  created:
    - sentinel-core/tests/test_cors.py
  modified:
    - sentinel-core/app/config.py
    - sentinel-core/app/main.py
    - sentinel-core/app/routes/modules.py
    - sentinel-core/tests/test_modules.py
decisions:
  - "CORSMiddleware added AFTER APIKeyMiddleware in source order — FastAPI LIFO ensures CORS runs first, intercepting OPTIONS before auth can 401 it"
  - "cors_allow_origins uses comma-separated string (not list) so pydantic-settings can read it from a single env var"
  - "GET /modules list route registered before GET /modules/{name}/{path} to prevent parameterized path shadowing the literal"
metrics:
  duration: "2m 38s"
  completed: "2026-04-21"
  tasks_completed: 2
  files_modified: 4
  files_created: 1
---

# Phase 28 Plan 01: CORS Middleware + Module Gateway GET Routes Summary

**One-liner:** CORSMiddleware wired as outermost Starlette middleware with explicit allow_origins + forge-vtt regex; GET /modules list and GET /modules/{name}/{path} proxy added to module gateway.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Add CORS settings + CORSMiddleware | 5f50fac | config.py, main.py, tests/test_cors.py |
| 2 | Add GET /modules list + GET proxy routes | 12f1656 | routes/modules.py, tests/test_modules.py |

## What Was Built

**Task 1 — CORSMiddleware**

- `cors_allow_origins` and `cors_allow_origin_regex` fields added to `Settings` in `config.py`
- Defaults: `http://localhost:30000` and `r"https://.*\.forge-vtt\.com"`
- Both fields configurable from env vars (`CORS_ALLOW_ORIGINS`, `CORS_ALLOW_ORIGIN_REGEX`)
- `CORSMiddleware` imported and added to `app` after `APIKeyMiddleware` — FastAPI LIFO ordering makes it the outermost middleware, so OPTIONS preflight is handled before auth runs
- `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`
- No wildcard in `allow_origins` — explicit list only (D-04: wildcard breaks `X-Sentinel-Key` credential delivery)

**Task 2 — Module Gateway GET Routes**

- `GET /modules` → `list_modules()` — returns JSON array of all registered modules
- `GET /modules/{name}/{path:path}` → `get_proxy_module()` — proxies via `http_client.get()`, forwards `X-Sentinel-Key`, returns 404/503 on not-registered/unreachable
- Both routes inserted before the existing `POST /modules/{name}/{path:path}` to prevent path collision

## Test Coverage

- `test_cors.py`: 4 tests — preflight 200, no wildcard, credentials header, regex configured
- `test_modules.py`: 10 tests total (5 pre-existing + 5 new) — list, list_empty, proxy, proxy_unavailable, proxy_unknown
- Full sentinel-core suite: 145 passed, 12 skipped

## Deviations from Plan

### Pre-existing Issue Deferred (Out of Scope)

`test_ai_agnostic_guardrail.py::test_no_vendor_ai_imports_or_hardcoded_models` fails due to `from litellm import` in `app/routes/message.py`. This failure exists on the base commit (cae28d9) before any changes in this plan. It is a pre-existing defect unrelated to CORS or module gateway changes. Logged to deferred items.

### Auto-fixed Issues

None — plan executed exactly as written (excluding pre-existing out-of-scope failure).

## Threat Flags

No new trust boundaries introduced beyond what the plan's threat model covers. CORS configuration matches T-28-01 (no wildcard) and T-28-02 (middleware ordering) mitigations as specified.

## Known Stubs

None — all routes return real data from `app.state.module_registry`.

## Self-Check: PASSED

- `sentinel-core/app/config.py` — cors_allow_origins field present: confirmed (line 84)
- `sentinel-core/app/main.py` — CORSMiddleware import + add_middleware: confirmed (lines 19, 194)
- `sentinel-core/app/routes/modules.py` — list_modules + get_proxy_module: confirmed
- `sentinel-core/tests/test_cors.py` — created: confirmed
- Commit 5f50fac exists: confirmed
- Commit 12f1656 exists: confirmed
- Test suite: 145 passed (10 test_modules + 4 test_cors all passing)
