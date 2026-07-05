---
phase: 43-embeddings-through-sentinel
plan: 01
subsystem: infra
tags: [pydantic-settings, litellm, embeddings, lm-studio, config]

requires:
  - phase: 42-provider-independence
    provides: exo_* settings triplet pattern (D-03 precedent), LiteLLMProvider, ProviderRouter
provides:
  - "Settings.embedding_base_url / Settings.embedding_api_key on sentinel-core, fully independent of chat's ai_provider"
  - "Both composition.py embeddings call sites (Embeddings construction + probe_embedding_model_loaded) reading embedding_base_url"
  - "Regression-guard tests preventing the exo :52415 port from ever becoming the embeddings default again"
affects: [43-02-embeddings-route, 43-04, 43-05, semantic-recall]

tech-stack:
  added: []
  patterns:
    - "embedding_* settings triplet mirrors the exo_*/lmstudio_* triplet shape but is read ONLY by the embeddings client, never by build_provider_router()'s chat wiring"

key-files:
  created: []
  modified:
    - sentinel-core/app/config.py
    - sentinel-core/app/clients/embeddings.py
    - sentinel-core/app/composition.py
    - sentinel-core/tests/test_composition.py
    - sentinel-core/tests/test_embeddings.py

key-decisions:
  - "embedding_base_url defaults to http://host.docker.internal:1234/v1 (LM Studio nomic endpoint), distinct from lmstudio_base_url and exo_base_url (D-01/D-02/D-03/D-04)"
  - "DEFAULT_LMSTUDIO_BASE_URL fallback constant in clients/embeddings.py repointed from exo's :52415 to LM Studio's :1234 so a falsy base_url degrades to a real embeddings backend"
  - "Both composition.py embeddings call sites (construction + probe) independently repointed onto embedding_base_url/embedding_api_key — Pitfall 3 (second call site) closed with a dedicated spy-based test"
  - "No provider_map/ProviderRouter abstraction introduced for embeddings (D-05 honored) — Embeddings stays a single injected client"

patterns-established:
  - "New backend-selection settings triplets for non-chat subsystems should mirror the exo_*/lmstudio_* triplet shape and be read exclusively by their own subsystem's composition wiring, never shared with chat's provider_map"

requirements-completed: [EMB-02, EMB-04]

coverage:
  - id: D1
    description: "Settings.embedding_base_url/embedding_api_key added, defaulting to LM Studio's :1234/v1 nomic endpoint, independent of lmstudio_base_url/exo_base_url; embedding_api_key wired into load_secrets secret_map"
    requirement: "EMB-02"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_embeddings.py#test_default_lmstudio_base_url_is_docker_reachable"
        status: pass
    human_judgment: false
  - id: D2
    description: "composition.py's Embeddings(...) construction and probe_embedding_model_loaded(...) call both read settings.embedding_base_url/embedding_api_key instead of the chat backend's lmstudio_base_url/lmstudio_api_key"
    requirement: "EMB-04"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_composition.py#test_build_application_wires_embeddings_from_embedding_base_url"
        status: pass
    human_judgment: false
  - id: D3
    description: "The two tests that previously locked in the exo-port bug as intended behavior now assert and regression-guard the LM Studio default"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_embeddings.py#test_default_lmstudio_base_url_is_docker_reachable, test_embeddings_falls_back_to_default_base_url_when_falsy"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-05
status: complete
---

# Phase 43 Plan 01: Embedding Settings Triplet + Composition Rewire Summary

