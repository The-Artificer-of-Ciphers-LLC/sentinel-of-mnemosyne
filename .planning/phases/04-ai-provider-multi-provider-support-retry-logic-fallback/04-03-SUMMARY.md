---
phase: 04-ai-provider-multi-provider-support-retry-logic-fallback
plan: "03"
subsystem: sentinel-core
tags: [ai-provider, model-registry, provider-router, fallback, tdd]
dependency_graph:
  requires:
    - sentinel-core/app/clients/base.py — AIProvider Protocol (Plan 02)
    - sentinel-core/app/clients/litellm_provider.py — get_context_window_from_lmstudio (Plan 02)
    - sentinel-core/app/config.py — Settings with provider fields (Plan 01)
    - sentinel-core/models-seed.json — static seed (Plan 01)
  provides:
    - sentinel-core/app/services/model_registry.py — build_model_registry(), ModelInfo
    - sentinel-core/app/services/provider_router.py — ProviderRouter, ProviderUnavailableError
    - sentinel-core/tests/test_model_registry.py — 5 TDD tests all passing
    - sentinel-core/tests/test_provider_router.py — 7 TDD tests all passing
  affects:
    - sentinel-core/app/main.py — will wire ProviderRouter and model registry at startup (Plan 04)
tech_stack:
  added: []
  patterns:
    - Hybrid live-fetch + seed fallback pattern for model registry (non-fatal fetch failure)
    - ConnectError-only fallback trigger (not HTTP 4xx/5xx)
    - ProviderUnavailableError for HTTP 503 propagation
    - dataclass for ModelInfo (lightweight, no ORM needed)
key_files:
  created:
    - sentinel-core/app/services/model_registry.py
    - sentinel-core/app/services/provider_router.py
    - sentinel-core/tests/test_model_registry.py
    - sentinel-core/tests/test_provider_router.py
  modified: []
decisions:
  - "Seed always loaded first — live fetch overlays it, never replaces missing seed entries"
  - "_FALLBACK_TRIGGERS tuple defined at module level so it reads clearly in except clause"
  - "ProviderUnavailableError message contains 'Both providers failed' (title-case) — lowercase check in tests uses .lower() so case is not a constraint"
  - "Fallback also catches all exceptions from fallback provider (not just ConnectError) — if fallback raises RateLimitError it still fails over to ProviderUnavailableError"
metrics:
  duration: "~8 min"
  completed: 2026-04-10
  tasks_completed: 2
  files_changed: 4
---

# Phase 04 Plan 03: Model Registry and ProviderRouter Summary

Model registry built as hybrid live-fetch + seed fallback (non-fatal, seed always loaded), ProviderRouter implemented with ConnectError/TimeoutException-only fallback trigger and ProviderUnavailableError when both fail — 12 TDD tests all pass.

## What Was Built

### Task 1: model_registry.py — hybrid live-fetch + seed fallback (commit 44fbc36)

Created `sentinel-core/app/services/model_registry.py`:

- `ModelInfo` dataclass: `id`, `provider`, `context_window`, `capabilities` (dict), `notes`
- `_SEED_PATH` pointing to `models-seed.json` via `Path(__file__).parent.parent.parent`
- `_load_seed()` — reads models-seed.json, returns empty dict on any error (non-fatal)
- `_fetch_lmstudio()` — calls `get_context_window_from_lmstudio()`, logs 4096 default when fetch fails
- `_fetch_claude()` — Anthropic SDK `models.list()`, skips entirely when `anthropic_api_key` is empty
- `build_model_registry(settings, http_client)` — loads seed, overlays live fetch per active provider, also fetches fallback provider registry if `ai_fallback_provider == "claude"`

Per-provider behavior:

| Provider | Live fetch | Failure handling |
|----------|-----------|-----------------|
| lmstudio | GET /api/v0/models/{model_name} → max_context_length | Returns 4096 default, logged at WARNING |
| claude | Anthropic SDK models.list() | Skipped if no key; logs WARNING on API failure |
| ollama | None (stub) | logs INFO, seed only |
| llamacpp | None (stub) | logs INFO, seed only |
| unknown | None | logs WARNING, seed only |

Created `sentinel-core/tests/test_model_registry.py` with 5 TDD tests:

| Test | Assertion |
|------|-----------|
| test_lmstudio_registry_uses_fetched_context_window | context_window == 32768 from mock response |
| test_lmstudio_registry_falls_back_to_seed_on_unavailable | local-model present; test-model absent or 4096 |
| test_claude_registry_skips_live_fetch_without_key | claude-haiku-4-5 in registry from seed |
| test_seed_always_present_in_registry | local-model and claude-haiku-4-5 present after ConnectError |
| test_unknown_provider_returns_seed_only | len(registry) >= 1 |

### Task 2: provider_router.py — primary with ConnectError-only fallback (commit 06f95b1)

Created `sentinel-core/app/services/provider_router.py`:

- `_FALLBACK_TRIGGERS = (httpx.ConnectError, httpx.TimeoutException)` — module-level constant
- `ProviderUnavailableError(Exception)` — raised when all providers fail with connectivity errors
- `ProviderRouter.__init__(primary_provider, fallback_provider=None)` — optional fallback
- `ProviderRouter.complete(messages)` — try primary, catch `_FALLBACK_TRIGGERS`, try fallback, raise `ProviderUnavailableError` with "Both providers failed" message if both fail

Routing logic:

| Scenario | Outcome |
|----------|---------|
| Primary succeeds | Returns primary response |
| Primary raises ConnectError/TimeoutException, fallback succeeds | Returns fallback response |
| Primary raises ConnectError/TimeoutException, no fallback | ProviderUnavailableError |
| Primary raises ConnectError/TimeoutException, fallback also fails | ProviderUnavailableError ("Both providers failed") |
| Primary raises RateLimitError/AuthError/etc. | Propagates unchanged — no fallback attempt |

Created `sentinel-core/tests/test_provider_router.py` with 7 TDD tests:

| Test | Assertion |
|------|-----------|
| test_returns_primary_response_on_success | "primary response", fallback not called |
| test_falls_back_on_connect_error | "fallback response" |
| test_falls_back_on_timeout | "fallback response" |
| test_no_fallback_on_rate_limit_error | RateLimitError propagated, fallback not called |
| test_raises_unavailable_when_both_fail | ProviderUnavailableError, message contains "both providers failed" |
| test_raises_unavailable_with_no_fallback | ProviderUnavailableError |
| test_unavailable_error_message_mentions_both | "both providers failed" in message |

## Verification Results

1. `pytest tests/test_model_registry.py tests/test_provider_router.py -v` — 12 passed
2. `grep "ProviderUnavailableError" app/services/provider_router.py` — matches (class definition + 2 raise sites)
3. `grep "_FALLBACK_TRIGGERS" app/services/provider_router.py` — matches (definition + except clause)
4. `grep "build_model_registry" app/services/model_registry.py` — matches
5. `grep "models-seed.json" app/services/model_registry.py` — matches (_SEED_PATH + docstring + _load_seed)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed generator-based ConnectError raise in test template**

- **Found during:** Task 1, RED phase
- **Issue:** The plan's test template used `lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused"))` to raise ConnectError from MockTransport. This generator expression syntax is not valid in all Python 3.12+ contexts and triggers a `SyntaxWarning`.
- **Fix:** Replaced with a named function `def raise_connect_error(request): raise httpx.ConnectError("refused")` — cleaner and unambiguous.
- **Files modified:** `sentinel-core/tests/test_model_registry.py`
- **Commit:** 44fbc36

## Threat Mitigations Applied

| Threat ID | Mitigation |
|-----------|-----------|
| T-04-07 (Availability — both-fail path) | ProviderUnavailableError propagates to caller; both failures logged at ERROR level |
| T-04-08 (Information Disclosure — error detail) | Error detail in message is acceptable for personal tool; contains no secret values |
| T-04-09 (Information Disclosure — registry fetch logs) | logger.warning logs only exception type/message, never API key values |

## Known Stubs

None that block plan goals. Ollama and llama.cpp live fetches in `model_registry.py` are intentional stubs (log INFO, use seed). Provider implementations are out of scope for this plan.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| sentinel-core/app/services/model_registry.py | FOUND |
| sentinel-core/app/services/provider_router.py | FOUND |
| sentinel-core/tests/test_model_registry.py | FOUND |
| sentinel-core/tests/test_provider_router.py | FOUND |
| commit 44fbc36 | FOUND |
| commit 06f95b1 | FOUND |
| 12 tests passing | CONFIRMED |
