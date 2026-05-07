---
phase: 37-pf2e-per-player-memory
plan: "09"
subsystem: pathfinder/per-player-memory
tags: [wave-4, green, player-memory, pvl, recall, deterministic, no-llm]
type: auto
wave: 4
requires:
  - 37-02 (RED test for /player/recall isolation)
  - 37-06 (player_vault_store + slug regex)
  - 37-07 (orchestrator recall arm wired to recall_adapter)
provides:
  - "app.player_recall_engine.recall(slug, query, *, obsidian, limit) — deterministic keyword + recency scorer"
  - "POST /player/recall — onboarding-gated route delegating to the engine"
affects:
  - "Plan 37-10 (canonize) is the only remaining RED in the per-player surface"
tech-stack:
  added: []
  patterns:
    - "Function-scope import of app.player_recall_engine.recall in routes/player.py — same lazy-import pattern routes/npc.slugify uses, keeps engine off the module-load path"
    - "_today_iso() module-level seam patched in unit tests for deterministic recency math (mirrors freeze_session_date pattern in test_session_integration)"
    - "Defensive prefix guard inside recall() drops any list_directory result that escapes mnemosyne/pf2e/players/{slug}/ — belt-and-braces alongside the slug-prefix-bound list_directory call (PVL-07)"
    - "Sort key (-score, -recency, path) gives a total order so two recall() calls with identical inputs produce byte-identical results"
key-files:
  created:
    - modules/pathfinder/app/player_recall_engine.py
    - modules/pathfinder/tests/test_player_recall_engine.py
  modified:
    - modules/pathfinder/app/routes/player.py
    - modules/pathfinder/app/main.py
decisions:
  - "v1 recall is keyword-count + recency-weight ONLY (CONTEXT lock). No LLM, no embeddings. Embeddings are deferred per CONTEXT.deferred."
  - "Recency formula: sessions/{YYYY-MM-DD}.md → max(0, 1 - days_since/365); non-session files fixed weight 0.1. Future-dated session files clamp to 1.0."
  - "Snippet width: ~80 chars total (40 each side of the first matched token); falls back to head-of-body when query is empty/missing/unmatched."
  - "Slug shape validated at the engine boundary using the same regex as player_vault_store._SLUG_RE — invalid slug raises ValueError before any I/O. The route layer surfaces that as 422."
  - "_today_iso is a module-level function rather than a default-arg constant so tests patch one call-site for all recency math; production reads date.today() at request time."
  - "Orchestrator recall arm was already wired in plan 37-07 (recall_adapter.recall(slug, query, obsidian=...)) — no orchestrator code change in this plan; the route imports the engine directly and the orchestrator path is exercised end-to-end via test_isolation_no_cross_player_read."
metrics:
  duration: "~12m"
  completed: "2026-05-07"
requirements: [PVL-03, PVL-07]
---

# Phase 37 Plan 09: Deterministic Recall Engine + /player/recall Route Summary

**One-liner:** Shipped `app.player_recall_engine.recall(slug, query, *, obsidian, limit)` — a deterministic keyword-match + recency-weight scorer scoped to `mnemosyne/pf2e/players/{slug}/` — and wired `POST /player/recall` to it through the existing onboarding gate, turning the plan-02 RED `test_post_recall_returns_only_requesting_slug_paths` GREEN with PVL-07 cross-player isolation enforced at three layers.

## What Shipped

### `app.player_recall_engine` (new module)