**Rewired sentinel-core's embeddings client off exo's dead :52415 port onto a dedicated `embedding_*` settings triplet defaulting to LM Studio's nomic endpoint on :1234, fixing both `composition.py` call sites that construct the client and probe readiness.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Added `Settings.embedding_base_url` (default `http://host.docker.internal:1234/v1`, LM Studio) and `Settings.embedding_api_key`, both fully independent of `lmstudio_base_url`/`exo_base_url` used by chat
- `embedding_api_key` wired into `load_secrets`'s `secret_map` for Docker-secrets parity with `exo_api_key`/`lmstudio_api_key`
- Repointed `DEFAULT_LMSTUDIO_BASE_URL` in `clients/embeddings.py` from exo's `:52415` to LM Studio's `:1234` so a falsy base_url degrades to a real embeddings-capable backend
- Repointed BOTH `composition.py` embeddings call sites — the `Embeddings(...)` construction and the independent `probe_embedding_model_loaded(...)` call (Pitfall 3) — onto `settings.embedding_base_url`/`settings.embedding_api_key`
- Corrected the two pre-existing tests that had locked in the exo-port bug as intended behavior; both now regression-guard the LM Studio default and explicitly assert the exo port is absent
- Added a new composition test proving both call sites read `embedding_base_url` via spies on `Embeddings` and `probe_embedding_model_loaded`

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the embedding_* settings triplet and repoint the client default constant off exo** - `840987f` (feat)
2. **Task 2: Repoint both composition.py embeddings call sites onto the embedding_* fields** - `93c1d6d` (feat)
3. **Task 3: Correct the two tests that assert the exo-port bug as intended behavior** - `206c969` (test)

**Plan metadata:** (pending — final docs commit follows this SUMMARY)

_Note: tasks 1-2 were marked `tdd="true"` in the plan, but this plan is a targeted config/wiring rewire against pre-existing tests (some of which encoded the bug being fixed), not new-feature TDD — each task was implemented and its own verification block run to green in a single commit rather than as separate RED/GREEN/REFACTOR commits. See Deviations._

## Files Created/Modified
- `sentinel-core/app/config.py` - added `embedding_base_url`/`embedding_api_key` fields + `secret_map` entry
- `sentinel-core/app/clients/embeddings.py` - `DEFAULT_LMSTUDIO_BASE_URL` repointed from exo `:52415` to LM Studio `:1234`
- `sentinel-core/app/composition.py` - `Embeddings(...)` construction and `probe_embedding_model_loaded(...)` call both repointed onto `embedding_base_url`/`embedding_api_key`
- `sentinel-core/tests/test_composition.py` - new test asserting both embeddings call sites read `embedding_base_url`
- `sentinel-core/tests/test_embeddings.py` - two exo-port-asserting tests corrected to guard the LM Studio default

## Decisions Made
- `embedding_base_url` default is `http://host.docker.internal:1234/v1` (LM Studio), never exo's `:52415` — exo does not implement `POST /v1/embeddings` (exo-explore/exo#1047)
- `embedding_model` field was reused as-is per plan instruction — no duplicate/rename
- No `provider_map`/`ProviderRouter` abstraction added for embeddings (D-05) — `Embeddings` remains a single injected client, consistent with the plan's explicit scope lock

## Deviations from Plan

### Auto-fixed Issues

None beyond the note below — no bugs, missing critical functionality, or blocking issues were discovered outside the plan's explicit scope.

**Process deviation (not a Rule 1-4 fix):** Tasks 1 and 2 carry `tdd="true"` in the plan frontmatter, but the plan's own `<action>` blocks describe combined settings/wiring changes alongside test updates in a single paragraph rather than a literal write-failing-test-first sequence (and Task 1's pre-existing `test_embeddings.py` assertions were already known-wrong until Task 3 corrected them — see Pitfall 2 in 43-RESEARCH.md). Each task's implementation + its own `<verify>` block were run to green and committed as a single `feat`/`test` commit rather than separate RED → GREEN → REFACTOR commits. All acceptance criteria and the plan's overall `<verification>` block (full `pytest` suite green, `grep -n "52415"` clean on the embeddings path) were satisfied.

---

**Total deviations:** 0 auto-fixed (process note only, no code/scope changes)
**Impact on plan:** None — plan executed exactly as specified; all verification and acceptance criteria met.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. Operators who override `LMSTUDIO_BASE_URL` for chat will need no changes; those who want a non-default embeddings backend can now set `EMBEDDING_BASE_URL` independently.

## Next Phase Readiness
- `embedding_base_url`/`embedding_api_key` and both composition.py call sites are now correctly wired for LM Studio — unblocks 43-02 (embeddings route) and 43-04/43-05 which depend on a working embeddings backend for semantic recall.
- Full `sentinel-core` test suite green (449 passed, 0 failed, 12 skipped) confirming no regression to chat provider wiring (`build_provider_router()` untouched).
- No blockers for subsequent plans in this phase.

---
*Phase: 43-embeddings-through-sentinel*
*Completed: 2026-07-05*
