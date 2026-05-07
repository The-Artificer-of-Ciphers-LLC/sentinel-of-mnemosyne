---
phase: 37-pf2e-per-player-memory
plan: 14
subsystem: pathfinder
tags: [tests, integration, isolation, idempotency, docs, closeout]
requires:
  - 37-12 (Foundry import route + projection wiring)
  - 37-13 (Discord adapter)
provides:
  - End-to-end PVL-07 isolation regression test
  - End-to-end Foundry-import idempotency test (route layer)
  - User-facing :pf player command reference
  - Phase 37 architecture map
affects:
  - modules/pathfinder/app/routes/foundry.py (Rule 1 bug fix)
tech-stack:
  added: []
  patterns:
    - ASGITransport route-level integration with recording obsidian mock
    - tmp_path-backed projection state file fixtures
key-files:
  created:
    - modules/pathfinder/tests/test_player_isolation.py
    - modules/pathfinder/tests/test_phase37_integration.py
    - docs/USER-GUIDE.md
  modified:
    - .planning/phases/37-pf2e-per-player-memory/37-CONTEXT.md
    - .planning/phases/37-pf2e-per-player-memory/deferred-items.md
    - modules/pathfinder/app/routes/foundry.py
decisions:
  - "Route resolver wrapper accepts string speaker_token (not record dict)"
  - "Test fixture uses exact-case roster keys (resolve_foundry_speaker is strict-dict, not case-insensitive)"
metrics:
  duration_minutes: 7
  completed: 2026-05-07
---

# Phase 37 Plan 14: Closeout — Integration Tests + Docs Summary

**One-liner:** End-to-end PVL-07 isolation + FCM-04 idempotency tests at the route layer caught and fixed a silent identity-resolver-shape bug in routes/foundry; closeout adds USER-GUIDE.md and the Phase 37 architecture map.

## What Shipped

### Integration tests (5 new tests, all GREEN)

`modules/pathfinder/tests/test_player_isolation.py`
- `test_two_users_recall_no_cross_leakage` — POST /player/recall for u1
  with two onboarded players in the vault. Asserts every list_directory
  and get_note path argument hitting the player namespace sits under u1's
  slug and never touches u2's slug-prefixed tree.
- `test_npc_writes_isolated_per_player` — Two players writing
  `:pf player npc Varek` produce two distinct put_note paths
  (`players/{slug_a}/npcs/varek.md` and `players/{slug_b}/npcs/varek.md`)
  and never the global `mnemosyne/pf2e/npcs/varek.md` Phase-29 path.

`modules/pathfinder/tests/test_phase37_integration.py`
- `test_foundry_import_idempotent_at_route_layer` — Two POST
  /foundry/messages/import calls on the same inbox dir. Run 1 produces
  >=1 player_updates, >=1 npc_updates, "Mystery Stranger" in
  unmatched_speakers. Run 2 produces 0/0 updates with non-zero deduped
  counts; obsidian.patch_heading and projection-target put_note counts
  unchanged.
- `test_foundry_import_dry_run_then_live_writes_once` — dry_run=true:
  zero put_note/patch_heading writes, full metric shape returned. First
  live: writes equal to first-pass live. Second live (same inbox
  recreated): zero new projection writes; idempotency holds across the
  dry-run boundary.
- `test_state_file_extended_in_place` — After live import, the on-disk
  `.foundry_chat_import_state.json` has all three arrays
  (`imported_keys`, `player_projection_keys`, `npc_projection_keys`)
  with `imported_keys` populated (legacy importer behavior preserved).

### Bug fix (Rule 1)

`modules/pathfinder/app/routes/foundry.py` — the plan-37-12 inline
`_identity_resolver` wrapper was typed and coded to accept a record dict
(`record.get("speaker")`), but `foundry_memory_projection.project_foundry_chat_memory`
invokes it with the already-extracted speaker token (string). The bug was
silent — every Foundry import classified all speakers as "unknown" and
produced zero player/npc projection updates. No Wave 7 unit test caught
this because the projection module's unit tests passed in their own
sync-callable resolvers; the route's resolver was only exercised in
production. The end-to-end integration test surfaced it on first run.

Fix: accept the string speaker_token directly. Defensive fallback retains
tolerance of the legacy dict shape so any older caller doesn't blow up.

### Docs

`docs/USER-GUIDE.md` (new) — top-level user guide with a PF2E Player
Commands section covering all eight `:pf player` verbs, onboarding flow,
and Foundry chat memory projection summary.

