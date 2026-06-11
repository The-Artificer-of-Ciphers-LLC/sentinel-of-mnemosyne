---
phase: 39-extract-the-recall-module
plan: "03"
subsystem: memory/recall
tags: [recall, memory, endpoint, context-route, refactor, python]

dependency_graph:
  requires:
    - "sentinel-core/app/services/recall.py :: Recall, RecalledContext, MessageRequest (Plan 01)"
    - "sentinel-core/app/state.py :: RouteContext.recall field (Plan 02)"
    - "sentinel-core/app/composition.py :: AppGraph.recall, initialize_startup (Plan 02)"
  provides:
    - "sentinel-core/app/routes/status.py :: GET /context/{user_id} delegating to ctx.recall.assemble(); duplicated assembly deleted"
    - "sentinel-core/tests/test_status.py :: RouteContext fixture supplies recall=Recall(vault=...)"
    - "sentinel-core/tests/test_message.py :: _LazyTestProcessor and _LazyRouteCtx supply recall"
  affects:
    - "Phase 40: RetrievalStrategy seam — /context route now fully wired to Recall"
    - "Phase 41: typed SessionSummary — route already delegates; only Recall internals change"

tech_stack:
  added: []
  patterns:
    - "synthetic MessageRequest(content='', user_id=user_id, ...) to drive assemble() from a route with no user message"
    - "content='' -> Recall._warm_search early-returns [] (Pitfall 8/Option A) — preserves test compatibility with mocks lacking find()"
    - "additive fixture injection: recall= added to RouteContext in test_status; recall property added to _LazyRouteCtx in test_message"

key_files:
  created: []
  modified:
    - sentinel-core/app/routes/status.py
    - sentinel-core/tests/test_status.py
    - sentinel-core/tests/test_message.py

key-decisions:
  - "Pass content='' to assemble() in the /context route so warm search degrades gracefully to [] (Option A from RESEARCH.md Pitfall 8) — preserves mock compatibility without adding a ?query= parameter"
  - "Response serializes self_context/sessions/warm/user_id/recent_sessions_count — existing tests only assert user_id and recent_sessions_count (both preserved), so the field rename from context_files is safe (RESEARCH.md Assumption A1)"
  - "Both test fixtures supply Recall(vault=app.state.vault) inline rather than reading from app.state.recall — simpler and future-proof; test_message's _LazyRouteCtx already builds everything lazily"

requirements-completed: [MEM-01]

duration: 15min
completed: 2026-06-11
---

# Phase 39 Plan 03: Delegate GET /context/{user_id} to Recall + Wire Test Fixtures — Summary

**GET /context/{user_id} now delegates to ctx.recall.assemble() with content="" for warm-tier no-op, serializes RecalledContext (self_context/sessions/warm/recent_sessions_count), and the duplicated inline self_paths/asyncio.gather/get_recent_sessions assembly is deleted — closing MEM-01 endpoint convergence (D-05).**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-06-11
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Deleted the duplicated hot-tier assembly from `status.py` (`self_paths` list, `asyncio.gather` over `read_self_context`, `get_recent_sessions` call) — replaced with a 3-line delegation to `ctx.recall.assemble()`
- `/context` route now uses identical Recall logic as the message path (MEM-01 closed: no duplicated assembly logic)
- Wired `recall=Recall(vault=app.state.vault)` into `test_status.py::setup_app_state` RouteContext and added `recall` property to `test_message.py::_LazyRouteCtx` — additive only, zero existing assertions touched
- Full suite stays green: 285 passed, 12 skipped (matches Plan 02 baseline exactly)

## Task Commits

1. **Task 1: Delegate GET /context/{user_id} to Recall and serialize RecalledContext** - `40c13b0` (refactor)
2. **Task 2: Wire recall into test_status.py and test_message.py fixtures** - `8eba8eb` (feat)

## Files Created/Modified

