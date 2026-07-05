---
phase: 43-embeddings-through-sentinel
plan: 03
subsystem: api
tags: [httpx, fastapi, litellm, sentinel-core, pathfinder, embeddings]

# Dependency graph
requires:
  - phase: 43-01
    provides: sentinel-core pointed at a real backend for the functional embeddings path
  - phase: 43-02
    provides: POST /embeddings route on sentinel-core (EmbeddingsRequest/EmbeddingsResponse)
provides:
  - "SentinelCoreClient.embed(texts, client) -> {embeddings, model} mirroring complete()'s raise-on-error posture"
  - "embed_texts() delegates to core instead of calling litellm.aembedding directly"
affects: [43-04, 43-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Strangler-Fig internal swap: only the leaf vector-compute call moves; embed_texts()'s signature and both call sites stay byte-identical"
    - "SentinelCoreClient.embed() mirrors complete()'s raise-on-error posture (not send_message()'s swallow-to-string), preserving pf2e's 503-degrade contract"

key-files:
  created:
    - modules/pathfinder/tests/test_llm_core_handoff.py (extended, not created — embed_texts tests appended)
  modified:
    - shared/sentinel_client.py
    - modules/pathfinder/app/llm.py
    - shared/tests/test_sentinel_client.py
    - modules/pathfinder/tests/test_llm_core_handoff.py

key-decisions:
  - "embed() sends ONLY {texts} in the request body — no model/api_base/base_url forwarded (D-04); core owns backend selection"
  - "embed_texts()'s model/api_base params remain accepted but vestigial so both call sites (main.py _rule_embed_fn, rule_query.py deps.embed_texts) need zero changes (Pattern 3)"
  - "Removed the now-dead _RULING_TIMEOUT_S constant after its sole call site (the old litellm.aembedding kwargs) was deleted"

patterns-established:
  - "embed() is the embeddings mirror of Phase 42's complete() chat handoff — same client, same raise-on-error posture, same caller-owned httpx.AsyncClient convention"

requirements-completed: [EMB-01, EMB-03]

coverage:
  - id: D1
    description: "SentinelCoreClient.embed() POSTs {texts} to /embeddings with X-Sentinel-Key header, raises on non-2xx, returns {embeddings, model}"
    requirement: "EMB-01"
    verification:
      - kind: unit
        ref: "shared/tests/test_sentinel_client.py#test_embed_success"
        status: pass
      - kind: unit
        ref: "shared/tests/test_sentinel_client.py#test_embed_sends_only_texts_no_model_or_base_url"
        status: pass
      - kind: unit
        ref: "shared/tests/test_sentinel_client.py#test_embed_raises_http_status_error"
        status: pass
    human_judgment: false
  - id: D2
    description: "embed_texts() delegates to _core_client.embed() instead of litellm.aembedding, with signature and validation behavior unchanged"
    requirement: "EMB-01"
    verification:
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_embed_texts_delegates_to_core_client_and_returns_vectors"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_embed_texts_raises_valueerror_on_count_mismatch"
        status: pass
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_embed_texts_core_raise_propagates_unswallowed"
        status: pass
    human_judgment: false
  - id: D3
    description: "No direct vendor embedding call remains in llm.py (comment-stripped guardrail)"
    requirement: "EMB-01"
    verification:
      - kind: unit
        ref: "modules/pathfinder/tests/test_llm_core_handoff.py#test_llm_module_has_no_direct_vendor_embedding_call"
        status: pass
    human_judgment: false
  - id: D4
    description: "Rules-index build and per-query embedding route through core end-to-end (functional path is out of scope for unit tests; gated in 43-05)"
    requirement: "EMB-03"
    verification: []
    human_judgment: true
    rationale: "Live end-to-end proof (real rules-index build against a running sentinel-core) is explicitly deferred to Phase 43-05 per the plan's own success criteria; only the code-path contract is verified here."

# Metrics
duration: 12min
completed: 2026-07-05
status: complete
---

# Phase 43 Plan 03: Embeddings Handoff — pf2e to sentinel-core Summary

**pf2e's `embed_texts()` now sources vectors from sentinel-core's `POST /embeddings` via a new `SentinelCoreClient.embed()`, removing the last direct vendor embedding call from pf2e-module.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-05T21:58Z
- **Completed:** 2026-07-05T22:08Z
- **Tasks:** 2 completed
- **Files modified:** 4

## Accomplishments
- Added `SentinelCoreClient.embed(texts, client)` mirroring `complete()`'s raise-on-error posture exactly — POSTs only `{"texts": [...]}` to `/embeddings` with the `X-Sentinel-Key` header, raises on non-2xx, returns `{"embeddings": [...], "model": "..."}`.
- Swapped `embed_texts()`'s internals in `modules/pathfinder/app/llm.py` to call `_core_client.embed()` via a short-lived `httpx.AsyncClient` (matching the file's existing chat-handoff convention). Signature `(texts, model, api_base=None)` is byte-identical; `model`/`api_base` are now vestigial (D-04) so both call sites (`main.py`'s `_rule_embed_fn` closure and `rule_query.py`'s injected `embed_texts`) needed zero changes.
- Preserved input-shape validation (non-list / empty / non-string items) and output-count validation (`len(vectors) == len(texts)`).
- Deleted the old `litellm.aembedding` call entirely (no stale comment) and added a guardrail test asserting the comment-stripped `llm.py` contains no `aembedding` token.
- Cleaned up the now-dead `_RULING_TIMEOUT_S` constant whose sole call site (the deleted litellm kwargs dict) no longer exists.

