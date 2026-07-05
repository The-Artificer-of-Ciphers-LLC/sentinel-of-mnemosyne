# Phase 42: First-Class exo Provider - Research

**Researched:** 2026-07-05
**Domain:** Multi-provider LLM gateway (LiteLLM-based), cross-service (Python FastAPI monorepo) chat handoff
**Confidence:** HIGH (codebase-verified for all sentinel-core/pf2e-module findings; HIGH for exo's `/state` contract via direct source read of exo-explore/exo; MEDIUM for exact wire-format of `/state`'s camelCase serialization — recommend a live smoke-test task before hardening parse code)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Provider modeling**
- **D-01:** Introduce a generic `openai_compatible` provider type in the Phase 4 framework (parametrized base_url / model / api_key), rather than a one-off `exo` type.
- **D-02:** Migrate **both** exo and the existing LM Studio path onto `openai_compatible` in this phase ("unify now"). LM Studio is currently working — the plan MUST include regression coverage for the LM Studio chat path.
- **D-03:** exo gets dedicated config (e.g. `exo_base_url` / `exo_model` / `exo_api_key`) and becomes a `provider_map["exo"]` entry; `ai_provider=exo` selects it. The debug-time reuse of `lmstudio_base_url` for exo is removed.

**Provider selection**
- **D-04:** Active provider chosen via the existing `ai_provider` env switch (add `exo` as a value). Switching LM Studio ↔ exo requires only a config change, no code edit.

