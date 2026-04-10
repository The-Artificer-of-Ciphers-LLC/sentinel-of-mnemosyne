---
phase: 02-memory-layer
plan: 02
subsystem: memory
tags: [obsidian, httpx, fastapi, backgroundtasks, tiktoken, tdd, token-budget]

# Dependency graph
requires:
  - phase: 02-memory-layer
    plan: 01
    provides: "ObsidianClient with get_user_context/get_recent_sessions/write_session_summary, obsidian_client on app.state, serializeMessages in bridge.ts, PiAdapterClient pattern"
provides:
  - "Full Phase 2 POST /message flow: context retrieval, 3-message injection, 25% token budget truncation, token guard, send_messages(), BackgroundTasks session write"
  - "PiAdapterClient.send_messages() — POSTs {messages:[...]} array to bridge POST /prompt"
  - "_truncate_to_tokens() — tiktoken-based truncation enforcing 25% context budget"
  - "_write_session_summary() — best-effort BackgroundTasks write to Obsidian vault"
  - "MEM-02 through MEM-07 unit test coverage via MockTransport (no live Obsidian/Pi needed)"
affects:
  - any plan that exercises POST /message
  - phase 03+ (any plan that reads session history from vault)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Context injection: user/assistant turn pair prepended to messages array before Pi call (Pi v0.66 no system role)"
    - "Token budget: 25% of context_window reserved for injected context; _truncate_to_tokens() enforces before token guard"
    - "BackgroundTasks for best-effort post-response writes — response sent immediately, write happens after"
    - "autouse pytest fixture provides default no-op obsidian mock so all tests work without explicit setup"

key-files:
  created: []
  modified:
    - sentinel-core/app/routes/message.py
    - sentinel-core/app/clients/pi_adapter.py
    - sentinel-core/tests/test_message.py

key-decisions:
  - "25% context budget enforced by _truncate_to_tokens() before token guard — prevents systematic 422s for users with large profile files"
  - "BackgroundTasks (not asyncio.create_task) for session write — FastAPI-idiomatic, response sent before write begins"
  - "send_messages() added alongside send_prompt() — old method preserved for backward compat"
  - "autouse default_obsidian_client fixture in test_message.py — existing tests gain obsidian state without signature changes"
  - "test_token_guard_fires_on_inflated_context uses context_window=10 (not 100) — ensures truncated array still exceeds tiny window"

patterns-established:
  - "POST /message 7-step flow: get_user_context → get_recent_sessions → build messages → truncate → token guard → send_messages → BackgroundTask write"
  - "Context injection format: [user: profile text] [assistant: Understood.] [user: actual message]"
  - "Session note path: core/sessions/{YYYY-MM-DD}/{user_id}-{HH-MM-SS}.md"

requirements-completed:
  - MEM-01
  - MEM-02
  - MEM-03
  - MEM-04
  - MEM-05
  - MEM-06
  - MEM-07

# Metrics
duration: 25min
completed: 2026-04-10
---

# Phase 02 Plan 02: Memory Layer Integration Summary

**POST /message now retrieves Obsidian context, injects it as a 3-message user/assistant pair with 25% token budget truncation, sends via send_messages(), and writes a session note via BackgroundTasks after every exchange**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-10T18:40:00Z
- **Completed:** 2026-04-10T19:05:00Z
- **Tasks:** 2 (1 automated + 1 human-verify checkpoint — PASSED)
- **Files modified:** 3

## Accomplishments

- Full Phase 2 memory pipeline wired into POST /message — the Sentinel now reads context before every response
- Context truncation at 25% of context_window prevents users with large Obsidian profile files from hitting systematic 422s
- Session summary written to Obsidian after every exchange via BackgroundTasks — write failure never blocks the HTTP response
- 31/31 tests pass (7 new Wave 2 tests + 2 existing tests fixed for new obsidian_client requirement)

## Task Commits

Each task was committed atomically:

1. **Task 1: POST /message Phase 2 flow — context injection, BackgroundTasks write, token budget** - `75b5fcb` (feat)

## Files Created/Modified

- `sentinel-core/app/routes/message.py` — Full Phase 2 replacement: 7-step memory pipeline, _truncate_to_tokens(), _write_session_summary(), BackgroundTasks integration
- `sentinel-core/app/clients/pi_adapter.py` — Added send_messages(messages: list[dict]) method alongside existing send_prompt()
- `sentinel-core/tests/test_message.py` — 7 new Wave 2 tests + autouse default_obsidian_client fixture; 12 total message tests

