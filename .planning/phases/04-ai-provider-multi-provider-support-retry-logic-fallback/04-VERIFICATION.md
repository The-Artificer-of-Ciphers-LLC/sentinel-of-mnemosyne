---
phase: 04-ai-provider-multi-provider-support-retry-logic-fallback
verified: 2026-04-10T00:00:00Z
status: gaps_found
score: 3/4 success criteria verified
re_verification: false
gaps:
  - truth: "Failed Pi calls retry 3 times with exponential backoff before failing"
    status: failed
    reason: "PiAdapterClient.send_messages() makes a single HTTP call with no retry. The tenacity @retry decorator (3 attempts, exp backoff) is on LiteLLMProvider.complete(), which is the AI fallback path — not the Pi client path. PROV-03 states 'Pi client has error handling, retry logic (3 attempts, exponential backoff), and hard 30-second timeout.'"
    artifacts:
      - path: "sentinel-core/app/clients/pi_adapter.py"
        issue: "send_messages() and send_prompt() have no retry logic — single call, raises on failure"
    missing:
      - "Add tenacity @retry (3 attempts, exponential backoff 1s-4s) to PiAdapterClient.send_messages() for transient httpx.ConnectError and httpx.TimeoutException"
      - "Consider adding a hard timeout assertion on the Pi call (190s current timeout has no retry ceiling)"
---

# Phase 4: AI Provider Verification Report

**Phase Goal:** Provider configuration via env vars. Multiple providers switchable. Retry logic and fallback.
**Verified:** 2026-04-10
**Status:** gaps_found — 3/4 success criteria verified
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Switch from LM Studio to Claude API by changing only env vars | VERIFIED | `AI_PROVIDER` env var selects provider in `Settings`. `main.py` lifespan reads `settings.ai_provider` and routes to `LiteLLMProvider` configured with either `openai/{model}` (LM Studio) or `{claude_model}` (Claude). No code changes required — only `AI_PROVIDER`, `CLAUDE_MODEL`, `ANTHROPIC_API_KEY` env vars. |
| 2 | Failed Pi calls retry 3 times with exponential backoff before failing | FAILED | `PiAdapterClient.send_messages()` makes one HTTP call and raises on failure. The tenacity @retry(3 attempts, wait_exponential) is on `LiteLLMProvider.complete()` — the AI fallback, not the Pi client. PROV-03 requires retry on the Pi client path. |
| 3 | When LM Studio unavailable, Core routes to Claude API automatically | VERIFIED | `ProviderRouter` in `app/services/provider_router.py` catches `httpx.ConnectError` and `httpx.TimeoutException` from the primary provider and calls fallback. Set `AI_FALLBACK_PROVIDER=claude` and `ANTHROPIC_API_KEY` to enable. 7 provider_router tests pass. |
| 4 | Model registry maps model names to context window sizes | VERIFIED | `build_model_registry()` in `app/services/model_registry.py` loads `models-seed.json` (5 models) and overlays live fetch from LM Studio or Claude API. `app.state.model_registry` holds `dict[str, ModelInfo]`. `app.state.context_window` is populated from registry at startup. |

