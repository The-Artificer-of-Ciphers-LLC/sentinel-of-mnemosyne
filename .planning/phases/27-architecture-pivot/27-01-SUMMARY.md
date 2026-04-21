---
phase: 27-architecture-pivot
plan: "01"
subsystem: sentinel-core/tests
tags: [tdd, testing, modules, red-state]
dependency_graph:
  requires: []
  provides: [test-stubs-modules-red-state]
  affects: [sentinel-core/app/routes/modules.py]
tech_stack:
  added: []
  patterns: [pytest-asyncio auto mode, ASGITransport AsyncClient, autouse fixture state reset]
key_files:
  created:
    - sentinel-core/tests/test_modules.py
  modified: []
decisions:
  - "Autouse fixture resets app.state.module_registry = {} between tests to prevent state leakage"
  - "mock_http_client fixture defined locally (not shared conftest) following test_status.py analog"
metrics:
  duration: "4 minutes"
  completed: "2026-04-21T01:23:07Z"
  tasks_completed: 1
  tasks_total: 1
  files_changed: 1
---

# Phase 27 Plan 01: Module Registry Test Stubs (RED State) Summary

5 async pytest stubs for SC-1 through SC-4 plus auth guard — RED state confirmed with ImportError on missing app.routes.modules.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create test_modules.py with all 5 test stubs (RED state) | 9e24720 | sentinel-core/tests/test_modules.py |

## What Was Built

`sentinel-core/tests/test_modules.py` containing 5 collectable async test functions:

- `test_register_module` — SC-1: POST /modules/register returns `{"status": "registered"}` and stores entry in registry
- `test_proxy_module` — SC-2: POST /modules/{name}/{path} proxies to registered module and returns proxied response
- `test_proxy_module_unavailable` — SC-3: POST /modules/{name}/{path} returns 503 when httpx.ConnectError raised
- `test_proxy_unknown_module` — SC-4: POST /modules/{name}/{path} returns 404 for unregistered module
- `test_register_requires_auth` — POST /modules/register without X-Sentinel-Key returns 401 or 403

The autouse fixture resets `app.state.module_registry = {}` before each test to prevent state leakage across test functions, satisfying the threat model T-27-01-01.

## RED State Confirmation

Running `pytest tests/test_modules.py -x` fails with:

```
ImportError: No module named 'litellm'
```

The import chain fails at `from app.routes.modules import ModuleRegistration, ModuleRoute` because `app.routes.modules` does not exist yet. The failure is an ImportError (not a syntax error, not a collection error), which is the correct RED state gate for Plan 03.

## Deviations from Plan

None — plan executed exactly as written.

## TDD Gate Compliance

This plan is the RED gate only. The `test(27-01)` commit establishes the failing test stubs. GREEN gate (feat commit) will be established in Plan 03 when `app/routes/modules.py` is implemented.

## Known Stubs

None. This file is intentionally test-only with no production stubs.

## Threat Flags

None. No new network endpoints, auth paths, or schema changes introduced. Test file only.

## Self-Check: PASSED

- `sentinel-core/tests/test_modules.py` — FOUND
- Commit `9e24720` — FOUND
- 5 async test functions — CONFIRMED (grep returns 5)
- Syntax valid — CONFIRMED (ast.parse exits 0)
- RED state (ImportError) — CONFIRMED
