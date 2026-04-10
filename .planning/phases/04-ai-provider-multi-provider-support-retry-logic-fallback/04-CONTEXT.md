# Phase 4: AI Provider — Context

**Gathered:** 2026-04-10
**Status:** Ready for research and planning

<domain>
## Phase Boundary

Provider configuration via env vars. Multiple AI providers switchable. Retry logic and fallback. Model registry.

This phase makes the AI backend swappable without code changes — only env vars change.

Out of scope: Pi harness changes, Obsidian changes, Discord changes.
</domain>

<decisions>
## Implementation Decisions

### Provider Abstraction
- **Pattern:** `typing.Protocol` defining `AIProvider` interface in `app/clients/base.py`
- **Implementation:** One `LiteLLMProvider` class wraps `litellm.acompletion()` — replaces `LMStudioClient` entirely
- **Why LiteLLM:** Normalizes LM Studio, Claude, Ollama, llama.cpp, and 100+ more to one call. No need for individual clients per provider.
- **Critical:** Pin exact LiteLLM version post-March 2026 supply chain incident (versions 1.82.7–1.82.8 were malicious). Verify safe version before adding to requirements.
- **Boundary:** `LiteLLMProvider` implements `AIProvider` Protocol — LiteLLM stays behind the interface, swappable if needed.

### Provider Selection
- **Primary provider:** `AI_PROVIDER=lmstudio|claude|ollama|llamacpp` env var
- **Fallback provider:** `AI_FALLBACK_PROVIDER=claude|none` env var  
- All provider connection details configured simultaneously via separate env vars:
  - `LMSTUDIO_BASE_URL`, `LMSTUDIO_API_KEY` (already exists)
  - `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` (new, default `claude-haiku-4-5`)
  - `OLLAMA_BASE_URL`, `OLLAMA_MODEL` (new — Linux workstation LAN IP)
  - `LLAMACPP_BASE_URL`, `LLAMACPP_MODEL` (new — stub only)
- At startup, Core instantiates all configured providers. `AI_PROVIDER` selects which is active.

### Retry Logic
- **Library:** `tenacity` (not hand-rolled, not httpx transport retry)
- **Why tenacity:** Handles 429 `Retry-After` headers, jitter, async-safe `@retry` decorator
- **Placement:** Inside the `LiteLLMProvider.complete()` method (per-client, not shared wrapper)
- **Policy:** 3 attempts, exponential backoff (1s→2s→4s), reraise on exhaustion
- **Retryable:** `litellm.RateLimitError`, `litellm.ServiceUnavailableError`, connection errors
- **Fatal (no retry):** 401, 422, 404 — propagate immediately

### Fallback Routing
- **Trigger:** ConnectError or timeout after all retries exhausted — NOT on HTTP 4xx/5xx responses
- **Behavior:** Try primary (with retries) → if unreachable, try fallback (with retries)
- **Both fail:** Return HTTP 503 with detail explaining both failed. Log both at ERROR level.
- **No fallback configured:** HTTP 503 immediately after primary exhausted.

### Model Registry
- **Pattern:** Hybrid — fetch live from provider API at startup, static seed JSON as fallback
- **Per-provider fetch:**
  - Claude: `GET /v1/models` → `max_input_tokens` + capability flags (verified API)
  - LM Studio: existing `GET /api/v0/models/{model}` at startup (already implemented)
  - Ollama: `POST /api/show` → `model_info.llama.context_length` (training max)
  - llama.cpp: `GET /props` → `n_ctx` (runtime configured value)
- **Seed file:** `sentinel-core/models-seed.json` — known models with context window + capability flags
- **Failure behavior:** Registry fetch failure is non-fatal — log warning, use seed fallback
- **Storage:** `app.state.model_registry` — accessible to all routes

### Ollama / llama.cpp Stubs
- **Ollama is preferred** over raw llama.cpp (Ollama IS llama.cpp + Docker + API management)
- **Target hardware:** Linux workstation with Nvidia A2000 (12GB VRAM, Ampere arch, compute 8.6)
- **Docker setup:** `ollama/ollama` image with `deploy.resources.reservations.devices` (nvidia-container-toolkit required on host)
- **Model recommendation:** Qwen 2.5 14B Q4_K_M (~10-11GB VRAM) for conversational use
- **Connection:** `OLLAMA_BASE_URL=http://<linux-workstation-lan-ip>:11434`
- **Binding gotcha:** Set `OLLAMA_HOST=0.0.0.0` in Ollama container for cross-machine access
- **Stub behavior:** `OllamaProvider.complete()` raises `NotImplementedError` with helpful message. Config vars defined. `AI_PROVIDER=ollama` works at startup, fails gracefully on first call.
- **llama.cpp:** Same approach — `LlamaCppProvider` stub. OpenAI-compatible (`api_base` → llama-server endpoint).

### Claude API Integration
- **Library:** `anthropic` SDK (not raw httpx) — handles mandatory `anthropic-version` header, response format differences, automatic retry on 429
- **Why SDK over httpx:** Claude API differs from OpenAI format: `system` is top-level not a message role, `max_tokens` is required, response is `content[0].text` not `choices[0].message.content`
- **Model:** `CLAUDE_MODEL` env var, default `claude-haiku-4-5` — runtime configurable
- **Available options:** `claude-haiku-4-5` (fast/cheap), `claude-sonnet-4-5`, `claude-sonnet-4-6` (stronger reasoning)
- **SDK version pinning:** `anthropic>=0.93.0,<1.0` in requirements

### Claude's Discretion
- Retry backoff specifics (exact multiplier, jitter) — use tenacity defaults
- `models-seed.json` initial content — populate with Qwen 2.5 14B, Claude Haiku, Claude Sonnet
- Factory function vs DI pattern for provider instantiation at startup — Claude picks most idiomatic for existing FastAPI lifespan pattern
- Whether to keep `LMStudioClient` as a legacy alias or delete it — delete it, replace entirely with `LiteLLMProvider`
</decisions>

<canonical_refs>
## Canonical References

- `sentinel-core/app/clients/lmstudio.py` — existing client being replaced
- `sentinel-core/app/clients/obsidian.py` — pattern for client structure
- `sentinel-core/app/config.py` — Settings class to extend with new env vars
- `sentinel-core/app/main.py` — lifespan function where providers are instantiated
- `sentinel-core/app/routes/message.py` — where `lm_client.complete()` is called (update to use AIProvider)
- REQUIREMENTS.md: PROV-01, PROV-02, PROV-03, PROV-04, PROV-05
- LiteLLM docs: https://docs.litellm.ai/docs/completion/input
- Anthropic API docs: https://platform.claude.com/docs/en/api/messages
- tenacity docs: https://tenacity.readthedocs.io/
</canonical_refs>

<deferred>
## Deferred Ideas

- **vLLM:** Production GPU serving for high-concurrency use. Overkill for single-user personal AI. Add if usage patterns change.
- **LiteLLM Proxy server (Docker sidecar):** More infrastructure complexity than needed. Library-mode is sufficient.
- **OpenAI API:** Could add as a stub alongside Claude, but omitted — Claude is the cloud provider of choice.
- **Streaming responses:** LiteLLM and Anthropic SDK both support streaming. Not in Phase 4 scope.
- **GPU workstation full setup:** Compose service for Ollama on Linux workstation — infrastructure work, not Sentinel Core code. Document in ops notes.
</deferred>
