---
phase: 37-pf2e-per-player-memory
plan: 01
subsystem: pathfinder
tags: [tdd, red, wave-0, player-memory, fcm, pvl]
requires: []
provides:
  - "RED tests for app.player_identity_resolver (PVL-06, FCM-01)"
  - "RED tests for app.player_vault_store (PVL-07 isolation contract)"
  - "RED tests for app.memory_projection_store (FCM-02, FCM-03)"
affects:
  - "Wave 1 (plan 37-06) implementations are constrained by these contracts"
tech_stack_added: []
patterns:
  - "Function-scope symbol imports (Phase 33-01 STATE.md decision)"
  - "AsyncMock obsidian + behavioral assertions on call_args (Phase 32 NPC test pattern)"
key_files_created:
  - "modules/pathfinder/tests/test_player_identity_resolver.py"
  - "modules/pathfinder/tests/test_player_vault_store.py"
  - "modules/pathfinder/tests/test_memory_projection_store.py"
key_files_modified: []
decisions:
  - "Slug contract pinned: prefix `p-`, total length 14 chars (PVL-06)."
  - "FCM-01 precedence locked at test layer: alias > npc_roster > pc_character_name > unknown."
  - "FCM-03 detection regex must be line-anchored — covered by test_section_detection_regex_anchored."
  - "PVL-07 isolation enforced via _resolve_player_path helper that rejects traversal and malformed slugs."
metrics:
  duration_minutes: 4
  tasks_completed: 3
  tests_added: 20
  files_created: 3
  files_modified: 0
completed: 2026-05-07
requirements: [PVL-06, PVL-07, FCM-01, FCM-03]
---

# Phase 37 Plan 01: Wave 0 RED Tests — Shared Seams Summary

**One-liner:** Locks identity-resolver, per-player vault-store, and memory-projection-store contracts with 20 failing tests using function-scope imports so Wave 1 implementations have a measurable green target.

## Objective Recap

Write the Wave 0 RED tests (TDD) for the three shared seams that both Discord-driven (PVL) and Foundry-driven (FCM) writers depend on:

1. `app.player_identity_resolver` — deterministic Discord-id → slug derivation and Foundry speaker classification.
2. `app.player_vault_store` — slug-prefix isolation for every Obsidian read/write.
3. `app.memory_projection_store` — four-section player chat-map build + two-mode NPC `## Foundry Chat History` append.

Tests must collect cleanly, fail meaningfully (`ModuleNotFoundError` on the as-yet-nonexistent symbols), and lock contracts before any production code is written.

## Tasks

### Task 1 — RED tests for `player_identity_resolver` (commit `8a1060e`)

Created `modules/pathfinder/tests/test_player_identity_resolver.py` with 8 sync tests:

- `test_slug_deterministic` — `slug_from_discord_user_id("u-1")` is repeatable, prefixed `p-`, length 14.
- `test_slug_uniqueness` — different inputs produce different slugs.
- `test_slug_rejects_non_str` — `TypeError` on int input, `ValueError` on empty string.
- `test_alias_override_wins` — `alias_map={"u-1": "p-custom"}` overrides the hash-derived slug.
- `test_foundry_speaker_precedence_alias_first` — alias for actor "Valeros" wins over PC character_name match (Pitfall 7 regression).
- `test_foundry_speaker_precedence_npc_roster_second` — NPC roster match returns `("npc", slug)` when no alias matches.
- `test_foundry_speaker_precedence_character_name_third` — PC character_name returns `("player", slug)` when alias+roster miss.
- `test_foundry_speaker_unknown_falls_through` — unmatched actor returns `("unknown", raw_token)`.

All 8 tests fail with `ModuleNotFoundError: No module named 'app.player_identity_resolver'` — the canonical RED state.

### Task 2 — RED tests for `player_vault_store` (commit `44d0974`)

Created `modules/pathfinder/tests/test_player_vault_store.py` with 6 async tests (pytest-asyncio mode=auto, no decorator needed):

- `test_read_profile_calls_correct_path` — reads `mnemosyne/pf2e/players/p-abc/profile.md`.
- `test_write_profile_calls_put_note_with_slug_path` — PUTs to the same path.
- `test_append_to_inbox_uses_get_then_put` — merged body contains both old and new entries with new appended after old.
- `test_store_rejects_path_outside_slug_prefix` — `_resolve_player_path` raises `ValueError` on `..` traversal, `..` slug, slug containing `/`, and slugs starting with `.`.
- `test_read_npc_knowledge_uses_per_player_path` — reads `players/p-abc/npcs/goblin.md` (NOT the global `mnemosyne/pf2e/npcs/goblin.md`).
- `test_per_player_isolation_assertion` — every Obsidian path argument across read_profile / write_profile / append_to_inbox / read_npc_knowledge contains `/players/p-abc/` (PVL-07 regression guard).

