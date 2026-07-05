---
phase: 42-first-class-exo-provider
plan: 03
subsystem: api
tags: [fastapi, pydantic, httpx, provider-completion, pf2e-handoff]

# Dependency graph
requires:
  - phase: 42-first-class-exo-provider (plan 01)
    provides: "RouteContext.ai_provider exposing the built ProviderRouter"
provides:
  - "POST /provider/complete — narrow, auth-gated, bounded chat/completion passthrough on sentinel-core"
  - "SentinelCoreClient.complete() — raise-on-error client method for domain modules to call core for chat"
affects: [42-04, 42-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin passthrough route (no /message pipeline reuse) mirroring modules.py's proxy_module shape + message.py's RouteContext/router conventions"
    - "Pydantic max_length caps on both a list field (messages) and a nested model field (content) as the DoS-guard pattern for future core routes accepting arbitrary-length arrays"
    - "SentinelCoreClient raise-on-error posture (post_to_module) reused verbatim for complete() — send_message()'s swallow-to-string posture intentionally NOT copied"

key-files:
  created:
    - sentinel-core/app/routes/provider.py
    - sentinel-core/tests/test_provider_route.py
  modified:
    - sentinel-core/app/main.py
    - shared/sentinel_client.py
    - shared/tests/test_sentinel_client.py

key-decisions:
  - "messages list cap set to 50 (no existing precedent in the codebase; RESEARCH.md flagged the gap but left the exact number to implementation discretion) — comfortably covers a multi-turn pf2e chat handoff while bounding worst-case LLM cost/latency"
  - "Per-message content cap set to 32,000 chars, mirroring MessageEnvelope.content's existing max_length pattern exactly (app/models.py)"
  - "Docstrings intentionally avoid naming MessageProcessor/Recall/InjectionFilter/OutputScanner literally (paraphrased as '/message pipeline') so the plan's own source-assertion (grep -c for those names returns 0) stays true even as documentation, not just code"

patterns-established:
  - "Any future narrow sentinel-core route that accepts a caller-supplied list should follow this file's dual-cap shape: Field(max_length=...) on the outer list AND on nested string fields, not just one or the other"

requirements-completed: [SC-6]

coverage:
  - id: D1
    description: "POST /provider/complete returns {content, model} via ctx.ai_provider.complete() passthrough; auth-gated by existing global middleware; ai_provider=None -> 500; ProviderUnavailableError -> 503 generic (no secrets leaked); oversized messages/content -> 422"
    requirement: "SC-6"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_provider_route.py#test_provider_complete_success"
        status: pass
      - kind: unit
        ref: "sentinel-core/tests/test_provider_route.py#test_provider_complete_requires_auth"
        status: pass
      - kind: unit
        ref: "sentinel-core/tests/test_provider_route.py#test_provider_complete_no_provider_configured"
        status: pass
      - kind: unit
        ref: "sentinel-core/tests/test_provider_route.py#test_provider_complete_503_on_provider_unavailable"
        status: pass
      - kind: unit
        ref: "sentinel-core/tests/test_provider_route.py#test_provider_complete_422_on_too_many_messages"
        status: pass
      - kind: unit
        ref: "sentinel-core/tests/test_provider_route.py#test_provider_complete_422_on_content_too_long"
        status: pass
    human_judgment: false
  - id: D2
    description: "SentinelCoreClient.complete() posts to /provider/complete with X-Sentinel-Key auth, returns parsed {content, model} dict, and raises (not swallows) httpx.HTTPStatusError/ConnectError/TimeoutException like post_to_module()"
    requirement: "SC-6"
    verification:
      - kind: unit
        ref: "shared/tests/test_sentinel_client.py#test_complete_success"
        status: pass
      - kind: unit
        ref: "shared/tests/test_sentinel_client.py#test_complete_forwards_stop_and_temperature"
        status: pass
      - kind: unit
        ref: "shared/tests/test_sentinel_client.py#test_complete_raises_http_status_error"
        status: pass
      - kind: unit
        ref: "shared/tests/test_sentinel_client.py#test_complete_raises_connect_error"
        status: pass
      - kind: unit
        ref: "shared/tests/test_sentinel_client.py#test_complete_raises_timeout_exception"
        status: pass
      - kind: unit
        ref: "shared/tests/test_sentinel_client.py#test_complete_sends_sentinel_key_header"
        status: pass
    human_judgment: false

duration: ~25min
completed: 2026-07-05
status: complete
---

# Phase 42 Plan 03: Provider Completion Route + Client Summary

**A narrow `POST /provider/complete` endpoint on sentinel-core (thin passthrough to `ctx.ai_provider.complete()`, no `/message` pipeline reuse) plus `SentinelCoreClient.complete()` — the receiving end of the pf2e→core chat handoff (D-09).**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-05T17:30:00Z
- **Completed:** 2026-07-05T17:55:37Z
- **Tasks:** 2 completed
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- `POST /provider/complete` returns `{content, model}` via a thin `ctx.ai_provider.complete()` passthrough — no `MessageProcessor`/recall/injection-filter/output-scanner reuse — satisfying D-09's "narrow completion endpoint, not the full pipeline" requirement
- Auth is entirely via the existing global `APIKeyMiddleware` — zero new auth code, confirmed by a 401-without-header test
- Both a list-size cap (`messages`, max 50) and a per-item content-length cap (32,000 chars, mirroring `MessageEnvelope.content`) reject oversized requests at 422 before any LLM call (V5 DoS guard, T-42-07)
- `ProviderUnavailableError` maps to a generic 503; a test proves the response body never contains the underlying provider's `api_base`/`api_key` values (T-42-08)
- `SentinelCoreClient.complete()` added to the shared client, mirroring `post_to_module()`'s raise-on-error posture exactly (not `send_message()`'s swallow-to-string posture) so pf2e call sites (Plan 42-04/05) get real exceptions to react to

