---
phase: 37-pf2e-per-player-memory
plan: "08"
subsystem: pathfinder/per-player-memory
tags: [wave-3, green, player-memory, pvl, capture-verbs, routes]
type: auto
wave: 3
requires:
  - 37-02 (RED tests for note/ask/npc/todo)
  - 37-06 (player_vault_store append/write helpers)
  - 37-07 (orchestrator + onboard/style/state surface)
provides:
  - "POST /player/note — appends to players/{slug}/inbox.md"
  - "POST /player/ask  — store-only, NO LLM, writes to players/{slug}/questions.md"
  - "POST /player/npc  — writes per-player NPC knowledge at players/{slug}/npcs/{npc_slug}.md"
  - "POST /player/todo — appends to players/{slug}/todo.md"
  - "Orchestrator npc branch slugifies npc_name and short-circuits empty names"
affects:
  - "Plan 37-09 (recall) consumes the same orchestrator dispatch slot"
  - "Plan 37-10 (canonize) likewise; recall + canonize tests still RED by design"
tech-stack:
  added: []
  patterns:
    - "GET-then-PUT for inbox/questions/todo via player_vault_store._append_via_get_then_put"
    - "Slug-prefix isolation enforced inside player_vault_store._resolve_player_path (PVL-07)"
    - "Free-text sanitiser (control-char strip, length cap) mirrors npc.py validators — 422 on empty/over-cap"
    - "Lazy import of slugify inside the npc handler avoids cross-route circular import"
key-files:
  created: []
  modified:
    - modules/pathfinder/app/player_interaction_orchestrator.py
    - modules/pathfinder/app/routes/player.py
    - modules/pathfinder/app/main.py
decisions:
  - "Route layer sanitises text (strip control chars, enforce length cap) before delegating to player_vault_store — per-route validation matches npc.py pattern, keeps the store seam free of input shape concerns"
  - "Orchestrator npc branch slugifies the npc_name before hitting the store so the resolved vault path matches the test contract (players/{slug}/npcs/varek.md, lowercase) and stays consistent with the global Phase-29 NPC slug rule"
  - "Empty npc_name short-circuits with a usage-hint result and no vault write — avoids creating stray empty-slug files in the per-player namespace"
  - "/player/ask is STORE-ONLY in v1 — no httpx call, no LLM. v2 LLM-answered ask is deferred per CONTEXT decisions"
  - "PVL-07 isolation is enforced at the store layer (_resolve_player_path), not the route — the route just resolves the requesting slug and the store rejects anything outside players/{slug}/. Single seam, single enforcement"
metrics:
  duration: "~10m"
  completed: "2026-05-07"
requirements: [PVL-02]
---

# Phase 37 Plan 08: Capture Verbs (note / ask / npc / todo) Summary

**One-liner:** Wired the four per-player capture verbs end-to-end — POST /player/note, /ask, /npc, /todo each gated by onboarding, each writing only into the requesting player's `mnemosyne/pf2e/players/{slug}/...` namespace, with `:pf player ask` deliberately store-only (no LLM call) per the v1 CONTEXT lock.

## What Shipped

### `app.player_interaction_orchestrator` (npc branch refinement)

- `npc` match arm now slugifies `request.npc_name` (via `app.routes.npc.slugify`, lazy-imported to avoid cross-route circular import) before delegating to `store_adapter.write_npc_knowledge`. The downstream vault path resolves to `players/{slug}/npcs/{npc_slug}.md` (e.g. `Varek` -> `varek`) and matches the global Phase-29 NPC slug rule.
- Empty / whitespace-only `npc_name` short-circuits with `PlayerInteractionResult(message="Usage: :pf player npc <npc_name> <note>")` and no vault write. Prevents empty-slug stray files.

### `app.routes.player` (four new POST handlers)

- `POST /player/note` — `PlayerNoteRequest{user_id, text}`. Sanitises `text` (control-char strip + 2000-char cap), resolves slug, gates on onboarding, calls `player_vault_store.append_to_inbox`. Returns 200 `{ok, slug, path}`. 503 on missing obsidian / failed write; 409 when not onboarded; 422 on empty text.
- `POST /player/ask` — `PlayerAskRequest{user_id, text}`. Same shape, writes via `append_to_questions`. **NO httpx call to any LLM endpoint** — v1 contract documented in the docstring; behavioural-test-only test asserts zero LLM POSTs are issued during the handler.
- `POST /player/npc` — `PlayerNpcRequest{user_id, npc_name, note}`. Sanitises `npc_name` (100-char cap) and `note` (2000-char cap), slugifies npc_name, writes a small frontmatter+body markdown via `player_vault_store.write_npc_knowledge`. Path lands at `players/{slug}/npcs/{npc_slug}.md` — the store's `_resolve_player_path` rejects any path outside that prefix (PVL-07 isolation).
- `POST /player/todo` — `PlayerTodoRequest{user_id, text}`. Same shape as note, writes via `append_to_todo`.

