---
phase: 37-pf2e-per-player-memory
plan: "10"
subsystem: pathfinder/per-player-memory
tags: [wave-5, green, player-memory, pvl, canonize, routes]
type: auto
wave: 5
requires:
  - 37-02 (RED test test_post_canonize_records_with_provenance)
  - 37-06 (player_vault_store helpers + slug-prefix isolation)
  - 37-07 (orchestrator + onboard/style/state surface)
  - 37-08 (capture verbs note/ask/npc/todo — establishes /player/ask `text` field used as the question source for canonize provenance)
provides:
  - "POST /player/canonize — records yellow→green or yellow→red outcome with question_id provenance to canonization.md"
  - "player_vault_store.append_canonization(slug, entry, *, obsidian) helper"
  - "Orchestrator canonize verb branch with closed-enum outcome validation (yellow|green|red)"
affects:
  - "Plan 37-11 (Discord :pf player command surface) — canonize route is now wireable end-to-end"
  - "Future operator-driven yellow→green/red flow has provenance back to the originating /player/ask question_id"
tech-stack:
  added: []
  patterns:
    - "GET-then-PUT canonization.md append (mirrors inbox/questions/todo append pattern, NOT PATCH heading per project_obsidian_patch_constraint memory)"
    - "Closed-enum validation at TWO seams: route via PlayerCanonizeRequest field_validator (422), orchestrator via VALID_OUTCOMES guard (ValueError) — defense in depth"
    - "Provenance line shape: `- [{outcome}] {iso_timestamp} — question:{question_id} — {rule_text}` — embeds all four load-bearing fields so substring asserts hit verbatim"
    - "v1: NO timeout-based auto-resolution (Open Question 4 / CONTEXT lock) — every canonization is operator-driven"
key-files:
  created: []
  modified:
    - modules/pathfinder/app/player_vault_store.py
    - modules/pathfinder/app/player_interaction_orchestrator.py
    - modules/pathfinder/app/routes/player.py
    - modules/pathfinder/app/main.py
decisions:
  - "Provenance shape uses `question:{question_id}` rather than an Obsidian wikilink — the question_id arrives from the Discord interface as an opaque uuid string (per 37-08 SUMMARY: /player/ask stores the question via `text` field with no separate id), so a wikilink target file does not yet exist. Substring `question:<id>` is grep-ready and forward-compatible with a v2 wikilink upgrade once question records get their own files."
  - "Outcome enum admits `yellow` in addition to `green`/`red` even though the verb's intent is yellow→green/red transitions. This lets the operator log a yellow re-affirmation (rule still genuinely ambiguous, no flip) which is observable behaviour we want recorded with provenance — keeps the canonization log a complete history rather than only flip events."
  - "Route handler validates `rule_text` via the existing `_validate_free_text` sanitiser (control-char strip + 2000-char cap) — same shape as note/ask/npc/todo. `question_id` gets a tighter dedicated validator (100-char cap, control-char ban, non-empty) since uuids are short and a freeform paragraph here would be a misuse."
  - "Orchestrator's existing canonize branch (shipped pre-emptively in plan 37-07/08) uses `store_adapter.write_canonization(question_id=, outcome=, rule_text=)` — the route bypasses the orchestrator and calls `player_vault_store.append_canonization` directly because the orchestrator's adapter shape was a placeholder and the route layer already owns the same onboarding-gate / 503-wrap pattern as note/ask. Orchestrator branch retained + tightened with VALID_OUTCOMES guard so the orchestrator-driven path (used by tests, not yet by the route) stays correct."
metrics:
  duration: "~12m"
  completed: "2026-05-07"
requirements: [PVL-04]
---

# Phase 37 Plan 10: Canonize Verb (PVL-04) Summary

**One-liner:** Wired POST /player/canonize end-to-end so yellow rule outcomes get canonized to green or red and appended to canonization.md with a provenance bullet that embeds the originating question_id.

## What Shipped

### `app.player_vault_store` (new helper)

- `async def append_canonization(slug, entry, *, obsidian) -> str` — GET-then-PUT into `mnemosyne/pf2e/players/{slug}/canonization.md`. Renders one bullet line per call:
  ```
  - [{outcome}] {iso_timestamp_utc} — question:{question_id} — {rule_text}
  ```
  Returns the resolved vault path so the route layer can include it in the JSON response without reconstructing the prefix. `_resolve_player_path` enforces PVL-07 isolation as it does for every other store helper.

### `app.player_interaction_orchestrator` (canonize branch tightened)

- New `VALID_OUTCOMES = frozenset({"yellow", "green", "red"})`.
- The pre-existing `case "canonize":` branch now raises `ValueError` on (a) outcome not in `VALID_OUTCOMES` and (b) empty/whitespace `question_id`. No vault I/O is issued before the validation runs.

### `app.routes.player` (new POST handler)

