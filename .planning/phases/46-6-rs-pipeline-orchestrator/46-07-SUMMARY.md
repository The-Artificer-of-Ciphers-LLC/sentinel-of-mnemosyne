---
phase: 46-6-rs-pipeline-orchestrator
plan: "07"
subsystem: interfaces/discord (command surface — final wave-4 wiring)
tags: [discord, pipeline, gateway, command-router, PIPE-02, PIPE-03, PIPE-04, PIPE-05, PIPE-06]

# Dependency graph
requires:
  - phase: 46-6-rs-pipeline-orchestrator
    plan: "06"
    provides: "POST /vault/pipeline/start + GET /vault/pipeline/status route contract (admin-gated start, ungated status, PipelineReport field set)"
provides:
  - "core_gateway.call_core_pipeline_start / call_core_pipeline_status — Discord-to-core HTTP gateway for the pipeline verbs"
  - "command_router.handle_subcommand explicit branch for ralph/pipeline/reweave/rethink/refactor with admin gate + mode mapping"
  - "bot.py wrappers + kwargs wiring; five dead _SUBCOMMAND_PROMPTS entries removed"
affects: []

tech-stack:
  added: []
  patterns:
    - "Gateway HTTP-call shape mirrored verbatim from call_core_sweep_start/status (core_gateway.py:78-115): timeout=120.0 for the POST via sentinel_client.post_to_module, timeout=20.0 for the GET with X-Sentinel-Key header; log-and-return-string on any transport exception."
    - "command_router branch mirrors the vault-sweep branch exactly: is_admin gate first, args.strip().split(maxsplit=1) verb parse, 'status' verb routes to the status gateway fn, otherwise routes to the start gateway fn with the resolved mode."
    - "Dead fixed-prompt removal precedent (Phase 45-07) repeated: five _SUBCOMMAND_PROMPTS entries deleted, replaced by real endpoint calls — same pattern already applied to graph/stats/check."

key-files:
  created: []
  modified:
    - interfaces/discord/core_gateway.py
    - interfaces/discord/command_router.py
    - interfaces/discord/bot.py
    - interfaces/discord/tests/test_core_gateway.py
    - interfaces/discord/tests/test_command_router_module.py
    - interfaces/discord/tests/test_subcommands.py

key-decisions:
  - "D-04a concurrency wording lives in core_gateway.py, not command_router.py: call_core_pipeline_start/status both check `data.get('status') == 'blocked'` and return the fixed message 'A vault operation is already in progress — please try again shortly.' The command_router branch is a pure pass-through of whatever the injected gateway callable returns — no special-casing needed there, since the plan's own Task-1 spec frames the concurrency test as 'the gateway reports a blocked/refused start.'"
  - "call_core_pipeline_start's user-facing message uses `mode` (not the literal verb the user typed) for the 'Use `:{mode} status`' hint, since the gateway function only receives mode, not subcmd. For four of the five verbs mode==subcmd; for `:refactor` the hint reads `:rethink status`, which is still a valid, working verb (D-09 synonym) even though the user typed `:refactor`."
  - "Status formatter (call_core_pipeline_status) surfaces all seven PipelineReport per-phase counts from the 46-06 route contract (entries_processed/entries_total, reduced, hubs_touched, reweave_edits, verify_failed, verify_requeued) plus status/mode/pipeline_id, mirroring the bounded-formatter precedent from call_core_sweep_status/call_core_graph/call_core_stats — never echoes raw errors[] list contents (T-46-LEAK)."

requirements-completed: [PIPE-02, PIPE-03, PIPE-04, PIPE-05, PIPE-06]

