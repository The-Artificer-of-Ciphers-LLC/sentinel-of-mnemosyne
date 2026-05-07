---
phase: 37-pf2e-per-player-memory
plan: 02
subsystem: pathfinder
tags: [tdd, red, wave-0, player-routes, orchestrator, pvl]
requires:
  - "37-01 (shared-seam RED tests provide identity_resolver / vault_store / projection_store contracts)"
provides:
  - "RED tests for app.routes.player module (PVL-01..05, PVL-07 isolation slice)"
  - "RED tests for app.player_interaction_orchestrator (gate, style enum, isolation, resolver seam)"
affects:
  - "Wave 1 (plan 37-06) /player/* route implementation constrained by these contracts"
  - "Wave 1 orchestrator implementation constrained by these contracts"
tech_stack_added: []
patterns:
  - "Function-scope symbol imports (Phase 33-01 STATE.md decision; Phase 37-01 reuse)"
  - "ASGITransport + AsyncMock obsidian + module-singleton patching (Phase 32 NPC test pattern)"
  - "Per-call repr() inspection for cross-player slug-leak regression"
key_files_created:
  - "modules/pathfinder/tests/test_player_routes.py"
  - "modules/pathfinder/tests/test_player_orchestrator.py"
key_files_modified: []
decisions:
  - "Onboarding gate locked at test layer: every verb except `start` and `style list` must return requires_onboarding=True (or HTTP 409) when profile.md is absent."
  - "Style preset closed enum locked at test layer: exactly Tactician, Lorekeeper, Cheerleader, Rules-Lawyer Lite. Invalid preset → 422 (route) and ValueError listing all four (orchestrator)."
  - "Identity resolver is the SOLE seam for slug derivation — orchestrator passes resolver-derived slug downstream; raw user_id MUST NOT appear in any downstream call (test_orchestrator_uses_identity_resolver_seam, test_recall_passes_resolver_slug_only)."
  - "PVL-07 isolation regression asserts: u1's slug != u2's slug AND each slug appears only in its own recall_adapter.recall await — repr()-based per-call inspection, not just response-not-None."
  - "v1 ask is store-only: test_post_ask_stores_question_no_llm subclasses httpx.AsyncClient and asserts zero LLM-bound POSTs are issued during /player/ask."
  - "/player/canonize provenance contract: canonization.md body MUST contain BOTH the outcome marker AND the question_id substring."
metrics:
  duration_minutes: 5
  tasks_completed: 2
  tests_added: 21
  files_created: 2
  files_modified: 0
completed: 2026-05-07
requirements: [PVL-01, PVL-02, PVL-03, PVL-04, PVL-05, PVL-07]
---

# Phase 37 Plan 02: Wave 0 RED Tests — /player/* Routes + Orchestrator Summary

