---
quick_id: 260426-lcl
slug: model-agnostic-llm-endpoint-discovery
status: complete
date: 2026-04-26
commit: 88483d6
---

# Quick Task 260426-lcl: Model-Agnostic LLM Endpoint Discovery

## What Was Done

Wired `/v1/models` OpenAI-compatible endpoint discovery into sentinel-core's startup flow so the Sentinel automatically discovers and uses whatever model the user has loaded, rather than requiring a hardcoded `MODEL_NAME` env var.

## Tasks Completed (3/3)

### Task 1 — model_selector.py + config.py + RED tests
- **New file:** `sentinel-core/app/services/model_selector.py` — ported from `modules/pathfinder/app/model_selector.py`; exports `discover_active_model()`, `get_loaded_models()`, `select_model()`
- **Extended:** `sentinel-core/app/config.py` — added `model_auto_discover: bool = True`, `model_preferred: str | None = None`, `model_task_chat/structured/fast: str | None = None`
- **New test file:** `sentinel-core/tests/test_model_selector_discovery.py` — 10 behavior cases covering full fallback chain (discovery succeeds, empty list, network failure, preferred model honored, first-loaded fallback, auto-discover disabled)
- **Commits:** `ea28bbe` (RED tests), `7786c51` (feat)

### Task 2 — Wire discovery into model_registry + main.py lifespan
- **Updated:** `sentinel-core/app/services/model_registry.py` — `_fetch_lmstudio` now accepts `discovered_name` param; `build_model_registry` calls `discover_active_model()` before the provider if-chain
- **Updated:** `sentinel-core/app/main.py` — lifespan calls `discover_active_model(settings, http_client)`; result drives `LiteLLMProvider(model_string=_lmstudio_model_str)`
- **Extended:** `sentinel-core/tests/test_model_registry.py` — 3 new tests covering discovery path
- **Commits:** `d65ca0f` (RED tests), `67a1bdc` (feat)

### Task 3 — Test suite validation + guardrail fix
- Fixed `test_ai_agnostic_guardrail.py` exclusion list to include `model_selector.py`
- Resolved ROADMAP.md merge conflict (worktree had stale ROADMAP content)
- **Result:** 156 tests passed, 1 pre-existing failure (unrelated litellm import in message.py — existed at base commit `6851dfd`), 12 skipped
- **Commit:** `19ed51f`

## Key Files Changed

| File | Change |
|------|--------|
| `sentinel-core/app/services/model_selector.py` | New — discovery + scoring |
| `sentinel-core/app/config.py` | +5 fields: model_auto_discover, model_preferred, model_task_{chat,structured,fast} |
| `sentinel-core/app/main.py` | discover_active_model() called at lifespan startup |
| `sentinel-core/app/services/model_registry.py` | Uses discovered name, not static settings.model_name |
| `sentinel-core/tests/test_model_selector_discovery.py` | New — 10 tests |
| `sentinel-core/tests/test_model_registry.py` | +3 tests for discovery path |

## Behavior After This Change

1. At startup, sentinel-core calls `GET <base_url>/v1/models`
2. If `MODEL_PREFERRED` or `MODEL_NAME` is loaded → uses it
3. Otherwise → scores available models with litellm.get_model_info() for "chat" task kind, picks best
4. Falls back to first loaded model, then to static `MODEL_NAME` if discovery fails
5. `MODEL_AUTO_DISCOVER=false` disables discovery entirely (static mode)

## Notes

- LM Studio in single-model mode returns one model from `/v1/models` — discovery still works (scores one model)
- Ollama also exposes `/v1/models` with compatible format
- `/api/v0/` LM Studio proprietary context-window endpoint unchanged; still provider-gated
- Hot-reload not implemented: model switch requires container restart (acceptable for v0.x)
- The 1 pre-existing test failure (`message.py` litellm import) predates this task and is out of scope