## Decisions Made

- **Token budget at 25% of context_window:** Enforced before token guard, not after. This prevents a user's large profile file from causing every request to 422. The truncation marker `[...context truncated to fit token budget]` is appended so Pi knows context was cut.
- **BackgroundTasks over asyncio.create_task:** FastAPI-idiomatic pattern. Response is streamed to caller before the write begins — no latency impact.
- **autouse fixture for obsidian default:** Rather than adding `obsidian_no_context` parameter to all three existing tests, an autouse fixture provides a no-op mock for every test in the file. Wave 2 tests override `app.state.obsidian_client` explicitly when they need specific behavior.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing tests missing app.state.obsidian_client after route rewrite**
- **Found during:** Task 1 GREEN phase (running full test suite)
- **Issue:** The Phase 1 route didn't use `obsidian_client`. After replacing message.py with Phase 2 flow, the three existing tests (`test_post_message_returns_response_envelope`, `test_post_message_503_when_pi_unavailable`, `test_post_message_422_when_message_too_long`) failed with `AttributeError: 'State' object has no attribute 'obsidian_client'`
- **Fix:** Added `default_obsidian_client` autouse fixture that sets a no-op AsyncMock on `app.state.obsidian_client` before every test — existing tests gain the required state without signature changes
- **Files modified:** sentinel-core/tests/test_message.py
- **Verification:** All 31 tests pass
- **Committed in:** 75b5fcb (Task 1 commit)

**2. [Rule 1 - Bug] test_token_guard_fires_on_inflated_context used wrong context_window**
- **Found during:** Task 1 GREEN phase (test failed: got 200, expected 422)
- **Issue:** With `context_window=100`, budget=25 tokens. The 5000-word context is truncated to 25 tokens, and the full array (context + "Understood." + "hello") totals ~31 tokens — well within 100. Token guard passed; no 422.
- **Fix:** Changed `context_window=10` (budget=2 tokens). Truncated context + overhead = ~31 tokens, which exceeds 10. Token guard fires → 422.
- **Files modified:** sentinel-core/tests/test_message.py
- **Verification:** `test_token_guard_fires_on_inflated_context` PASS; `test_context_truncated_to_budget` still PASS with window=400
- **Committed in:** 75b5fcb (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both fixes were correctness issues introduced by the Phase 2 route rewrite. No scope creep.

## Issues Encountered

None beyond the auto-fixed deviations above.

## Human Verify Checkpoint (Task 2 — PASSED)

All 5 UAT checks passed on 2026-04-10:
1. Health returns `obsidian: "ok"` — PASS
2. Context injection — model response reflected "prefers concise answers" from user profile — PASS
3. Session note written to vault (PUT 204, confirmed in logs) — PASS
4. Hot tier loaded prior sessions on second call (GET 200 on session files) — PASS
5. Path traversal `../../etc/passwd` rejected with 422 — PASS

## Known Stubs

None. All methods are fully implemented. Session write, context retrieval, and token truncation are all wired end-to-end.

## Threat Flags

None — all new surface (BackgroundTasks write, _write_session_summary path construction) was covered by the plan's threat model (T-2-06 through T-2-10).

## Test Coverage Summary

| Req ID | Test | Location | Status |
|--------|------|----------|--------|
| MEM-02 | test_context_injected_when_file_exists | test_message.py | PASS |
| MEM-02 | test_no_injection_when_user_file_missing | test_message.py | PASS |
| MEM-02 | test_no_injection_when_obsidian_down | test_message.py | PASS |
| MEM-03 | test_response_succeeds_when_write_fails | test_message.py | PASS |
| MEM-06 | BackgroundTasks.add_task called after every response | message.py (verified via write_fails test) | PASS |
| MEM-07 | test_token_guard_fires_on_inflated_context | test_message.py | PASS |
| MEM-07 | test_context_truncated_to_budget | test_message.py | PASS |
| PiAdapter | test_send_messages_sends_array | test_message.py | PASS |

## Next Phase Readiness

- POST /message full Phase 2 pipeline is live and tested
- Human verify checkpoint (MEM-04 cross-session demo) is the only remaining gate
- Phase 3 can begin once checkpoint is approved

---
*Phase: 02-memory-layer*
*Completed: 2026-04-10*
