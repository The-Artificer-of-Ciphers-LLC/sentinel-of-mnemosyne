---
phase: 45-note-quality-schema-graph-analysis
plan: 07
subsystem: discord-interface
tags: [discord, gateway, httpx, rewire]
status: complete

requires:
  - phase: 45-note-quality-schema-graph-analysis (plan 06)
    provides: "GET /vault/graph, /vault/stats, /vault/check routes returning modeled JSON (no admin gate, no model probe)"
provides:
  - "core_gateway.call_core_graph/call_core_stats/call_core_check — httpx GET to /vault/graph|stats|check with X-Sentinel-Key, formatted Discord-ready strings, friendly failure on Exception"
  - ":graph/:stats/:check Discord subcommands now invoke the real read-only endpoints instead of a free-text call_core fixed prompt"
affects: [46-6rs-pipeline-orchestrator, 47-migration-cutover-hardening]

tech-stack:
  added: []
  patterns:
    - "Gateway fn posture mirrors call_core_sweep_status exactly: httpx.AsyncClient GET with X-Sentinel-Key header + 20s timeout, resp.raise_for_status(), JSON parsed and formatted into a bounded summary string, try/except degrades to a friendly failure string (never raises to the caller)."
    - "command_router branches call the injected gateway callable directly (call_core_graph(user_id) etc.) rather than composing a free-text prompt for call_core — same threading convention as call_core_sweep_start/status through handle_subcommand kwargs."

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
  - "call_core_check's formatter emits only compliant/total counts plus up to 10 failing paths with their failure reasons (truncated with a '...and N more' tail) — bounded output, no raw route internals leaked into chat (T-45-KEY mitigation)."
  - "command_router.py gained explicit stats/check branches (previously both fell through to the fixed_prompt dict lookup at the bottom of handle_subcommand); graph's branch was rewritten in place. All three now call the injected gateway callable positionally (call_core_graph(user_id)), matching the existing call_core_sweep_status(user_id) convention rather than the keyword-heavy core_gateway signature (that keyword surface is only used by the bot.py thin wrappers)."
  - "_SUBCOMMAND_PROMPTS lost its stats and check entries (the now-dead fixed-prompt fallback); SUBCOMMAND_HELP text for :graph/:stats/:check was left untouched since it already documented the correct user-facing behavior."
  - "test_subcommands.py's pre-existing test_check_subcommand_calls_core (which asserted the old free-text call_core dispatch) was rewritten to test_check_subcommand_calls_gateway_not_core, asserting the new gateway path and asserting call_core is never invoked — this is a direct-conflict test-authored-for-old-behavior fix, not a new deviation from plan scope."

requirements-completed: [NOTE-03]

coverage:
  - id: D1
    description: "call_core_graph/call_core_stats/call_core_check GET the correct /vault/* paths with X-Sentinel-Key, format the route JSON into a Discord-ready string, and degrade to a friendly failure string on transport error"
    requirement: "NOTE-03"
    verification:
      - kind: unit
        ref: "interfaces/discord/tests/test_core_gateway.py#test_call_core_graph_formats_response"
        status: pass
      - kind: unit
        ref: "interfaces/discord/tests/test_core_gateway.py#test_call_core_stats_formats_response"
        status: pass
      - kind: unit
        ref: "interfaces/discord/tests/test_core_gateway.py#test_call_core_check_formats_response_with_failures"
        status: pass
      - kind: unit
        ref: "interfaces/discord/tests/test_core_gateway.py#test_call_core_graph_transport_error_returns_friendly_string (+ stats/check equivalents)"
        status: pass
  - id: D2
    description: ":graph/:stats/:check branches invoke the new gateway callables, never the free-text call_core path; dead stats/check fixed-prompt entries removed"
    requirement: "NOTE-03"
    verification:
      - kind: unit
        ref: "interfaces/discord/tests/test_command_router_module.py#test_graph_subcommand_invokes_gateway_not_call_core (+ stats/check equivalents)"
        status: pass
      - kind: unit
        ref: "interfaces/discord/tests/test_subcommands.py#test_check_subcommand_calls_gateway_not_core (+ stats/graph equivalents)"
        status: pass
      - kind: manual
        ref: "grep -c 'call_core_graph' interfaces/discord/command_router.py -> 2 (import + call site)"
        status: pass

metrics:
  duration: ~7min
  completed: 2026-07-06
  tasks_completed: 2
  files_changed: 6
---

# Phase 45 Plan 07: Discord Gateway Rewire for :graph/:stats/:check Summary

Added `call_core_graph`/`call_core_stats`/`call_core_check` to `core_gateway.py` (mirroring
`call_core_sweep_status` exactly) and rewired the `:graph`, `:stats`, and `:check` Discord
subcommands to call them instead of resolving to a free-text `call_core` fixed prompt, closing
SC-3/SC-4 on the interface side and removing the now-dead `_SUBCOMMAND_PROMPTS` stats/check
entries.

## What Was Built

**Task 1 — Gateway functions (`core_gateway.py`):**

- `call_core_graph(*, user_id, core_url, api_key)` — GETs `/vault/graph`, formats
  `note_count`/`orphans`/`hub_count`/`link_density` into `"Graph: {N} notes, {M} orphans, {K} hubs,
  link_density={D:.2f}"`, appending a `(caveat)` suffix when the route reports a stale-index caveat.
