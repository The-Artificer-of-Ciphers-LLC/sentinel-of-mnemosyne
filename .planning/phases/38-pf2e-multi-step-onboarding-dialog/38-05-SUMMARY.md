---
phase: 38-pf2e-multi-step-onboarding-dialog
plan: 05
subsystem: discord-pathfinder-onboarding
tags: [pathfinder, discord, dialog, wave-2, green, routing]
requires: [38-02, 38-04]
provides:
  - "dialog_router.maybe_consume_as_answer (pre-router gate enforcing D-02 hit conditions)"
  - "discord_router_bridge two-step pipeline (dialog_router → command_router fall-through)"
affects:
  - "interfaces/discord/dialog_router.py (new file, 116 lines)"
  - "interfaces/discord/discord_router_bridge.py (rewritten — additive sentinel_client/http_client kwargs + pre-gate call)"
  - "interfaces/discord/bot.py (additive only at _route_message bridge call site — httpx.AsyncClient + 2 kwargs)"
  - "interfaces/discord/tests/conftest.py (pre-import of pathfinder_player_dialog to fix collection-order pollution)"
tech-stack:
  added: []
  patterns:
    - "pre-router gate / pipeline: bridge tries dialog_router first, falls through to command_router on None"
    - "lazy import of pathfinder_player_dialog inside the gate function (decouples module load from bot.py import cycle)"
    - "lightweight HTTP existence check (status-only, no frontmatter parse) at the gate layer; full draft load deferred to consume_as_answer"
key-files:
  created:
    - interfaces/discord/dialog_router.py
  modified:
    - interfaces/discord/discord_router_bridge.py
    - interfaces/discord/bot.py
    - interfaces/discord/tests/conftest.py
decisions:
  - "Plan example used ppd.load_draft for the draft pre-check, but the 38-02 RED tests assert (a) http_client.get is invoked with the canonical /vault/.../{thread_id}-{user_id}.md URL and (b) the default response body 'step: character_name\\n' (no `---` frontmatter delimiters) constitutes a hit. ppd.load_draft would parse that body, find no frontmatter, and return None — turning hit tests into misses. Per the Test-Rewrite Ban, the implementation was adapted to the tests: dialog_router does its own raw GET, branches on status_code == 200, and lets consume_as_answer load the draft authoritatively in the hit path. Documented as Rule 1 deviation."
  - "Dialog gate runs only when both sentinel_client AND http_client are passed. This keeps existing test fixtures (test_discord_router_bridge.py) byte-for-byte equivalent — they call route_message without those kwargs and continue to delegate straight to command_router. Production wiring in bot.py always supplies both."
  - "bot.py _route_message wraps the bridge call in `async with httpx.AsyncClient()` (additive — the pattern is already used by dispatch_pf at bot.py:460). on_message body is unchanged."
  - "conftest.py pre-imports pathfinder_player_dialog to fix a collection-order issue where test_dialog_router's stub helper would register an empty ModuleType into sys.modules if no real module was loaded yet, polluting test_pathfinder_player_dialog. Pre-importing ensures the helper finds the real module via sys.modules.get and only patches its consume_as_answer attribute. Rule 3 deviation: blocking collection-order issue."
metrics:
  duration_minutes: 10
  tasks_completed: 2
  tests_turned_green: 8
  files_created: 1
  files_modified: 3
  commits: 2
completed: 2026-05-09
---

# Phase 38 Plan 05: Wave 2 Dialog Router Wiring Summary

Wired the pre-router gate. `discord_router_bridge.route_message` now tries
`dialog_router.maybe_consume_as_answer` first; on a hit it returns the dialog
response directly, on a miss it falls through to `command_router` with the
original kwargs unchanged. All 8 RED tests from Plan 38-02 turn GREEN. The
locked seam constraints D-03 (`command_router.py` unchanged) and D-04
(`bot.py:on_message` unchanged) are honored — only `_route_message` gained
additive kwargs at its bridge call site.

## Tasks

| # | Task | Commit | Tests |
|---|------|--------|-------|
| 1 | Implement dialog_router.maybe_consume_as_answer | 8398c81 | 8/8 RED → GREEN |
| 2 | Wire dialog_router into discord_router_bridge (D-01) | f5c1775 | 36/36 across dialog_router + bridge + command_router + player_dialog suites |

## Hit Conditions (D-02) — Behavioural Contract

`maybe_consume_as_answer` returns a non-None string ONLY when ALL of the
following hold:

1. `message` is non-empty (after `.strip()`)
2. `message.lstrip()` does NOT start with `:` (raw command prefix, ignoring
   leading whitespace per `command_router.py:8-34` semantics)
