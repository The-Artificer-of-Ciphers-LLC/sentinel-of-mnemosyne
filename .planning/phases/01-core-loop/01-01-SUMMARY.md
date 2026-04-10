---
phase: 01-core-loop
plan: "01"
subsystem: infrastructure
tags: [docker-compose, python, pytest, scaffolding, wave-0]
dependency_graph:
  requires: []
  provides:
    - docker-compose include directive pattern (CORE-07)
    - sentinel-core Python project foundation
    - pytest harness green baseline (9 stubs, all skipped)
    - pi-harness compose skeleton
  affects:
    - 01-02 (pi-harness container — uses pi-harness/compose.yml skeleton)
    - 01-03 (sentinel-core implementation — fills in test stubs)
tech_stack:
  added:
    - python:3.12-slim (Dockerfile base)
    - fastapi>=0.135.0
    - uvicorn[standard]>=0.44.0
    - pydantic>=2.7.0
    - pydantic-settings>=2.13.0
    - httpx>=0.28.1
    - tiktoken
    - pytest>=8.0 + pytest-asyncio>=0.23
  patterns:
    - Docker Compose include directive (Compose v2.20+) — all future modules add via include, never -f
    - pytest asyncio_mode=auto — all async test functions work without explicit decorator
    - Skip-decorated stubs — green baseline before implementation exists
key_files:
  created:
    - docker-compose.yml
    - sentinel-core/compose.yml
    - pi-harness/compose.yml
    - sentinel-core/pyproject.toml
    - sentinel-core/Dockerfile
    - sentinel-core/tests/__init__.py
    - sentinel-core/tests/conftest.py
    - sentinel-core/tests/test_message.py
    - sentinel-core/tests/test_token_guard.py
    - sentinel-core/tests/test_lmstudio_client.py
  modified:
    - .env.example
decisions:
  - "include directive pattern locked: docker-compose.yml uses include:, never -f flag stacking"
  - "depends_on uses condition: service_started (not service_healthy) for Core graceful degradation"
  - "LMSTUDIO_BASE_URL uses host.docker.internal (not LAN IP) per single Mac Mini topology"
metrics:
  duration: "2 minutes"
  completed: "2026-04-10"
  tasks_completed: 2
  tasks_total: 2
  files_created: 10
  files_modified: 1
---

# Phase 01 Plan 01: Wave 0 Scaffolding Summary

Wave 0 scaffolding complete: Docker Compose include-directive pattern, Sentinel Core Python project with pyproject.toml, Dockerfile, and pytest harness with 9 skip-decorated test stubs all green.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | docker-compose.yml with include directive + service compose skeletons | fe570ad | docker-compose.yml, sentinel-core/compose.yml, pi-harness/compose.yml |
| 2 | Python project scaffold — pyproject.toml, Dockerfile, test stubs, .env.example fix | ede4234 | sentinel-core/pyproject.toml, sentinel-core/Dockerfile, sentinel-core/tests/* (4 files), .env.example |

## What Was Built

### Docker Compose include pattern (CORE-07)

`docker-compose.yml` at project root uses the `include:` directive to pull in `sentinel-core/compose.yml` and `pi-harness/compose.yml`. This is the canonical pattern for all future modules — each module ships its own compose file and adds itself here via an `include` entry. The `-f` flag stacking approach is explicitly prohibited by comment.

`sentinel-core/compose.yml` defines the Core service with an 8000:8000 port mapping, env_file, healthcheck, and `depends_on: pi-harness: condition: service_started`. The `service_started` condition (not `service_healthy`) allows Core to start and degrade gracefully if Pi is not yet ready.

`pi-harness/compose.yml` is a skeleton with the pi-harness service definition, port 3000:3000, and a healthcheck with a longer `start_period` (30s) to account for Node.js startup.

### Python project foundation (CORE-06)

`sentinel-core/pyproject.toml` declares all production dependencies (FastAPI, uvicorn, pydantic, pydantic-settings, httpx, tiktoken) and dev dependencies (pytest, pytest-asyncio, httpx). The `[tool.pytest.ini_options]` section sets `asyncio_mode = "auto"` so async test functions work without per-function decorators.

`sentinel-core/Dockerfile` uses `python:3.12-slim`, installs curl for the Docker healthcheck, copies pyproject.toml first for layer caching, installs deps, then copies source. Entrypoint is `uvicorn app.main:app`.

### Test harness baseline

`sentinel-core/tests/conftest.py` provides two fixtures: `mock_lmstudio_response` (a minimal chat.completion JSON) and `mock_lmstudio_models_response` (a model metadata JSON with max_context_length). These fixtures are ready for Plan 03 to wire into httpx MockTransport.

Three test stub files created, each with 3 `@pytest.mark.skip` decorated tests:
- `test_message.py` — CORE-03 coverage (POST /message endpoint)
- `test_token_guard.py` — CORE-05 coverage (rejects oversized, permits normal, overhead counting)
- `test_lmstudio_client.py` — CORE-04 coverage (completion, context window fetch, 4096 fallback)

`pytest sentinel-core/tests/ -x -q` exits 0 with 9 skipped.

### .env.example corrections

- `LMSTUDIO_BASE_URL` updated from `http://192.168.1.x:1234/v1` to `http://host.docker.internal:1234/v1` per the locked single Mac Mini topology decision
- `PI_HARNESS_URL=http://pi-harness:3000` added with explanatory comment (internal Docker network name, not user-configurable)

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

| File | Stub | Reason |
|------|------|--------|
| sentinel-core/tests/test_message.py | 3 skipped tests | Intentional — implementations go in Plan 03 Wave 2 |
| sentinel-core/tests/test_token_guard.py | 3 skipped tests | Intentional — implementations go in Plan 03 Wave 2 |
| sentinel-core/tests/test_lmstudio_client.py | 3 skipped tests | Intentional — implementations go in Plan 03 Wave 2 |

These stubs are intentional scaffolding. Plan 03 fills them with real assertions against real implementations. The stubs' purpose is to give later executors a green baseline they can break-then-fix (TDD green-red-green cycle).

## Threat Flags

None. This plan creates only configuration files, Dockerfile, and test stubs. No network endpoints, auth paths, or schema changes were introduced.

## Self-Check: PASSED

Files verified:
- docker-compose.yml: FOUND
- sentinel-core/compose.yml: FOUND
- pi-harness/compose.yml: FOUND
- sentinel-core/pyproject.toml: FOUND
- sentinel-core/Dockerfile: FOUND
- sentinel-core/tests/conftest.py: FOUND
- sentinel-core/tests/test_message.py: FOUND
- sentinel-core/tests/test_token_guard.py: FOUND
- sentinel-core/tests/test_lmstudio_client.py: FOUND
- .env.example (host.docker.internal): FOUND
- .env.example (PI_HARNESS_URL): FOUND

Commits verified:
- fe570ad: Task 1 (docker-compose files)
- ede4234: Task 2 (Python scaffold + test stubs)
