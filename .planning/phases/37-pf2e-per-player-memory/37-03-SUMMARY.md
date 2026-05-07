---
phase: 37-pf2e-per-player-memory
plan: "03"
subsystem: pathfinder/foundry-memory-projection
tags: [tdd, red, fcm, projection, idempotency, dedupe]
type: tdd
wave: 0
requires:
  - Phase 35 (Foundry import flow)
  - app.foundry_chat_import (existing helpers reused at function-scope)
provides:
  - RED contract tests for app.foundry_memory_projection.project_foundry_chat_memory
  - RED contract test for app.foundry_chat_import._load_projection_state (Wave 6 loader)
affects:
  - modules/pathfinder/tests/
tech-stack:
  added: []
  patterns:
    - function-scope ImportError gate for Wave 0 RED before Wave 5/6 modules land
    - per-target dedupe key discrimination (player_map vs npc_history)
    - dry-run parity: identical metric keys, zero mutation
key-files:
  created:
    - modules/pathfinder/tests/test_foundry_memory_projection.py
    - modules/pathfinder/tests/test_projection_idempotency.py
  modified:
    - modules/pathfinder/tests/test_foundry_chat_import.py (1 additive test only)
decisions:
  - "Row format regex anchors timestamp + (foundry, key=...) + content — protects FCM-03 contract from drift"
  - "Per-target dedupe disjointness asserted via set isolation rather than reaching into the projection module's hashing internals"
  - "Backcompat loader test tolerates either dict-of-sets or dataclass shape — leaves Wave 6 implementer the choice without weakening the contract"
metrics:
  duration: ~12 min
  completed: 2026-05-07
  tests_added: 15
---

# Phase 37 Plan 03: Wave 0 RED Tests for Foundry Memory Projection Summary

**One-liner:** 15 RED tests pinning the FCM projection contracts (classification precedence, player-map four-section build, NPC history two-mode append, idempotency, per-target dedupe, dry-run parity, state-file backcompat) before any production code lands.

## Scope

Wave 0 RED slice for the FCM (Foundry Chat Memory) projection module that Wave 5 will implement. Tests fail at the import boundary today (`No module named 'app.foundry_memory_projection'` for the projection tests; `ImportError` on `_load_projection_state` for the backcompat test) and turn green when Waves 5 and 6 land.

## Tasks Executed

### Task 1: RED tests for foundry_memory_projection (FCM-01..03, FCM-05)

**File:** `modules/pathfinder/tests/test_foundry_memory_projection.py`
**Commit:** `5877bf6`
**Tests added:** 10

| Test                                                                  | Requirement | Contract pinned                                                            |
| --------------------------------------------------------------------- | ----------- | -------------------------------------------------------------------------- |
| `test_classify_speaker_precedence_alias_first`                        | FCM-01      | alias_map wins over npc_roster                                             |
| `test_classify_speaker_precedence_npc_roster_second`                  | FCM-01      | npc_roster wins over unknown                                               |
| `test_classify_speaker_unknown_increments_stat`                       | FCM-01      | unknown speaker → unmatched stat, zero writes                              |
| `test_project_player_map_creates_four_sections`                       | FCM-02      | Voice Patterns / Notable Moments / Party Dynamics / Chat Timeline headings |
| `test_npc_history_append_existing_section`                            | FCM-03      | section exists → patch_heading append, no put_note                         |
| `test_npc_history_create_section_when_missing`                        | FCM-03      | section missing → put_note adds section, no patch_heading                  |
| `test_npc_history_row_format_includes_timestamp_source_hash`          | FCM-03      | row regex `- [YYYY-MM-DD HH:MM:SS] (foundry, key=...) <content>`           |
| `test_dry_run_no_writes_same_metric_shape`                            | FCM-05      | dry_run=True → 0 writes, identical metric keys                             |
| `test_profile_md_is_never_written_by_projector`                       | Pitfall 1   | projector never touches profile.md (schema-drift guard)                    |
| `test_unknown_speaker_does_not_create_unknown_npc_note`               | FCM-01      | unknown speaker doesn't even GET an NPC note                               |

**RED verified:** all 10 fail with `ModuleNotFoundError: No module named 'app.foundry_memory_projection'`.

### Task 2: RED idempotency + ADDITIVE state-file backcompat test

**Files:**
- `modules/pathfinder/tests/test_projection_idempotency.py` (created)
- `modules/pathfinder/tests/test_foundry_chat_import.py` (1 test appended)

**Commit:** `83365b9`
**Tests added:** 4 + 1 = 5

| Test                                                  | File                              | Requirement | Contract pinned                                              |
| ----------------------------------------------------- | --------------------------------- | ----------- | ------------------------------------------------------------ |
| `test_projection_idempotent_on_rerun`                 | test_projection_idempotency.py    | FCM-04      | second run = 0 player_updates, 0 npc_updates, 0 new writes   |
| `test_state_file_persists_player_and_npc_keys`        | test_projection_idempotency.py    | FCM-04      | state JSON contains player_projection_keys + npc_projection_keys |
| `test_dedupe_key_uses_foundry_id_when_present`        | test_projection_idempotency.py    | FCM-04      | _id wins; fallback uses timestamp\|speaker\|content          |
| `test_dedupe_key_target_discriminator`                | test_projection_idempotency.py    | FCM-04      | player vs npc key sets disjoint per-record                   |
| `test_state_file_backcompat_missing_projection_keys`  | test_foundry_chat_import.py (END) | FCM-04      | legacy `{imported_keys: [...]}` JSON loads with empty projection sets |

**RED verified:** 4 idempotency tests fail on `ModuleNotFoundError: app.foundry_memory_projection`; backcompat test fails on `ImportError: _load_projection_state` (Wave 6 symbol).

## Verification

```
$ cd modules/pathfinder && python -m pytest \
    tests/test_foundry_memory_projection.py \
    tests/test_projection_idempotency.py \
    tests/test_foundry_chat_import.py \
    --tb=line --no-header
Pytest: 4 passed, 15 failed
```

- **15 RED** — all new tests fail at the import boundary (expected).
- **4 PASSED** — pre-existing tests in `test_foundry_chat_import.py` are unchanged. Test-Rewrite Ban honored: no existing test was modified, weakened, skipped, or deleted; the new test was appended to the end of the file.

## Requirements Touched

- FCM-01 (speaker classification) — 3 RED tests (alias precedence, npc fallback, unknown stat)
- FCM-02 (player map four sections) — 1 RED test
- FCM-03 (NPC history two-mode append + row format) — 3 RED tests
- FCM-04 (idempotency + dedupe key + state-file shape + backcompat) — 5 RED tests
- FCM-05 (dry-run parity) — 1 RED test

Plus 2 hardening tests (profile.md schema-drift guard, unknown-speaker NPC isolation) covering Pitfall 1.

## Deviations from Plan

None — plan executed exactly as written. 10 + 4 + 1 = 15 RED tests delivered; row regex uses `re.search` on the actual `patch_heading` call args (behavioral, not source-grep); per-target dedupe asserted via set disjointness without reaching into module internals.

## Self-Check: PASSED

- File exists: `modules/pathfinder/tests/test_foundry_memory_projection.py` ✓
- File exists: `modules/pathfinder/tests/test_projection_idempotency.py` ✓
- File modified: `modules/pathfinder/tests/test_foundry_chat_import.py` ✓ (additive)
- Commit `5877bf6` in git log ✓
- Commit `83365b9` in git log ✓
- 15 RED tests confirmed via pytest run ✓
- 4 pre-existing tests still PASS ✓
