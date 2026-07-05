---
phase: 42-first-class-exo-provider
plan: 04
subsystem: api
tags: [httpx, sentinel-client, pf2e, provider-completion, chat-handoff]

# Dependency graph
requires:
  - phase: 42-first-class-exo-provider (plan 03)
    provides: "POST /provider/complete on sentinel-core + SentinelCoreClient.complete() raise-on-error client method"
provides:
  - "pf2e llm.py chat/completion call sites reach the LLM exclusively through SentinelCoreClient.complete() — no direct litellm chat calls remain in pf2e's largest chat surface"
  - "modules/pathfinder/Dockerfile now copies sentinel_client.py into the pf2e container (previously only sentinel_shared/ was copied — a latent gap this plan closed)"
affects: [42-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Short-lived httpx.AsyncClient per call site (foundry.py's notify_discord_bot convention), not a caller-owned injected client — since none of llm.py's ~10 chat functions had a client in scope, this keeps the migration confined to the invocation line instead of threading a new required parameter through every route/caller"
    - "Module-level SentinelCoreClient singleton built from settings.sentinel_core_url/sentinel_api_key — mirrors interfaces/discord/bot.py and interfaces/imessage/bridge.py's existing singleton convention"
    - "Flattened bare-module Dockerfile COPY for a shared/ file (sentinel_client.py -> /app/sentinel_client.py), matching the existing sentinel_shared/ flattening precedent so `from sentinel_client import SentinelCoreClient` resolves identically in Docker and local pytest (pythonpath = [\".\", \"../../shared\"])"

key-files:
  created:
    - modules/pathfinder/tests/test_llm_core_handoff.py
  modified:
    - modules/pathfinder/app/llm.py
    - modules/pathfinder/Dockerfile
    - modules/pathfinder/tests/test_npc.py
    - modules/pathfinder/tests/test_harvest.py
    - modules/pathfinder/tests/test_rules.py
    - modules/pathfinder/tests/test_rules_garble_regression.py
    - modules/pathfinder/tests/test_session_integration.py

key-decisions:
  - "Import path chosen as bare `from sentinel_client import SentinelCoreClient` (not `from shared.sentinel_client import ...`) to match pf2e's existing bare-import convention for everything under shared/ (e.g. `from sentinel_shared.llm_call import ...`), which is what pf2e's pyproject.toml pythonpath=[\".\", \"../../shared\"] and conftest.py sys.path insert actually support locally"
  - "Function signatures (model, api_base, profile params) were left unchanged on all 10 migrated call sites — only the invocation/content-extraction lines changed, per the plan's explicit scope. These params are now unused by the call itself (core resolves provider+model) but removing them would require touching every caller across app/routes/*.py, which is out of scope for this plan"
  - "max_tokens (generate_mj_description) and per-call timeout kwargs are dropped at all 10 sites — SentinelCoreClient.complete()'s contract is {messages, stop, temperature} only (per 42-03), so these knobs have no forwarding path until a future core-side contract extension"

patterns-established:
  - "Any future pf2e module wiring a shared/ top-level file into the Docker image should add a single targeted `COPY --from=shared <file> /app/<file>` line, mirroring the sentinel_shared/ and sentinel_client.py precedents, rather than introducing a package-qualified `shared.` import path that the current build/pytest wiring doesn't support"

requirements-completed: [SC-6]

coverage:
  - id: D1
    description: "generate_npc_reply, generate_ruling_from_passages, generate_ruling_fallback, generate_session_recap, and generate_mj_description migrated from acompletion_with_profile to core_client.complete() — no model/api_base forwarded, JSON-parse/salvage/citation-framing logic preserved"
    requirement: "SC-6"
    verification:
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_generate_npc_reply_consumes_core_client_content"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_generate_npc_reply_json_parse_failure_still_salvages"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_generate_npc_reply_core_raise_propagates_unswallowed"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_generate_ruling_from_passages_uses_core_client_and_preserves_citations"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_generate_ruling_fallback_uses_core_client_generated_marker"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_generate_session_recap_uses_core_client_and_parses_required_keys"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_generate_mj_description_uses_core_client_returns_plain_string"
        status: pass
    human_judgment: false
  - id: D2
    description: "extract_npc_fields, update_npc_fields, generate_harvest_fallback, classify_rule_topic, and generate_story_so_far migrated to core_client.complete(); acompletion_with_profile import removed from llm.py entirely; embeddings (embed_texts/litellm.aembedding) untouched"
    requirement: "SC-6"
    verification:
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_extract_npc_fields_uses_core_client_and_parses_field_dict"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_update_npc_fields_uses_core_client_and_parses_changed_fields"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_generate_harvest_fallback_uses_core_client_and_parses_shape"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_classify_rule_topic_uses_core_client_returns_known_slug"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_generate_story_so_far_uses_core_client_returns_plain_string"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_generate_story_so_far_core_raise_degrades_gracefully"
        status: pass
      - kind: other
        ref: "grep -vn '^\\s*#' modules/pathfinder/app/llm.py | grep -c 'acompletion_with_profile(' == 0"
        status: pass
      - kind: other
        ref: "grep -c 'litellm.aembedding' modules/pathfinder/app/llm.py unchanged (13, includes embed_texts docstring references)"
        status: pass
    human_judgment: false

# Metrics
duration: ~25min
completed: 2026-07-05
status: complete
---

# Phase 42 Plan 04: pf2e Chat Handoff (llm.py -> SentinelCoreClient) Summary

**All 10 chat/completion call sites in pf2e's `app/llm.py` (NPC dialogue, ruling composition, session notes, harvest fallback, topic classification) now reach the LLM exclusively through `SentinelCoreClient.complete()` — the `acompletion_with_profile` import is fully removed; embeddings stay on `litellm.aembedding` untouched.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-05T17:59:45Z
- **Completed:** 2026-07-05T18:23:33Z
- **Tasks:** 2 completed
- **Files modified:** 8 (1 created, 7 modified)

## Accomplishments
- `app/llm.py` gets a module-level `SentinelCoreClient` singleton built from `settings.sentinel_core_url`/`settings.sentinel_api_key` (no new URL literal), mirroring the existing singleton convention already used by `interfaces/discord/bot.py` and `interfaces/imessage/bridge.py`
- All 10 `acompletion_with_profile` chat call sites (`extract_npc_fields`, `generate_npc_reply`, `generate_mj_description`, `update_npc_fields`, `generate_harvest_fallback`, `classify_rule_topic`, `generate_ruling_from_passages`, `generate_session_recap`, `generate_story_so_far`, `generate_ruling_fallback`) migrated to `core_client.complete()` — no `model`/`api_base` forwarded, core resolves provider+model per D-09
- Each site's surrounding JSON-parse/salvage/citation-framing/error-handling logic preserved exactly; only the invocation and content-extraction lines changed
- `acompletion_with_profile` import removed from `llm.py` entirely; `litellm.aembedding` (embeddings, Phase 43 scope) untouched
- Fixed a genuine deployment gap in `modules/pathfinder/Dockerfile`: only `shared/sentinel_shared/` was ever copied into the pf2e container — `shared/sentinel_client.py` (the client this migration depends on) had no COPY path at all. Without this fix the code would import successfully in local pytest (pythonpath already includes `../../shared`) but fail at container startup with `ModuleNotFoundError`.
- New `tests/test_llm_core_handoff.py` (13 tests) patches `app.llm._core_client.complete` directly and proves: no model/api_base forwarded, existing salvage paths still fire on malformed content, `complete()`-raises propagates unswallowed where the function doesn't wrap it (`generate_npc_reply`), and degrades gracefully where it does (`generate_story_so_far`)
- Updated 6 pre-existing test files whose `litellm.acompletion`/`app.llm.litellm.acompletion` mocks were bypassed by the migration (`test_npc.py`, `test_harvest.py`, `test_rules.py`, `test_rules_garble_regression.py`, `test_session_integration.py`) — required to keep the plan's "full pf2e suite green" verification criterion true
- Full pf2e suite: **395 passed, 0 failures, 0 warnings** (was 389 before this plan; +6 net from the new structured-site tests)

## Task Commits

1. **Task 1: pf2e core-client wiring + migrate llm.py free-text chat call sites (SC-6, D-09)** - `de8717b` (feat)
2. **Task 2: Migrate llm.py structured (JSON-contract) chat call sites + drop the direct-litellm chat import (SC-6, D-09)** - `d2782b7` (feat)

**Plan metadata:** (this commit) - `docs(42-04): complete pf2e chat handoff plan`

## Files Created/Modified
- `modules/pathfinder/app/llm.py` - `SentinelCoreClient` wiring + module-level `_core_client` singleton; all 10 chat call sites migrated to `core_client.complete()`; `acompletion_with_profile` import removed; module docstring updated to describe the new architecture
- `modules/pathfinder/Dockerfile` - Added `COPY --from=shared sentinel_client.py /app/sentinel_client.py` (blocking-issue fix — see Deviations)
- `modules/pathfinder/tests/test_llm_core_handoff.py` - NEW: 13 tests covering all 10 migrated call sites, patching `app.llm._core_client.complete` directly
- `modules/pathfinder/tests/test_npc.py` - `test_npc_say_json_parse_salvage` updated to patch `app.llm._core_client.complete` instead of `app.llm.litellm.acompletion`
- `modules/pathfinder/tests/test_harvest.py` - 2 tests (`test_harvest_llm_missing_medicine_dc_filled_from_level`, `test_harvest_llm_truly_malformed_500`) updated to patch `app.llm._core_client.complete`
- `modules/pathfinder/tests/test_rules.py` - 3 `classify_rule_topic` tests updated to patch `app.llm._core_client.complete`; unused `SimpleNamespace` import removed
- `modules/pathfinder/tests/test_rules_garble_regression.py` - 3 ruling-salvage tests updated to patch `app.llm._core_client.complete`; unused `SimpleNamespace` import removed
- `modules/pathfinder/tests/test_session_integration.py` - 4 tests (`test_show_calls_llm_and_patches_story`, `test_end_writes_full_note`, `test_end_llm_failure_writes_skeleton`, `test_location_stub_created`) updated to patch `app.llm._core_client.complete`; `_make_llm_narrative_response`/`_make_llm_json_response` helpers changed to return `{content, model}` dicts instead of litellm-shaped `SimpleNamespace` objects

## Decisions Made
- Bare `from sentinel_client import SentinelCoreClient` import path chosen over `from shared.sentinel_client import ...` to match pf2e's established bare-import convention for the `shared/` directory's contents (mirrors `from sentinel_shared.llm_call import ...`) — this is what pf2e's `pyproject.toml` (`pythonpath = [".", "../../shared"]`) and `conftest.py`'s sys.path insertion actually support today; the discord/imessage interfaces' `from shared.sentinel_client import ...` convention doesn't apply to pf2e because those interfaces copy the *entire* `shared/` tree preserving its package structure, while pf2e has always flattened `shared/`'s contents into `/app/`
- Short-lived `httpx.AsyncClient()` opened per call site (foundry.py's `notify_discord_bot` convention), not a caller-owned client threaded through every function signature — none of the 10 migrated functions had a client in scope, and adding one as a new required parameter would ripple into every route file that calls them, which is out of scope for "only the invocation line changes"
- Function signatures (`model`, `api_base`, `profile` params) left unchanged on all 10 sites even though the values are now unused by the completion call itself — removing them is a separate, broader refactor (every caller in `app/routes/*.py` would need updating) not authorized by this plan's stated scope
- `max_tokens` (`generate_mj_description`) and the various per-site `timeout=` kwargs are dropped at all sites since `SentinelCoreClient.complete()`'s contract (per 42-03) is `{messages, stop, temperature}` only — no forwarding path exists yet for these knobs

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `modules/pathfinder/Dockerfile` never copied `sentinel_client.py` into the pf2e container**
- **Found during:** Task 1 (before writing any code — verified via reading the Dockerfile against the plan's import target)
- **Issue:** The Dockerfile's shared-package copy step (`COPY --from=shared sentinel_shared/ /app/sentinel_shared/`) only brings in the `sentinel_shared/` subdirectory. `shared/sentinel_client.py` — the exact file this plan's `SentinelCoreClient` import depends on — is a sibling top-level file in `shared/` with no copy path into the pf2e image at all. Without a fix, the migrated code would pass all local pytest runs (pf2e's `pyproject.toml` pythonpath already includes `../../shared`) but fail at container startup with `ModuleNotFoundError: No module named 'sentinel_client'`.
- **Fix:** Added `COPY --from=shared sentinel_client.py /app/sentinel_client.py`, following the exact flattening convention already established for `sentinel_shared/` one line above it.
- **Files modified:** `modules/pathfinder/Dockerfile`
- **Verification:** File presence confirmed (`ls shared/sentinel_client.py`); import path confirmed to match pf2e's existing pythonpath convention (local pytest suite green, 395 passed).
- **Committed in:** `de8717b` (Task 1 commit)

**2. [Rule 3 - Blocking] 6 pre-existing test files mocked `litellm.acompletion`/`app.llm.litellm.acompletion` for functions this plan migrated**
- **Found during:** Task 1 and Task 2 (discovered via grep across `modules/pathfinder/tests/` before editing any test, to scope the full blast radius up front)
- **Issue:** `test_npc.py`, `test_harvest.py`, `test_rules.py`, `test_rules_garble_regression.py`, and `test_session_integration.py` all patched the pre-migration LLM call path directly for `generate_npc_reply`, `generate_ruling_from_passages`, `generate_ruling_fallback`, `generate_session_recap`, `generate_harvest_fallback`, `classify_rule_topic`, and `generate_story_so_far`. Once each function migrated to `core_client.complete()`, these mocks would never fire — the tests would either attempt a real (failing) network call or silently pass on stale assertions, breaking the plan's own stated verification criterion ("Full pf2e suite green: `pytest -q`").
- **Fix:** Updated each affected test to patch `app.llm._core_client.complete` (returning a `{content, model}` dict) instead of the old litellm-level mock, split across the two task commits by which function each test exercises (Task-1-migrated functions' tests fixed in the Task 1 commit; Task-2-migrated functions' tests fixed in the Task 2 commit). Also updated `test_session_integration.py`'s two helper functions (`_make_llm_narrative_response`, `_make_llm_json_response`) to build result dicts instead of litellm-shaped `SimpleNamespace` objects, and removed two now-unused `SimpleNamespace` imports (`test_rules.py`, `test_rules_garble_regression.py`).
- **Files modified:** `modules/pathfinder/tests/test_npc.py`, `modules/pathfinder/tests/test_harvest.py`, `modules/pathfinder/tests/test_rules.py`, `modules/pathfinder/tests/test_rules_garble_regression.py`, `modules/pathfinder/tests/test_session_integration.py`
- **Verification:** Full pf2e suite green (395 passed, 0 failures, 0 warnings) after both commits.
- **Committed in:** `de8717b` (Task 1 — 5 test-file fixes for Task-1-scope functions), `d2782b7` (Task 2 — remaining fixes for Task-2-scope functions)

---

**Total deviations:** 2 auto-fixed (both Rule 3 — blocking issues that would have broken container startup or the plan's own verification gate)
**Impact on plan:** Both fixes were necessary for the migration to actually work end-to-end (Docker) and to keep the plan's stated success criteria true (full suite green). No scope creep — `app/foundry.py`'s own separate `acompletion_with_profile` call site (a different module, out of this plan's `files_modified` list) and `app/pf_npc_extract.py`'s `extract_npc` (a different function entirely, using `response_format=json_schema` — confirmed via `test_pf_npc_extract.py`) were both left untouched, correctly out of scope.

## Issues Encountered
None beyond the two deviations above.

## User Setup Required
None - no external service configuration required. The Dockerfile fix takes effect on the next `docker compose build pf2e-module` (or `./sentinel.sh --pf2e up --build`); no manual step needed.

## Next Phase Readiness
- pf2e's `llm.py` chat surface is now fully on the sentinel-core gateway; `app/foundry.py`'s Foundry-narration `acompletion_with_profile` call site remains the one pf2e chat call site NOT covered by this plan (out of scope — different module, not in `files_modified`) and is presumably 42-05's target given the phase's remaining wave.
- Full pf2e suite green: 395 passed, 0 skipped-with-concern, 0 warnings.
- No blockers.

---
*Phase: 42-first-class-exo-provider*
*Completed: 2026-07-05*

## Self-Check: PASSED

All 8 created/modified files found on disk; both task commit hashes (de8717b, d2782b7) found in git log.