## Task Commits

Each task followed the RED → GREEN TDD cycle:

1. **Task 1: Add `SentinelCoreClient.embed()` mirroring `complete()`**
   - `b2c89d8` (test) — failing tests for `embed()` (RED)
   - `7df0c68` (feat) — `embed()` implementation (GREEN)
2. **Task 2: Swap `embed_texts()` internals to the core client and add delegation + guardrail tests**
   - `e6708c8` (test) — failing delegation + guardrail tests (RED)
   - `ae39310` (feat) — `embed_texts()` rewritten to delegate to core (GREEN)

**Plan metadata:** (this commit)

## Files Created/Modified
- `shared/sentinel_client.py` — added `embed(self, texts, client) -> dict` method
- `shared/tests/test_sentinel_client.py` — added 6 tests for `embed()` (success, texts-only body, raise-on-4xx/5xx/timeout/connect, header)
- `modules/pathfinder/app/llm.py` — rewrote `embed_texts()` body to delegate to `_core_client.embed()`; updated module docstring; removed dead `_RULING_TIMEOUT_S` constant
- `modules/pathfinder/tests/test_llm_core_handoff.py` — added 7 tests: delegation, 3 validation-preserved cases, raise-propagation, guardrail

## Decisions Made
- `embed()`'s request body carries ONLY `texts` — no `model`/`api_base`/`base_url` forwarded, per D-04 (core owns backend selection).
- `embed_texts()` keeps accepting `model`/`api_base` as vestigial parameters (not forwarded) purely so its two existing callers compile unchanged this phase (Pattern 3) — a one-line comment in the docstring documents why.
- Removed `_RULING_TIMEOUT_S` (dead after its only use site — the old `litellm.aembedding` kwargs — was deleted) rather than leaving unused dead code (Rule 1: bug/cleanup directly caused by this task's change).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Dead code] Removed unused `_RULING_TIMEOUT_S` constant**
- **Found during:** Task 2 (swapping `embed_texts()` internals)
- **Issue:** `_RULING_TIMEOUT_S` was used only inside the deleted `litellm.aembedding` kwargs dict; after the swap it had zero remaining references.
- **Fix:** Deleted the constant definition.
- **Files modified:** `modules/pathfinder/app/llm.py`
- **Verification:** Full pathfinder test suite (405 tests) still green after removal.
- **Committed in:** `ae39310` (part of the Task 2 feat commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — dead-code cleanup).
**Impact on plan:** No scope creep — a direct, necessary cleanup of code made dead by this plan's own change.

## Issues Encountered
None.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
`embed_texts()` now routes through sentinel-core for its vector-compute leaf, with `RulesIndex`, `_build_rules_index_safely()`'s 503-degrade, and both call sites completely unchanged. Full pathfinder suite (405 tests) and shared suite (24 tests) both green. Live end-to-end proof of the rules-index build and `:pf rule` retrieval against a running sentinel-core is deferred to 43-05 per the plan's own success criteria — no blockers identified for that gate.

---
*Phase: 43-embeddings-through-sentinel*
*Completed: 2026-07-05*

## Self-Check: PASSED

All created/modified files verified present on disk; all 4 task commit hashes (`b2c89d8`, `7df0c68`, `e6708c8`, `ae39310`) verified in git log.