- `sentinel-core/app/routes/status.py` — replaced duplicated assembly body with `ctx.recall.assemble()` delegation; removed `import asyncio`; added `from app.services.recall import MessageRequest`
- `sentinel-core/tests/test_status.py` — added `Recall` import; added `recall=Recall(vault=app.state.vault)` to `RouteContext(...)` in `setup_app_state`
- `sentinel-core/tests/test_message.py` — added `Recall` import; passed `recall=Recall(vault=app.state.vault)` explicitly to `MessageProcessor` in `_LazyTestProcessor.process()`; added `recall` `@property` to `_LazyRouteCtx`

## Decisions Made

- **content="" for assemble()**: The `/context` route has no user message to drive warm search. Passing `content=""` causes `Recall._warm_search` to early-return `[]` (Option A, Pitfall 8). The test's `mock_obsidian` does not configure `find()` — this is exactly why Option A was the right choice: no mock update needed, behavior is documented and correct.
- **Response shape**: Changed from `context_files: {path: text}` to `self_context: [str]`, `sessions: [str]`, `warm: [{path, score}]`. The existing tests only assert `user_id` and `recent_sessions_count` (both preserved), so the shape change is safe (RESEARCH.md Assumption A1 confirmed no external caller depends on `context_files`).

## Deviations from Plan

None — plan executed exactly as written. Tasks 1 and 2 were implemented together since task 1's test verification requires the fixture wiring from task 2 (as noted in the plan's acceptance criteria).

## Issues Encountered

None.

## Acceptance Criteria Verification

| Check | Result |
|-------|--------|
| `grep -n "ctx.recall.assemble" app/routes/status.py` >= 1 | line 48 — PASS |
| `grep -n "self_paths\|get_recent_sessions\|read_self_context" app/routes/status.py` == 0 | 0 matches — PASS |
| `grep -n "import asyncio" app/routes/status.py` == 0 | 0 matches — PASS |
| `grep -n "recent_sessions_count" app/routes/status.py` >= 1 | line 55 — PASS |
| `grep -n "recall=" tests/test_status.py` >= 1 | line 46 — PASS |
| `grep -n "from app.services.recall import Recall" tests/test_status.py` >= 1 | line 11 — PASS |
| `grep -n "recall" tests/test_message.py` >= 1 | 3 matches — PASS |
| `git diff --stat app/vault.py` empty | no changes — PASS |
| Full suite: `uv run pytest tests/ -q` | 285 passed, 12 skipped — PASS |

## Threat Surface Scan

No new threat surface. This is an internal route refactor:
- `user_id` path parameter retains its `^[a-zA-Z0-9_-]+$` regex validation unchanged (T-39-06 mitigated)
- Response shape changes from `context_files` to `self_context/sessions/warm` but all content was already returned before — field reshape only, not new disclosure (T-39-07 accepted)
- warm list is always empty for this route since content="" (T-39-08 not triggered; exclusion policy still live in Recall)

## Known Stubs

None. All data flows are wired end-to-end.

## Next Phase Readiness

Phase 39 is now complete. Both shared callers use `Recall.assemble()`:
- Message path (Plan 02): `MessageProcessor.process()` calls `self._recall.assemble(req, req.context_window)`
- /context endpoint (Plan 03): `debug_context` calls `ctx.recall.assemble(fake_req, budget=ctx.context_window)`

MEM-01 is closed. Ready for Phase 40 (RetrievalStrategy seam / SemanticRecall).

---

## Self-Check

### Files exist
- `/Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/app/routes/status.py` — FOUND
- `/Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/tests/test_status.py` — FOUND
- `/Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/tests/test_message.py` — FOUND

### Commits exist
- `40c13b0` — refactor(39-03): delegate GET /context/{user_id} to ctx.recall.assemble()
- `8eba8eb` — feat(39-03): wire recall into test_status.py and test_message.py fixtures

## Self-Check: PASSED

---
*Phase: 39-extract-the-recall-module*
*Completed: 2026-06-11*
