---
phase: 37-pf2e-per-player-memory
plan: "07"
subsystem: pathfinder/per-player-memory
tags: [wave-2, green, player-memory, pvl, orchestrator, routes]
type: auto
wave: 2
requires:
  - 37-02 (RED tests for orchestrator + routes)
  - 37-06 (Wave 1 modules: identity_resolver, vault_markdown, player_vault_store)
provides:
  - "app.player_interaction_orchestrator — handle_player_interaction, PlayerInteractionRequest/Result, VALID_STYLE_PRESETS"
  - "app.routes.player — POST /player/onboard, POST /player/style, GET /player/state (+ 503/409 surface for /player/note)"
  - "Lifespan wiring + REGISTRATION_PAYLOAD entries for the three new player routes"
affects:
  - "Plan 37-08 (capture verbs note/ask/npc/todo) extends the orchestrator match block and widens routes/player.py /note plus adds /ask/npc/todo"
  - "Plan 37-09 (recall) consumes the same orchestrator dispatch slot"
  - "Plan 37-10 (canonize) likewise"
tech-stack:
  added: []
  patterns:
    - "Open/closed orchestrator dispatch — new verbs extend the match block; no branch is removed across waves"
    - "Module-level singleton injection (Phase 32-04 STATE decision) — lifespan sets app.routes.player.obsidian, tests patch the same"
    - "GET-then-PUT for profile.md updates (project_obsidian_patch_constraint memory) — replaces PATCH replace-on-missing"
    - "Closed enum style preset at both orchestrator (ValueError) and Pydantic route boundary (422)"
key-files:
  created:
    - modules/pathfinder/app/player_interaction_orchestrator.py
    - modules/pathfinder/app/routes/player.py
    - .planning/phases/37-pf2e-per-player-memory/37-07-SUMMARY.md
  modified:
    - modules/pathfinder/app/main.py
    - modules/pathfinder/tests/conftest.py
decisions:
  - "Pydantic Literal narrows verbs to the union of waves 2/3/4 even though only start/style/state are dispatched here — keeps subsequent plans purely additive without bumping a request schema version"
  - "Validation of the style preset happens twice: at the Pydantic boundary (422) and inside the orchestrator (ValueError) — the orchestrator-side check is required by the plan-02 isolation/enum tests that bypass FastAPI"
  - "Pre-import app.main in conftest.py to make mock.patch('app.main.<symbol>') resolve at __enter__ time — long-standing local-pytest issue that affected test_session_integration and test_player_routes equally"
  - "Ship the /player/note 503+409 surface in this slice (plan 08 widens to actually write inbox.md). The verifier's -k 'onboard' filter incidentally selects test_post_note_blocked_when_not_onboarded; the gate logic is correct today, the inbox write lands in plan 08"
metrics:
  duration: "~25m"
  completed: "2026-05-07"
---

# Phase 37 Plan 07: First Wired Slice — Orchestrator + Onboard/Style/State Routes Summary

**One-liner:** Lit the per-player module's first end-to-end path — POST /player/onboard creates profile.md, POST /player/style list|set returns/persists the four-preset enum, GET /player/state reads the frontmatter, all gated by an onboarding check that short-circuits non-`start`/non-`style:list` verbs without invoking writes.

## What Shipped

### `app.player_interaction_orchestrator`

- `PlayerInteractionRequest` — Pydantic v2 BaseModel with a `Literal` verb tag spanning the full Phase 37 verb set. Plans 08–10 only need to extend the match block; the request schema does not change again.
- `PlayerInteractionResult` — `slug`, `verb`, `requires_onboarding`, optional `data`/`message`/`presets`.
- `VALID_STYLE_PRESETS = frozenset({"Tactician", "Lorekeeper", "Cheerleader", "Rules-Lawyer Lite"})`.
- `handle_player_interaction(...)` — derives slug via the injected identity adapter, runs `_check_onboarded` against profile.md, then dispatches via `match request.verb`. Pre-onboarding allows only `start` and `style:list`; everything else returns `requires_onboarding=True` without calling any write adapter.
- Future-verb seams (`note`/`ask`/`npc`/`todo`/`recall`/`canonize`) route the resolver-derived slug to their store/recall adapters today so the PVL-07 isolation and PVL-06 resolver-seam plan-02 tests can verify the invariant in this slice; full route-side behaviour ships in plans 08–10.

### `app.routes.player`

- `router = APIRouter(prefix="/player", tags=["player"])`, module-level `obsidian = None` singleton.
- `POST /player/onboard` — `PlayerOnboardRequest` (style_preset closed enum at Pydantic level, 422 on miss); always rewrites profile.md via `player_vault_store.write_profile`. 200 with `{slug, path}`. 503 if obsidian singleton missing.
- `POST /player/style` — `action: Literal["list", "set"]`. `list` returns the four sorted presets, no put_note. `set` requires `preset`, gates on onboarding (409 with hint), GET-then-PUT profile.md frontmatter via `vault_markdown.build_frontmatter_markdown`.
- `GET /player/state` — query param `user_id`; returns `{slug, onboarded, style_preset, character_name, preferred_name}`. 200 even when not onboarded.
- `POST /player/note` — 503-when-obsidian-None + 409-when-not-onboarded surface only; HTTPException(501) when gate passes (plan 08 replaces the body with the inbox.md GET-then-PUT). This intentional partial keeps the verifier's `-k "onboard"` selector clean while leaving the `writes_to_inbox` test RED for plan 08.

### `app.main`

- Imports `_player_module` and `player_router`; `app.include_router(player_router)`.
- Lifespan sets `_player_module.obsidian = obsidian_client` at startup, clears it at shutdown.
- `REGISTRATION_PAYLOAD["routes"]` lists `player/onboard`, `player/style`, `player/state` so sentinel-core's module proxy can route to them.