## Task Commits

1. **Task 1: POST /provider/complete narrow completion route + main.py registration (SC-6, D-09)** - `21141dc` (feat)
2. **Task 2: SentinelCoreClient.complete() raise-on-error client method (SC-6)** - `b38d447` (feat)

**Plan metadata:** (this commit) - `docs(42-03): complete provider completion route + client plan`

## Files Created/Modified
- `sentinel-core/app/routes/provider.py` - New `APIRouter` with `POST /provider/complete`; `ProviderMessage`/`ProviderCompleteRequest`/`ProviderCompleteResponse` Pydantic models with dual max_length caps
- `sentinel-core/app/main.py` - Imports and registers `provider_router` alongside `message_router`/`status_router`/`modules_router`/`note_router`
- `sentinel-core/tests/test_provider_route.py` - New FastAPI `TestClient`-style tests (via `AsyncClient`+`ASGITransport` against `app.main.app`, mirroring `test_modules.py`'s `RouteContext` seeding convention): 200 success, 401 no-auth, 500 no-provider, 503 provider-unavailable (secret-leak assertion), 422 too-many-messages, 422 content-too-long
- `shared/sentinel_client.py` - `SentinelCoreClient.complete(messages, client, stop=None, temperature=None) -> dict` method
- `shared/tests/test_sentinel_client.py` - 6 new tests: success + stop/temperature forwarding, raise-on-HTTPStatusError/ConnectError/TimeoutException, X-Sentinel-Key header assertion

## Decisions Made
- Messages list cap chosen as 50 (no existing precedent — RESEARCH.md explicitly flagged this as a gap to be filled at implementation time); per-item content cap set to exactly match `MessageEnvelope.content`'s existing `max_length=32_000`
- Docstrings in `provider.py` paraphrase "no `/message` pipeline reuse" instead of naming `MessageProcessor`/`Recall`/`InjectionFilter`/`OutputScanner` literally, so the plan's own `grep -c "MessageProcessor\|Recall\|InjectionFilter\|OutputScanner"` source-assertion (expected: 0) holds even against documentation text, not just executable code — caught during self-verification of the plan's acceptance criteria and fixed before commit (not logged as a Rule 1-3 deviation since no behavior was ever wrong; it was a wording adjustment made pre-commit while validating the plan's own literal grep assertion)

## Deviations from Plan

None - plan executed exactly as written. (One pre-commit wording adjustment to `provider.py`'s docstrings is documented above under Decisions Made rather than as a deviation, since it did not change behavior or require rework — it was applied before the first commit while validating the plan's own acceptance-criteria grep.)

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- pf2e-module (Plan 42-04/05) can now call `SentinelCoreClient.complete()` to migrate its ~13 direct litellm chat call sites to the core gateway
- Full sentinel-core suite green: 447 passed, 12 skipped (up from 427 in Plan 42-01, +20 net from Plan 42-02 and this plan combined)
- `shared` test suite green: 18 passed (12 existing + 6 new `complete()` tests)
- No blockers.

---
*Phase: 42-first-class-exo-provider*
*Completed: 2026-07-05*

## Self-Check: PASSED

All 5 created/modified files found on disk; both task commit hashes (21141dc, b38d447) found in git log.