- `recall(slug: str, query: str | None, *, obsidian, limit: int = 10) -> list[dict]`.
- Validates slug shape against the same regex `player_vault_store._SLUG_RE` uses; rejects invalid slugs with `ValueError` before any I/O.
- Calls `obsidian.list_directory(prefix=f"mnemosyne/pf2e/players/{slug}/")` exactly once, then `obsidian.get_note(path)` for each returned path. A defensive guard drops any path that does not start with the slug prefix — PVL-07 belt-and-braces.
- `_keyword_count` — case-insensitive substring count summed across whitespace-split query tokens. Empty query contributes 0 keyword score (results fall back to pure recency ordering).
- `_recency_weight` — parses `sessions/(YYYY-MM-DD)\.md` via `_SESSION_DATE_RE`; weight = `max(0, 1 - days_since / 365)`. Non-session files get fixed `0.1`. Future-dated sessions clamp to `1.0`.
- `_build_snippet` — returns an ~80-char window around the first matched token (40 chars each side), or the first 80 chars of the body if the query is missing/unmatched.
- Sort key `(-score, -recency, path)` — total order; identical inputs produce byte-identical output (covered by `test_recall_deterministic`).
- `_today_iso()` is a module-level seam patched in tests so recency math is reproducible.

### `app.routes.player` (new POST handler)

