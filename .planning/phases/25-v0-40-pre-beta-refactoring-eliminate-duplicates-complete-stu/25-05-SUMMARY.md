---
phase: 25-v0-40-pre-beta-refactoring-eliminate-duplicates-complete-stu
plan: "05"
subsystem: shared-library, sentinel-core, interfaces
tags: [shared-client, litellm, status-routes, compose-profiles, tdd]
dependency_graph:
  requires: [25-04-PLAN.md]
  provides:
    - shared/sentinel_client.py (SentinelCoreClient — canonical HTTP client for all interfaces)
    - sentinel-core/app/routes/status.py (GET /status, GET /context/{user_id})
    - sentinel.sh (profile-based Docker Compose wrapper)
  affects:
    - interfaces/discord/bot.py
    - interfaces/imessage/bridge.py
    - sentinel-core/app/main.py
tech_stack:
  added:
    - shared/ Python package with pyproject.toml (asyncio_mode=auto pytest config)
    - shared/sentinel_client.py — SentinelCoreClient using httpx.AsyncClient
  patterns:
    - Shared library package at repo root — imported via PYTHONPATH by interfaces
    - Discord Dockerfile build context changed to repo root for shared/ access
    - All 4 AI backends unified through LiteLLMProvider (no more stub providers)
    - Docker Compose profiles (--profile discord) replaces -f flag stacking
key_files:
  created:
    - shared/__init__.py
    - shared/sentinel_client.py
    - shared/pyproject.toml
    - shared/tests/__init__.py
    - shared/tests/conftest.py
    - shared/tests/test_sentinel_client.py
    - sentinel-core/app/routes/status.py
    - sentinel-core/tests/test_status.py
    - modules/README.md
  modified:
    - interfaces/discord/bot.py (replaced inline call_core with SentinelCoreClient)
    - interfaces/discord/Dockerfile (build context repo root, explicit COPYs)
    - interfaces/discord/compose.yml (context=../.. + profiles=[discord])
    - interfaces/imessage/bridge.py (replaced inline call_core with SentinelCoreClient)
    - interfaces/imessage/launch.sh (PYTHONPATH export)
    - sentinel-core/app/main.py (status_router, ai_provider_name, LiteLLM-only map)
    - sentinel.sh (profile-based rewrite)
  deleted:
    - sentinel-core/app/clients/ollama_provider.py (stub with NotImplementedError)
    - sentinel-core/app/clients/llamacpp_provider.py (stub with NotImplementedError)
decisions:
  - "SentinelCoreClient uses per-call httpx.AsyncClient (not long-lived) — matches existing discord bot pattern; caller owns connection lifecycle"
  - "module-level _sentinel_client instance in bot.py and bridge.py — initialized from env vars at module load, consistent with existing SENTINEL_CORE_URL/SENTINEL_API_KEY pattern"
  - "Renamed internal discord helper to _call_core (not call_core) to avoid shadowing the removed function in any lingering test imports"
  - "shared/pyproject.toml added for asyncio_mode=auto — sentinel-core venv provides pytest-asyncio, shared/ tests run via same venv"
metrics:
  duration_seconds: 563
  completed_date: "2026-04-11"
  tasks_completed: 3
  tasks_total: 3
  files_created: 9
  files_modified: 7
  files_deleted: 2
  test_count_added: 15
---

# Phase 25 Plan 05: Cluster B — Shared Library, Status Routes, Compose Profiles Summary

One-liner: Extracted duplicate call_core() into shared/sentinel_client.py (SentinelCoreClient), implemented authenticated /status and /context/{user_id} endpoints, consolidated all AI backends to LiteLLMProvider, and rewrote sentinel.sh to use Docker Compose profiles.

## What Was Built

### Task 1 — shared/sentinel_client.py + interface migration (TDD)

Created `shared/sentinel_client.py` with the canonical `SentinelCoreClient` class. The class:
- Takes `base_url`, `api_key`, `timeout` at construction
- Exposes `async send_message(user_id, content, client)` that delegates to a caller-provided `httpx.AsyncClient`
- Returns user-facing strings on all error paths — never leaks `base_url` or `api_key` values to callers

Seven behavioral tests in `shared/tests/test_sentinel_client.py` verify success, timeout, 401, 422, ConnectError, URL-not-leaked, and API-key-not-leaked.

Both interfaces migrated:
- `interfaces/discord/bot.py`: inline `call_core()` removed, replaced by module-level `_sentinel_client` and thin `_call_core()` wrapper
- `interfaces/imessage/bridge.py`: same pattern; `call_core(client, user_id, content)` replaced by `_sentinel_client.send_message(user_id, text, http_client)`

Discord Dockerfile build context changed to repo root so `shared/` is accessible during image build. `interfaces/imessage/launch.sh` now exports `PYTHONPATH` to include repo root before invoking `bridge.py`.

### Task 2 — GET /status + GET /context/{user_id} + provider consolidation (TDD)

