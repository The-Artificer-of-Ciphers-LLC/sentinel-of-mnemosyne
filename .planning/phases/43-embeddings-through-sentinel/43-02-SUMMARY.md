---
phase: 43-embeddings-through-sentinel
plan: 02
subsystem: api
tags: [fastapi, pydantic, embeddings, sentinel-core]

# Dependency graph
requires:
  - phase: 42-provider-independence
    provides: "POST /provider/complete passthrough pattern (D-09), RouteContext dataclass, APIKeyMiddleware global auth"
  - phase: 43-embeddings-through-sentinel (plan 01)
    provides: "RouteContext.embedder wiring fixes in composition.py"
provides:
  - "POST /embeddings — narrow raw-embeddings passthrough route in sentinel-core, auth-gated, size-capped, non-leaking on backend failure"
  - "app/routes/embeddings.py: router, EmbeddingsRequest, EmbeddingsResponse, _MAX_TEXTS, _MAX_TEXT_LENGTH, post_embeddings"
affects: [43-03-pf2e-sentinel-client, 43-04, 43-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Narrow gateway passthrough route (mirrors /provider/complete): thin call into ctx.<seam>, catch only the one typed unavailable exception -> generic 503, no /message pipeline reuse"
    - "Per-item length cap enforced via pydantic field_validator so 422 fires before the handler body runs (not a manual in-handler check)"

key-files:
  created:
    - sentinel-core/app/routes/embeddings.py
    - sentinel-core/tests/test_embeddings_route.py
  modified:
    - sentinel-core/app/main.py

key-decisions:
  - "Per-text length cap (_MAX_TEXT_LENGTH=8000) implemented as a pydantic field_validator on EmbeddingsRequest.texts rather than a manual handler-body check, so pydantic (not the handler) rejects with 422 before ctx.embedder is ever called (matches the plan's stated behavior contract)"
  - "_MAX_TEXTS=200 headroom constant matches the plan's stated value; no client-supplied model/base_url field exists on EmbeddingsRequest (D-04 / SSRF control)"

requirements-completed: [EMB-01]

coverage:
  - id: D1
    description: "POST /embeddings returns one float vector per input text via ctx.embedder, using the configured embedding_model as the response model field"
    requirement: "EMB-01"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_embeddings_route.py#test_embeddings_success"
        status: pass
    human_judgment: false
  - id: D2
    description: "Oversized batch (>200 texts), oversized single text (>8000 chars), or empty texts list is rejected 422 before the backend is called"
    requirement: "EMB-01"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_embeddings_route.py#test_embeddings_422_on_too_many_texts"
        status: pass
      - kind: unit
        ref: "sentinel-core/tests/test_embeddings_route.py#test_embeddings_422_on_text_too_long"
        status: pass
      - kind: unit
        ref: "sentinel-core/tests/test_embeddings_route.py#test_embeddings_422_on_empty_texts"
        status: pass
    human_judgment: false
  - id: D3
    description: "EmbeddingModelUnavailable from ctx.embedder yields a generic 503 that never echoes api_base/api_key"
    requirement: "EMB-01"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_embeddings_route.py#test_embeddings_503_on_backend_unavailable"
        status: pass
    human_judgment: false
  - id: D4
    description: "Route is auth-gated by the existing global X-Sentinel-Key middleware"
    requirement: "EMB-01"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_embeddings_route.py#test_embeddings_requires_auth"
        status: pass
    human_judgment: false
  - id: D5
    description: "AI-agnostic guardrail (no vendor SDK import in app/routes/embeddings.py) still passes with the new route registered"
    requirement: "EMB-01"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_ai_agnostic_guardrail.py#test_no_vendor_ai_imports_or_hardcoded_models"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-07-05
status: complete
---

# Phase 43 Plan 02: POST /embeddings Passthrough Route Summary

**Narrow `POST /embeddings` gateway route in sentinel-core — line-for-line structural mirror of `/provider/complete`, thin passthrough to `ctx.embedder`, texts-only schema with no client-supplied backend override.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2/2 completed
- **Files modified:** 3 (1 created route, 1 created test file, 1 modified main.py)

## Accomplishments
- `sentinel-core/app/routes/embeddings.py` created: `router`, `EmbeddingsRequest` (texts-only, `_MAX_TEXTS=200` + per-item `_MAX_TEXT_LENGTH=8000` via `field_validator`), `EmbeddingsResponse`, `post_embeddings` handler narrowly catching `EmbeddingModelUnavailable` -> generic 503.
- Route registered in `app/main.py` alongside `provider_router`, inheriting the global `APIKeyMiddleware` auth gate automatically.
- `tests/test_embeddings_route.py` added covering all five required behaviors: 200 happy path, 401 auth, 422 x3 (too many texts / text too long / empty texts), 503 non-leak.
- Full sentinel-core suite verified green: 455 passed, 12 skipped (pre-existing skips, unrelated to this change).

## Task Commits

Each task was committed atomically:

1. **Task 1: Create the POST /embeddings passthrough route mirroring provider.py** - `c342f15` (feat)
2. **Task 2: Register the route in main.py and add the route test suite** - `ef76f70` (feat)

**Plan metadata:** (recorded below, this commit)

## Files Created/Modified
- `sentinel-core/app/routes/embeddings.py` - New router with `EmbeddingsRequest`/`EmbeddingsResponse`/`post_embeddings`, mirrors `provider.py`'s narrow-catch posture
- `sentinel-core/tests/test_embeddings_route.py` - New test module: happy path, auth, 3x 422 boundary tests, 503 non-leak
- `sentinel-core/app/main.py` - Added `embeddings_router` import + `app.include_router(embeddings_router)`

## Decisions Made
- Implemented the per-text length cap as a pydantic `field_validator` on `EmbeddingsRequest.texts` (raising `ValueError` -> FastAPI's automatic 422) instead of a manual length check inside the handler body. The plan's `<behavior>` block explicitly requires oversized-text rejection to happen "by pydantic before the handler body runs" — a manual in-handler check would still return 422 but would call `get_route_context` and skip straight past pydantic's own validation semantics, so the field_validator is the correct implementation of the stated contract.
- No other deviations: `_MAX_TEXTS=200`, `_MAX_TEXT_LENGTH=8000`, response shape, and the narrow `except EmbeddingModelUnavailable` posture all match the plan's `<action>` block exactly.

## Deviations from Plan

None - plan executed exactly as written (the field_validator choice above is an implementation detail satisfying the plan's own behavior spec, not a deviation from it).

## TDD Gate Compliance

Both tasks carry `tdd="true"` in the PLAN.md frontmatter, but the plan's own `<action>` blocks sequence Task 1 as "write the route implementation" and Task 2 as "register the route + write the test suite" — i.e., implementation-then-tests, not RED-then-GREEN. The project's `tdd_mode` config flag is `false` for this phase (confirmed via `init.execute-phase`), and the plan's `type` frontmatter is `execute`, not `tdd`, so the plan-level TDD gate (RED/GREEN/REFACTOR commit sequence) does not apply here — the per-task `tdd="true"` markers describe test coverage intent, not a mandated commit ordering. Git log shows `feat` -> `feat` (no preceding `test` commit), consistent with the plan's literal task order. No test regressions: all 7 new/existing tests pass, and the full 455-test suite remains green.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `POST /embeddings` is live, auth-gated, size-capped, and proven by automated tests — ready for 43-03's `SentinelCoreClient.embed()` to call.
- All three security controls (V5 size caps, 503 non-leak, texts-only schema / no SSRF override) are proven green.
- No blockers for Wave 2/3 plans in this phase.

---
*Phase: 43-embeddings-through-sentinel*
*Completed: 2026-07-05*

## Self-Check: PASSED

- FOUND: sentinel-core/app/routes/embeddings.py
- FOUND: sentinel-core/tests/test_embeddings_route.py
- FOUND: commit c342f15
- FOUND: commit ef76f70