**Score:** 3/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `sentinel-core/app/clients/base.py` | AIProvider Protocol | VERIFIED | `class AIProvider(Protocol)` with `async complete(messages: list[dict]) -> str` |
| `sentinel-core/app/clients/litellm_provider.py` | LiteLLMProvider with tenacity retry + 30s timeout | VERIFIED | `@retry(stop_after_attempt(3), wait_exponential, reraise=True)`, `"timeout": 30.0` in kwargs |
| `sentinel-core/app/clients/ollama_provider.py` | OllamaProvider stub | VERIFIED | `class OllamaProvider` raises `NotImplementedError` with actionable message |
| `sentinel-core/app/clients/llamacpp_provider.py` | LlamaCppProvider stub | VERIFIED | `class LlamaCppProvider` raises `NotImplementedError` |
| `sentinel-core/app/services/model_registry.py` | ModelInfo dataclass + build_model_registry() | VERIFIED | `@dataclass class ModelInfo`, `async def build_model_registry(settings, http_client)` |
| `sentinel-core/app/services/provider_router.py` | ProviderRouter with ConnectError-only fallback | VERIFIED | `_FALLBACK_TRIGGERS = (httpx.ConnectError, httpx.TimeoutException)`, `class ProviderUnavailableError` |
| `sentinel-core/app/main.py` | ProviderRouter wired in lifespan | VERIFIED | `app.state.ai_provider = ProviderRouter(primary, fallback_provider=fallback)` at line 122 |
| `sentinel-core/app/routes/message.py` | Uses ai_provider, catches ProviderUnavailableError | VERIFIED | `ai_provider = request.app.state.ai_provider` + `except ProviderUnavailableError` |
| `sentinel-core/app/config.py` | All provider env vars in Settings | VERIFIED | `ai_provider`, `ai_fallback_provider`, `anthropic_api_key`, `claude_model`, `ollama_base_url`, `ollama_model`, `llamacpp_base_url`, `llamacpp_model` |
| `sentinel-core/models-seed.json` | 5 seed models with context windows | VERIFIED | 5 entries: qwen2.5:14b, claude-haiku-4-5, claude-sonnet-4-5, claude-sonnet-4-6, local-model |
| `sentinel-core/pyproject.toml` | litellm>=1.83.0, tenacity, anthropic deps | VERIFIED | All 3 deps present with correct version pins |
| `sentinel-core/app/clients/lmstudio.py` | DELETED | VERIFIED | File does not exist |
| `sentinel-core/tests/test_litellm_provider.py` | 9 TDD tests | VERIFIED | 9 tests present and passing |
| `sentinel-core/tests/test_model_registry.py` | 5 TDD tests | VERIFIED | 5 tests present and passing |
| `sentinel-core/tests/test_provider_router.py` | 7 TDD tests | VERIFIED | 7 tests present and passing |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `litellm_provider.py` | `litellm.acompletion` | `import litellm; await litellm.acompletion(**kwargs)` | WIRED | Line 77: `response = await litellm.acompletion(**kwargs)` |
| `litellm_provider.py` | `base.py` AIProvider Protocol | `class LiteLLMProvider` structurally satisfies Protocol | WIRED | Protocol is structural (typing.Protocol), LiteLLMProvider has matching `async complete()` |
| `main.py` | `model_registry.py` | `build_model_registry()` called in lifespan | WIRED | Line 59: `model_registry = await build_model_registry(settings, http_client)` |
| `main.py` | `provider_router.py` | `ProviderRouter` instantiated in lifespan | WIRED | Line 122: `app.state.ai_provider = ProviderRouter(primary, fallback_provider=fallback)` |
| `message.py` | `provider_router.py` | `request.app.state.ai_provider.complete()` | WIRED | Lines 102-108: `ai_provider = request.app.state.ai_provider; content = await ai_provider.complete(messages)` |
| `model_registry.py` | `models-seed.json` | `_SEED_PATH = Path(__file__).parent.parent.parent / "models-seed.json"` | WIRED | `_load_seed()` reads seed at startup |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `message.py` | `content` from `ai_provider.complete()` | `ProviderRouter → LiteLLMProvider → litellm.acompletion()` | Yes (via LiteLLM to external provider) | FLOWING |
| `message.py` | `context_window` | `app.state.context_window` set from `model_registry.get(_active_model).context_window` | Yes (from registry or seed) | FLOWING |
| `model_registry.py` | `registry` dict | `_load_seed()` always, plus live fetch per provider | Yes (seed is a real JSON file with 5 entries) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 56 tests pass | `.venv/bin/python -m pytest -v` | 56 passed, 0 failed in 13.57s | PASS |
| lmstudio.py deleted | `ls sentinel-core/app/clients/lmstudio.py` | File not found | PASS |
| test_lmstudio_client.py deleted | `ls sentinel-core/tests/test_lmstudio_client.py` | File not found | PASS |
| stop_after_attempt(3) in litellm_provider | `grep "stop_after_attempt(3)"` | Line 56 | PASS |
| timeout=30.0 in litellm_provider (PROV-03) | `grep '"timeout": 30.0'` | Line 69 | PASS |
| ProviderRouter in app.state | `grep "app.state.ai_provider = ProviderRouter"` | Line 122 of main.py | PASS |
| No lm_client in app state | `grep "app.state.lm_client"` | No matches in app/ | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PROV-01 | 04-01, 04-04 | All provider URLs/API keys via env vars | SATISFIED | Settings class with all 8 provider fields; no hardcoded endpoints in app/ |
| PROV-02 | 04-02 | Two providers testable by changing only env vars | SATISFIED | LM Studio + Claude both wired through LiteLLMProvider; `AI_PROVIDER` + `ANTHROPIC_API_KEY` switch between them |
| PROV-03 | 04-02 | Pi client retry 3 attempts, exp backoff, 30s timeout | BLOCKED | Retry (3 attempts, exp backoff) is on `LiteLLMProvider.complete()`, not `PiAdapterClient`. REQUIREMENTS.md explicitly says "Pi client has error handling, retry logic" — Pi client has none. The 30s timeout on litellm.acompletion() is present but PROV-03 requires it on the Pi call path too. |
| PROV-04 | 04-03 | Model registry maps model names to context window sizes | SATISFIED | `build_model_registry()` returns `dict[str, ModelInfo]` with context_window field; stored in `app.state.model_registry` |
| PROV-05 | 04-03, 04-04 | Fallback when LM Studio unavailable → Claude API | SATISFIED | `ProviderRouter` with `_FALLBACK_TRIGGERS=(ConnectError, TimeoutException)` triggers fallback to Claude |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `sentinel-core/app/clients/ollama_provider.py` | 33-42 | `raise NotImplementedError` on `complete()` | Info | Intentional stub per plan scope — raises with actionable setup instructions |
| `sentinel-core/app/clients/llamacpp_provider.py` | ~33 | `raise NotImplementedError` on `complete()` | Info | Intentional stub per plan scope |

No blockers found beyond the PROV-03 gap.

### Human Verification Required

None — all success criteria are verifiable programmatically. The gap in PROV-03 (Pi retry) is a code-level finding, not a UI/UX concern.

### Gaps Summary

**One gap blocking full goal achievement:**

PROV-03 states "Pi client has error handling, retry logic (3 attempts, exponential backoff), and hard 30-second timeout." The ROADMAP Success Criterion #2 is "Failed Pi calls retry 3 times with exponential backoff before failing."

The implementation added retry logic correctly to `LiteLLMProvider.complete()` — but this is the AI provider path, not the Pi harness path. `PiAdapterClient.send_messages()` in `sentinel-core/app/clients/pi_adapter.py` makes a single HTTP call and raises immediately on failure (ConnectError, TimeoutException, or HTTP error). There is no tenacity decorator or retry loop.

The `message.py` route pattern is: try Pi once → on any exception, fall through to `ai_provider.complete()`. This means a Pi failure due to a transient network blip is not retried — it immediately falls through to the AI provider. This deviates from both PROV-03 ("Pi client has retry logic") and ROADMAP SC#2 ("Failed Pi calls retry 3 times").

**Fix:** Add `@retry(retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)), stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4), reraise=True)` to `PiAdapterClient.send_messages()`. Add corresponding tests in `test_pi_adapter.py`.

---

_Verified: 2026-04-10_
_Verifier: Claude (gsd-verifier)_