3. `channel` is an instance of `discord.Thread`
4. HTTP GET against `{OBSIDIAN_API_URL}/vault/mnemosyne/pf2e/players/_drafts/{thread.id}-{user_id}.md`
   returns status 200 (existence check; full parse deferred to
   `consume_as_answer`)

On miss (any condition fails) or any pre-check exception
(`httpx.RequestError`, unexpected `Exception`), the function returns `None`
and the bridge falls through to `command_router` unchanged. The `:` /
non-thread checks complete BEFORE any HTTP call so regular text channels
incur zero additional network traffic.

## Wiring (D-01)

```
on_message  →  _route_message  →  discord_router_bridge.route_message
                                       │
                                       ├── dialog_router.maybe_consume_as_answer  (NEW pre-gate)
                                       │       │
                                       │       ├── hit  →  consume_as_answer  →  return string
                                       │       └── miss →  None
                                       │
                                       └── command_router.route_message          (UNCHANGED, fall-through)
```

## Locked-Seam Verification

| Constraint | Verification | Result |
|------------|--------------|--------|
| D-03: `command_router.py` byte-for-byte unchanged | `git diff interfaces/discord/command_router.py` | empty |
| D-04: `bot.py:on_message` byte-for-byte unchanged | `git diff` shows single hunk at `_route_message` (line 489); `on_message` (line 664+) untouched | confirmed |
| Bridge call site additive only | New kwargs `sentinel_client=_sentinel_client`, `http_client=http_client`; existing kwargs unchanged | confirmed |

## Test Results

```
tests/test_dialog_router.py            8 passed   (8 RED → 8 GREEN — plan 38-02 contract met)
tests/test_discord_router_bridge.py    2 passed   (no regression — bridge still delegates on miss)
tests/test_command_router_module.py    3 passed   (no regression)
tests/test_pathfinder_player_dialog.py 23 passed  (no regression — wave 1 tests still GREEN)
                                       ────────
                                       36 passed
```

`test_pathfinder_player_adapter.py` shows 22 passed / 17 failed both with and
without this plan's changes (verified by `git stash` baseline). Those
failures are pre-existing and out of scope per the executor scope-boundary
rule; logged below for the deferred-items tracker.

## Deviations from Plan

### Rule 1 — Bug fix in plan example

**Found during:** Task 1.
**Issue:** The plan's reference implementation called `ppd.load_draft(...)`
for the draft pre-check. `load_draft` parses frontmatter and returns `None`
when no `---` delimiters are present. The 38-02 RED tests use a default
response body of `"step: character_name\n"` (no frontmatter delimiters) AND
assert that this body constitutes a hit — so `load_draft` would have flipped
all hit-path tests into miss-path tests.
**Fix:** Inline a lightweight `http_client.get` at the gate (status-only
existence check). The authoritative draft load remains in
`consume_as_answer` (Wave 1, plan 38-04), unchanged.
**Files:** `interfaces/discord/dialog_router.py`.
**Commit:** 8398c81.

### Rule 3 — Blocking collection-order issue in test infrastructure

**Found during:** Task 2 verification.
**Issue:** `test_dialog_router.py::_stub_consume_as_answer` registers a stub
`types.ModuleType("pathfinder_player_dialog")` into `sys.modules` if no
real module is loaded yet. In default alphabetical collection order
`test_dialog_router` runs before `test_pathfinder_player_dialog`, so the
stub poisoned `sys.modules` and downstream tests got `ImportError: cannot
import name 'draft_path' from 'pathfinder_player_dialog'`.
**Fix:** Pre-import `pathfinder_player_dialog` at conftest module scope so
the stub helper's `sys.modules.get(...)` finds the real module first and
only patches its `consume_as_answer` attribute (which `monkeypatch`
correctly reverts after each test). RED tests in `test_dialog_router.py`
remain byte-for-byte unchanged (Test-Rewrite Ban honored).
**Files:** `interfaces/discord/tests/conftest.py`.
**Commit:** f5c1775.

## Deferred Issues (Pre-existing, Out of Scope)

`test_pathfinder_player_adapter.py` has 17 pre-existing failures unrelated
to dialog routing (verified against baseline `git stash` run on `main`
before this plan landed). These predate Phase 38-05 and are tracked
separately; this plan neither caused nor cleared them.

## Self-Check: PASSED

- `interfaces/discord/dialog_router.py` exists.
- Commit 8398c81 in git log.
- Commit f5c1775 in git log.
- `git diff interfaces/discord/command_router.py` empty.
- 8 of 8 plan-38-02 RED tests now GREEN.
