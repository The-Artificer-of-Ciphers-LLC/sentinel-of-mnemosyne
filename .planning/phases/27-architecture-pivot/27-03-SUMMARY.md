---
phase: 27-architecture-pivot
plan: "03"
subsystem: sentinel-core
tags: [module-gateway, proxy, fastapi, phase-27]
dependency_graph:
  requires: [27-01, 27-02]
  provides: [module-registry, module-proxy-endpoint]
  affects: [sentinel-core/app/main.py, sentinel-core/app/routes/modules.py]
tech_stack:
  added: []
  patterns: [in-memory-module-registry, httpx-proxy, starlette-path-converter]
key_files:
  created:
    - sentinel-core/app/routes/modules.py
  modified:
    - sentinel-core/app/main.py
decisions:
  - "Used app.state.module_registry (in-memory dict) — no external persistence needed for personal single-user system; resets on restart, acceptable per threat register T-27-03-02"
  - "Used {path:path} Starlette converter for proxy route to support slash-containing sub-paths"
  - "Proxy uses shared app.state.http_client (timeout=30s already configured) rather than creating new client"
metrics:
  duration: "8 minutes"
  completed: "2026-04-20"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 27 Plan 03: Module Gateway Router Summary

**One-liner:** In-memory module registry with POST /modules/register + httpx proxy via POST /modules/{name}/{path:path}, making all 5 GREEN.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create sentinel-core/app/routes/modules.py | 28af1a1 | sentinel-core/app/routes/modules.py |
| 2 | Wire modules router and module_registry into main.py | 8e6d5df | sentinel-core/app/main.py |

## What Was Built

`sentinel-core/app/routes/modules.py` — new FastAPI router providing the Phase 27 module gateway:

- `ModuleRoute(BaseModel)` — path + description for a single route a module exposes
- `ModuleRegistration(BaseModel)` — name, base_url, list[ModuleRoute]
- `POST /modules/register` — stores registration in `app.state.module_registry[name]`, returns `{"status": "registered"}`
- `POST /modules/{name}/{path:path}` — looks up registry, POSTs request body to `module.base_url/path` via shared httpx client; returns 404 if not registered, 503 on `httpx.ConnectError`

`sentinel-core/app/main.py` — three targeted edits:
1. Added `from app.routes.modules import router as modules_router`
2. Added `app.state.module_registry = {}` initialization in lifespan (before yield)
3. Added `app.include_router(modules_router)` after status_router

## Verification

```
pytest tests/test_modules.py -v
5 passed in 1.10s

pytest -x (full suite)
131 passed, 1 warning in 20.46s
```

The 1 warning (`coroutine 'OutputScanner._classify' was never awaited`) is pre-existing in test_output_scanner.py, not introduced by this plan.

## Deviations from Plan

None — plan executed exactly as written. The formatter (PostToolUse hook) removed the modules import on first application, requiring a second edit, but this was a tooling interaction not a deviation from the implementation plan.

## Known Stubs

None. The module registry is fully functional: register stores, proxy forwards, error paths return correct status codes.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: SSRF | sentinel-core/app/routes/modules.py | POST /modules/register accepts user-supplied base_url used for outbound proxy — SSRF surface. Accepted per T-27-03-01: X-Sentinel-Key gates registration; local-network personal system. Mitigated in v1.0 community release by CIDR validation. |

## Self-Check: PASSED

- sentinel-core/app/routes/modules.py: FOUND
- sentinel-core/app/main.py contains `from app.routes.modules import router as modules_router`: FOUND
- sentinel-core/app/main.py contains `app.state.module_registry = {}`: FOUND
- sentinel-core/app/main.py contains `app.include_router(modules_router)`: FOUND
- Commit 28af1a1: FOUND
- Commit 8e6d5df: FOUND
- All 5 tests in tests/test_modules.py: PASSED
- Full suite (131 tests): PASSED