`.planning/phases/37-pf2e-per-player-memory/37-CONTEXT.md` — appended
Architecture Map section: two deep modules, six shared seams, the ten
routes table, vault layout diagram, requirement→test traceability matrix,
and closeout notes including the resolver bug fix.

## Commits

| Hash | Message |
|------|---------|
| `a8b7172` | test(37-14): add E2E isolation regression + foundry import idempotency |
| `8aee784` | fix(37-14): foundry route resolver accepts speaker token, not record dict |
| `9d5c227` | docs(37-14): add USER-GUIDE.md and Phase 37 architecture map |

## Verification

`cd modules/pathfinder && python3 -m pytest tests/test_player_isolation.py tests/test_phase37_integration.py` — **5 passed**.

Full pathfinder suite: 333 passed, 4 failed (all pre-existing on main; logged in `deferred-items.md`).

Full discord suite: 138 passed, 18 failed (all pre-existing on main; identical pass/fail count via `git stash` baseline check).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] routes/foundry._identity_resolver shape mismatch**

- **Found during:** Task 1 (running the new E2E idempotency test)
- **Issue:** `routes/foundry._identity_resolver(record: dict)` was being
  invoked by `foundry_memory_projection.project_foundry_chat_memory` with
  a string speaker_token, raising `AttributeError: 'str' object has no
  attribute 'get'`. The exception was swallowed by the projection
  module's defensive try/except, silently classifying every speaker as
  "unknown" — so production Foundry imports produced zero player/npc
  updates without any visible error.
- **Fix:** Accept the string token directly; tolerate the legacy dict
  shape as a defensive fallback for older callers.
- **Files modified:** `modules/pathfinder/app/routes/foundry.py`
- **Commit:** `8aee784`

### Deferred (Out of Scope)

Two pre-existing main-branch test failures verified via `git stash` and
logged in `deferred-items.md`. Both are out of scope for plan 37-14:

- `test_foundry.py::test_roll_event_accepted` / `test_notify_dispatched`
  / `test_llm_fallback` — `NameError: name 'get_profile' is not defined`
  at `routes/foundry.py:106`. Pre-existing since plan 37-12.
- `test_registration.py::test_registration_payload_has_16_routes` —
  asserts 16 routes but actual count is 29 after Phases 36 + 37. The
  Test-Rewrite Ban applies to this assertion change; surfaced for
  operator-authorized fix.

## Phase 37 Acceptance Criteria Coverage

The 12 Phase 37 requirements (PVL-01..07, FCM-01..05) and 9 PRD acceptance
criteria all have at least one passing behavioral test. The new E2E tests
in this plan close the route-layer coverage gap that allowed the
identity-resolver bug to ship undetected through plan 37-12.

| Requirement | Covered By |
|-------------|------------|
| PVL-01 onboarding | `test_player_routes::test_post_onboard_*` |
| PVL-02 capture (note/ask/todo) | `test_player_routes::test_post_*` |
| PVL-03 deterministic recall | `test_player_recall_engine`, `test_post_recall_*` |
| PVL-04 canonization | `test_player_routes::test_post_canonize_*` |
| PVL-05 style preset | `test_player_routes::test_post_style_*` |
| PVL-06 deterministic slug | `test_player_identity_resolver` |
| PVL-07 cross-player isolation | `test_player_vault_store`, **`test_player_isolation`** |
| FCM-01 identity classifier | `test_player_identity_resolver` |
| FCM-02 player chat map | `test_memory_projection_store` |
| FCM-03 NPC chat history | `test_memory_projection_store` |
| FCM-04 idempotency | `test_projection_idempotency`, **`test_phase37_integration`** |
| FCM-05 dry-run contract | `test_foundry_memory_projection`, **`test_phase37_integration`** |

## Self-Check: PASSED

Files created and present on disk:
- `modules/pathfinder/tests/test_player_isolation.py` ✓
- `modules/pathfinder/tests/test_phase37_integration.py` ✓
- `docs/USER-GUIDE.md` ✓

Section headings present:
- `## PF2E Player Commands` in USER-GUIDE.md ✓
- `## Architecture Map` in 37-CONTEXT.md ✓

Commits in git log:
- `a8b7172` ✓
- `8aee784` ✓
- `9d5c227` ✓

Tests:
- 5/5 new E2E tests passing ✓
- No regressions in pathfinder or discord suites (failures are pre-existing) ✓