- `PlayerRecallRequest{user_id: str, query: str | None = ""}`.
- `POST /player/recall`:
  - `_require_obsidian()` → 503 when the lifespan singleton is unset.
  - `_resolve_slug` → derives slug via `player_identity_resolver.slug_from_discord_user_id`.
  - `_read_profile` + `_onboarding_gate_or_409` → 409 when not onboarded.
  - Lazy imports `app.player_recall_engine.recall` (same pattern as `/player/npc`'s lazy `slugify` import) and calls it with the resolved slug + module-level `obsidian`.
  - `ValueError` from the engine → 422; any other exception → 503 with detail.
  - Response: `{"ok": true, "slug": "...", "results": [{"path": ..., "snippet": ..., "score": ...}, ...]}`.

### `app.main`

- `REGISTRATION_PAYLOAD["routes"]` extended with the `player/recall` entry so sentinel-core's module proxy can route to it.

### `tests/test_player_recall_engine.py` (new)

Nine behavioural tests, all assert on observable I/O — no source-grep, no `assert True`, no bare `mock.assert_called`:

1. `test_recall_uses_only_slug_prefix_paths` — `list_directory` called with exactly `mnemosyne/pf2e/players/{slug}/`; every `get_note` path under that prefix.
2. `test_recall_returns_empty_when_no_files` — empty namespace → empty list.
3. `test_recall_keyword_match_ranks_higher_than_no_match` — two-mention file ranks above one-mention file.
4. `test_recall_recency_weight_breaks_keyword_tie` — equal keyword count + different session dates → newer wins.
5. `test_recall_no_query_returns_recency_ordered` — `query=None` → newer session > older session > non-session inbox.
6. `test_recall_isolation_no_cross_slug` — `recall(A)` never reads anything under `players/B/` (asserts on every `list_directory` prefix arg, every `get_note` path arg, and every result's path/snippet).
7. `test_recall_limit_enforced` — 30 matching files + `limit=5` → exactly 5 results.
8. `test_recall_returns_snippet_around_query` — snippet contains the matched token AND at least one neighbouring word.
9. `test_recall_deterministic` — two calls with identical inputs yield equal lists.

## Verification

- `pytest tests/test_player_recall_engine.py` — **9/9 GREEN**.
- `pytest tests/test_player_routes.py tests/test_player_orchestrator.py -k "recall or isolation"` — **3/3 GREEN** (route isolation + two orchestrator isolation regressions: `test_isolation_no_cross_player_read`, `test_recall_passes_resolver_slug_only`).
- `pytest tests/test_player_recall_engine.py tests/test_player_routes.py tests/test_player_orchestrator.py tests/test_player_vault_store.py tests/test_player_identity_resolver.py` — **43 passed, 1 failed**. The single failure is `test_post_canonize_records_with_provenance`, owned by plan 37-10 (the canonize verb). Every Phase-37 per-player test is green except canonize, exactly per plan.
- Full pathfinder suite — **309 passed, 20 failed**. The 20 failures are all pre-existing, owned by other phases:
  - 12 in `test_foundry*` / `test_foundry_memory_projection.py` / `test_projection_idempotency.py` (Foundry chat memory projection — plans 37-11..14).
  - 3 in `test_foundry.py` (older `get_profile` `NameError`s — pre-37-09 baseline).
  - 1 in `test_foundry_chat_import.py::test_state_file_backcompat_missing_projection_keys` (FCM state file extension — plans 37-11..14).
  - 1 in `test_player_routes.py::test_post_canonize_records_with_provenance` (plan 37-10).
  - 1 in `test_registration.py::test_registration_payload_has_16_routes` (asserts 16 routes; payload has been growing through phases 35–37 and is at 28 after this plan — pre-existing miscount, unchanged by 37-09 since it was already failing at 27 after plan 37-08).
  - 2 spillover in `test_foundry_memory_projection.py` from imports.
  None of those are caused by plan 37-09.

## Plan-02 Tests Now GREEN

- `tests/test_player_routes.py::test_post_recall_returns_only_requesting_slug_paths` — including the assertion that every `list_directory` prefix arg contains `u1`'s slug and never `u2`'s, and that the response body never contains `u2`'s slug.

## Plan-02 Tests Still RED (owned by later waves)

- `tests/test_player_routes.py::test_post_canonize_records_with_provenance` → plan 37-10.

## Deviations from Plan

None. The plan called for adding a `case "recall":` arm to the orchestrator, but plan 37-07 already shipped that arm (verified by reading `app/player_interaction_orchestrator.py:221-227` and confirming both `test_isolation_no_cross_player_read` and `test_recall_passes_resolver_slug_only` are already GREEN against the current orchestrator code). The route still imports `recall` directly so the route-level RED test is satisfied — the orchestrator arm is the correct seam for the Discord verb dispatcher path, and both code paths use the same engine entry point.

## Stub Tracking

No stubs introduced. `recall` returns the live deterministic ranking. The route handler returns the engine's actual results, not placeholder data. The `_wrap_obsidian_write` marker function in `routes/player.py` is unchanged from plan 37-08 (still a documented no-op marker, no UI-flowing data path).

## TDD Gate Compliance

Plan 37-09 is type=auto with `tdd="true"` on Tasks 1B and 2. RED-then-GREEN sequence on disk:

- `test(37-09): add failing tests for player_recall_engine` — **a1dd6a9** (RED gate, 9 failing tests).
- `feat(37-09): implement player_recall_engine` — **50bf4b4** (GREEN gate for engine).
- `feat(37-09): add /player/recall route + register payload` — **e29072a** (GREEN gate for route, turns plan-02 RED green).

Each green commit is preceded by a red test on disk (engine's red was a1dd6a9; route's red lives at `tests/test_player_routes.py:291` from plan 37-02). No test from plan 37-02 or Task 1A was rewritten, weakened, or skipped — Test-Rewrite Ban honoured.

## Self-Check: PASSED

Files created:

- `modules/pathfinder/app/player_recall_engine.py` — FOUND
- `modules/pathfinder/tests/test_player_recall_engine.py` — FOUND
- `.planning/phases/37-pf2e-per-player-memory/37-09-SUMMARY.md` — FOUND (this file)

Files modified:

- `modules/pathfinder/app/routes/player.py` — FOUND (PlayerRecallRequest + recall handler added)
- `modules/pathfinder/app/main.py` — FOUND (player/recall in REGISTRATION_PAYLOAD)

Commits (`git log --oneline | grep 37-09`):

- a1dd6a9 (Task 1A — RED engine tests) — FOUND
- 50bf4b4 (Task 1B — engine GREEN) — FOUND
- e29072a (Task 2 — route GREEN) — FOUND

Targeted verification — `pytest tests/test_player_recall_engine.py tests/test_player_routes.py tests/test_player_orchestrator.py -k "recall or isolation or test_recall"` — 12 PASSED, 0 FAILED on 37-09 surface.