- `POST /player/canonize` with `PlayerCanonizeRequest{user_id, outcome, question_id, rule_text}`:
  - `outcome` field-validator → 422 if not in `{yellow, green, red}`.
  - `question_id` field-validator → 422 on empty / over-100-char / control-char.
  - `rule_text` sanitised by `_validate_free_text` (strip control chars, 2000-char cap, 422 on empty/over-cap).
  - Onboarding-gated via `_onboarding_gate_or_409` (mirrors note/ask/npc/todo).
  - 503 on missing obsidian client / write failure.
  - 200 response: `{ok, slug, path, outcome, question_id}`.

### `app.main`

- `REGISTRATION_PAYLOAD["routes"]` extended with `player/canonize` so sentinel-core's module proxy routes to it.

## Verification

- `pytest tests/test_player_routes.py tests/test_player_orchestrator.py -k "canoniz"` — 1/1 GREEN (`test_post_canonize_records_with_provenance`).
- `pytest tests/test_player_routes.py tests/test_player_orchestrator.py` — 21/21 GREEN. The two previously-RED tests from plan 37-02 (`test_post_recall_returns_only_requesting_slug_paths` shipped in 37-09; `test_post_canonize_records_with_provenance` ships here) are now both GREEN. **All seven PVL requirements have at least one passing behavioral test.**
- `pytest tests/test_player_*.py` — 44/44 GREEN (player routes, orchestrator, vault store, recall engine, identity resolver — full per-player surface).

## Plan-02 Tests Now GREEN

- `test_post_canonize_records_with_provenance` — verifies the put_note targets `mnemosyne/pf2e/players/{slug}/canonization.md` AND the body contains both the `green` outcome marker and the `q-uuid-1` question_id substring (provenance link).

## Plan-02 Tests Still RED (owned by later waves)

None — the plan-02 RED test surface is now fully GREEN.

## Deviations from Plan

### Auto-fixed Issues

None. The plan called out the orchestrator's `canonize` adapter as `store_adapter.append_canonization`, but the orchestrator code shipped in plans 37-07/08 already had a `case "canonize":` branch calling `store_adapter.write_canonization(question_id=, outcome=, rule_text=)`. Following the Test-Rewrite Ban / Spec-Conflict Guardrail — the existing orchestrator branch is observable behaviour exercised by `test_player_orchestrator.py`'s adapter mock (`store_adapter.write_canonization = AsyncMock()` at line 50) and breaking it would regress the orchestrator surface tests.

The route layer therefore calls `player_vault_store.append_canonization` directly (matching plan-text), and the orchestrator's `write_canonization` adapter remains the orchestrator-side seam (matching the orchestrator test contract). Both seams co-exist; both are validated; no test was rewritten or weakened.

### Plan-text vs implementation alignment

- Plan called for "store_adapter.append_canonization" as the orchestrator dispatch; existing test contract used `write_canonization`. Honoured the test contract (orchestrator) and the plan helper name (vault store) — they live at different seams so both names ship. Documented above under Decisions.
- Plan called for "v1: NO timeout-based auto-resolution" — implementation has zero scheduling code, zero timer, zero polling. The route only writes when explicitly invoked. Verified by reading the handler — no `asyncio.sleep`, no background task, no scheduler import.

## Stub Tracking

No stubs introduced. The route writes the requested canonization line on every successful invocation. No placeholder text, no "coming soon", no hardcoded empty values.

## Threat Flags

None. The /player/canonize route writes to a per-player namespace already covered by the existing PVL-07 threat model (slug-prefix isolation in `player_vault_store._resolve_player_path`). No new network endpoint, no new auth surface, no new file-access pattern, no new schema at a trust boundary — the route reuses the same onboarding-gate, the same `X-Sentinel-Key` middleware, and the same store-layer isolation as the four capture verbs shipped in 37-08.

## TDD Gate Compliance

Plan 37-10 is the **GREEN half** for `test_post_canonize_records_with_provenance` whose RED gate landed in plan 37-02 (commit 88623aa, the same RED batch that covered note/ask/npc/todo/recall). GREEN gate satisfied here:

- `feat(37-10): implement /player/canonize with question_id provenance (PVL-04)` — ecc2e3c

No REFACTOR commit needed — the new code is small, the orchestrator branch already existed, and the helper mirrors the established `_append_via_get_then_put` pattern.

## Self-Check: PASSED

Files modified:
- modules/pathfinder/app/player_vault_store.py — FOUND
- modules/pathfinder/app/player_interaction_orchestrator.py — FOUND
- modules/pathfinder/app/routes/player.py — FOUND
- modules/pathfinder/app/main.py — FOUND
- .planning/phases/37-pf2e-per-player-memory/37-10-SUMMARY.md — FOUND (this file)

Commits:
- ecc2e3c (Task 1 — append_canonization helper + canonize orchestrator branch tightening + POST /player/canonize route + REGISTRATION_PAYLOAD entry) — FOUND in `git log`

Targeted verification (`pytest tests/test_player_routes.py tests/test_player_orchestrator.py -k "canoniz"`) — 1/1 PASSED. Full plan-02 surface — 21/21 PASSED.
