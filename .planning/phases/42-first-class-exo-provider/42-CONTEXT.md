# Phase 42: First-Class exo Provider - Context

**Gathered:** 2026-07-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Restore the intended **"everything through Sentinel"** architecture for the LLM **chat/completion** path, and make exo a first-class provider alongside LM Studio inside the existing Phase 4 framework (`AIProvider` / `LiteLLMProvider` / `ProviderRouter` / `ModelRegistry`).

**North-star (architectural principle, per owner):** Sentinel core is the single AI gateway. Domain modules (pf2e, etc.) own their local logic and **hand off all AI work to core**. The `LITELLM_*` config and direct exo calls currently living inside pf2e-module are **drift** from this design and are corrected here (for chat).

**In scope:**
- A generic `openai_compatible` provider type; **migrate BOTH exo AND LM Studio onto it** in this phase.
- Explicit provider selection via `ai_provider` (config-only switching, no code edit — Phase 4 parity).
- Generalized fallback: any provider ↔ any provider (not Claude-only), with model `NotFoundError`/404 as a fallback trigger in addition to `ConnectError`/`Timeout`.
- exo-aware model resolution via exo `GET /state` (running instances), not `/v1/models`.
- pf2e-module hands its **chat/completions** off to sentinel-core; remove pf2e's direct chat litellm config + hardcoded model default.
- Remove the debug-time `LMSTUDIO_*`-hijack for exo and the hardcoded exo model default.

**Out of scope (→ Phase 43):**
- Embeddings handoff (pf2e rules RAG index) and wiring a non-exo embeddings backend. The rules index stays on graceful 503 until Phase 43.
- (Related, belongs to Phase 43) core's own Phase-40 semantic recall embeddings, which are currently broken if embedding against exo.

</domain>

<decisions>
## Implementation Decisions

### Provider modeling
- **D-01:** Introduce a generic `openai_compatible` provider type in the Phase 4 framework (parametrized base_url / model / api_key), rather than a one-off `exo` type.
- **D-02:** Migrate **both** exo and the existing LM Studio path onto `openai_compatible` in this phase ("unify now"). ⚠️ LM Studio is currently working — the plan MUST include regression coverage for the LM Studio chat path.
- **D-03:** exo gets dedicated config (e.g. `exo_base_url` / `exo_model` / `exo_api_key`) and becomes a `provider_map["exo"]` entry; `ai_provider=exo` selects it. The debug-time reuse of `lmstudio_base_url` for exo is removed.

### Provider selection
- **D-04:** Active provider chosen via the existing `ai_provider` env switch (add `exo` as a value). Switching LM Studio ↔ exo requires only a config change, no code edit.

