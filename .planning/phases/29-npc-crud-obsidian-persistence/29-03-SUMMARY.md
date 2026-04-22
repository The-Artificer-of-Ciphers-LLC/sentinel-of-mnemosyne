---
phase: 29-npc-crud-obsidian-persistence
plan: "03"
subsystem: discord-bot + shared-client
tags: [discord, npc, pathfinder, routing, tdd]
dependency_graph:
  requires:
    - "29-01"  # pathfinder module NPC endpoints (modules/pathfinder/app/routes/npc.py)
  provides:
    - "SentinelCoreClient.post_to_module — shared/sentinel_client.py"
    - "_pf_dispatch() + :pf subcommand routing — interfaces/discord/bot.py"
  affects:
    - "interfaces/discord/bot.py"
    - "shared/sentinel_client.py"
tech_stack:
  added: []
  patterns:
    - "post_to_module raises on error (caller formats domain errors) vs send_message swallows"
    - "_pf_dispatch noun/verb/rest parser mirrors existing subcmd routing pattern"
    - "attachments threaded from on_message -> _route_message -> handle_sentask_subcommand -> _pf_dispatch"
key_files:
  created: []
  modified:
    - shared/sentinel_client.py
    - interfaces/discord/bot.py
    - interfaces/discord/tests/test_subcommands.py
    - shared/tests/test_sentinel_client.py
decisions:
  - "post_to_module does NOT swallow errors — callers in _pf_dispatch handle 409/404 with domain-specific messages"
  - "_pf_dispatch inserted before :help check so :pf is dispatched before the fallback dict lookup"
  - "Relation validation in bot.py (not module) — fail fast, no API call on invalid enum value"
  - "attachments default=None on both handle_sentask_subcommand and _route_message — backward-compatible with /sen slash command which has no attachment support"
metrics:
  duration: "~3 min"
  completed: "2026-04-22"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 29 Plan 03: Discord Bot :pf Routing + SentinelCoreClient.post_to_module Summary

SentinelCoreClient gains `post_to_module()` for direct module proxy calls; `bot.py` gains `_pf_dispatch()` routing all five NPC verbs plus `:pf` wired into `handle_sentask_subcommand`.

## What Was Built

### Task 1 — `post_to_module()` on SentinelCoreClient

`shared/sentinel_client.py` now exposes a second async method alongside `send_message()`:

- `async def post_to_module(self, path: str, payload: dict, client: httpx.AsyncClient) -> dict`
- POSTs to `{base_url}/{path}` with `X-Sentinel-Key` header
- Strips leading slash from `path` automatically
- Raises `httpx.HTTPStatusError`, `httpx.ConnectError`, `httpx.TimeoutException` — callers format domain errors
- Existing `send_message()` is unchanged

### Task 2 — `_pf_dispatch()` + bot wiring

`interfaces/discord/bot.py` changes:

- `_VALID_RELATIONS = frozenset({"knows", "trusts", "hostile-to", "allied-with", "fears", "owes-debt"})` — closed enum per D-13
- `async def _pf_dispatch(args, user_id, attachments=None)` — parses `<noun> <verb> <rest>`, routes 5 NPC verbs to module proxy paths
- `handle_sentask_subcommand` gains `attachments: list | None = None` kwarg; `if subcmd == "pf":` is the first branch
- `_route_message` gains `attachments: list | None = None` kwarg, forwards to `handle_sentask_subcommand`
- `on_message` passes `list(message.attachments)` through the chain

**NPC verb routing:**

| Command | Module path |
|---------|-------------|
| `:pf npc create <name> \| <desc>` | `modules/pathfinder/npc/create` |
| `:pf npc update <name> \| <correction>` | `modules/pathfinder/npc/update` |
| `:pf npc show <name>` | `modules/pathfinder/npc/show` |
| `:pf npc relate <name> <rel> <target>` | `modules/pathfinder/npc/relate` (after local validation) |
| `:pf npc import` (attachment) | `modules/pathfinder/npc/import` |

## Tests

**TDD cycle followed for both tasks.**

- `shared/tests/test_sentinel_client.py`: 5 new tests for `post_to_module` (success, leading-slash strip, HTTPStatusError propagation, ConnectError propagation, X-Sentinel-Key header) — all pass GREEN
- `interfaces/discord/tests/test_subcommands.py`: 10 new tests for `_pf_dispatch` and bot wiring — all pass GREEN
- All pre-existing tests continue to pass (7 sentinel_client + 9 subcommands)
- **Total: 31 tests passing**

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. All five NPC verbs are fully wired. `_pf_dispatch` returns real responses from `post_to_module()` results; error handling for 409/404/connect/timeout is complete.

## Threat Surface Scan

No new network endpoints or auth paths introduced. Changes are client-side only (bot.py calls existing module proxy via existing SentinelCoreClient). All threat mitigations from plan threat model are applied:

- T-29-01: NPC name passed as JSON field, not in URL
- T-29-03: `X-Sentinel-Key` header on every `post_to_module` call
- T-29-04: `timeout=10.0` on attachment fetch in `npc import`

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `shared/sentinel_client.py` exists | FOUND |
| `interfaces/discord/bot.py` exists | FOUND |
| Commit 4b046a3 (post_to_module) | FOUND |
| Commit 6f4ec80 (_pf_dispatch) | FOUND |
| 31 tests passing | PASSED |
