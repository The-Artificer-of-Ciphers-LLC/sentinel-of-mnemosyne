---
phase: 42-first-class-exo-provider
plan: 05
subsystem: api
tags: [httpx, sentinel-client, pf2e, provider-completion, chat-handoff, config-cleanup]

# Dependency graph
requires:
  - phase: 42-first-class-exo-provider (plan 04)
    provides: "SentinelCoreClient.complete() singleton pattern + all 10 llm.py chat call sites migrated (SC-6, D-09)"
provides:
  - "The last two pf2e chat/completion call sites (foundry.py roll-narration, pf_npc_extract.py archive-import) reach the LLM exclusively through SentinelCoreClient.complete() — the acompletion_with_profile import is fully removed from modules/pathfinder/app/"
  - "pf2e's chat-only litellm config (litellm_model, litellm_model_chat/structured/fast, session_recap_model, foundry_narration_model) is removed from app/config.py; litellm_api_base + rules_embedding_model retained for Phase 43 embeddings"
  - "app/resolve_model.py no longer reads a per-task-kind or hardcoded chat-model default from settings — it falls back to a structurally-inert placeholder that is never forwarded to a real completion call"
  - "Phase-wide gate: acompletion_with_profile( count is 0 across modules/pathfinder/app/ — D-09's full pf2e chat handoff is complete"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single-caller signature simplification: when a migrated function has exactly one real caller (generate_foundry_narrative <- routes/foundry.py._handle_roll), drop the now-fully-unused model/api_base/profile parameters from the signature entirely rather than keeping vestigial dead-weight params — the 42-04 precedent of leaving them unchanged was scoped to llm.py's 10 functions, which have real callers spread across 4 route files (out of scope to touch every one)."
    - "Inert placeholder over silent-crash: when config that fed a network-facing discovery helper (app.resolve_model) is deleted but the discovery helper's callers cannot all be touched in this plan's scope, replace the removed default with a structurally-guaranteed-unused placeholder string (never forwarded to any real completion call — grep-verifiable) instead of letting the helper raise on empty discovery, which would regress the 4 untouched route callers (npc.py/session.py/rule.py/harvest.py) that still thread model/api_base/profile through llm.py's unchanged (42-04) function signatures."

key-files:
  created: []
  modified:
    - modules/pathfinder/app/foundry.py
    - modules/pathfinder/app/pf_npc_extract.py
    - modules/pathfinder/app/routes/foundry.py
    - modules/pathfinder/app/config.py
    - modules/pathfinder/app/resolve_model.py
    - modules/pathfinder/app/model_selector.py
    - modules/pathfinder/tests/test_foundry.py
    - modules/pathfinder/tests/test_pf_npc_extract.py
    - modules/pathfinder/tests/test_pf_archive_import_alias.py
    - modules/pathfinder/tests/test_pf_archive_import_integration.py
    - modules/pathfinder/tests/test_resolve_model.py

key-decisions:
  - "pf_npc_extract.py's extract_npc() drops the strict json_schema response_format entirely (SentinelCoreClient.complete()'s contract is {messages, client, stop, temperature} only, per 42-03/42-04 — there is no response_format passthrough on sentinel-core's /provider/complete route or the AIProvider protocol beneath it). Schema conformance now rests solely on the existing system prompt + _validate_payload() runtime checks, which the module's own pre-42-05 docstring already characterized as a defense-in-depth backstop behind LM Studio's strict mode — they are now the PRIMARY gate instead. Extending sentinel-core's chat contract to support response_format would be a genuine architectural change (touching routes/provider.py, clients/base.py, clients/litellm_provider.py, services/provider_router.py — none in this plan's files_modified) and was not what the plan's Task 1 action directed (it names only the {messages, client, stop, temperature} shape)."
  - "generate_foundry_narrative's model/api_base/profile parameters were dropped from its signature in the same commit as the migration (not deferred to Task 2), since routes/foundry.py._handle_roll is its ONLY caller in the codebase — verified by grep before making the change. This differs from 42-04's decision to leave llm.py's 10 signatures unchanged (those have callers spread across app/routes/npc.py, session.py, rule.py, harvest.py — touching every one was explicitly out of that plan's scope)."
  - "app/resolve_model.py's per-task-kind chat/structured/fast preference dict and its settings.litellm_model default fallback are removed (Task 2's explicit direction: 'delete that dead chat-resolution path too'), replaced with a single inert placeholder constant (_UNUSED_MODEL_PLACEHOLDER) used only when model discovery returns nothing loaded. This was necessary, not optional: a naive removal (raising ModelSelectorError on empty discovery with no default) would have broken 4+ currently-passing pf2e route tests (test_npc.py, test_session_integration.py, test_harvest.py, test_rule_query.py-adjacent flows) that rely on resolve()/resolve_model() gracefully returning SOME model id even when the test environment's litellm_api_base is unreachable — because model/api_base/profile are structurally unused by every already-migrated LLM call site, the placeholder is provably harmless."
  - "session_recap_model was removed from config.py with zero caller-side changes needed — grep confirmed it was never read anywhere in the codebase (a dead field pre-dating this plan)."

