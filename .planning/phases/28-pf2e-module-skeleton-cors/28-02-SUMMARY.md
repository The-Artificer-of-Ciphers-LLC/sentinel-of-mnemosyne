---
phase: 28-pf2e-module-skeleton-cors
plan: "02"
subsystem: pf2e-module
tags: [fastapi, docker, compose, registration, retry, tdd]
dependency_graph:
  requires: []
  provides:
    - modules/pathfinder/app/main.py — pf2e-module FastAPI app with /healthz and startup registration
    - modules/pathfinder/Dockerfile — container image definition
    - modules/pathfinder/compose.yml — Docker Compose service with pf2e profile
    - modules/pathfinder/pyproject.toml — project deps and pytest config
  affects:
    - sentinel-core: pf2e-module registers at startup via POST /modules/register
tech_stack:
  added:
    - fastapi>=0.135.0 (pf2e-module dependency)
    - uvicorn[standard]>=0.44.0 (pf2e-module ASGI server)
    - httpx>=0.28.1 (pf2e-module registration HTTP client)
    - pytest-asyncio>=0.23 (async test support, asyncio_mode=auto)
  patterns:
    - Lifespan context manager for startup registration (matches sentinel-core pattern)
    - _register_with_retry: 5 attempts, delays [1,2,4,8,16]s, SystemExit(1) on full failure
    - SENTINEL_API_KEY read via os.getenv() at call time (not captured at module load)
    - Docker profile "pf2e" for optional module activation
    - depends_on: sentinel-core: condition: service_healthy (Path B module pattern)
key_files:
  created:
    - modules/pathfinder/app/main.py
    - modules/pathfinder/app/__init__.py
    - modules/pathfinder/__init__.py
    - modules/pathfinder/pyproject.toml
    - modules/pathfinder/tests/__init__.py
    - modules/pathfinder/tests/test_healthz.py
    - modules/pathfinder/tests/test_registration.py
    - modules/pathfinder/Dockerfile
    - modules/pathfinder/compose.yml
  modified: []
decisions:
  - SENTINEL_API_KEY read dynamically via os.getenv() in _register_with_retry rather than captured at module import — prevents stale value when env var is set after module is cached (discovered during TDD Green phase)
  - start_period: 30s in healthcheck — covers worst-case 31s registration retry window (1+2+4+8+16s delays)
  - compose.yml build context is "." (module directory) not "../.." — module is self-contained, no shared code at root
metrics:
  duration: "2m 20s"
  completed: "2026-04-22T01:14:07Z"
  tasks_completed: 2
  files_created: 9
  files_modified: 0
---

# Phase 28 Plan 02: pf2e-module FastAPI Skeleton Summary

pf2e-module FastAPI skeleton with /healthz endpoint, lifespan startup registration with 5-attempt exponential backoff retry, python:3.12-slim Dockerfile, and compose.yml with pf2e profile depending on sentinel-core service_healthy.

## What Was Built

The complete `modules/pathfinder/` skeleton: the Path B reference implementation for module containers in Sentinel of Mnemosyne. Any future module (music, finance, trading) can copy this pattern.

**`modules/pathfinder/app/main.py`** implements:
- `GET /healthz` — returns `{"status": "ok", "module": "pathfinder"}` per D-18
- `_register_with_retry(client)` — POSTs `REGISTRATION_PAYLOAD` to `{SENTINEL_CORE_URL}/modules/register` with `X-Sentinel-Key` header; 5 attempts with delays `[1, 2, 4, 8, 16]`s; `SystemExit(1)` on full failure so Docker restart policy recovers
- `lifespan` context manager — creates a short-lived `httpx.AsyncClient` for registration, closes it before yielding; matches sentinel-core lifespan pattern

**`modules/pathfinder/compose.yml`** declares:
- Service name `pf2e-module` (matches `base_url` in `REGISTRATION_PAYLOAD` per D-17 Pitfall 3)
- Profile `pf2e` (D-10) — activated via `./sentinel.sh --pf2e up`
- `depends_on: sentinel-core: condition: service_healthy`
- `healthcheck` on `/healthz` with `start_period: 30s` (covers worst-case retry window)
- `sentinel_api_key` Docker secret

**`modules/pathfinder/Dockerfile`** builds from `python:3.12-slim` with curl installed for the compose healthcheck.

## TDD Gate Compliance

- RED gate commit: `5dc7c28` — 5 failing tests (app/main.py absent)
- GREEN gate commit: `5a7512f` — all 5 tests pass
- REFACTOR: not needed (clean implementation on first pass)

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing tests for healthz and registration retry | 5dc7c28 | tests/test_healthz.py, tests/test_registration.py, pyproject.toml, __init__ files |
| 1 (GREEN) | pf2e-module FastAPI app with /healthz and _register_with_retry | 5a7512f | app/main.py |
| 2 | Dockerfile and compose.yml for pf2e-module | c277921 | Dockerfile, compose.yml |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SENTINEL_API_KEY read at call time, not module load time**
- **Found during:** Task 1 GREEN phase — `test_registration_payload_correct` failed
- **Issue:** `SENTINEL_API_KEY = os.getenv("SENTINEL_API_KEY", "")` at module level captures the value at import time. The test sets `os.environ["SENTINEL_API_KEY"] = "test-sentinel-key"` inside the test function, but the module was already imported (and the value cached) by prior tests.
- **Fix:** Changed `_register_with_retry` to call `os.getenv("SENTINEL_API_KEY", "")` at call time rather than reading the module-level constant. This correctly reflects any env var changes and is the right pattern for config that may vary between environments.
- **Files modified:** `modules/pathfinder/app/main.py`
- **Commit:** 5a7512f (included in GREEN commit)

## Known Stubs

None — all endpoints return real data. No placeholder text. No wired-but-empty data sources.

## Threat Flags

No new security surface introduced beyond the plan's threat model. The plan already documented:
- T-28-06: X-Sentinel-Key required for POST /modules/register (mitigated by sentinel-core APIKeyMiddleware)
- T-28-08: exponential backoff prevents retry storm — implemented as specified
- T-28-09: /healthz behind sentinel-core proxy; no published host port in compose.yml

## Self-Check: PASSED

- `modules/pathfinder/app/main.py` — FOUND
- `modules/pathfinder/compose.yml` — FOUND
- `modules/pathfinder/Dockerfile` — FOUND
- `modules/pathfinder/pyproject.toml` — FOUND
- `modules/pathfinder/tests/test_healthz.py` — FOUND
- `modules/pathfinder/tests/test_registration.py` — FOUND
- Commit `5dc7c28` (RED) — verified
- Commit `5a7512f` (GREEN) — verified
- Commit `c277921` (Task 2) — verified
- 5 tests pass — verified