**One-liner:** Locks /player/* HTTP contracts and the player_interaction_orchestrator's onboarding gate, style-enum, PVL-07 isolation, and resolver-seam invariants with 21 failing tests using the established function-scope-import RED pattern.

## Objective Recap

Write the Wave 0 RED tests (TDD) for the two surface-level seams that complete the per-player-memory write/read path:

1. `app.routes.player` — FastAPI router with eight verbs (`onboard`, `note`, `ask`, `npc`, `todo`, `recall`, `style`, `canonize`) and one query (`state`).
2. `app.player_interaction_orchestrator` — verb-dispatch service that owns onboarding-gate logic, style-preset enum enforcement, and per-player isolation.

Tests must collect cleanly, fail meaningfully (`ModuleNotFoundError` / `AttributeError` on the as-yet-nonexistent symbols), and lock the contracts before any production code is written. Plan 37-06 (Wave 1) is the GREEN gate.

## Tasks

### Task 1 — RED tests for `/player/*` routes (commit `88623aa`)

Created `modules/pathfinder/tests/test_player_routes.py` with 13 async tests (asyncio_mode=auto, no decorator):

- `test_post_onboard_creates_profile_md` — PUT to `mnemosyne/pf2e/players/{slug}/profile.md` with frontmatter containing `onboarded: true`, `character_name: Aria`, `preferred_name: Ari`, `style_preset: Tactician`.
- `test_post_onboard_rejects_invalid_style_preset` — `style_preset="MadeUp"` → 422; no put_note awaited.
- `test_post_note_writes_to_player_inbox` — gated by `_onboarded_profile()` mock; asserts PUT to `players/{slug}/inbox.md` with the note text.
- `test_post_note_blocked_when_not_onboarded` — profile None → 409 with `:pf player start` hint; inbox.md NEVER written.
- `test_post_ask_stores_question_no_llm` — subclasses `httpx.AsyncClient` to count any POST containing `1234` / `/v1/` / `completions` and asserts the count is zero. Asserts PUT to `questions.md` with the question text.
- `test_post_npc_writes_per_player_namespace` — PUT to `players/{slug}/npcs/varek.md`; explicit assertion that the global `mnemosyne/pf2e/npcs/varek.md` is NOT written (PVL-07 isolation).
- `test_post_todo_writes_per_player_todo` — PUT to `players/{slug}/todo.md`.
- `test_post_recall_returns_only_requesting_slug_paths` — every `list_directory` prefix arg contains u1's slug AND not u2's slug; response body must not contain u2's slug.
- `test_post_style_set_persists_to_profile` — PUT to `players/{slug}/profile.md` with body containing `style_preset: Lorekeeper`.
- `test_post_style_list_returns_four_presets` — body contains all four canonical preset names; `put_note` not awaited.
- `test_post_canonize_records_with_provenance` — PUT to `canonization.md` with body containing both `green` and `q-uuid-1`.
- `test_get_state_returns_onboarding_status` — JSON body `{onboarded: true, slug, style_preset: "Tactician"}` parsed from profile frontmatter.
- `test_obsidian_unavailable_returns_503` — `app.routes.player.obsidian` patched to `None`; POST returns 503 with detail mentioning `obsidian` and `initialised`/`initialized`.

All 13 fail at the `patch("app.routes.player.obsidian", ...)` boundary because `app.routes.player` does not yet exist (`AttributeError: module 'app' has no attribute 'main'` cascade — the route module isn't imported by `app.main`, which fails the patch). Canonical RED.

### Task 2 — RED tests for `player_interaction_orchestrator` (commit `c82d1d8`)

Created `modules/pathfinder/tests/test_player_orchestrator.py` with 8 async tests:

- `test_first_interaction_triggers_onboarding` — `verb="note"` + profile None → `result.requires_onboarding is True`; `store.append_to_inbox` not awaited.
- `test_start_verb_allowed_when_not_onboarded` — `verb="start"` + profile None → `store.write_profile` awaited once; no rejection.
- `test_style_list_allowed_when_not_onboarded` — `verb="style", action="list"` + profile None → result surfaces all four preset names; `update_style_preset` not awaited.
- `test_style_set_blocked_when_not_onboarded` — `verb="style", action="set"` + profile None → `result.requires_onboarding is True`; `update_style_preset` not awaited.
- `test_isolation_no_cross_player_read` — runs recall for u1 then u2 with a side-effect-recording `recall_adapter.recall`; asserts `u1_slug != u2_slug`, u2's slug not in u1's call repr, u1's slug not in u2's call repr (PVL-07).
- `test_recall_passes_resolver_slug_only` — sentinel resolver returns `"p-resolver-sentinel-XYZ"`; assertion: that string IS in the recall call repr AND `"raw-discord-id-12345"` is NOT.
- `test_invalid_style_preset_raises` — `preset="MadeUp"` → `ValueError` whose message contains all four canonical preset names.
- `test_orchestrator_uses_identity_resolver_seam` — pinned resolver returns `"p-fixed"` regardless of input; downstream `store.append_to_inbox` call repr must contain `"p-fixed"` AND must not contain the raw user_id.

All 8 fail with `ModuleNotFoundError: No module named 'app.player_interaction_orchestrator'`. Canonical RED.

## Verification

| Check | Expected | Actual |
|-------|----------|--------|
| Test files created | 2 | 2 |
| Test functions added | 21 (13 + 8) | 21 |
| Collection succeeds | Yes (function-scope imports) | Yes (`13 tests collected`, `8 tests collected`) |
| All fail (RED) | 21/21 | 21/21 |
| Pre-existing tests not modified | Yes | Yes |
| No `# TODO`, `pass`, or `NotImplementedError` stubs | Yes | Yes |
| Behavioral-Test-Only Rule honored | Each test calls a function and asserts on observable I/O / return value / exception | Confirmed |

Verification commands:
```bash
cd modules/pathfinder
python3 -m pytest tests/test_player_routes.py        # 13 failed (route module absent)
python3 -m pytest tests/test_player_orchestrator.py  # 8 failed, ModuleNotFoundError
```

## Deviations from Plan

None — plan executed exactly as written. The two test files were created with exactly the 13 + 8 = 21 test cases specified in the plan's `<behavior>` blocks, using the function-scope-import RED pattern from Phase 37-01 / Phase 33-01.

One minor refinement (within plan scope): `test_post_ask_stores_question_no_llm` instruments LLM-call detection by subclassing `httpx.AsyncClient` and counting any POST whose URL contains `1234`, `/v1/`, or `completions`. The plan specified "no extra mock interaction beyond obsidian"; subclass-based counting is a strictly stronger and behavior-observable check than absence-of-mock-interaction.

## Out-of-scope Findings (Not Fixed)

None new this plan. Pre-existing optional-dependency collection failures noted in 37-01-SUMMARY.md remain unchanged.

## TDD Gate Compliance

Plan 37-02 is the **RED** half of the TDD cycle for Wave 0 of the /player/* surface and orchestrator. The corresponding GREEN gate lives in plan 37-06 (Wave 1 implementations). RED gate satisfied: two `test(...)` commits exist on main (`88623aa`, `c82d1d8`) ahead of any implementation commits for `app.routes.player` or `app.player_interaction_orchestrator`.

## Self-Check: PASSED

Files exist:
- FOUND: modules/pathfinder/tests/test_player_routes.py
- FOUND: modules/pathfinder/tests/test_player_orchestrator.py

Commits exist:
- FOUND: 88623aa (test 13 RED tests for /player/* routes)
- FOUND: c82d1d8 (test 8 RED tests for player_interaction_orchestrator)
