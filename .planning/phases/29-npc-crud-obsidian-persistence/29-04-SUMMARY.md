---
phase: 29-npc-crud-obsidian-persistence
plan: "04"
subsystem: pathfinder-npc-router
tags: [fastapi, npc, obsidian, pathfinder, pf2e]
dependency_graph:
  requires:
    - "29-02"  # obsidian.py ObsidianClient
    - "29-03"  # llm.py extract_npc_fields / update_npc_fields
  provides:
    - modules/pathfinder/app/routes/npc.py
    - app.include_router(npc_router) in main.py
  affects:
    - modules/pathfinder/app/main.py
tech_stack:
  added: []
  patterns:
    - FastAPI APIRouter with prefix=/npc
    - Module-level obsidian variable for test patchability
    - GET-before-write collision check pattern
    - YAML frontmatter + fenced stats block parse/build
key_files:
  created:
    - modules/pathfinder/app/routes/__init__.py
    - modules/pathfinder/app/routes/npc.py
  modified:
    - modules/pathfinder/app/main.py
decisions:
  - "Module-level obsidian=None in npc.py set by lifespan instead of request.app.state injection — matches Wave 0 test patch targets (app.routes.npc.obsidian)"
  - "os.environ.get(SENTINEL_API_KEY) used at call time in _register_with_retry to preserve monkeypatch test compatibility"
metrics:
  duration: "~15 minutes"
  completed: "2026-04-21"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 3
requirements:
  - NPC-01
  - NPC-02
  - NPC-03
---

# Phase 29 Plan 04: NPC Router + main.py Integration Summary

NPC FastAPI router with `/create`, `/update`, `/show` endpoints wired into the pathfinder module via ObsidianClient lifespan and full 6-entry REGISTRATION_PAYLOAD.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create app/routes/npc.py with /create, /update, /show | 791ba1e | routes/__init__.py, routes/npc.py |
| 2 | Update main.py — router inclusion + ObsidianClient lifespan + REGISTRATION_PAYLOAD | c402efb | app/main.py |

## What Was Built

### modules/pathfinder/app/routes/npc.py

FastAPI router (`prefix="/npc"`) with three POST endpoints:

- **POST /npc/create** (NPC-01): `slugify()` the name, `get_note()` collision check (409 if exists), `extract_npc_fields()` LLM call, `put_note()` to Obsidian. Returns `{status, slug, path, name, level, ancestry, class, traits, personality, backstory, mood}`.
- **POST /npc/update** (NPC-02): `get_note()` (404 if missing), `update_npc_fields()` LLM call for changed fields only, merge into parsed frontmatter, `put_note()` rebuilt note. Returns `{status, slug, path, changed_fields}`.
- **POST /npc/show** (NPC-03): `get_note()` (404 if missing), parse frontmatter + stats block, return combined dict with `slug`, `path`, all frontmatter fields, and `stats` (empty dict if block absent).

Support functions: `slugify()`, `_parse_frontmatter()`, `_parse_stats_block()`, `build_npc_markdown()`.

### modules/pathfinder/app/main.py

Four changes from Phase 28 skeleton:
1. Imports: `from app.config import settings`, `from app.obsidian import ObsidianClient`, `from app.routes.npc import router as npc_router`, `import app.routes.npc as _npc_module`
2. `REGISTRATION_PAYLOAD` routes expanded from 1 entry to 6 (healthz + 5 NPC routes)
3. `lifespan` creates persistent `ObsidianClient` on `app.state.obsidian_client` and sets `_npc_module.obsidian` for test patchability
4. `app.include_router(npc_router)` added after `app = FastAPI(...)`

## Test Results

```
14 collected:
  1 PASSED   test_healthz_returns_ok
  5 XPASSED  test_npc_create_success, test_npc_create_collision,
             test_npc_update_identity_fields, test_npc_show_returns_fields,
             test_npc_show_not_found  [Wave 0 stubs now passing]
  4 XFAILED  test_npc_relate_valid, test_npc_relate_invalid_type,
             test_npc_import_basic, test_npc_import_collision_skipped
             [Plan 05 — expected]
  4 PASSED   test_registration_* suite
```

Exit 0. All NPC-01, NPC-02, NPC-03 acceptance criteria met.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Module-level obsidian variable instead of request.app.state injection**
- **Found during:** Task 1 test verification
- **Issue:** Wave 0 tests patch `app.routes.npc.obsidian` (module-level name). Plan's action code used `request.app.state.obsidian_client` which is not patchable via the test's `patch("app.routes.npc.obsidian", mock_obs)`.
- **Fix:** Added `obsidian = None` module-level variable in `npc.py`; route handlers reference it directly. `lifespan` sets both `app.state.obsidian_client` and `_npc_module.obsidian` from the same client instance.
- **Files modified:** modules/pathfinder/app/routes/npc.py, modules/pathfinder/app/main.py
- **Commits:** 791ba1e, c402efb

**2. [Rule 1 - Bug] os.environ.get() for SENTINEL_API_KEY instead of frozen settings value**
- **Found during:** Task 2 full suite run
- **Issue:** `test_registration_payload_correct` uses `monkeypatch.setenv("SENTINEL_API_KEY", "test-sentinel-key")` then calls `_register_with_retry`. `pydantic-settings` freezes `Settings()` at import time, so `settings.sentinel_api_key` held the value set by `test_npc.py`'s `os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")`. The monkeypatched value was never seen.
- **Fix:** Changed `_register_with_retry` to use `os.environ.get("SENTINEL_API_KEY", "")` at call time, matching the original Phase 28 behavior and test design intent. `settings` is still used for `sentinel_core_url` and Obsidian config (no test monkeypatching of those values).
- **Files modified:** modules/pathfinder/app/main.py
- **Commit:** c402efb

## Known Stubs

None. All three endpoints are fully implemented with real Obsidian and LLM calls. No placeholder text or hardcoded empty values that flow to the caller.

## Threat Flags

T-29-01 mitigated: `slugify()` implemented as `re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")` — strips `../`, `/`, `.`, and all non-alphanumeric characters. Path traversal impossible.

T-29-02 mitigated: `extract_npc_fields` and `update_npc_fields` wrapped in try/except; `json.loads()` parse failure raises to caller which returns HTTP 500. No Obsidian write on LLM failure.

T-29-04 mitigated: ObsidianClient uses `timeout=5.0` on GET and `timeout=10.0` on PUT/PATCH (implemented in Plan 02 obsidian.py).

## Self-Check: PASSED

| Item | Status |
|------|--------|
| modules/pathfinder/app/routes/__init__.py | FOUND |
| modules/pathfinder/app/routes/npc.py | FOUND |
| modules/pathfinder/app/main.py | FOUND |
| commit 791ba1e | FOUND |
| commit c402efb | FOUND |
