# Research: Model-Agnostic LLM Endpoint Discovery

**Date:** 2026-04-26
**Domain:** LLM provider abstraction, OpenAI-compatible endpoint discovery
**Confidence:** HIGH — based on direct codebase analysis + existing implementation patterns

---

## Current State

### What exists today

The Sentinel already has a multi-layer LLM abstraction. Most of the plumbing for model-agnostic operation is built. The gaps are specific, not architectural.

**sentinel-core** (`sentinel-core/app/`):
- `config.py` — has `ai_provider` (lmstudio|claude|ollama|llamacpp), `lmstudio_base_url`, `model_name`. The `model_name` is a static env var — it does NOT auto-discover.
- `clients/litellm_provider.py` — `LiteLLMProvider` wraps `litellm.acompletion()`. LM Studio uses `model_string="openai/<model_name>"`, `api_base=settings.lmstudio_base_url`. Model string is baked at startup from `settings.model_name`.
- `services/model_registry.py` — calls `GET /api/v0/models/{model_name}` (LM Studio proprietary endpoint) to fetch context window. Still requires a specific model name — no discovery.
- `services/provider_router.py` — primary/fallback routing. Model selection is not its concern.

**modules/pathfinder** (`modules/pathfinder/app/`):
- `model_selector.py` — already implements `GET /v1/models` discovery + litellm capability scoring. Queries the OpenAI-compatible endpoint, NOT the proprietary `/api/v0/` endpoint. Caches results per process. [VERIFIED: codebase]
- `resolve_model.py` — thin adapter wiring `model_selector` into pathfinder settings. Prepends `openai/` provider prefix for LiteLLM.
- `config.py` — has `litellm_model` (static fallback), `litellm_api_base`, plus three optional per-task-kind overrides (`litellm_model_chat/structured/fast`).

### What is hardcoded vs configurable

| Component | Hardcoded? | Notes |
|-----------|-----------|-------|
| LM Studio base URL | Configurable via env (`LMSTUDIO_BASE_URL`) | Works today |
| Active model name | **Hardcoded at startup** — from `MODEL_NAME` env var | Core gap |
| Model discovery in sentinel-core | **Not implemented** — seed JSON + single model fetch | Core gap |
| Model discovery in pathfinder | Working — `model_selector.py` queries `/v1/models` | Already done |
| Provider prefix (`openai/`) | Manual in `resolve_model.py` | Pattern established |

### Where LLM calls are made

**sentinel-core:**
- `routes/message.py` — calls `app.state.ai_provider.complete(messages)` (via `ProviderRouter`)
- `main.py` lifespan — instantiates `LiteLLMProvider` with `f"openai/{settings.model_name}"` baked in at startup

**pathfinder module:**
- `llm.py` — all call sites (`extract_npc_fields`, `generate_npc_reply`, `generate_mj_description`, `update_npc_fields`, `generate_harvest_fallback`, `embed_texts`, all Phase 33/34 helpers). All accept `model: str` and `api_base: str | None` as explicit parameters — already decoupled.
- `routes/npc.py` — calls `await resolve_model("structured"|"fast")` for 3 call sites. The dynamic resolution pattern is live.

---

## Recommended Approach

The architecture for model-agnostic operation is already established in the pathfinder module. The task is to:

1. Lift `model_selector.py` from pathfinder into a shared location (or duplicate into sentinel-core's `app/services/`)
2. Replace the hardcoded `settings.model_name` in sentinel-core's lifespan with a startup discovery call
3. Align the model registry's context-window fetch to use the discovered model name, not a static one

**The critical insight:** sentinel-core's `LiteLLMProvider` is constructed once at startup with a baked-in model string. For model-agnostic operation, the model string must be resolved at construction time via `/v1/models` discovery, with the static env var as fallback — not just used directly.

---

## Library Decision

**Use LiteLLM (already in stack) — no new dependencies needed.** [VERIFIED: codebase]

| Option | Verdict | Reason |
|--------|---------|--------|
| `httpx` direct | Already used for `/v1/models` discovery in `model_selector.py` | Keep for discovery calls |
| `litellm` | Already in stack, handles provider routing, `get_model_info()` for capability scoring | Keep for completions |
| `openai` SDK | Would add a dependency; litellm already wraps OpenAI-compatible endpoints via `openai/<model>` prefix | Reject |
| `litellm` router | Not needed — `ProviderRouter` already handles primary/fallback | Reject |

The pattern that works: `httpx` for `/v1/models` discovery, `litellm.acompletion()` for completions, `litellm.get_model_info()` for capability metadata.

---

## Configuration Schema

Extend `sentinel-core/app/config.py` Settings:

```python
# Existing (keep):
lmstudio_base_url: str = "http://host.docker.internal:1234/v1"
model_name: str = "local-model"        # kept as static fallback / preferred model hint

# New fields:
model_auto_discover: bool = True       # if True, query /v1/models at startup; if False, use model_name directly
model_preferred: str | None = None     # preferred model name; None = pick best from /v1/models
model_task_chat: str | None = None     # override: model for chat task kind
model_task_structured: str | None = None  # override: model for structured task kind
model_task_fast: str | None = None     # override: model for fast task kind
```

The existing `model_name` field is retained as both the static fallback (when discovery fails) and the "preferred" hint (resolution step 1 before scoring). This avoids a breaking change to any existing `.env` files.

For Ollama, llama.cpp, and future OpenAI-compatible backends: the same `model_auto_discover` flag applies because they all expose `/v1/models`. For the `claude` provider, discovery is already handled by `anthropic_registry.py` and is out of scope here.

---

## Discovery Algorithm

```python
async def discover_active_model(
    settings: Settings,
    http_client: httpx.AsyncClient,
) -> str:
    """
    Returns a LiteLLM-compatible model string (e.g. "openai/Qwen2.5-14B-Instruct").
    Falls back to f"openai/{settings.model_name}" on any failure.
    """
    if not settings.model_auto_discover:
        # Static mode — use whatever is in model_name, prepend provider prefix
        return _with_provider_prefix(settings.model_name, settings.ai_provider)

    base_url = _resolve_base_url(settings)  # lmstudio_base_url or ollama_base_url etc.

    # Step 1: Fetch loaded models from /v1/models
    try:
        resp = await http_client.get(f"{base_url.rstrip('/')}/models", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        loaded = [e["id"] for e in data.get("data", []) if isinstance(e.get("id"), str)]
    except Exception as exc:
        logger.warning("Model discovery failed: %s — using MODEL_NAME=%s", exc, settings.model_name)
        return _with_provider_prefix(settings.model_name, settings.ai_provider)

    if not loaded:
        logger.warning("No models loaded at %s — using MODEL_NAME=%s", base_url, settings.model_name)
        return _with_provider_prefix(settings.model_name, settings.ai_provider)

    # Step 2: Honor MODEL_PREFERRED if it's actually loaded
    preferred = settings.model_preferred or settings.model_name
    if preferred and preferred in loaded:
        logger.info("Using preferred model: %s", preferred)
        return _with_provider_prefix(preferred, settings.ai_provider)

    # Step 3: Score remaining models; pick best for "chat" task kind
    # (sentinel-core's primary use is conversational message responses)
    best = _score_best(loaded, task_kind="chat")
    if best:
        logger.info("Auto-selected model: %s (scored best for chat)", best)
        return _with_provider_prefix(best, settings.ai_provider)

    # Step 4: First loaded model as last resort
    logger.info("Using first loaded model: %s", loaded[0])
    return _with_provider_prefix(loaded[0], settings.ai_provider)


def _with_provider_prefix(model_name: str, ai_provider: str) -> str:
    if "/" in model_name:
        return model_name  # already has prefix
    if ai_provider == "ollama":
        return f"ollama/{model_name}"
    return f"openai/{model_name}"  # LM Studio, llama.cpp, generic OpenAI-compat
```

The `_score_best` function is identical to `model_selector.select_model` — reuse that logic directly.

---

## Capability Discovery: What the API Actually Returns

### LM Studio `/v1/models` [VERIFIED: existing implementation in model_selector.py]

Returns standard OpenAI-format:
```json
{
  "data": [
    {"id": "Qwen2.5-14B-Instruct-GGUF", "object": "model", ...}
  ]
}
```

LM Studio also exposes a proprietary endpoint `/api/v0/models/{model_name}` that returns `max_context_length` — this is what `get_context_window_from_lmstudio()` uses today. The `/v1/models` endpoint does NOT include context window size reliably.

### Ollama `/v1/models` [ASSUMED — not verified in this session]

Ollama's OpenAI-compatible layer exposes `/v1/models` with standard format. Context window requires a separate `POST /api/show` call.

### Capability detection via `litellm.get_model_info()`

`litellm.get_model_info(model_id)` returns `{"max_tokens": ..., "supports_function_calling": ...}` for models in LiteLLM's internal registry. For local GGUFs with names not in LiteLLM's registry (common), this returns nothing and the model scores 0 — falling through to preference/default chain. [VERIFIED: model_selector.py comment + tests in test_model_selector.py]

**Context window for the active model after discovery:**

The existing `get_context_window_from_lmstudio()` function uses the proprietary `/api/v0/models/{name}` endpoint and requires the specific model name. After discovery resolves the name, this call still works — it just gets called with the discovered name rather than the static env var. No change to that logic needed.

---

## Pitfalls and Gotchas

### 1. LiteLLM provider prefix requirement
LiteLLM errors with "LLM Provider NOT provided" when the model string has no provider prefix (e.g., `Qwen2.5-14B` vs `openai/Qwen2.5-14B`). The `resolve_model.py` pattern handles this with an `if "/" in chosen` guard. Apply the same guard everywhere. [VERIFIED: resolve_model.py line 37-38]

### 2. LM Studio loads one model at a time; `/v1/models` returns only that one
In practice LM Studio returns a list with a single entry. Discovery degenerates to "use whatever is loaded." The scoring rubric still works — it just scores one model. The important case is when LM Studio is in multi-model mode (LM Studio 0.3+) or when the user switches models between sessions.

### 3. Empty model list on cold start
If discovery runs before LM Studio has finished loading a model, `/v1/models` returns `{"data": []}`. The fallback to `settings.model_name` prevents a crash but the caller won't know if `model_name` is actually what's loaded. Log a clear warning. Don't make discovery fatal — non-fatal is the existing contract for `build_model_registry`.

### 4. `/api/v0/` is LM Studio proprietary
The context-window fetch uses `/api/v0/models/{name}` — this endpoint does NOT exist on Ollama or llama.cpp. When the `ai_provider` is not `lmstudio`, skip this fetch and use seed data or a configurable default. The current code already guards this with `if settings.ai_provider == "lmstudio"` in `build_model_registry`. Keep that guard.

### 5. Model name encoding in LM Studio
LM Studio model IDs from `/v1/models` may include the full filename including quantization tag (e.g., `Qwen2.5-14B-Instruct-Q4_K_M.gguf`), but the `/api/v0/models/{name}` endpoint may use a different name format. Test both. The existing `get_context_window_from_lmstudio()` already handles the 5-second timeout + 4096 fallback gracefully.

### 6. Sentinel-core `LiteLLMProvider` is constructed once at startup
The model string is baked into the `LiteLLMProvider.__init__` at lifespan startup. There is no hot-reload mechanism. If the user switches models in LM Studio, sentinel-core continues using the old model string until restart. This is acceptable for v0.x — document it. A future improvement would be to make `LiteLLMProvider` resolve the model lazily per call, but that's a larger refactor.

### 7. Pathfinder's `model_selector` is not reachable from sentinel-core's Docker build context
The 260423-mdl SUMMARY.md explicitly documents this: `modules/pathfinder/` build context does not include `shared/`, so `model_selector.py` cannot be imported from sentinel-core. The options are:
  - Duplicate the ~145-LOC `model_selector.py` into `sentinel-core/app/services/`
  - Restructure build contexts to include a `shared/` layer (larger scope)
  
For a quick task, duplication into `sentinel-core/app/services/` is the right call.

---

## Implementation Touchpoints

The following files need changes to implement model-agnostic discovery end-to-end:

| File | Change | Size |
|------|--------|------|
| `sentinel-core/app/config.py` | Add `model_auto_discover`, `model_preferred`, `model_task_chat/structured/fast` fields | +5 lines |
| `sentinel-core/app/services/model_selector.py` | **New file** — copy from `modules/pathfinder/app/model_selector.py` verbatim (or symlink if build context allows, but it doesn't) | ~145 LOC |
| `sentinel-core/app/services/model_registry.py` | Replace static `settings.model_name` lookup with result of `discover_active_model()` call in `_fetch_lmstudio()` | ~20 lines changed |
| `sentinel-core/app/main.py` lifespan | Replace `f"openai/{settings.model_name}"` with `await discover_active_model(settings, http_client)` for all 4 `LiteLLMProvider` instantiations in `_provider_map` | ~10 lines changed |
| `sentinel-core/tests/test_model_registry.py` | Add tests for discovery path (mock `/v1/models` response, verify discovered name used) | ~30 lines |

**Files NOT touched:**
- `modules/pathfinder/app/model_selector.py` — source of truth for the algorithm; do not modify it, just copy to sentinel-core
- `clients/litellm_provider.py` — no change; it already accepts any model string
- `services/provider_router.py` — no change; routing is model-agnostic already

---

## Sources

- [VERIFIED: codebase] `sentinel-core/app/main.py` — startup provider instantiation
- [VERIFIED: codebase] `sentinel-core/app/config.py` — current Settings fields
- [VERIFIED: codebase] `sentinel-core/app/services/model_registry.py` — current discovery logic
- [VERIFIED: codebase] `sentinel-core/app/clients/litellm_provider.py` — model string format
- [VERIFIED: codebase] `modules/pathfinder/app/model_selector.py` — working discovery + scoring implementation
- [VERIFIED: codebase] `modules/pathfinder/app/resolve_model.py` — provider prefix pattern
- [VERIFIED: codebase] `modules/pathfinder/app/config.py` — per-task-kind preference env vars
- [VERIFIED: codebase] `.planning/quick/260423-mdl-llm-model-selector-registry-aware/SUMMARY.md` — Docker build context constraint documented
- [ASSUMED] Ollama exposes `/v1/models` in OpenAI-compatible format — not tested in this session