### `tests/conftest.py`

- `import app.main` after the env-var setdefaults so `mock.patch("app.main.<symbol>")` resolves at `__enter__` time. Without this, `pytest tests/test_player_routes.py` (and `tests/test_session_integration.py`) failed locally with `AttributeError: module 'app' has no attribute 'main'`. CI/Docker happened to import main earlier in the test order; local runs did not.

## Verification

- `pytest tests/test_player_orchestrator.py` — 8/8 GREEN (was 0/8 — full plan-02 orchestrator slice).
- `pytest tests/test_player_routes.py -k "onboard or style or state or obsidian_unavailable"` — 7/7 GREEN.
- Wider regression run (`test_player_*`, `test_session*`, `test_npc*`, `test_npcs`, `test_healthz`) — 104 passed, 6 failed. The 6 failures are exactly the plan-02 RED tests for `/player/note (write)`, `/player/ask`, `/player/npc`, `/player/todo`, `/player/recall`, `/player/canonize` — by design, owned by plans 37-08/09/10.

## Plan-02 Tests Now GREEN

Orchestrator (8 tests):
- test_first_interaction_triggers_onboarding
- test_start_verb_allowed_when_not_onboarded
- test_style_list_allowed_when_not_onboarded
- test_style_set_blocked_when_not_onboarded
- test_isolation_no_cross_player_read
- test_recall_passes_resolver_slug_only
- test_invalid_style_preset_raises
- test_orchestrator_uses_identity_resolver_seam

Routes (7 tests):
- test_post_onboard_creates_profile_md
- test_post_onboard_rejects_invalid_style_preset
- test_post_note_blocked_when_not_onboarded (gate-only — write test stays RED for plan 08)
- test_post_style_set_persists_to_profile
- test_post_style_list_returns_four_presets
- test_get_state_returns_onboarding_status
- test_obsidian_unavailable_returns_503

## Plan-02 Tests Still RED (owned by later waves)

- test_post_note_writes_to_player_inbox → plan 37-08
- test_post_ask_stores_question_no_llm → plan 37-08
- test_post_npc_writes_per_player_namespace → plan 37-08
- test_post_todo_writes_per_player_todo → plan 37-08
- test_post_recall_returns_only_requesting_slug_paths → plan 37-09
- test_post_canonize_records_with_provenance → plan 37-10

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Pre-import `app.main` in `tests/conftest.py`**
- **Found during:** Task 2 verification.
- **Issue:** `mock.patch("app.main.<symbol>")` resolves the dotted path at `__enter__` time via `getattr(app, "main")`. Locally, no test had imported `app.main` at collection time, so the attribute lookup raised `AttributeError: module 'app' has no attribute 'main'`. This affected `tests/test_session_integration.py` (pre-existing) and `tests/test_player_routes.py` equally.
- **Fix:** Set the env-var defaults that `app.config` requires, then `import app.main  # noqa: E402,F401` once at conftest load. No behavioural side-effects — `import app.main` constructs the FastAPI `app` but does not invoke the lifespan.
- **Files modified:** `modules/pathfinder/tests/conftest.py`.
- **Commit:** 7739b99.

**2. [Rule 2 — Critical functionality] Ship `/player/note` 503/409 gate surface in this slice**
- **Found during:** Task 2 verification — the verify command `-k "onboard or style or state or obsidian_unavailable"` selects both `test_post_note_blocked_when_not_onboarded` (matches "onboard") and `test_obsidian_unavailable_returns_503` (which posts to `/player/note`).
- **Issue:** Plan text scopes Wave 2 to `/onboard`, `/style`, `/state` only, but the verify selector requires the `/player/note` 503 + 409 surface to be GREEN. Without `/player/note` registered, both tests fail with 404.
- **Fix:** Register `POST /player/note` with the obsidian-None → 503 check + onboarding-gate → 409 check + 501 (NotImplemented) when the gate passes. Plan 37-08 will replace the 501 body with the actual `append_to_inbox` write — extension, not deletion. The `writes_to_inbox` RED test correctly remains RED.
- **Files modified:** `modules/pathfinder/app/routes/player.py`.
- **Commit:** 7739b99.

### Other notes

- The `match` block in the orchestrator pre-wires `note`/`ask`/`npc`/`todo`/`recall`/`canonize` to call their respective store/recall adapters with the resolver-derived slug. The plan-02 isolation and resolver-seam tests (`test_isolation_no_cross_player_read`, `test_recall_passes_resolver_slug_only`, `test_orchestrator_uses_identity_resolver_seam`) require this; the alternative was to skip three of the eight Wave 2 GREEN targets. Plans 08/09/10 will widen the bodies but not change the dispatch shape.

## Self-Check: PASSED

Files created:
- modules/pathfinder/app/player_interaction_orchestrator.py — FOUND
- modules/pathfinder/app/routes/player.py — FOUND
- .planning/phases/37-pf2e-per-player-memory/37-07-SUMMARY.md — FOUND (this file)

Files modified:
- modules/pathfinder/app/main.py — FOUND (player imports + REGISTRATION_PAYLOAD entries + lifespan singleton)
- modules/pathfinder/tests/conftest.py — FOUND (app.main pre-import)

Commits:
- 81c7501 (Task 1 — orchestrator) — FOUND in `git log`
- 7739b99 (Task 2 — routes + main + conftest) — FOUND in `git log`

Targeted verification (`pytest tests/test_player_orchestrator.py` + `tests/test_player_routes.py -k "onboard or style or state or obsidian_unavailable"`) — 15/15 PASSED.