### Fallback semantics
- **D-05:** Generalize `ai_fallback_provider` to accept **any** configured provider (enable exo ↔ lmstudio), not just `claude`/`none`.
- **D-06:** Add model **`NotFoundError`/404 as a fallback trigger** alongside `ConnectError`/`TimeoutException` in `ProviderRouter`. (exo's real failure mode is a 404, so ConnectError-only fallback would never fire for it.)

### Model resolution (exo)
- **D-07:** Resolve exo's model via exo **`GET /state`** (currently-loaded running instance), NOT `/v1/models` (exo advertises ~120 models but serves only the loaded one — the root cause of the `exo-model-notfound-502` bug).
- **D-08:** On **zero loaded instances**: trigger fallback per D-05/D-06; if no fallback is configured, raise a clear "exo has no loaded model" error. **Never guess a model / never pick `catalog[0]`.** (Preserves the `model_selector.select_model()` hardening.)

### pf2e-module (chat handoff)
- **D-09:** pf2e-module delegates its **chat/completions** to a sentinel-core provider-completion endpoint (core = single AI gateway). Remove pf2e's own direct chat litellm config + hardcoded model default.
- **D-10:** Accept a pf2e→core runtime dependency for chat (largely already present via compose `depends_on: sentinel-core healthy`).

### Claude's Discretion
- Exact `openai_compatible` config schema/field names, the shape of core's provider-completion endpoint that pf2e calls, and how `/state` discovery feeds `select_model()` — left to research/planning, provided the decisions above hold.
- Naming of the new provider type key and settings fields (research to align with existing `ai_provider` value conventions).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provider framework (sentinel-core — the code being extended)
- `sentinel-core/app/composition.py` — `build_provider_router()` (~lines 113–237); `ProviderRouter(primary, fallback)` instantiation at **line 225**; the `provider_map` assembly + `settings.ai_provider` primary selection. **This is the central wiring site.**
- `sentinel-core/app/services/provider_router.py` — `ProviderRouter` (lines 29–88): primary+fallback, current fallback triggers (`ConnectError`/`Timeout` only), `ProviderUnavailableError`. Generalize here (D-05/D-06).
- `sentinel-core/app/clients/litellm_provider.py` — `LiteLLMProvider(model_string, api_base, api_key)` (lines 55–127): `openai/<model>` prefixing, `api_base` passthrough, retry/timeout. Reused for `openai_compatible`.
- `sentinel-core/app/services/model_selector.py` — `select_model()` 6-rule selector (recently hardened in `exo-model-notfound-502`); `discover_active_model()`. `/state` discovery (D-07) feeds this.
- `sentinel-core/app/services/model_registry.py` — `build_model_registry()` / `ModelInfo` (model discovery is inline, no distinct ModelRegistry class).
- `sentinel-core/app/config.py` — `Settings` provider/model fields: `ai_provider`, `ai_fallback_provider`, `lmstudio_base_url`, `model_name`, `model_preferred`, `model_auto_discover`, `model_task_*`, `ollama_*`, `llamacpp_*`, `anthropic_api_key`, `claude_model`, `embedding_model`.

### pf2e-module (the drift being corrected — chat path)
- `modules/pathfinder/app/config.py` — pf2e's `LITELLM_API_BASE` / `LITELLM_MODEL` config (to remove for chat).
- `modules/pathfinder/app/main.py` — `_build_rules_index_safely()` (embeddings path — leave on graceful 503; belongs to Phase 43) and the chat/generation call sites (to route through core).
- `modules/pathfinder/app/model_selector.py` — pf2e's own model selection (drift).

### Roadmap + exo behavior
- `.planning/ROADMAP.md` — Phase 42 (this phase) + **Phase 4: AI Provider** detail (the framework's original success criteria, incl. env-var switchability + auto-fallback).
- `.planning/debug/resolved/lmstudio-provider-switch.md` — the LM Studio→exo cutover + graceful-degradation pattern.
- `.planning/debug/exo-model-notfound-502.md` — exo runtime behavior (advertises 120, serves 1; `GET /state`; 404 NotFound failure mode) and the selector hardening.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `LiteLLMProvider(model_string, api_base, api_key)`: already the right abstraction for any OpenAI-compatible backend (`openai/` prefix + `api_base`). exo and LM Studio both become instances of it under `openai_compatible`.
- `provider_map` construction in `build_provider_router()`: the extension point — add `openai_compatible` instances keyed by `ai_provider`.
- `ProviderRouter`: already does primary+fallback; needs (a) generalized fallback provider selection and (b) an additional NotFound trigger.
- `select_model()` 6-rule selector: already hardened against arbitrary `catalog[0]`; `/state` discovery plugs into its "loaded models" input.

### Established Patterns
- Per-provider settings triplet pattern (`ollama_base_url`/`ollama_model`, `llamacpp_base_url`/`llamacpp_model`) — `exo_*` follows it.
- Env-var-only provider switching (`ai_provider`) — Phase 4 contract to preserve.
- Graceful-degradation on missing capability (`_build_rules_index_safely()` → 503) — the embeddings path stays on this until Phase 43.

### Integration Points
- `composition.py:225` — where the router (and thus the new `openai_compatible` providers + generalized fallback) is assembled.
- A new/renamed sentinel-core provider-completion endpoint that pf2e-module calls for chat (replaces pf2e's direct exo call).
- exo `GET /state` — new outbound call from core's model discovery.

</code_context>

<specifics>
## Specific Ideas

- exo endpoint: `http://host.docker.internal:52415/v1` (from containers) / `http://localhost:52415/v1` (from host); OpenAI-compatible; litellm model string `openai/mlx-community/<Model>`.
- exo's only serveable model is whatever `GET /state` reports as the loaded instance (e.g. `mlx-community/Qwen3.5-27B-8bit` during the debug sessions); `/v1/models` lists ~120 non-serveable ids.
- Owner's design intent quote: *"the design was everything goes through the sentinel (hence the name) but something drifted and put it in pf2e. pf2e is supposed to handle the local logic and hand off to sentinel."*

</specifics>

<deferred>
## Deferred Ideas

- **Phase 43 — Embeddings handoff + non-exo embeddings backend:** pf2e-module hands embeddings/retrieval for its rules RAG index off to core; wire a real embeddings-capable provider (LM Studio embed model / Ollama nomic / dedicated endpoint — NOT exo) so the rules index works again. Same work also **fixes core's own Phase-40 semantic recall**, which is currently broken if embedding against exo (exo has no `/v1/embeddings`). This was split out of Phase 42 because it needs an embeddings-backend decision independent of the chat-provider work.
- **LM Studio path regression risk:** unifying LM Studio onto `openai_compatible` (D-02) puts the currently-working LM Studio chat path in the blast radius — flagged for explicit regression coverage, not a separate phase.

</deferred>

---

*Phase: 42-first-class-exo-provider*
*Context gathered: 2026-07-05*