patterns-established:
  - "When deleting a config field, grep the WHOLE app tree (not just the plan's files_modified list) for every reader before deleting — resolve_model.py and routes/foundry.py both consumed fields this plan's frontmatter didn't name as files_modified, and leaving them unfixed would have broken the module at request time (foundry.py) or crashed 4 route handlers whenever LM Studio/exo discovery came back empty (resolve_model.py)."

requirements-completed: [SC-5, SC-6]

coverage:
  - id: D1
    description: "foundry.py's generate_foundry_narrative and pf_npc_extract.py's extract_npc migrated from acompletion_with_profile to core_client.complete() — no model/api_base/response_format forwarded to core; existing narrative/JSON-extraction logic preserved"
    requirement: "SC-6"
    verification:
      - kind: unit
        ref: "modules/pathfinder/tests/test_foundry.py#test_generate_foundry_narrative_consumes_core_client_content"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_foundry.py#test_generate_foundry_narrative_core_raise_degrades_to_empty_string"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_foundry.py#test_llm_fallback"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_pf_npc_extract.py#test_format_a_extraction_returns_expected_fields"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_pf_npc_extract.py#test_format_b_extraction_preserves_default_level"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_pf_npc_extract.py#test_core_client_raise_propagates_unswallowed"
        status: pass
      - kind: other
        ref: "grep -rvn '^\\s*#' modules/pathfinder/app/ | grep -c 'acompletion_with_profile(' == 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "pf2e's chat-only litellm config (litellm_model, litellm_model_chat/structured/fast, session_recap_model, foundry_narration_model) removed from app/config.py; litellm_api_base + rules_embedding_model retained; resolve_model.py no longer depends on the removed fields; full pf2e + sentinel-core suites green including the LM Studio construction pin (D-02) and embeddings graceful-503 path (SC-5)"
    requirement: "SC-5"
    verification:
      - kind: other
        ref: "grep -c 'litellm_model\\b' modules/pathfinder/app/config.py == 0"
        status: pass
      - kind: other
        ref: "grep -c 'litellm_api_base' modules/pathfinder/app/config.py >= 1 AND grep -c 'rules_embedding_model' modules/pathfinder/app/config.py >= 1"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_resolve_model.py#test_resolve_model_falls_back_to_placeholder_when_discovery_empty"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_main.py#test_degrades_to_none_when_embedding_build_raises"
        status: pass
      - kind: integration
        ref: "sentinel-core/tests/test_composition.py (LM Studio construction-args pin, D-02)"
        status: pass
      - kind: other
        ref: "cd modules/pathfinder && pytest -q -> 398 passed"
        status: pass
      - kind: other
        ref: "cd sentinel-core && pytest -q -> 447 passed, 12 skipped"
        status: pass
    human_judgment: false

# Metrics
duration: ~35min
completed: 2026-07-05
status: complete
---

# Phase 42 Plan 05: Finish pf2e Chat Handoff + Config Cleanup + Phase Regression Gate Summary

**foundry.py and pf_npc_extract.py — the last two pf2e chat call sites — now reach the LLM exclusively through `SentinelCoreClient.complete()`; pf2e's chat-only litellm config is deleted from `app/config.py` while the embeddings path stays untouched; both full test suites (398 + 447 tests) pass, closing out Phase 42's D-09 chat handoff.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-07-05T18:20:00Z
- **Completed:** 2026-07-05T18:55:00Z
- **Tasks:** 2 completed
- **Files modified:** 11 (0 created, 11 modified)

