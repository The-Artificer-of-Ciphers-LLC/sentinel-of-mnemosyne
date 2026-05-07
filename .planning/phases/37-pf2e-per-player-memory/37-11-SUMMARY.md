---
phase: 37-pf2e-per-player-memory
plan: 11
subsystem: pathfinder
tags: [pathfinder, foundry, memory, projection, idempotency, tdd-green]
requires:
  - 37-03 (RED tests)
  - 37-06 (player_identity_resolver)
  - 37-08 (npc_matcher)
  - 37-09 (memory_projection_store)
provides:
  - app.foundry_memory_projection.project_foundry_chat_memory
  - app.foundry_memory_projection._load_projection_state (re-exported by plan 12)
  - app.foundry_memory_projection._save_projection_state
  - app.foundry_memory_projection._projection_key
affects:
  - .foundry_chat_import_state.json schema (in-place extension)
tech-stack:
  added: []
  patterns:
    - per-target dedupe key discriminator (target:player_map vs target:npc_history)
    - GET-then-PUT batched writes (one put_note per slug per import)
    - sync-or-async resolver/matcher tolerance (_maybe_await)
key-files:
  created:
    - modules/pathfinder/app/foundry_memory_projection.py
  modified: []
decisions:
  - "Dedupe key composes _message_key(record) with |target:{target} suffix for per-target idempotency."
  - "Player-map rows are batched per slug and flushed once; default section is Chat Timeline."
  - "options dict is reserved for future per-record section overrides; not yet wired."
  - "_maybe_await wrapper accepts both sync (test fixtures) and async (production) resolver/matcher."
  - "State save preserves legacy imported_keys via read-then-merge, never overwriting the foundry_chat_import importer's data."
metrics:
  duration_minutes: 4
  completed: 2026-05-07
requirements: [FCM-01, FCM-02, FCM-03, FCM-04, FCM-05]
---

# Phase 37 Plan 11: Foundry Chat Memory Projection Summary

Implements `app.foundry_memory_projection.project_foundry_chat_memory`, the second deep module of Phase 37, turning all 14 plan-37-03 RED tests GREEN.

## What Shipped

`modules/pathfinder/app/foundry_memory_projection.py` with the public API:

```python
async def project_foundry_chat_memory(
    *,
    records: list[dict],
    dry_run: bool,
    obsidian_client,
    dedupe_store_path: Path,
    identity_resolver: Callable[[str], tuple[Literal["player","npc","unknown"], str]],
    npc_matcher: Callable[[str], str | None],
    options: dict | None = None,
) -> dict
```

Returns the contracted metric shape:
`{player_updates, npc_updates, player_deduped, npc_deduped, unmatched_speakers, dry_run}`.

## How It Maps to Requirements

| Req    | Behavior                                                                         | Test                                                              |
| ------ | -------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| FCM-01 | Classification precedence: alias_map → npc_roster → unknown                      | `test_classify_speaker_precedence_*` (3 tests)                    |
| FCM-02 | Player-map renders all four canonical sections via write_player_map_section      | `test_project_player_map_creates_four_sections`                   |
| FCM-03 | NPC history append (existing section) or create (missing section)                | `test_npc_history_append_existing_section`, `..._create_section_when_missing`, `..._row_format_includes_timestamp_source_hash` |
| FCM-04 | Idempotent on rerun; per-target dedupe; foundry _id preferred, fallback recipe   | `test_projection_idempotent_on_rerun`, `test_state_file_persists_player_and_npc_keys`, `test_dedupe_key_uses_foundry_id_when_present`, `test_dedupe_key_target_discriminator` |
| FCM-05 | Dry-run writes nothing but emits identical metric shape                          | `test_dry_run_no_writes_same_metric_shape`                        |

Plus Pitfall 1 (schema-drift prevention) verified by `test_profile_md_is_never_written_by_projector` and `test_unknown_speaker_does_not_create_unknown_npc_note`.

## Key Design Choices

**Per-target dedupe key.** The dedupe key is `_message_key(record)|target:{player_map|npc_history}`. This means a single Foundry record routed to two destinations (e.g. an alias-mapped player whose name also appears in `npc_roster`) dedupes independently per target. The `test_dedupe_key_target_discriminator` test asserts the player and NPC key sets are disjoint.

**State file backward compatibility.** `_load_projection_state` accepts state files that contain only the legacy `imported_keys` array (foundry_chat_import.py's format). `_save_projection_state` preserves `imported_keys` on every write via read-then-merge so the importer's data is never trampled.

**Player-map batching.** Each player slug accumulates timeline rows in a per-slug list during the loop; one consolidated `write_player_map_section` call per slug fires at the end. This produces the single put_note per slug that the FCM-02 test asserts.

**Sync-or-async tolerance.** Tests pass plain sync callables for `identity_resolver` and `npc_matcher`. Production wiring (plan 12) may pass async coroutines. The `_maybe_await` helper handles both transparently.

**Profile.md is never touched.** The projector only writes to `mnemosyne/pf2e/players/{slug}.md` (via `write_player_map_section`) and `mnemosyne/pf2e/npcs/{slug}.md` (via `append_npc_history_row`). `profile.md` is structurally unreachable from this module.

## Verification

```
modules/pathfinder $ pytest tests/test_foundry_memory_projection.py tests/test_projection_idempotency.py -x
14 passed
```

The single still-RED test in `test_foundry_chat_import.py::test_state_file_backcompat_missing_projection_keys` is the cross-module re-export test that plan 37-12 will turn GREEN by re-exporting `_load_projection_state` from `foundry_chat_import`. This is intentional per plan 11 verification spec.

All other `test_foundry_chat_import.py` tests still pass — schema extension is fully backward-compatible.

## Deviations from Plan

None — plan executed exactly as written. The `npc_matcher` defence-in-depth fallback (when resolver returns `("npc", "")`) is an additive safety net; the tests' resolvers always return a populated slug so the fallback path is unexercised in tests but harmless.

## Commits

| Task | Description                                        | Commit  |
| ---- | -------------------------------------------------- | ------- |
| 1    | Implement foundry_memory_projection module        | 92647d7 |

## Self-Check: PASSED

- modules/pathfinder/app/foundry_memory_projection.py — FOUND
- 92647d7 — FOUND in git log
- 14/14 plan-03 RED tests GREEN (10 + 4)