coverage:
  - id: D1
    description: "core_gateway.call_core_pipeline_start POSTs {user_id, mode} to vault/pipeline/start via sentinel_client.post_to_module (timeout=120.0) and formats a 'Pipeline started' ack string; degrades to a log-and-return-string on transport error; surfaces the D-04a concurrency message when the response reports status=blocked"
    requirement: "PIPE-02/03/04/05"
    verification:
      - kind: unit
        ref: "interfaces/discord/tests/test_core_gateway.py::test_call_core_pipeline_start_posts_and_formats_response"
        status: pass
      - kind: unit
        ref: "interfaces/discord/tests/test_core_gateway.py::test_call_core_pipeline_start_transport_error_returns_friendly_string"
        status: pass
      - kind: unit
        ref: "interfaces/discord/tests/test_core_gateway.py::test_call_core_pipeline_start_blocked_surfaces_concurrency_message"
        status: pass
    human_judgment: false
  - id: D2
    description: "core_gateway.call_core_pipeline_status GETs vault/pipeline/status (X-Sentinel-Key header, timeout=20.0) and formats the real per-phase counts (reduced/hubs_touched/reweave_edits/verify_failed/verify_requeued); surfaces the D-04a message when status=blocked"
    requirement: "PIPE-06"
    verification:
      - kind: unit
        ref: "interfaces/discord/tests/test_core_gateway.py::test_call_core_pipeline_status_formats_per_phase_counts"
        status: pass
      - kind: unit
        ref: "interfaces/discord/tests/test_core_gateway.py::test_call_core_pipeline_status_transport_error_returns_friendly_string"
        status: pass
      - kind: unit
        ref: "interfaces/discord/tests/test_core_gateway.py::test_call_core_pipeline_status_blocked_surfaces_concurrency_message"
        status: pass
    human_judgment: false
  - id: D3
    description: "command_router.handle_subcommand routes ralph/pipeline/reweave/rethink to call_core_pipeline_start with the identity mode, and refactor to mode=rethink (D-09 synonym); <verb> status routes to call_core_pipeline_status; non-admin callers are refused"
    requirement: "PIPE-02/03/04/05"
    verification:
      - kind: unit
        ref: "interfaces/discord/tests/test_command_router_module.py::test_pipeline_verb_starts_with_correct_mode[ralph-ralph,pipeline-pipeline,reweave-reweave,rethink-rethink,refactor-rethink]"
        status: pass
      - kind: unit
        ref: "interfaces/discord/tests/test_command_router_module.py::test_pipeline_verb_status_invokes_status_gateway[ralph,pipeline,reweave,rethink,refactor]"
        status: pass
      - kind: unit
        ref: "interfaces/discord/tests/test_command_router_module.py::test_pipeline_verb_non_admin_refused"
        status: pass
      - kind: unit
        ref: "interfaces/discord/tests/test_command_router_module.py::test_pipeline_verb_concurrency_message_passed_through"
        status: pass
    human_judgment: false
  - id: D4
    description: "bot.py: five dead _SUBCOMMAND_PROMPTS entries (ralph/pipeline/reweave/rethink/refactor) removed; tasks/next/health/goals/reminders remain; _call_core_pipeline_start/_call_core_pipeline_status wrappers wired into the kwargs dict passed to discord_router_bridge.handle_subcommand"
    requirement: "PIPE-02/03/04/05/06"
    verification:
      - kind: unit
        ref: "interfaces/discord/tests/test_subcommands.py::test_pipeline_subcommand_calls_core (rewritten — asserts gateway routing, not the retired free-text prompt)"
        status: pass
      - kind: unit
        ref: "interfaces/discord suite: 276 passed, 50 skipped, 0 failed (`cd interfaces/discord && .venv/bin/python -m pytest tests/ -q`)"
        status: pass
    human_judgment: false

duration: ~20min
completed: 2026-07-06
status: complete
---

# Phase 46 Plan 07: 6 Rs Pipeline Orchestrator — Discord Command Surface Rewire Summary

**`:ralph`/`:pipeline`/`:reweave`/`:rethink`/`:refactor` now call the real Wave-3 `/vault/pipeline/start` and `/vault/pipeline/status` endpoints via two new `core_gateway.py` functions and an explicit admin-gated `command_router.py` branch, replacing the five dead fixed-prompt stubs in `bot.py` — the final rewire in the Phase-45-07 "drop dead prompts" lineage (graph/stats/check → sweep → now the full 6 Rs pipeline).**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-06
- **Tasks:** 3/3 (RED tests → gateway+router implementation → bot.py wiring)
- **Files modified:** 6 (3 source, 3 test)

## Accomplishments

- Added `call_core_pipeline_start(*, user_id, mode, sentinel_client)` and `call_core_pipeline_status(*, user_id, core_url, api_key)` to `core_gateway.py`, mirroring `call_core_sweep_start`/`call_core_sweep_status`'s exact HTTP-call shape (timeouts, header, log-and-return-string error handling).
- Added an explicit `if subcmd in ("ralph", "pipeline", "reweave", "rethink", "refactor")` branch to `command_router.py`, mirroring the `vault-sweep` branch: `is_admin` gate first, `status` verb routes to the status fn, otherwise routes to the start fn with the resolved mode (`refactor` → `rethink`, D-09 synonym).
- Removed the five stale `_SUBCOMMAND_PROMPTS` entries from `bot.py`; added `_call_core_pipeline_start`/`_call_core_pipeline_status` wrappers and wired both into the `kwargs` dict passed to `discord_router_bridge.handle_subcommand`.
- Full discord suite: **276 passed, 50 skipped, 0 failed** (258 baseline + 18 net new tests across the two new gateway fns and the five-verb router branch).

## Task Commits

Each task was committed atomically (TDD RED → GREEN):

1. **Task 1: RED tests for the five rewired verbs + gateway fns** — `2c86140` (test)
2. **Task 2: core_gateway pipeline fns + command_router branch/signature** — `87b6bb5` (feat)
3. **Task 3: bot.py — remove dead prompts, add wrappers, wire kwargs** — `40767fb` (feat)

_TDD gate sequence confirmed in git log: `test(46-07)` commit precedes both `feat(46-07)` commits._