New `sentinel-core/app/routes/status.py` router with:
- `GET /status` — checks `obsidian_client.check_health()` and `http_client.get(pi_url/health)`, returns `{status, obsidian, pi_harness, ai_provider}`. Uses correct `app.state` attribute names (`obsidian_client`, `settings.pi_harness_url`).
- `GET /context/{user_id}` — gathers 5 self/ context files in parallel via `asyncio.gather`, returns `{user_id, context_files, recent_sessions_count}`.

Both routes protected by `APIKeyMiddleware` (returns 401 without `X-Sentinel-Key`).

`app.state.ai_provider_name = settings.ai_provider` added to lifespan startup.

Provider map consolidated: `OllamaProvider` and `LlamaCppProvider` stubs (both raised `NotImplementedError`) deleted. All 4 backends (`lmstudio`, `ollama`, `llamacpp`, `claude`) now route through `LiteLLMProvider` with the appropriate `model_string` prefix.

Eight status tests + 9 existing litellm tests = 17 new assertions. Full 129-test suite passes GREEN.

### Task 3 — sentinel.sh profiles rewrite + modules/README.md (auto)

`sentinel.sh` rewritten from `-f flag stacking` to `--profile` accumulation:
- `--discord` → `--profile discord`
- `--imessage` → exits with "iMessage runs natively on Mac, not in Docker." (exit 1)
- `--pathfinder`, `--music`, `--finance`, `--trader`, `--coder` → respective profiles
- Unknown args passed through to `docker compose`

`interfaces/discord/compose.yml` already had `profiles: ["discord"]` added in Task 1.

`modules/README.md` created to document the module contract (resolves STUB-07 partial).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Ruff formatter stripped unused imports**
- **Found during:** Tasks 1 and 2
- **Issue:** The PostToolUse ruff `--fix` hook removed `from shared.sentinel_client import SentinelCoreClient` and `from app.routes.status import router as status_router` when added as isolated edits, because `shared` is not installed in the venv and ruff treated them as unused/unresolvable.
- **Fix:** Rewrote entire files (bot.py, bridge.py, main.py) in single Write operations that included both the import and all call sites, so ruff sees each import as used.
- **Files modified:** interfaces/discord/bot.py, interfaces/imessage/bridge.py, sentinel-core/app/main.py

**2. [Rule 2 - Missing config] pytest asyncio_mode not set for shared/ tests**
- **Found during:** Task 1 GREEN phase
- **Issue:** Running `pytest shared/tests/` failed with "async functions are not natively supported" — no asyncio_mode config existed outside sentinel-core/.
- **Fix:** Added `shared/pyproject.toml` with `[tool.pytest.ini_options] asyncio_mode = "auto"`.
- **Files modified:** shared/pyproject.toml (created)

**3. [Rule 1 - Bug] Discord bot.py call_core renamed to _call_core**
- **Found during:** Task 1 implementation
- **Issue:** The plan specified removing `call_core` and replacing all call sites. The replacement helper was named `_call_core` (private, not `call_core`) to avoid any confusion with the removed function and to match Python convention for module-private helpers.
- **Fix:** All 14 call sites in bot.py use `_call_core(...)` which delegates to `_sentinel_client.send_message(...)`.
- **Files modified:** interfaces/discord/bot.py

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (test/25-05) | 12fb694 (Task 1 — tests created before impl) | PASS |
| GREEN (feat/25-05) | 12fb694 (same commit — impl + tests together) | PASS |
| RED (test/25-05-02) | 6307098 (test_status.py created, ran RED first) | PASS |
| GREEN (feat/25-05-02) | 6307098 (routes/status.py + main.py updates) | PASS |

Note: TDD RED and GREEN were committed atomically per task rather than as separate commits. Both RED failures were confirmed (ImportError for missing module; 404 for missing routes) before GREEN implementation.

## Known Stubs

None. All stub providers (`OllamaProvider`, `LlamaCppProvider`) were deleted. No placeholder text or TODO comments introduced.

## Self-Check

### Files Exist
- shared/sentinel_client.py: FOUND
- shared/tests/test_sentinel_client.py: FOUND
- sentinel-core/app/routes/status.py: FOUND
- sentinel-core/tests/test_status.py: FOUND
- modules/README.md: FOUND
- interfaces/discord/Dockerfile: FOUND (updated)
- interfaces/discord/compose.yml: FOUND (updated)
- interfaces/imessage/launch.sh: FOUND (updated)

### Deleted Files
- sentinel-core/app/clients/ollama_provider.py: CONFIRMED DELETED
- sentinel-core/app/clients/llamacpp_provider.py: CONFIRMED DELETED

### Commits Exist
- 12fb694: feat(25-05): create shared/sentinel_client.py + migrate both interfaces — FOUND
- 6307098: feat(25-05): implement /status + /context routes + consolidate AI providers — FOUND
- e754b47: feat(25-05): rewrite sentinel.sh to Docker Compose profiles + modules/README.md — FOUND

### Test Results
- shared/tests/: 7 passed
- sentinel-core/tests/: 129 passed, 1 pre-existing warning
- Zero NotImplementedError in sentinel-core/app/ source files

## Self-Check: PASSED