- `call_core_stats(*, user_id, core_url, api_key)` — GETs `/vault/stats`, formats
  `note_count`/`hub_count`/`orphan_count`/`avg_notes_per_hub`/`link_density` similarly.
- `call_core_check(*, user_id, core_url, api_key)` — GETs `/vault/check`, formats
  `compliant_count`/`note_count` plus up to 10 failing note paths with their `failures` list
  (truncated with a count tail beyond 10).
- All three share the exact `call_core_sweep_status` posture: `httpx.AsyncClient` GET with the
  `X-Sentinel-Key` header and a 20s timeout, `resp.raise_for_status()`, JSON parse, and a
  try/except that logs a warning and returns a friendly failure string on any `Exception` — never
  raises to the caller.
- 8 new unit tests in `test_core_gateway.py` mock `core_gateway.httpx` (mirroring the
  `patch("bot.httpx")` pattern already used in `test_thread_persistence.py`) to assert both the
  formatted-success path and the friendly-failure-on-transport-error path for each function.

**Task 2 — Rewire + thread through bot.py (`command_router.py`, `bot.py`):**

- `command_router.handle_subcommand` gained three new required keyword parameters:
  `call_core_graph`, `call_core_stats`, `call_core_check`.
- The `:graph` branch (previously a free-text prompt built from `args`) now calls
  `call_core_graph(user_id)` directly; `:stats` and `:check` gained explicit branches calling
  `call_core_stats(user_id)` / `call_core_check(user_id)` (previously both silently fell through
  to the bottom-of-function `subcommand_prompts.get(subcmd)` fixed-prompt fallback).
- `bot.py` gained three thin wrappers — `_call_core_graph`, `_call_core_stats`,
  `_call_core_check` — mirroring `_call_core_sweep_status`'s shape (positional `user_id`,
  supplying `SENTINEL_CORE_URL`/`SENTINEL_API_KEY`), registered in
  `handle_sentask_subcommand`'s kwargs dict passed to `command_router.handle_subcommand`.
  the `stats` and `check` entries were removed from `_SUBCOMMAND_PROMPTS` (dead fixed-prompt
  fallback eliminated); `SUBCOMMAND_HELP` text for all three commands was left unchanged since it
  already documented correct user-facing behavior.
- Test updates: `test_command_router_module.py` gained three new tests asserting `:graph`/`:stats`/
  `:check` invoke the injected gateway callable and never `call_core`; the existing direct
  `handle_subcommand` call was extended with the three new required kwargs.
  `test_subcommands.py`'s `test_check_subcommand_calls_core` (which asserted the old free-text
  dispatch) was rewritten to `test_check_subcommand_calls_gateway_not_core`, and new
  `test_stats_subcommand_calls_gateway_not_core` / `test_graph_subcommand_calls_gateway_not_core`
  tests were added.

## Verification

- `cd interfaces/discord && .venv/bin/python -m pytest tests/test_core_gateway.py -q` → 8 passed.
- `cd interfaces/discord && .venv/bin/python -m pytest tests/test_command_router_module.py tests/test_subcommands.py -q` → 72 passed.
- `cd interfaces/discord && .venv/bin/python -m pytest tests/ -q` → 258 passed, 50 skipped (full discord suite green).
- `cd sentinel-core && .venv/bin/python -m pytest tests/ -q` → 550 passed, 12 skipped (473+ baseline floor holds — count grew across Phase 45).
- `grep -c 'call_core_graph' interfaces/discord/command_router.py` → 2 (import + call site).
- Confirmed `_SUBCOMMAND_PROMPTS` no longer contains `stats` or `check` keys (manual read of `bot.py:174-189`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — stale test contradicting the plan's intended change] Rewrote `test_check_subcommand_calls_core`**
- **Found during:** Task 2
- **Issue:** `test_subcommands.py` contained a pre-existing test (`test_check_subcommand_calls_core`)
  that explicitly asserted `:check` routes through `_SUBCOMMAND_PROMPTS` to the free-text
  `call_core` path — directly contradicted by this plan's objective (remove the dead
  stats/check prompt entries, rewire to the gateway). The plan's own verification step
  (`pytest tests/test_command_router_module.py tests/test_subcommands.py -q` → green) requires
  this test to be reconciled with the new behavior, not left failing.
- **Fix:** Renamed/rewrote it as `test_check_subcommand_calls_gateway_not_core`, asserting
  `bot._call_core_check` is invoked and `bot._call_core` is not; added parallel
  `test_stats_subcommand_calls_gateway_not_core` and `test_graph_subcommand_calls_gateway_not_core`
  for full coverage of the three rewired subcommands.
- **Files modified:** `interfaces/discord/tests/test_subcommands.py`
- **Commit:** c8c530c

None else — plan executed as written.

## Known Stubs

None.

## Threat Flags

None — this plan closes the T-45-DEAD threat (dead fixed-prompt fallback) identified in the plan's
own threat model rather than introducing new surface; no new endpoints, auth paths, or schema
changes were added.

## Self-Check: PASSED