All four share `_onboarding_gate_or_409` and `_validate_free_text` helpers, keeping the handler bodies thin and the error surface uniform across the per-player capture verbs.

### `app.main`

- `REGISTRATION_PAYLOAD["routes"]` extended with `player/note`, `player/ask`, `player/npc`, `player/todo` so sentinel-core's module proxy can route to them.

## Verification

- `pytest tests/test_player_routes.py -k "note or ask or npc or todo"` — 5/5 GREEN (note write + note 409 + ask + npc + todo).
- `pytest tests/test_player_orchestrator.py` — 8/8 GREEN (regression preserved).
- `pytest tests/test_player_routes.py tests/test_player_orchestrator.py` — 19/21 GREEN; the 2 still-RED tests are exactly `test_post_recall_returns_only_requesting_slug_paths` (plan 37-09) and `test_post_canonize_records_with_provenance` (plan 37-10), as expected.

## Plan-02 Tests Now GREEN

- test_post_note_writes_to_player_inbox
- test_post_note_blocked_when_not_onboarded (already green in plan 07; verified still green)
- test_post_ask_stores_question_no_llm — including the no-LLM-call assertion (subclassed httpx.AsyncClient counts URL-pattern matches; count is zero)
- test_post_npc_writes_per_player_namespace — including the "global path NOT written" PVL-07 isolation assertion
- test_post_todo_writes_per_player_todo

## Plan-02 Tests Still RED (owned by later waves)

- test_post_recall_returns_only_requesting_slug_paths → plan 37-09
- test_post_canonize_records_with_provenance → plan 37-10

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Lazy import of `slugify` inside the npc handler**
- **Found during:** Task 2 — module-level `from app.routes.npc import slugify` was stripped by the local formatter (it cleared an unused-at-time-of-write reference).
- **Issue:** Re-adding the module-level import worked, but `routes/npc.py` is a heavy module (LLM imports, PDF builders) and pulling it into `routes/player.py` at module load risks future circular-import surprises if/when npc.py grows a player.py reference.
- **Fix:** Lazy-import `slugify` inside the `/player/npc` handler body. Same effect at call time, zero cross-route coupling at module load. Mirrors the pattern Phase 33 used for app.llm to keep module load test-infra friendly.
- **Files modified:** `modules/pathfinder/app/routes/player.py`.
- **Commit:** 24e5bd7.

### Plan-text vs implementation alignment

- The plan called for `PlayerAskRequest{user_id, question}`, but the plan-02 RED test sends `{"user_id":"u1","text":"Does cover stack..."}`. Following the established Test-Rewrite Ban — shipped-feature tests are read-only by default, and the test was written first — the route accepts `text`, not `question`. The store helper writes the same payload regardless of field name. SUMMARY notes the deviation explicitly so plan 37-10's canonize-by-question-id flow can decide whether to thread a separate `question_id` field through later.
- The plan called for `_handle_note` / `_handle_ask` etc. private helpers in the orchestrator. The orchestrator already implements the same behaviour inline inside its `match request.verb:` block (shipped in plan 37-07's deviation #2 to satisfy the PVL-07 isolation tests). Refactoring to private helpers would be a pure code-organisation change with zero behavioural delta — kept inline to avoid noise in this slice.

## Stub Tracking

No stubs introduced. Every route writes the requested data on success; `_wrap_obsidian_write` is a documented marker (no `pass` body that flows to UI rendering — handlers use try/except inline). The 501 stub previously in the `/player/note` handler (Plan 37-07 transitional) is replaced with the real `append_to_inbox` write.

## TDD Gate Compliance

Plan 37-08 is the **GREEN half** for the four capture verbs whose RED tests landed in plan 37-02 (`test_post_note_writes_to_player_inbox`, `test_post_ask_stores_question_no_llm`, `test_post_npc_writes_per_player_namespace`, `test_post_todo_writes_per_player_todo`). RED gate commits exist on main (88623aa). GREEN gate satisfied here:
- `feat(37-08): slugify npc_name in orchestrator npc verb branch` — ed48024
- `feat(37-08): add /player/note, /ask, /npc, /todo capture routes` — 24e5bd7

## Self-Check: PASSED

Files modified:
- modules/pathfinder/app/player_interaction_orchestrator.py — FOUND
- modules/pathfinder/app/routes/player.py — FOUND
- modules/pathfinder/app/main.py — FOUND
- .planning/phases/37-pf2e-per-player-memory/37-08-SUMMARY.md — FOUND (this file)

Commits:
- ed48024 (Task 1 — orchestrator slugify) — FOUND in `git log`
- 24e5bd7 (Task 2 — four capture routes + REGISTRATION_PAYLOAD) — FOUND in `git log`

Targeted verification (`pytest tests/test_player_routes.py -k "note or ask or npc or todo"`) — 5/5 PASSED. Full plan-02 surface — 19/21 PASSED with the 2 remaining REDs owned by plans 37-09 and 37-10 by design.