**Fallback semantics**
- **D-05:** Generalize `ai_fallback_provider` to accept **any** configured provider (enable exo ↔ lmstudio), not just `claude`/`none`.
- **D-06:** Add model **`NotFoundError`/404 as a fallback trigger** alongside `ConnectError`/`TimeoutException` in `ProviderRouter`. (exo's real failure mode is a 404, so ConnectError-only fallback would never fire for it.)

**Model resolution (exo)**
- **D-07:** Resolve exo's model via exo **`GET /state`** (currently-loaded running instance), NOT `/v1/models` (exo advertises ~120 models but serves only the loaded one — the root cause of the `exo-model-notfound-502` bug).
- **D-08:** On **zero loaded instances**: trigger fallback per D-05/D-06; if no fallback is configured, raise a clear "exo has no loaded model" error. **Never guess a model / never pick `catalog[0]`.**

**pf2e-module (chat handoff)**
- **D-09:** pf2e-module delegates its **chat/completions** to a sentinel-core provider-completion endpoint (core = single AI gateway). Remove pf2e's own direct chat litellm config + hardcoded model default.
- **D-10:** Accept a pf2e→core runtime dependency for chat (largely already present via compose `depends_on: sentinel-core healthy`).

### Claude's Discretion
- Exact `openai_compatible` config schema/field names, the shape of core's provider-completion endpoint that pf2e calls, and how `/state` discovery feeds `select_model()` — left to research/planning, provided the decisions above hold.
- Naming of the new provider type key and settings fields (research to align with existing `ai_provider` value conventions).

### Deferred Ideas (OUT OF SCOPE)
- **Phase 43 — Embeddings handoff + non-exo embeddings backend:** pf2e-module hands embeddings/retrieval for its rules RAG index off to core; wire a real embeddings-capable provider (LM Studio embed model / Ollama nomic / dedicated endpoint — NOT exo) so the rules index works again. Same work also fixes core's own Phase-40 semantic recall, which is currently broken if embedding against exo (exo has no `/v1/embeddings`).
- **LM Studio path regression risk:** unifying LM Studio onto `openai_compatible` (D-02) puts the currently-working LM Studio chat path in the blast radius — flagged for explicit regression coverage, not a separate phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

No REQ-IDs are assigned yet (CONTEXT.md marks requirements TBD; a `PRV-*` family is proposed but not finalized). Anchor planning to ROADMAP.md's Phase 42 success criteria instead:

| Anchor ID | Description (ROADMAP.md Phase 42 Success Criteria) | Research Support |
|-----------|------------------------------------------------------|------------------|
| SC-1 | exo configured through dedicated env vars (`EXO_BASE_URL`/`EXO_MODEL`/`EXO_API_KEY`), no `LMSTUDIO_*` overload; LM Studio + exo configurable simultaneously | Standard Stack §Config fields; Architecture Patterns §Pattern 1 |
| SC-2 | Active provider selected explicitly via `ai_provider`; switching requires config only, no code edit | Architecture Patterns §Pattern 1; Common Pitfalls §1–2 |
| SC-3 | `ProviderRouter` falls back LM Studio ↔ exo on unreachability (ROADMAP says "ConnectError-only" — **superseded by CONTEXT D-06**, which adds `NotFoundError`) | Code Examples §1; Common Pitfalls §3 |
| SC-4 | Hardcoded exo model default removed; model resolves from config/catalog; unavailable/misconfigured model surfaces a clear error, never `catalog[0]` | Code Examples §2; `model_selector.select_model()` (already hardened, see Existing Code Insights) |
| SC-5 | exo's OpenAI-compatible quirks handled: embeddings-dependent paths degrade gracefully (existing pattern, Phase 43 concern); litellm model string uses `openai/` prefix for the custom base | Architecture Patterns §Pattern 1 |
| SC-6 | Both sentinel-core and pf2e-module resolve provider/model through unified configuration — no module hardcodes an endpoint or model id | Architecture Patterns §Pattern 2 (pf2e→core handoff); Open Questions §1 |

Note: ROADMAP.md's Phase 42 entry predates the 42-CONTEXT.md discuss-phase session and does not yet reflect D-01/D-02 (generic `openai_compatible` unifying LM Studio too) or D-09/D-10 (pf2e chat handoff to core) — those are the more specific, later-locked decisions and take precedence over the ROADMAP prose where they differ.
</phase_requirements>

## Summary

This phase closes out debt from two recent live-incident debug sessions (`lmstudio-provider-switch`, `exo-model-notfound-502`) by promoting exo from a debug-time hack (borrowed `LMSTUDIO_*` env vars, hardcoded model default) into a proper peer of LM Studio inside the Phase-4 provider framework, and by correcting an architectural drift where pf2e-module was calling litellm directly instead of routing chat through sentinel-core.

The codebase-verified reality is more nuanced than the CONTEXT.md canonical refs alone suggest: `build_provider_router()` in `composition.py` and `discover_active_model()`/`build_model_registry()` in `model_selector.py`/`model_registry.py` currently have **provider-name-keyed branches that silently omit exo** even where exo would otherwise "just work" as an OpenAI-compatible backend. Concretely: (1) the `active_model` ternary chain in `composition.py:143-151` has no `exo` arm and falls through to `settings.llamacpp_model`; (2) `discover_active_model()`'s `base_url` lookup dict (`model_selector.py:247-251`) has no `"exo"` key and silently defaults to `settings.lmstudio_base_url`; (3) the model-profile/stop-sequence fetch in `build_provider_router()` (`composition.py:164-183`) is hardcoded to `settings.lmstudio_base_url` regardless of active provider. All three must be generalized, not just extended with an `if ai_provider == "exo"` patch, or the next new provider will reproduce the same gap.

litellm 1.83.4 is confirmed installed and pinned (`litellm>=1.83.0,<2.0`); `litellm.NotFoundError` (aka `litellm.exceptions.NotFoundError`) is a real, stable, top-level-importable exception class raised whenever any provider's HTTP response — including the generic `openai`/openai-compatible path used for LM Studio and exo — is a 404. This directly satisfies D-06.

exo's `GET /state` contract was resolved by reading exo-explore/exo's actual Pydantic source (not just prose docs, which are sparse): `state.instances` is a `Mapping[InstanceId, Instance]` where each `Instance` is a **tagged union** serialized as `{"MlxRingInstance": {...}}` or `{"MlxJacclInstance": {...}}`, and the currently-loaded model id lives at `<tag>.shardAssignments.modelId` (camelCase on the wire, via `alias_generator=to_camel`). Zero running instances serializes as `"instances": {}` — this exactly matches the debug session's captured evidence.

On the pf2e side: pf2e-module has **zero existing code path that calls sentinel-core** for anything (no `SentinelCoreClient` import found anywhere in `modules/pathfinder/app/`). All ~13 `acompletion_with_profile`/`litellm.acompletion` call sites in `app/llm.py`, `app/foundry.py`, and `app/pf_npc_extract.py` call litellm directly against `settings.litellm_api_base`. Core has no existing lightweight completion-only endpoint — `/message` is the full memory/recall/injection-filter/output-scanner pipeline and is the wrong shape for pf2e's per-NPC or per-ruling prompts. A new, narrow endpoint must be added to core, and `RouteContext` must be extended to expose the `ProviderRouter` (it currently only exposes `processor` and `ai_provider_name`, not the router itself).

**Primary recommendation:** Generalize the three provider-name-branch points in `composition.py`/`model_selector.py`/`model_registry.py` into a single table-driven `openai_compatible` backend registry (keyed by provider name → `{base_url, model_field, api_key, discovery_strategy}`), reusing `LiteLLMProvider` unchanged for the actual completion call; give exo a `/state`-based discovery function distinct from LM Studio's `/v1/models`-based one; add `litellm.NotFoundError` to `ProviderRouter`'s fallback triggers; and add one new narrow `POST /provider/complete`-style endpoint on sentinel-core (auth already covered by the existing global `X-Sentinel-Key` middleware) that pf2e-module calls via a new thin client (either a new method on the existing `shared.sentinel_client.SentinelCoreClient`, or its already-generic `post_to_module()` — see Open Questions §2).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Provider selection (`ai_provider` → primary instance) | API / Backend (sentinel-core `composition.py`) | — | Single gateway design; only core constructs `LiteLLMProvider` instances |
| Fallback routing (primary→fallback on error) | API / Backend (`ProviderRouter`) | — | Router already owns this; generalizing scope only, not tier |
| exo model discovery (`GET /state`) | API / Backend (sentinel-core `model_selector.py`) | — | New outbound call from core's startup/model-registry path, not pf2e |
| Chat/completion request composition (system+user prompts) | API / Backend — for the *shared* completion primitive | Domain module (pf2e) — for *prompt content* | pf2e still owns prompt text (NPC persona, rules-adjudicator framing); core owns "how do I reach an LLM" |
| pf2e chat handoff (dialogue, rule generation) | Domain module (pf2e) initiates | API / Backend (sentinel-core) executes | D-09: pf2e hands off; core is the only tier that talks to litellm/exo/LM Studio directly going forward (chat) |
| Embeddings / RAG retrieval (rules index) | Domain module (pf2e), unchanged | — | Explicitly OUT of scope this phase (Phase 43); stays on existing graceful-503 pattern |
| Config (env vars: `EXO_*`, `AI_PROVIDER`, `AI_FALLBACK_PROVIDER`) | API / Backend (`Settings` in `config.py`) | — | Single source of truth; pf2e no longer needs its own `LITELLM_*` chat config |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| litellm | 1.83.4 (installed; pinned `>=1.83.0,<2.0`) [VERIFIED: local `.venv` inspection] | Unified `acompletion()` across LM Studio / exo / Claude / Ollama / llama.cpp | Already the sole AI-vendor SDK import point in `app/clients/`; no new dependency needed |
| httpx | already a dependency (`>=0.28.1`) | `GET /state` outbound call, MockTransport-based tests | Already used identically for `/v1/models` discovery |
| tenacity | already a dependency (`>=8.2.0,<10.0`) | Retry wrapper on `LiteLLMProvider.complete()` | Unchanged this phase — `NotFoundError` is deliberately NOT added to the retry set (it is a fallback trigger, not a transient error) |

**No new external packages are required for this phase.** The `openai_compatible` provider type is a configuration/wiring change reusing the existing `LiteLLMProvider` class; exo is already reached via `model_string="openai/<model>"` + `api_base` (the same "openai" custom_llm_provider litellm already uses for LM Studio).

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic-settings | already a dependency (`>=2.13.0`) | New `exo_base_url`/`exo_model`/`exo_api_key` Settings fields | Same pattern as `ollama_base_url`/`ollama_model` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| New `OpenAICompatibleProvider` wrapper class | Reuse `LiteLLMProvider` directly, keyed by a config table | `LiteLLMProvider(model_string, api_base, api_key)` already IS the generic OpenAI-compatible shape (D-01's own phrasing: "parametrized base_url/model/api_key"). A new class only makes sense if it must also own *discovery* behavior (see Architecture Patterns §Pattern 1) — recommend a thin discovery-strategy function per backend, not a new provider class. |
| pf2e calling `litellm.acompletion` directly (status quo) | pf2e calls a new sentinel-core completion endpoint via `shared.sentinel_client` | Status quo is exactly the drift D-09 corrects; the shared client already exists and is unused by pf2e today |

**Installation:** None — no new packages.

**Version verification:** `litellm==1.83.4` confirmed installed via `sentinel-core/.venv/lib/python3.13/site-packages/litellm-1.83.4.dist-info`, matching the `pyproject.toml` pin `litellm>=1.83.0,<2.0` (comment there already documents the 1.82.7-1.82.8 supply-chain incident — no action needed, just confirming currency). [VERIFIED: local venv + pyproject.toml inspection]

## Package Legitimacy Audit

**No new external packages are introduced by this phase.** All required capability (OpenAI-compatible HTTP client, exception classes, retry) is already present via the pinned `litellm`, `httpx`, and `tenacity` dependencies used identically by the existing LM Studio path. The Package Legitimacy Gate is not applicable — no `npm view`/`pip index versions`/registry check is required since zero new install lines are added to any `pyproject.toml`.

**Packages removed due to [SLOP] verdict:** none (N/A — no new packages evaluated)
**Packages flagged as suspicious [SUS]:** none (N/A)

## Architecture Patterns

### System Architecture Diagram

```
                     ┌─────────────────────────────────────────────┐
                     │              sentinel-core                  │
                     │  (the ONLY tier that talks to litellm/LLMs) │
                     │                                              │
  Discord/iMessage → │ POST /message ──► MessageProcessor           │
                     │                     └──► ProviderRouter      │
                     │                            (primary+fallback)│
                     │                                              │
  pf2e-module ─────► │ POST /provider/complete (NEW, this phase)    │
  (dialogue, rules)  │      └──► ProviderRouter ─────────────────┐  │
                     │                            (same router)  │  │
                     └───────────────────────────────────────────┼──┘
                                                                  │
                              ┌───────────────────────────────────┘
                              ▼
                     ┌─────────────────────┐
                     │   provider_map       │
                     │  { lmstudio: LiteLLMProvider(api_base=lmstudio_base_url) }
                     │  { exo:      LiteLLMProvider(api_base=exo_base_url) }     ← NEW
                     │  { ollama:   LiteLLMProvider(...) }
                     │  { llamacpp: LiteLLMProvider(...) }
                     │  { claude:   LiteLLMProvider(...) }
                     └─────────┬─────────────┘
                                │  primary = provider_map[settings.ai_provider]
                                │  fallback = provider_map[settings.ai_fallback_provider]  ← generalized (D-05)
                                ▼
                     ┌─────────────────────┐
                     │   ProviderRouter     │
                     │  .complete(messages) │
                     │  try primary         │
                     │  except (ConnectError, TimeoutException,
                     │          litellm.NotFoundError):  ← NEW (D-06)
                     │    try fallback                    │
                     └─────────┬────────────┘
                                │
                                ▼  litellm.acompletion(model=f"openai/{model}", api_base=..., ...)
                     ┌─────────────────────┐        ┌──────────────────┐
                     │   LM Studio          │        │   exo             │
                     │   GET /v1/models      │        │   GET /state      │◄── model discovery (D-07)
                     │   (loaded-only list)  │        │   GET /v1/models  │    (120-entry static catalog,
                     │                       │        │   (~120 catalog)  │     NOT used for discovery)
                     │   POST /v1/chat/completions      POST /v1/chat/completions
                     └─────────────────────┘        └──────────────────┘
```

### Recommended Project Structure
No new top-level modules needed. Changes land in existing files:
```
sentinel-core/app/
├── config.py                  # + exo_base_url, exo_model, exo_api_key fields
├── composition.py             # build_provider_router(): generalize active_model lookup +
│                               #   provider_map construction + fallback selection (table-driven)
├── services/
│   ├── provider_router.py     # + litellm.NotFoundError to _FALLBACK_TRIGGERS
│   ├── model_selector.py      # discover_active_model(): generalize base_url map;
│                               #   NEW: discover_active_model_exo() using GET /state
│   └── model_registry.py      # build_model_registry(): + exo branch (skip LM-Studio-only
│                               #   /api/v0/models context-window call; use model_profiles fallback)
├── routes/
│   └── provider.py            # NEW — POST /provider/complete (name TBD, see Open Questions)
├── state.py                   # RouteContext: + ai_provider field (the ProviderRouter itself)
modules/pathfinder/app/
├── config.py                  # remove litellm_model/litellm_api_base (chat-only fields);
│                               #   rules_embedding_model / embedding config stays (Phase 43)
├── llm.py, foundry.py,        # chat-shaped call sites migrate to the new core client call
│   pf_npc_extract.py          #   (scope of WHICH call sites — see Open Questions §1)
shared/
└── sentinel_client.py         # + complete() method (or reuse existing post_to_module())
```

### Pattern 1: Table-driven `openai_compatible` backend registry (generalizing D-01/D-02/D-03)

**What:** Replace the three separate provider-name branches (`active_model` ternary in `composition.py`, `base_url` dict in `discover_active_model()`, `if/elif` chain in `build_model_registry()`) with one small table mapping provider name → `{base_url, model_setting, api_key_setting, discovery_fn}`. Both `lmstudio` and `exo` become entries in this table (LM Studio's discovery stays `/v1/models`-based; exo's is `/state`-based). `ollama`/`llamacpp`/`claude` can stay as they are (they are not part of D-01/D-02's "openai_compatible" unification) or be folded in later — do not over-scope this phase.

**When to use:** Any time a new provider is selected via `ai_provider`, this table is the single place that needs a new entry — not three separate hardcoded branches.

**Example (illustrative — adapt to actual code shape):**
```python
# app/composition.py — sketch, not a literal diff
_OPENAI_COMPATIBLE_BACKENDS: dict[str, "BackendSpec"] = {
    "lmstudio": BackendSpec(
        base_url_field="lmstudio_base_url",
        model_field="model_name",           # existing generic field, unchanged
        api_key_field="lmstudio_api_key",
        discover=discover_via_v1_models,      # existing behavior
    ),
    "exo": BackendSpec(
        base_url_field="exo_base_url",        # NEW
        model_field="exo_model",              # NEW
        api_key_field="exo_api_key",          # NEW
        discover=discover_via_exo_state,      # NEW — GET /state (D-07)
    ),
}
```

**Why this matters for D-06/D-08:** `discover_via_exo_state()` returns the empty list (or raises a typed "no loaded model" condition) when `state["instances"]` is `{}` — this is what feeds `select_model()`'s `loaded` argument, preserving the existing hardened rule set (never guesses `catalog[0]`; single unambiguous entry is safe; explicit `default` beats guessing; else raise `ModelSelectorError`, which `discover_active_model`'s except-handler already treats as "fall back to configured default, never `loaded[0]`" per the `exo-model-notfound-502` fix).

### Pattern 2: pf2e→core chat handoff via a narrow completion endpoint (D-09/D-10)

**What:** Add ONE new endpoint on sentinel-core, e.g. `POST /provider/complete`, that accepts `{messages: [{role, content}], stop?: [str], temperature?: float}` and returns `{content: str, model: str}` — i.e. a thin passthrough to `ctx.ai_provider.complete(messages, stop=stop, temperature=temperature)`, NOT the full `/message` pipeline (no recall, no injection filter, no output scanner, no session-note writing — pf2e's own prompts already carry all needed context).

**When to use:** For every pf2e call site that is a pure chat/completion (not requiring core's memory features). Composing which specific pf2e call sites move in this phase is a real open question — see Open Questions §1 for the full inventory (10+ candidate call sites across `llm.py`/`foundry.py`/`pf_npc_extract.py`).

**Wiring requirement:** `RouteContext` (in `app/state.py`) currently exposes `processor` (`MessageProcessor`) and `ai_provider_name` (a string) but NOT the `ProviderRouter` itself. Add an `ai_provider: "ProviderRouter | None" = None` field, pinned in `initialize_startup()` from `graph.ai_provider` (already available — see `composition.py:381`).

**Example — pf2e-side client call (reusing the existing generic proxy method):**
```python
# shared/sentinel_client.py already has a generically-usable method:
result = await client.post_to_module(
    "provider/complete",
    {"messages": messages, "stop": stop, "temperature": 0.4},
    http_client,
)
content = result["content"]
```
`post_to_module()` already POSTs to `f"{base_url}/{path}"` with the `X-Sentinel-Key` header and raises `httpx.HTTPStatusError`/`ConnectError`/`TimeoutException` on failure (unlike `send_message()`, which swallows errors into user-facing strings) — this is the right error-propagation shape for pf2e's internal call sites, which already have their own error handling (e.g. `generate_npc_reply`'s JSON-parse-failure salvage). Its name is confusingly module-proxy-flavored, but the implementation is generic; alternatively add a dedicated `complete()` method to `SentinelCoreClient` for clarity — see Open Questions §2.

### Anti-Patterns to Avoid
- **Per-provider `if ai_provider == "exo":` patches sprinkled across 3 files:** This is exactly the shape of bug that caused `exo-model-notfound-502`'s root cause (a provider silently falling through to the wrong default). Use the table-driven registry (Pattern 1) instead.
- **Routing pf2e's embeddings-dependent calls through the new core endpoint:** Embeddings/RAG retrieval stay local to pf2e per CONTEXT.md's explicit Phase-43 deferral — the new endpoint is chat/completion-only.
- **Making the new core endpoint call `MessageProcessor`/`Recall`:** That reintroduces memory-assembly overhead and cross-contaminates pf2e's per-NPC/per-ruling context with the operator's own Discord memory — architecturally wrong for a "the domain module owns its local logic" design.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OpenAI-compatible HTTP client for exo | A bespoke exo HTTP client | `LiteLLMProvider` (already exists, unchanged) | exo IS OpenAI-compatible for `/v1/chat/completions`; litellm's `openai/` custom-provider path already works (confirmed via debug session curl evidence: 200 on `/v1/chat/completions`) |
| Detecting "model not found" | String-matching response bodies | `litellm.NotFoundError` (confirmed importable, raised for ANY provider's 404 via `exception_mapping_utils.py`'s generic `status_code == 404` branch) | Already the vendor-normalized signal; string-matching is what `_is_context_length_error()` does for a DIFFERENT problem (context length) precisely because litellm doesn't have a typed exception for that — NotFoundError already exists, so no string-matching needed here |
| Parsing exo's `/state` JSON | Regex/substring scanning of the response | Structural walk: `state["instances"].values()` → unwrap the tagged-union key (`"MlxRingInstance"` or `"MlxJacclInstance"`) → `["shardAssignments"]["modelId"]` | The shape is a well-defined (if externally-documented-only-in-source) Pydantic schema; a structural walk survives exo API version bumps better than string scraping |

**Key insight:** Nothing in this phase requires new HTTP client code or new exception-handling primitives — the entire "generalize" mandate (D-01 through D-08) is about *wiring* existing primitives (`LiteLLMProvider`, `litellm.NotFoundError`, `ProviderRouter`) into a provider-name-agnostic table, not building new abstractions.

## Runtime State Inventory

Not applicable — this is a wiring/feature phase, not a rename/refactor/migration phase. No stored data, live-service config, OS-registered state, or build artifacts carry a name that changes here. (`exo_*` are brand-new config keys, not renames of existing keys — `lmstudio_base_url` etc. are untouched.)

## Common Pitfalls

### Pitfall 1: `active_model` ternary chain silently defaults to the wrong provider for any unlisted `ai_provider` value
**What goes wrong:** `composition.py:143-151`'s if/elif-as-ternary chain (`lmstudio_model_name if ai_provider=="lmstudio" else claude_model if =="claude" else ollama_model if =="ollama" else llamacpp_model`) has no `exo` arm. Setting `AI_PROVIDER=exo` today would resolve `active_model = settings.llamacpp_model` — completely wrong, and used for the context-window registry lookup (wrong/missing context window, not a crash, so it's silently wrong rather than loudly broken).
**Why it happens:** Provider support was added incrementally (Phase 4: lmstudio/claude/ollama/llamacpp) with each new provider requiring a new `elif`; exo was bolted on afterward via env-var reuse (the `lmstudio-provider-switch` incident) without ever touching this chain.
**How to avoid:** Replace with a dict lookup keyed by `settings.ai_provider`, built from the same table as Pattern 1, with an explicit `.get(provider, <safe default>)` and a WARNING log if the key is missing (not a silent fallback to an arbitrary other provider's model name).
**Warning signs:** Context window logged at startup doesn't match the actually-active model; `models-seed.json`/registry entries silently missing for exo.

### Pitfall 2: `discover_active_model()`'s base_url map has the identical gap
**What goes wrong:** `model_selector.py:247-251`'s `{"lmstudio":..., "ollama":..., "llamacpp":...}.get(settings.ai_provider, settings.lmstudio_base_url)` defaults to `lmstudio_base_url` for `ai_provider="exo"` — meaning exo model discovery would silently query LM Studio's endpoint instead of exo's, discovering LM Studio's loaded model (or nothing, if LM Studio isn't running) instead of exo's.
**Why it happens:** Same incremental-branch-growth pattern as Pitfall 1, compounded by this being a DIFFERENT function than the one in composition.py (two places drifted independently).
**How to avoid:** Same table-driven fix as Pattern 1 — one source of truth for provider→base_url, consumed by both `composition.py` and `model_selector.py`.
**Warning signs:** exo model discovery logs show LM Studio's base_url, or return an empty list even when exo has an instance running.

### Pitfall 3: The model-profile/stop-sequence fetch is unconditionally hardcoded to `lmstudio_base_url`
**What goes wrong:** `composition.py:164-183`'s `lmstudio_api_base = settings.lmstudio_base_url or "http://host.docker.internal:52415"` is used for the stop-sequence/model-profile fetch (`get_profile(...)`) REGARDLESS of `settings.ai_provider`. When `ai_provider=exo` and `lmstudio_base_url` still points at a real LM Studio instance (D-02 requires BOTH to be independently configurable), this queries the wrong backend for stop sequences — degraded (not crashing, since it's already wrapped in try/except) but silently wrong model-family stop tokens.
**Why it happens:** This code predates exo entirely; the variable name `lmstudio_api_base` was never generalized when exo was bolted on.
**How to avoid:** Use the SAME table-driven base_url resolution as Pitfalls 1–2 for this fetch too — it must follow the active provider, not always LM Studio.
**Warning signs:** Wrong/missing stop sequences causing runaway generation or premature truncation on exo models; the log line `"Model stop sequences: ... (arch: ...)"` shows an LM-Studio-family arch even when running against exo.

### Pitfall 4: exo has no LM-Studio-style `/api/v0/models/{id}` context-window endpoint
**What goes wrong:** `model_registry.py::_fetch_lmstudio()` calls `get_context_window_from_lmstudio()`, which hits `{api_base}/api/v0/models/{model_name}` — an LM Studio-specific REST extension. exo does not implement this path (unconfirmed definitively in this research pass, flagged as [ASSUMED] — exo's documented endpoints per `docs/api.md` are `/node_id`, `/state`, `/events`, `/instance*`, `/models`, `/v1/models`, `/v1/chat/completions`, image endpoints — no `/api/v0/*` namespace was found in the fetched source tree).
**Why it happens:** `_fetch_lmstudio` was written LM-Studio-specific before exo existed as a target.
**How to avoid:** Add an exo-specific registry-fetch function that skips the `/api/v0/models/{id}` call entirely and falls straight to the existing `model_profiles` family-based context-window inference (the same fallback `_fetch_lmstudio` already uses when its primary fetch returns the sentinel 4096 value) — do not attempt the LM-Studio-only endpoint against exo.
**Warning signs:** A 404 (or exception, non-fatal) logged for every exo startup at the context-window-fetch step; context window falls back to a possibly-wrong `model_profiles` family guess or the 4096 conservative default for large local models.

### Pitfall 5: LM Studio chat-path regression (D-02's explicit risk)
**What goes wrong:** Migrating LM Studio onto the same `openai_compatible` table-driven construction as exo could change its `model_string`/`api_base`/`api_key` assembly subtly (e.g. losing the `"lmstudio"` literal `api_key` currently passed, or changing which discovery function fires) and silently break the currently-working LM Studio path.
**Why it happens:** Any refactor of a working path carries regression risk; explicitly flagged by the user in CONTEXT.md D-02.
**How to avoid:** Keep a REGRESSION TEST that pins the exact `LiteLLMProvider(model_string=..., api_base=..., api_key=...)` construction args for `ai_provider="lmstudio"` both before and after the refactor (assert equality, not just "it returns a provider"). `tests/test_composition.py` already has this exact pattern for `test_build_provider_router_picks_primary_from_settings` — extend it, don't replace it.
**Warning signs:** `test_build_provider_router_picks_primary_from_settings` (or its post-refactor equivalent) failing; LM Studio chat completions returning `AuthenticationError` after the refactor (a common symptom of a dropped/changed `api_key="lmstudio"`).

## Code Examples

### 1. Adding `litellm.NotFoundError` as a fallback trigger (D-06)
```python
# sentinel-core/app/services/provider_router.py
import litellm  # NEW import

# Errors that trigger fallback (connectivity failures + model-not-served)
_FALLBACK_TRIGGERS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    litellm.NotFoundError,   # NEW — D-06: exo's real failure mode is a 404
)
```
[VERIFIED: `litellm==1.83.4` local venv — `litellm.NotFoundError is litellm.exceptions.NotFoundError`, MRO `NotFoundError → APIStatusError → APIError → OpenAIError → Exception`, raised via the generic `status_code == 404` branch in `litellm/litellm_core_utils/exception_mapping_utils.py` for any `custom_llm_provider` including `"openai"` (the provider tag used for both LM Studio and exo).]

Existing style precedent: `app/clients/litellm_provider.py` already does `from litellm import BadRequestError` — follow the same top-level-import convention (`from litellm import NotFoundError` also works; `litellm.NotFoundError` is the same object).

### 2. Extracting exo's currently-loaded model from `GET /state` (D-07/D-08)
```python
# sentinel-core/app/services/model_selector.py (new function, sketch)
async def discover_via_exo_state(base_url: str, http_client: httpx.AsyncClient) -> list[str]:
    """Return the list of currently-loaded exo model ids via GET /state.

    Unlike /v1/models (a ~120-entry static catalog of servable-but-not-necessarily-
    running models), /state.instances reflects ONLY models with an active running
    instance. Each instance value is a tagged union — {"MlxRingInstance": {...}}
    or {"MlxJacclInstance": {...}} — with the model id at
    <tag-value>.shardAssignments.modelId (camelCase on the wire).

    Zero running instances → "instances": {} → returns [] (caller feeds this into
    select_model(), which raises ModelSelectorError rather than guessing when
    `loaded` is empty and no default is configured — D-08).
    """
    resp = await http_client.get(f"{base_url.rstrip('/')}/state", timeout=5.0)
    resp.raise_for_status()
    data = resp.json()
    instances = data.get("instances", {})
    model_ids: list[str] = []
    for instance_value in instances.values():
        # Tagged union: exactly one key, the class name (MlxRingInstance | MlxJacclInstance)
        for tagged_body in instance_value.values():
            model_id = tagged_body.get("shardAssignments", {}).get("modelId")
            if isinstance(model_id, str) and model_id:
                model_ids.append(model_id)
    return model_ids
```
[VERIFIED: exo-explore/exo source, `src/exo/shared/types/state.py` (`State.instances: Mapping[InstanceId, Instance]`), `src/exo/shared/types/worker/instances.py` (`Instance = MlxRingInstance | MlxJacclInstance`, both `BaseInstance(TaggedModel)` with `shard_assignments: ShardAssignments`), `src/exo/utils/pydantic_ext.py` (`TaggedModel._serialize` wraps as `{ClassName: {...}}`), `src/exo/shared/types/worker/runners.py` (`ShardAssignments.model_id: ModelId`). Route registration confirmed at `src/exo/api/main.py:397` (`self.app.get("/state")(self.get_state)`).]

[MEDIUM confidence / needs live verification]: exact camelCase key names (`shardAssignments`, `modelId`) are inferred from `alias_generator=to_camel` on the Pydantic models plus FastAPI's `jsonable_encoder` default of `by_alias=True` — this was NOT confirmed against a live exo `/state` response in this research session (the debug session's own captured evidence used the top-level `"instances": {}` key, which is single-word and unaffected by camelCasing either way, so it doesn't disambiguate the nested field names). **Recommend the plan include a `checkpoint:human-verify`-style task**: run `curl http://localhost:52415/state` against a real, loaded exo instance and confirm the nested key names before finalizing the parser, OR write the parser defensively to also check snake_case (`shard_assignments`/`model_id`) as a fallback.

### 3. `ProviderRouter` fallback test extension pattern (existing style, extend for D-05/D-06)
```python
# sentinel-core/tests/test_provider_router.py — existing pattern, add analogous cases:
async def test_falls_back_on_not_found_error(primary, fallback):
    primary.complete.side_effect = litellm.NotFoundError(
        "no instance found", llm_provider="openai", model="mlx-community/x"
    )
    router = ProviderRouter(primary, fallback)
    result = await router.complete([{"role": "user", "content": "hi"}])
    assert result == "fallback response"
    fallback.complete.assert_awaited_once()
```
[VERIFIED: existing file `tests/test_provider_router.py` already has the identical structure for `ConnectError`/`TimeoutException` — this is a direct extension of that pattern, not a new pattern.]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| exo reached by overloading `LMSTUDIO_BASE_URL`/`MODEL_NAME` (debug-time hack from `lmstudio-provider-switch`) | Dedicated `EXO_BASE_URL`/`EXO_MODEL`/`EXO_API_KEY` config, `ai_provider=exo` | This phase | LM Studio and exo can run simultaneously; no config collision |
| exo model resolved via `/v1/models` catalog[0]-or-preference match | Resolved via `GET /state` running-instance list | This phase (D-07) | Root-causes and closes `exo-model-notfound-502` at the architecture level, not just the `select_model()` patch already shipped |
| `ai_fallback_provider: claude \| none` | `ai_fallback_provider: <any configured provider>` | This phase (D-05) | Enables exo↔lmstudio fallback, previously impossible |
| pf2e-module calls litellm directly | pf2e-module calls sentinel-core's new completion endpoint | This phase (D-09) | Restores "everything through Sentinel" gateway design; centralizes the NotFoundError/fallback logic in one place instead of duplicating it in pf2e too |

**Deprecated/outdated:**
- pf2e-module's `Settings.litellm_model`/`litellm_api_base` (chat-purpose fields) — removed for chat call sites per D-09; `rules_embedding_model` and embedding-related config are UNCHANGED (Phase 43 concern, embeddings stay local to pf2e this phase).
- `select_model()`'s pre-`exo-model-notfound-502` unconditional `loaded[0]` fallback — already fixed in a prior session; this phase's `/state`-based discovery for exo is complementary, not a re-fix of the same bug.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | exo's `GET /state` JSON serializes nested fields in camelCase (`shardAssignments`, `modelId`) rather than snake_case on the wire | Code Examples §2 | Parser silently returns `[]` (empty model list) for every exo instance, causing D-08's "zero loaded instances" path to fire incorrectly, triggering unwanted fallback or a spurious "no model loaded" error even when exo has a model running. Mitigation already recommended: live curl verification task, or a parser that checks both cases. |
| A2 | exo does not implement an LM-Studio-style `/api/v0/models/{id}` context-window endpoint | Common Pitfalls §4 | If exo DOES implement it, the existing `_fetch_lmstudio`-style call would simply work (harmless — no code that assumes its absence is being written, only a bypass being recommended); low risk either way, but worth a quick live-`curl` check before deciding whether to write an exo-specific context-window fetch at all. |
| A3 | Which pf2e-module call sites (of the ~13 `acompletion_with_profile` call sites across `llm.py`/`foundry.py`/`pf_npc_extract.py`) are in-scope for D-09's "chat/completions" handoff — CONTEXT.md's north-star quote and the orchestrator's task framing name only `:pf rule` (rule generation) and `:pf say` (dialogue) as examples, but D-09's text ("pf2e-module delegates its chat/completions") could be read as ALL non-embedding LLM calls | Open Questions §1 | Under-migrating leaves architectural drift unresolved for NPC extraction/harvest/session-recap/foundry-narration call sites (all currently direct-litellm); over-migrating in one phase increases blast radius/regression risk beyond what CONTEXT.md's examples suggest. Needs explicit planner/user scoping decision — see Open Questions §1 for the full inventory table. |

## Open Questions (RESOLVED)

1. **Which pf2e call sites migrate to the new core endpoint in this phase?**
   - What we know: CONTEXT.md's `<specifics>` section names `:pf rule` (rule generation) and `:pf say` (dialogue) as the illustrative examples of "pf2e-module's chat path." D-09's text says "pf2e-module delegates its chat/completions" without an explicit call-site list. Full inventory of `acompletion_with_profile`/`litellm.acompletion` call sites found in this research pass:

     | File | Function | Task kind | Uses JSON-contract response? |
     |------|----------|-----------|-------------------------------|
     | `app/llm.py` | `extract_npc_fields` | structured | yes (JSON) |
     | `app/llm.py` | `generate_npc_reply` (DLG-01/02 — `:pf say`) | chat | yes (JSON: `{reply, mood_delta}`) |
     | `app/llm.py` | (NPC field update helper, ~line 165) | structured | yes |
     | `app/llm.py` | (MJ prompt / fast-kind helper, ~line 227) | fast | no |
     | `app/llm.py` | (harvest-fallback composer, ~line 305) | structured | yes |
     | `app/llm.py` | `generate_ruling_from_passages` (RUL-01 — `:pf rule`, corpus-hit) | chat/structured | yes (D-08 shape) |
     | `app/llm.py` | (topic classifier, ~line 697) | structured | yes |
     | `app/llm.py` | `generate_ruling_fallback` (RUL-02 — `:pf rule`, corpus-miss) | chat | yes (D-08 shape) |
     | `app/llm.py` | (session-recap composer, ~line 867) | chat | no |
     | `app/llm.py` | (one more call site, ~line 937) | unknown — not read in this pass | unknown |
     | `app/foundry.py` | roll-narration composer | fast/chat | no |
     | `app/pf_npc_extract.py` | archive-import NPC extraction | structured | yes |
   - What's unclear: whether "structured"-task-kind calls (JSON extraction) are in scope, or only free-text "chat" calls; whether embeddings-adjacent RAG *composition* calls (which need retrieved passages as context but the LLM call itself has no embedding dependency) count as in-scope "chat" per D-09.
   - Recommendation: Treat this as a planner-facing scoping decision, not something research should unilaterally resolve. Suggest the plan explicitly scope to the two named examples (`:pf rule` chat-composition calls + `:pf say`) as the MVP for this phase, with the remaining call sites flagged as a natural Phase-42-follow-on (or folded in if the user confirms broader scope during plan review) — narrower scope reduces regression blast radius given exo/LM Studio's already-fragile recent incident history.
   - **RESOLVED:** CONTEXT.md D-09 (resolved 2026-07-05 at plan-phase) locks **ALL ~13 pf2e chat/completion call sites** migrating in Phase 42 (full handoff), NOT the narrower "two named examples as MVP" this question speculated. Plans 42-04 (llm.py) + 42-05 (foundry.py/pf_npc_extract.py) implement it with a phase-wide grep gate (`acompletion_with_profile(` count must be 0). Embeddings call sites stay OUT → Phase 43.

2. **New endpoint naming and client-method shape.**
   - What we know: no existing sentinel-core route serves this purpose; `shared.sentinel_client.SentinelCoreClient.post_to_module()` is already generic enough to call any core path including a new one, despite its module-proxy-flavored name; pf2e does not currently import `sentinel_client` at all.
   - What's unclear: whether to (a) reuse `post_to_module()` as-is (zero new shared-lib code, slightly confusing name for a non-module-proxy use), or (b) add a dedicated `complete()` method to `SentinelCoreClient` for clarity and future-proofing (e.g. if the endpoint later needs typed request/response models beyond a raw dict).
   - Recommendation: Add a small dedicated `complete()` method — mirrors the existing `send_message()`/`post_to_module()` split (one convenience method per well-known core capability) and gives a natural place to document the request/response contract close to the call site.
   - **RESOLVED:** plan 42-03 adds a dedicated `SentinelCoreClient.complete()` (raise-on-error posture like `post_to_module()`) hitting a new narrow `POST /provider/complete` route (thin passthrough, not the `/message` pipeline).

3. **exo model-readiness signal beyond "an instance exists".**
   - What we know: `state.runners` is a SEPARATE mapping (`RunnerId → RunnerStatus`) from `state.instances`; only a runner in the `RunnerReady`/`RunnerRunning` tagged state can actually serve. The debug session observed a case where an instance existed in a downloading/evicted state and a request still 404'd.
   - What's unclear: whether D-07/D-08's "loaded instances" input to `select_model()` should be restricted to instances whose runners are actually `RunnerReady`/`RunnerRunning` (cross-referencing `shard_assignments.runner_to_shard.keys()` against `state.runners`), or whether the simpler "instance exists in `state.instances`" check is sufficient given the single-Mac-Mini, single-model-loaded-at-a-time operating reality documented in STATE.md.
   - Recommendation: Start with the simpler "instance exists" check (matches D-08's literal wording, "zero loaded instances") since it already correctly reproduces the debug session's `instances: {}` zero-case; document the readiness-cross-reference as a follow-up hardening item if repeated false-positive 404s are observed in practice (the disk-eviction race documented in `exo-model-notfound-502.md`'s evidence log is an operational/external-timing issue, not something a readiness flag would fully close either).
   - **RESOLVED:** plan 42-02 uses `state.instances` non-empty (model id at `<InstanceType>.shardAssignments.modelId`); zero instances → fallback-or-clear-error, never catalog[0].

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| litellm | ProviderRouter / LiteLLMProvider / NotFoundError | ✓ | 1.83.4 (pinned `>=1.83.0,<2.0`) | — |
| httpx | `/state` discovery call, endpoint tests | ✓ | `>=0.28.1` (pyproject) | — |
| exo (live inference backend) | exo provider path, live end-to-end verification | Unknown at research time — live container state is external/operational, not inspectable from this dev checkout (per `exo-model-notfound-502.md`, exo's serving state changes independently of code) | — | Tests use `httpx.MockTransport`/`patch("litellm.acompletion", ...)`, no live exo dependency needed for unit/integration tests; live end-to-end verification is an operator action post-deploy (same posture as the two prior debug sessions) |
| sentinel-core reachability from pf2e-module | New chat-handoff calls (D-09/D-10) | ✓ (already `depends_on: sentinel-core` with health condition per CONTEXT.md D-10) | — | — |

**Missing dependencies with no fallback:** none — all required libraries are already installed and pinned.

**Missing dependencies with fallback:** live exo instance availability (handled via mocked tests + existing graceful-degradation posture; not a blocker for implementation).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio (auto mode) — sentinel-core: `sentinel-core/pyproject.toml`; pathfinder: `modules/pathfinder/pyproject.toml` (same stack, confirmed via existing test files) |
| Config file | `sentinel-core/pyproject.toml` (`[tool.pytest.ini_options]`, `asyncio_mode = "auto"`, `testpaths = ["tests"]`, `pythonpath = [".", "../shared"]`) |
| Quick run command | `cd sentinel-core && pytest tests/test_provider_router.py tests/test_composition.py tests/test_model_selector_discovery.py -x` |
| Full suite command | `cd sentinel-core && pytest` (421+ tests as of the last debug session) and `cd modules/pathfinder && pytest` (382+ tests) |

### Phase Requirements → Test Map
(Anchored to ROADMAP SC-IDs per `<phase_requirements>` above, since formal REQ-IDs are TBD.)

| Anchor ID | Behavior | Test Type | Automated Command | File Exists? |
|-----------|----------|-----------|--------------------|--------------|
| SC-1 | `exo_base_url`/`exo_model`/`exo_api_key` Settings fields parse from env, independent of `lmstudio_*` | unit | `pytest tests/test_config.py -k exo -x` | ❌ Wave 0 (extend `tests/test_config.py`) |
| SC-2 | `ai_provider=exo` selects the exo `LiteLLMProvider` instance in `provider_map` | unit | `pytest tests/test_composition.py -k exo -x` | ❌ Wave 0 (extend `tests/test_composition.py`, follow `test_build_provider_router_picks_primary_from_settings` pattern) |
| SC-3 | `ProviderRouter` falls back on `litellm.NotFoundError` (D-06); `ai_fallback_provider` accepts non-claude values (D-05) | unit | `pytest tests/test_provider_router.py -k "not_found or fallback" -x` | ❌ Wave 0 (extend `tests/test_provider_router.py` — see Code Examples §3) |
| SC-4 | exo `GET /state` zero-instances → no guessed model; raises/falls back per D-08 | unit | `pytest tests/test_model_selector_discovery.py -k exo -x` | ❌ Wave 0 (new tests alongside existing exo-shaped tests in this file) |
| SC-5 | exo embeddings-dependent paths still degrade gracefully (unchanged; regression check only) | integration | `pytest tests/test_embeddings.py -x` | ✅ existing |
| SC-6 (LM Studio regression, D-02) | LM Studio `LiteLLMProvider` construction args unchanged after `openai_compatible` refactor | unit | `pytest tests/test_composition.py -k lmstudio -x` | ✅ existing (`test_build_provider_router_picks_primary_from_settings`) — extend assertions, don't just re-run |
| SC-6 (pf2e→core handoff, D-09) | pf2e's dialogue/rule-generation call sites successfully call the new core endpoint; core endpoint returns `{content, model}` | integration | `pytest tests/test_provider_route.py -x` (core, NEW) + `pytest tests/test_llm.py -k core_handoff -x` (pf2e, NEW) | ❌ Wave 0 (both sides — new endpoint route test with `httpx.MockTransport`/TestClient, and pf2e-side test patching the new client call) |

### Sampling Rate
- **Per task commit:** targeted `pytest tests/test_<touched_file>.py -x` in the affected package (sentinel-core or pathfinder)
- **Per wave merge:** full suite in BOTH `sentinel-core` and `modules/pathfinder` (this phase touches both)
- **Phase gate:** Full suite green in both packages before `/gsd-verify-work`; additionally, if any live exo/LM Studio verification is feasible, a manual `curl` smoke test against `/provider/complete` (mirrors the two prior debug sessions' "operator must verify live" posture)

### Wave 0 Gaps
- [ ] `sentinel-core/tests/test_provider_router.py` — extend with `litellm.NotFoundError` fallback case (Code Examples §3) — covers SC-3
- [ ] `sentinel-core/tests/test_config.py` — extend with `exo_base_url`/`exo_model`/`exo_api_key` field tests — covers SC-1
- [ ] `sentinel-core/tests/test_composition.py` — extend with exo primary-selection + LM-Studio-regression-pinning cases — covers SC-2, SC-6
- [ ] `sentinel-core/tests/test_model_selector_discovery.py` — new exo `/state` discovery tests (empty-instances, single-instance, tagged-union unwrap) — covers SC-4
- [ ] `sentinel-core/tests/test_provider_route.py` (NEW FILE) — new `/provider/complete` endpoint tests (success, auth via existing middleware, error mapping) — covers SC-6 (pf2e handoff, core side)
- [ ] `modules/pathfinder/tests/` — new test(s) for the migrated chat call site(s), patching the new `SentinelCoreClient.complete()` (or `post_to_module()`) call — covers SC-6 (pf2e handoff, pf2e side); exact file(s) depend on Open Questions §1's scoping decision

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes (unchanged) | Existing `APIKeyMiddleware` (`X-Sentinel-Key` header, exact-match against `settings.sentinel_api_key`) already covers ALL non-`/health` routes including the new `/provider/complete` — no new auth code needed, confirmed by reading `app/main.py`'s middleware, which applies globally before route dispatch. |
| V3 Session Management | no | Stateless request/response; no session concept in this endpoint |
| V4 Access Control | yes (unchanged) | Single shared `X-Sentinel-Key` is the only access-control boundary today (no per-module scoping) — this phase does not change that model; note as an existing limitation, not a new one introduced here |
| V5 Input Validation | yes | New `ProviderCompletionRequest`-style Pydantic model should mirror `MessageEnvelope`'s bounds (e.g. `max_length` on content, list-size caps on `messages`) — no existing cap on message list length was found; recommend adding one (unbounded `messages: list[dict]` is a resource-exhaustion vector against the underlying LLM call's timeout/cost) |
| V6 Cryptography | no | No new crypto surface — `exo_api_key`/`lmstudio_api_key` follow the existing `_read_secret()`/Docker-secrets pattern already used for `anthropic_api_key` etc. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| SSRF via operator-configured `exo_base_url`/`lmstudio_base_url` pointing at an internal service | Tampering/Information Disclosure | Already an accepted, pre-existing risk class for this codebase (these are operator-controlled env vars in a single-operator personal-tool deployment, not user-supplied input — see PROJECT.md "single DM campaign only" / "personal tool" framing). Not newly introduced by this phase; no additional mitigation recommended beyond what already exists for `lmstudio_base_url`. |
| Unbounded `messages` array in the new endpoint causing excessive LLM cost/latency | Denial of Service | Add a Pydantic `max_length` constraint on the new request model's `messages` list (see V5 above) — mirrors `MessageEnvelope.content`'s existing `max_length=32_000` pattern. |
| pf2e-module trusting an unauthenticated/misconfigured core response | Spoofing | Existing `X-Sentinel-Key` middleware already prevents unauthenticated callers from reaching the route at all; the NEW risk surface is pf2e now trusting core's `{content, model}` response shape — recommend the pf2e-side client raise (not silently coerce) on an unexpected response shape, matching `post_to_module()`'s existing raise-on-error posture rather than `send_message()`'s swallow-to-string posture. |

## Sources

### Primary (HIGH confidence — direct source/code inspection this session)
- `sentinel-core/app/composition.py` (full read) — `build_provider_router()`, `build_application()`, `initialize_startup()`
- `sentinel-core/app/services/provider_router.py` (full read) — `ProviderRouter`, `_FALLBACK_TRIGGERS`
- `sentinel-core/app/clients/litellm_provider.py` (full read) — `LiteLLMProvider`, `get_context_window_from_lmstudio`
- `sentinel-core/app/services/model_selector.py` (full read) — `select_model`, `discover_active_model`, `get_loaded_models`
- `sentinel-core/app/services/model_registry.py` (full read) — `build_model_registry`, `_fetch_lmstudio`
- `sentinel-core/app/config.py` (full read) — `Settings`
- `sentinel-core/app/state.py`, `app/main.py`, `app/errors.py`, `app/models.py`, `app/routes/message.py`, `app/routes/modules.py` (read) — `RouteContext`, `APIKeyMiddleware`, error hierarchy, envelope shapes, module-proxy pattern
- `sentinel-core/.venv/lib/python3.13/site-packages/litellm-1.83.4.dist-info`, `litellm/litellm_core_utils/exception_mapping_utils.py`, live `python3 -c "import litellm; ..."` interpreter check — confirmed `litellm.NotFoundError` identity, MRO, version
- `sentinel-core/tests/test_provider_router.py`, `test_composition.py`, `test_litellm_provider.py`, `test_model_selector_discovery.py` (read) — existing test patterns
- `modules/pathfinder/app/config.py`, `app/llm.py`, `app/dialogue.py`, `app/resolve_model.py` (read) — pf2e chat call sites, config, model resolution
- `shared/sentinel_shared/llm_call.py`, `shared/sentinel_client.py`, `shared/tests/test_sentinel_client.py` (read) — shared completion wrapper and core client
- `.planning/debug/exo-model-notfound-502.md`, `.planning/debug/resolved/lmstudio-provider-switch.md` (full read) — root-cause history for D-06/D-07/D-08
- exo-explore/exo GitHub source (fetched via `gh api` at commit on `main` branch, this session): `src/exo/api/main.py` (route registration, `get_state` handler), `src/exo/shared/types/state.py` (`State` model), `src/exo/shared/types/worker/instances.py` (`Instance`/`BaseInstance`/`MlxRingInstance`/`MlxJacclInstance`), `src/exo/shared/types/worker/runners.py` (`RunnerStatus`/`ShardAssignments`), `src/exo/utils/pydantic_ext.py` (`FrozenModel`/`TaggedModel` serialization)

### Secondary (MEDIUM confidence)
- exo-explore/exo `docs/api.md` (fetched via WebFetch) — endpoint list confirmed, but the doc's own prose for `GET /state` is sparse ("JSON object describing topology, nodes, and instances") with no example response body; the concrete field-shape claims in this document come from the PRIMARY source-code read above, not from this doc.
- Wire-format camelCase assumption (A1 in Assumptions Log) — inferred from Pydantic `alias_generator=to_camel` + FastAPI's `jsonable_encoder` default `by_alias=True`, not confirmed against a live exo response this session.

### Tertiary (LOW confidence)
- exo's lack of an `/api/v0/models/{id}`-equivalent endpoint (Assumption A2) — based on the absence of such a path in the fetched route-registration code, not an exhaustive negative-space search of the entire exo repo.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; existing pinned versions confirmed via direct venv inspection.
- Architecture: HIGH for sentinel-core/pf2e internals (full source read of every touched file); MEDIUM for exo's exact wire format (source-code-verified schema, wire-serialization behavior inferred not curl-confirmed).
- Pitfalls: HIGH — all 5 pitfalls are directly observed gaps in the read source (line-cited), not speculative.

**Research date:** 2026-07-05
**Valid until:** 30 days for the sentinel-core/pf2e-module findings (stable, internally-controlled code); 14 days for the exo `/state` schema specifics (exo is an actively-developed external project — re-verify against the pinned/running exo version before implementation if more than ~2 weeks elapse, and definitely before hardening the parser per the A1 recommendation).