## Files Created/Modified

- `interfaces/discord/core_gateway.py` — added `call_core_pipeline_start`/`call_core_pipeline_status` + the shared `_PIPELINE_BLOCKED_MESSAGE` constant (D-04a wording)
- `interfaces/discord/command_router.py` — added `call_core_pipeline_start`/`call_core_pipeline_status` keyword-only params to `handle_subcommand`; added the five-verb dispatch branch before the `subcommand_prompts` fallback
- `interfaces/discord/bot.py` — removed 5 dead `_SUBCOMMAND_PROMPTS` entries; added `_call_core_pipeline_start`/`_call_core_pipeline_status` wrappers; added both to the `kwargs` dict
- `interfaces/discord/tests/test_core_gateway.py` — 7 new tests for the two pipeline gateway fns (format, transport error, D-04a blocked path for both)
- `interfaces/discord/tests/test_command_router_module.py` — updated 3 existing call sites with the 2 new required kwargs; added 13 new parametrized/direct tests for the five-verb branch (mode mapping, status verb, admin refusal, concurrency pass-through)
- `interfaces/discord/tests/test_subcommands.py` — rewrote `test_pipeline_subcommand_calls_core` (Rule 1 deviation, see below)

## Decisions Made

- **D-04a message placement:** the "a vault operation is already in progress" wording is generated inside `core_gateway.py`'s two pipeline functions (checking `status == "blocked"` on the response), not in `command_router.py`. The router branch is a pure pass-through of the gateway's return value — this matches the plan's Task-1 framing ("when the gateway reports a blocked/refused start") and keeps the concurrency-detection logic in one place (the HTTP-facing layer) rather than duplicated in the dispatcher.
- **Status-hint verb in the start ack uses `mode`, not the raw subcmd** — `call_core_pipeline_start` only receives `mode`, so the "Use `:{mode} status`" hint reads `:rethink status` even when the user typed `:refactor ...`. This is still correct behavior (`:rethink status` is a valid, working verb per D-09), just not a verbatim echo of what the user typed.
- **Status formatter field set** mirrors the full 46-06 `PipelineReport` contract: `pipeline_id`, `status`, `mode`, `entries_processed`/`entries_total`, `reduced`, `hubs_touched`, `reweave_edits`, `verify_failed`, `verify_requeued` — the `errors` list is deliberately never echoed to Discord (bounded-formatter precedent, T-46-LEAK).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Updated a pre-existing test that encoded the now-retired dead-prompt behavior**
- **Found during:** Task 3 full-suite verification — `interfaces/discord/tests/test_subcommands.py::test_pipeline_subcommand_calls_core` asserted `"pipeline" in bot._SUBCOMMAND_PROMPTS` and that `:pipeline` routed through the free-text `_call_core` prompt path. This is exactly the dead-prompt behavior the plan requires removing, so the test necessarily broke once Task 3 deleted the five `_SUBCOMMAND_PROMPTS` entries.
- **Fix:** Rewrote the test (same file, same test name) to assert none of the five verbs have `_SUBCOMMAND_PROMPTS` entries and that `:pipeline` now routes to `_call_core_pipeline_start(user_id, mode="pipeline")` instead of `_call_core` — following the exact precedent already set in the same file by `test_check_subcommand_calls_gateway_not_core`/`test_stats_subcommand_calls_gateway_not_core`/`test_graph_subcommand_calls_gateway_not_core` (Phase 45-07). Patched `bot._is_admin` to `True` in the test since the pipeline branch is now admin-gated and the test's default env has no `SENTINEL_ADMIN_USER_IDS` set (fail-closed).
- **Files modified:** `interfaces/discord/tests/test_subcommands.py`
- **Commit:** `40767fb` (bundled into the Task 3 commit — the fix was required for the full-suite green criterion in that same task's `<verify>` step)

---

**Total deviations:** 1 auto-fixed (Rule 1 — pre-existing test encoding retired behavior)
**Impact on plan:** Necessary to satisfy the plan's own "full discord suite green" acceptance criterion for Task 3; no scope creep beyond the plan's explicit dead-prompt-removal directive.

## Issues Encountered

None beyond the deviation above.

## User Setup Required

None — no external service configuration required. This plan only rewires existing Discord-to-core HTTP calls against endpoints already shipped and route-contracted in 46-06.

## Next Phase Readiness

- All five 6 Rs pipeline verbs are now live end-to-end from Discord through to the real orchestrator (PIPE-02 through PIPE-06 fully wired across the phase's four waves).
- Deferred from this phase's explicit scope (per 46-CONTEXT.md): core→Discord completion push (still pull-only `:pipeline status` polling, D-03); full prose-rewrite reweave (still append-only, D-01); migration/backfill of existing flat-7 content into `notes/` — reserved for Phase 47.
- No blockers for Phase 47.

---
*Phase: 46-6-rs-pipeline-orchestrator*
*Completed: 2026-07-06*