## Accomplishments
- `app/foundry.py`'s `generate_foundry_narrative` (roll-narration) and `app/pf_npc_extract.py`'s `extract_npc` (archive-import) both migrated to `SentinelCoreClient.complete()`, mirroring the 42-04 `_core_client` singleton convention — `acompletion_with_profile` is now fully removed from `modules/pathfinder/app/` (phase-wide grep gate: 0 matches)
- `generate_foundry_narrative`'s `model`/`api_base`/`profile` parameters dropped entirely (its one and only caller, `routes/foundry.py._handle_roll`, updated in lockstep) rather than kept as unused dead weight — this was safe because grep confirmed no other caller exists anywhere in the codebase
- `pf_npc_extract.py`'s `extract_npc` no longer forwards a strict `json_schema` `response_format` (core's `/provider/complete` passthrough has no such parameter); the pre-existing system prompt + `_validate_payload()` become the primary schema-conformance gate. The dead `_resolve_structured_model()` helper — which hardcoded a hardcoded `qwen3.6-35b-a3b` chat-model default and read `LMSTUDIO_BASE_URL`/`MODEL_PREFERRED` env vars directly, bypassing `app.config` entirely — is removed
- `app/config.py`'s chat-only fields (`litellm_model`, `litellm_model_chat`, `litellm_model_structured`, `litellm_model_fast`, `session_recap_model`, `foundry_narration_model`) are gone; `litellm_api_base` and `rules_embedding_model` are retained and documented as Phase 43 embeddings scope
- `app/resolve_model.py` no longer reads a per-task-kind operator override or a hardcoded chat-model default from settings — it falls back to a clearly-labelled, structurally-inert placeholder (`_UNUSED_MODEL_PLACEHOLDER`) only when model discovery returns nothing loaded, which is provably safe since no `core_client.complete()` call anywhere forwards `model=`
- Phase-wide regression gate: full pf2e suite (398 passed) and full sentinel-core suite (447 passed, 12 skipped) both green — including sentinel-core's LM Studio construction-args pin (D-02, `test_composition.py`) and pf2e's rules-index embeddings graceful-503 path (SC-5, `test_main.py::test_degrades_to_none_when_embedding_build_raises`)
- Blast-radius fix: `test_pf_archive_import_alias.py` and `test_pf_archive_import_integration.py` (not in this plan's files_modified list) both patched `app.pf_npc_extract.acompletion_with_profile` directly and would have failed with `AttributeError` the moment the import was removed — updated their mocks and litellm-shaped fake response builders to the new `{content, model}` core-client contract

## Task Commits

1. **Task 1: Migrate foundry.py + pf_npc_extract.py chat call sites to core_client.complete() (SC-6, D-09)** - `dcc278a` (feat)
2. **Task 2: Remove pf2e chat-only litellm config + phase-wide regression gate (SC-5, SC-6, D-02)** - `67a7bda` (feat)

**Plan metadata:** (this commit) - `docs(42-05): complete pf2e chat handoff finish-line plan`

## Files Created/Modified
- `modules/pathfinder/app/foundry.py` - `generate_foundry_narrative` migrated to `_core_client.complete()`; `model`/`api_base`/`profile` params dropped (single caller); module-level `SentinelCoreClient` singleton added; `acompletion_with_profile` import removed
- `modules/pathfinder/app/pf_npc_extract.py` - `extract_npc` migrated to `_core_client.complete()`; strict `json_schema` `response_format` dropped; `_resolve_structured_model()` (hardcoded chat model/api_base resolver) removed; `NPC_EXTRACTION_SCHEMA` retained as a local validation reference
- `modules/pathfinder/app/routes/foundry.py` - `_handle_roll` no longer reads `settings.foundry_narration_model`/`settings.litellm_model` or calls `get_profile()`; simplified call to `generate_foundry_narrative`
- `modules/pathfinder/app/config.py` - removed `litellm_model`, `litellm_model_chat`, `litellm_model_structured`, `litellm_model_fast`, `session_recap_model`, `foundry_narration_model`; retained + re-documented `litellm_api_base` and `rules_embedding_model`
- `modules/pathfinder/app/resolve_model.py` - `resolve_model()` no longer reads per-task-kind preferences or a hardcoded default from settings; added `_UNUSED_MODEL_PLACEHOLDER` fallback + updated module/function docstrings explaining why this file still exists post-D-09
- `modules/pathfinder/app/model_selector.py` - docstring updated to reflect that `preferences`/`default` are no longer settings-driven
- `modules/pathfinder/tests/test_foundry.py` - `test_llm_fallback` re-pointed at `app.foundry._core_client.complete`; added 2 new direct unit tests for `generate_foundry_narrative`'s core-client handoff (content consumption + graceful-degrade-on-raise)
- `modules/pathfinder/tests/test_pf_npc_extract.py` - all mocks re-pointed at `app.pf_npc_extract._core_client.complete`; `response_format` assertions removed; added a `complete()`-raises-propagates-unswallowed test
- `modules/pathfinder/tests/test_pf_archive_import_alias.py` - 4 mocks re-pointed at `app.pf_npc_extract._core_client.complete`; fake LLM response reshaped to `{content, model}`
- `modules/pathfinder/tests/test_pf_archive_import_integration.py` - 11 mocks re-pointed at `app.pf_npc_extract._core_client.complete`; `_make_llm_response` helper reshaped to `{content, model}`
- `modules/pathfinder/tests/test_resolve_model.py` - empty-discovery fallback test updated to assert the new placeholder value instead of the removed `settings.litellm_model` default

## Decisions Made
- Dropped `response_format` (strict `json_schema`) enforcement from `pf_npc_extract.extract_npc` entirely rather than extending sentinel-core's `/provider/complete` contract to support it — the latter would touch `routes/provider.py`, `clients/base.py`, `clients/litellm_provider.py`, and `services/provider_router.py` (none in this plan's scope), and the plan's Task 1 action explicitly named only the `{messages, client, stop, temperature}` invocation shape. `_validate_payload()`'s existing enum/range/required-field checks (previously documented as "defensive, since strict mode should already catch them") are now the sole conformance gate.
- Simplified `generate_foundry_narrative`'s signature (dropped `model`/`api_base`/`profile`) in the same commit as its migration, rather than leaving them as unused dead parameters per the 42-04 precedent — justified because grep confirmed exactly one caller exists (`routes/foundry.py._handle_roll`), which this plan already had to touch to remove the now-deleted `foundry_narration_model`/`litellm_model` config reads. This differs from `llm.py`'s 10 functions, whose callers are spread across 4 route files 42-04 explicitly left untouched.
- `app/resolve_model.py`'s `resolve_model()` now falls back to a structurally-inert placeholder string (`openai/unused-core-resolves-model`) instead of raising `ModelSelectorError` when discovery returns nothing loaded — a bare removal of the settings-driven default would have broken 4+ passing pf2e route tests whose environment has no reachable LM Studio/exo backend (their `resolve()`/`resolve_model()` calls previously succeeded only because of the now-removed hardcoded `litellm_model` fallback). The placeholder is provably harmless: no `core_client.complete()` call anywhere in the codebase forwards a `model=` kwarg.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `routes/foundry.py._handle_roll` directly read `settings.foundry_narration_model`/`settings.litellm_model` (not in this plan's `files_modified`)**
- **Found during:** Task 1, while migrating `generate_foundry_narrative` (verified via grep for all callers before editing the function's signature)
- **Issue:** This route is `generate_foundry_narrative`'s only caller and computed `model`/`api_base`/`profile` from two settings fields (`foundry_narration_model`, `litellm_model`) that Task 2 was about to delete, plus a `get_profile()` LM Studio lookup whose result the migrated function no longer consumes.
- **Fix:** Removed the settings reads, the `get_profile()` call, and the now-unused `sentinel_shared.model_profiles.get_profile` import; simplified the call to `generate_foundry_narrative` to match its new signature.
- **Files modified:** `modules/pathfinder/app/routes/foundry.py`
- **Verification:** `pytest tests/test_foundry.py` green; full pf2e suite green.
- **Committed in:** `dcc278a` (Task 1 commit)

**2. [Rule 3 - Blocking] `app/resolve_model.py` read the 4 config fields Task 2 removed, and its settings-driven default fallback masked a network dependency that would otherwise crash 4+ route handlers**
- **Found during:** Task 2, per the plan's own read_first direction to grep model_selector.py/resolve_model.py for chat-field references before deleting config
- **Issue:** `resolve_model()` built a `preferences` dict from `settings.litellm_model_chat/structured/fast` and passed `default=settings.litellm_model` to `select_model()`. Removing those fields outright (no replacement) would make `select_model()` raise `ModelSelectorError` whenever `get_loaded_models()` returns an empty list — which it silently does in every test environment where `litellm_api_base` (`http://localhost:1234/v1`) has no reachable backend. This would have broken `routes/npc.py` (`/create`, `/update`, `/token`, `/say`), `routes/session.py`, and `routes/harvest.py`'s `resolve()`/`resolve_model()`/`resolve_model_profile()` calls, none of which are in this plan's `files_modified`.
- **Fix:** Replaced the settings-driven preferences/default with a single inert placeholder constant (`_UNUSED_MODEL_PLACEHOLDER = "openai/unused-core-resolves-model"`), used only when discovery is empty. This value is never forwarded to a real completion call — every migrated LLM call site (llm.py's 10 functions, foundry.py, pf_npc_extract.py) ignores its `model`/`api_base`/`profile` parameters entirely post-D-09 migration, confirmed by grep (`core_client.complete(` invocations never pass `model=`).
- **Files modified:** `modules/pathfinder/app/resolve_model.py`, `modules/pathfinder/app/model_selector.py` (docstring only), `modules/pathfinder/tests/test_resolve_model.py`
- **Verification:** Full pf2e suite green (398 passed) with no route-file changes needed to `npc.py`/`session.py`/`rule.py`/`harvest.py`.
- **Committed in:** `67a7bda` (Task 2 commit)

**3. [Rule 3 - Blocking] `test_pf_archive_import_alias.py` and `test_pf_archive_import_integration.py` (not in this plan's `files_modified`) mocked `acompletion_with_profile` directly**
- **Found during:** Task 1, discovered by running the full pf2e suite before committing (per the plan's phase-wide regression posture)
- **Issue:** Both test files patched `app.pf_npc_extract.acompletion_with_profile` (4 + 11 call sites respectively) and built litellm-shaped fake responses (`{"choices": [{"message": {...}}]}`). Once the import was removed, every one of these `patch(...)` calls raised `AttributeError` at test setup — 15 failing tests.
- **Fix:** Re-pointed all patch targets to `app.pf_npc_extract._core_client.complete` and reshaped the fake-response builders (`_make_llm_response` in the integration file, an inline builder in the alias file) to the `{content, model}` core-client contract.
- **Files modified:** `modules/pathfinder/tests/test_pf_archive_import_alias.py`, `modules/pathfinder/tests/test_pf_archive_import_integration.py`
- **Verification:** Full pf2e suite green (398 passed, 0 failures) after the fix.
- **Committed in:** `dcc278a` (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (all Rule 3 — blocking issues that would have broken the module at request time, crashed 4+ untouched route handlers, or left 15 tests failing with `AttributeError`)
**Impact on plan:** All three fixes were necessary to keep the plan's own stated verification criteria true (phase-wide `acompletion_with_profile(` count of 0; full pf2e + sentinel-core suites green). No scope creep beyond what the config/call-site removals directly forced — `routes/npc.py`, `routes/session.py`, `routes/rule.py`, `routes/harvest.py`, and `rule_query.py` were all evaluated and correctly left untouched (their `resolve()`/`resolve_model()` call shape is unchanged; only the values it returns changed source).

## Issues Encountered
None beyond the three deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 42 (First-Class exo Provider) is complete: sentinel-core's provider registry supports exo natively (42-02), a narrow `POST /provider/complete` gateway exists with a raise-on-error client method (42-03), and ALL ~13 pf2e chat/completion call sites across `llm.py` (42-04), `foundry.py`, and `pf_npc_extract.py` (this plan) now route through it — `acompletion_with_profile` is fully removed from `modules/pathfinder/app/`.
- Embeddings (`embed_texts`, `litellm.aembedding`, `litellm_api_base`, `rules_embedding_model`) are explicitly out of this phase's scope and remain on litellm directly, degrading gracefully to 503 when the configured backend lacks `/v1/embeddings` — this is Phase 43's starting point.
- `app/resolve_model.py`/`app/model_selector.py` are now documented as vestigial (their return value is unused by any real completion call) but were not removed entirely — a future phase could delete them along with the `model`/`api_base`/`profile` parameters on `llm.py`'s 10 functions and their 4 route-file callers, if that full cleanup is ever prioritized. Not required for Phase 42's SC-6/D-09 correctness bar, which this plan satisfies.
- No blockers.

---
*Phase: 42-first-class-exo-provider*
*Completed: 2026-07-05*

## Self-Check: PASSED

All 11 created/modified files found on disk; both task commit hashes (dcc278a, 67a7bda) found in git log.