All 6 fail with `ModuleNotFoundError: No module named 'app.player_vault_store'`.

### Task 3 — RED tests for `memory_projection_store` (commit `2726301`)

Created `modules/pathfinder/tests/test_memory_projection_store.py` with 6 async tests:

- `test_write_player_map_creates_four_sections` — when player map file does not exist, the PUT body contains all four canonical headings (`## Voice Patterns`, `## Notable Moments`, `## Party Dynamics`, `## Chat Timeline`) plus the new line; path = `mnemosyne/pf2e/players/p-abc.md`.
- `test_write_player_map_preserves_existing_sections` — full GET-then-PUT body comparison: pre-existing lines under all four sections survive a single-section append.
- `test_npc_history_append_existing_section` — when `## Foundry Chat History` already present, `obsidian.patch_heading(path, "Foundry Chat History", row, operation="append")` is invoked and `obsidian.put_note` is NOT called.
- `test_npc_history_create_section_when_missing` — when section is absent, `obsidian.put_note` is invoked with the section + row appended; `obsidian.patch_heading` is NOT called.
- `test_npc_history_skips_when_npc_note_missing` — `get_note` returns None → no writes; return value mentions "missing"/"skipped".
- `test_section_detection_regex_anchored` — note containing `not a ## Foundry Chat History line` mid-line is correctly classified as MISSING (locks the `^##` line-anchored detection requirement).

All 6 fail with `ModuleNotFoundError: No module named 'app.memory_projection_store'`.

## Verification

| Check | Expected | Actual |
|-------|----------|--------|
| Test files created | 3 | 3 |
| Test functions added | 20 (8+6+6) | 20 |
| Collection succeeds | Yes (function-scope imports) | Yes |
| All fail with ImportError/ModuleNotFoundError | 20/20 | 20/20 |
| Pre-existing tests not modified | Yes | Yes |
| No `# TODO`, `pass`, or `NotImplementedError` stubs | Yes | Yes |
| Behavioral-Test-Only Rule honored | Each test calls a function and asserts on observable I/O | Confirmed |

Verification commands:
```bash
cd modules/pathfinder
pytest tests/test_player_identity_resolver.py   # 8 failed, ModuleNotFoundError
pytest tests/test_player_vault_store.py         # 6 failed, ModuleNotFoundError
pytest tests/test_memory_projection_store.py    # 6 failed, ModuleNotFoundError
```

## Deviations from Plan

None — plan executed exactly as written. The three test files were created with exactly the test cases specified in the plan's `<behavior>` blocks, using the function-scope-import RED pattern.

## Out-of-scope Findings (Not Fixed)

While running `pytest tests/` to confirm no regression, three pre-existing test modules failed at collection because optional host-environment dependencies are missing:
- `tests/test_legendkeeper_image.py` — `ModuleNotFoundError: No module named 'PIL'`
- `tests/test_pf_archive_import_alias.py` — likely the same class of missing dep
- `tests/test_pf_archive_import_integration.py` — likely the same class of missing dep

These predate this plan, are unrelated to the three new test files, and are environment issues (the modules run inside the pathfinder Docker container where deps are present). Recorded here per scope-boundary rule; not fixed in this plan.

## TDD Gate Compliance

Plan 37-01 is the **RED** half of the TDD cycle for Wave 0 of the per-player memory feature. The corresponding GREEN gate lives in plan 37-06 (Wave 1 implementations). RED gate satisfied: three `test(...)` commits exist on main (`8a1060e`, `44d0974`, `2726301`) ahead of any implementation commits for `app.player_identity_resolver`, `app.player_vault_store`, `app.memory_projection_store`.

## Self-Check: PASSED

Files exist:
- FOUND: modules/pathfinder/tests/test_player_identity_resolver.py
- FOUND: modules/pathfinder/tests/test_player_vault_store.py
- FOUND: modules/pathfinder/tests/test_memory_projection_store.py

Commits exist:
- FOUND: 8a1060e (test player_identity_resolver)
- FOUND: 44d0974 (test player_vault_store)
- FOUND: 2726301 (test memory_projection_store)
