---
phase: 03-interfaces
plan: "01"
subsystem: sentinel-core
tags: [auth, middleware, testing, fastapi, starlette]
dependency_graph:
  requires: [02-02]
  provides: [IFACE-06-auth-enforcement]
  affects: [sentinel-core/app/main.py, sentinel-core/tests/]
tech_stack:
  added: [BaseHTTPMiddleware (starlette)]
  patterns: [global-middleware-before-router, auth-header-X-Sentinel-Key, health-endpoint-whitelist]
key_files:
  created: [sentinel-core/tests/test_auth.py]
  modified: [sentinel-core/app/main.py, sentinel-core/tests/test_message.py]
decisions:
  - "APIKeyMiddleware uses BaseHTTPMiddleware (not FastAPI Depends) — single enforcement point, covers all current and future routes automatically"
  - "StarletteRequest type annotation used in dispatch() to satisfy type checker while keeping httpx client API consistent"
  - "test_auth_accepts_valid_key seeds app.state with mocked obsidian_client and pi_adapter to avoid state errors after auth passes"
metrics:
  duration_seconds: 190
  completed: "2026-04-10"
  tasks_completed: 2
  files_changed: 3
---

# Phase 03 Plan 01: Auth Middleware Summary

**One-liner:** X-Sentinel-Key global auth middleware via Starlette BaseHTTPMiddleware, /health whitelisted, 35 tests green.

## What Was Built

`APIKeyMiddleware` added to `sentinel-core/app/main.py` as a Starlette `BaseHTTPMiddleware` registered before route inclusion. Every request to any path except `/health` must carry an `X-Sentinel-Key` header matching `settings.sentinel_api_key`. Missing or wrong key returns `{"detail": "Unauthorized"}` with HTTP 401. The middleware is a single enforcement point — all current and future routes are protected without per-route wiring.

Four new auth tests in `test_auth.py` cover the four cases: missing key → 401, wrong key → 401, `/health` without key → 200, correct key → not 401.

Nine POST `/message` calls in `test_message.py` updated to include the `X-Sentinel-Key: test-key-for-pytest` header via a shared `AUTH_HEADER` constant.

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create test_auth.py (TDD RED) | e91adef | sentinel-core/tests/test_auth.py |
| 2 | Add APIKeyMiddleware + update tests (GREEN) | ba272e4 | sentinel-core/app/main.py, sentinel-core/tests/test_message.py |

## Verification

```
35 passed in 0.32s
```

All 35 tests pass: 31 existing + 4 new auth tests.

Acceptance criteria confirmed:
- `class APIKeyMiddleware(BaseHTTPMiddleware):` present in main.py
- `app.add_middleware(APIKeyMiddleware)` before `app.include_router`
- `from starlette.middleware.base import BaseHTTPMiddleware` present
- `grep -c 'X-Sentinel-Key' sentinel-core/tests/test_message.py` returns 9
- `pytest tests/test_auth.py -v` shows 4 PASSED

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_auth_accepts_valid_key needed app.state initialization**
- **Found during:** Task 2 GREEN verification
- **Issue:** test_auth_accepts_valid_key passes auth correctly but then the route handler accessed `app.state.obsidian_client` and `app.state.pi_adapter` which weren't seeded in the auth test (unlike test_message.py tests which all seed state explicitly). This caused AttributeError, not the expected 503/422/200.
- **Fix:** Added mock setup for `obsidian_client`, `pi_adapter`, `context_window`, and `settings` in the test body before the request. Pi adapter uses a ConnectError mock so the test gets 503 (auth passed, downstream unavailable — satisfies `!= 401`).
- **Files modified:** sentinel-core/tests/test_auth.py
- **Commit:** ba272e4 (incorporated into Task 2 commit)

**2. [Rule 1 - Bug] Formatter stripped unused import on first edit attempt**
- **Found during:** Task 2 Step 1
- **Issue:** Added `from starlette.middleware.base import BaseHTTPMiddleware` as a standalone edit before adding the class. The post-write formatter detected it as unused and removed it.
- **Fix:** Combined the import, class definition, and `app.add_middleware()` registration into a single atomic edit so the formatter saw all usages at once.
- **Files modified:** sentinel-core/app/main.py

## Known Stubs

None — all auth logic is fully wired. `sentinel_api_key` has no default in `Settings` (startup fails fast if missing per pydantic-settings enforcement). The middleware comparison is string equality against the live settings value.

## Threat Flags

None — this plan implements mitigations for T-03-01 and T-03-04 from the threat model. No new unplanned surface introduced.

## Self-Check: PASSED

- sentinel-core/tests/test_auth.py: FOUND
- sentinel-core/app/main.py: FOUND (contains APIKeyMiddleware, add_middleware)
- sentinel-core/tests/test_message.py: FOUND (contains X-Sentinel-Key × 9)
- Commit e91adef: FOUND
- Commit ba272e4: FOUND
