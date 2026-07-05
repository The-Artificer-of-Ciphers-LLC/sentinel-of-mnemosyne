# Phase 43: Embeddings Through Sentinel - Research

**Researched:** 2026-07-05
**Domain:** Internal service-to-service embeddings gateway (FastAPI passthrough route + litellm client repoint), Python/pydantic-settings, LM Studio OpenAI-compatible embeddings API
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Embeddings backend (SC-2)**
- **D-01:** The non-exo embeddings backend is **LM Studio serving `text-embedding-nomic-embed-text-v1.5`** on its local server (default `http://host.docker.internal:1234/v1` from containers / `http://localhost:1234/v1` from host). This is already the code's default model (`embeddings.py::_default_model()`) and already has a reachability UAT (`scripts/uat_rules.py::test_lm_studio_embeddings_reachable` targets port 1234).
- **D-02:** The core fix is therefore **narrow — a base_url rewire, not a new backend**: the embeddings `api_base` must move off exo's port 52415 (the hardcoded `DEFAULT_LMSTUDIO_BASE_URL = "http://host.docker.internal:52415"` in `embeddings.py:14` is exo's port and is the root cause of the broken semantic recall). Ollama nomic-embed-text and hosted endpoints were considered and rejected for now. Ollama remains the fallback if LM Studio's GUI-driven model-loading proves operationally fragile.

**Config independence (SC-2)**
- **D-03:** Introduce a **dedicated `embedding_*` settings triplet** — `embedding_base_url` / `embedding_model` / `embedding_api_key` — in `sentinel-core/app/config.py::Settings`, wired at the compose root (`composition.py`). Mirrors the Phase 42 per-provider triplet pattern (`exo_*`/`ollama_*`/`llamacpp_*`).
- **D-04:** Embeddings selection is **fully independent of the chat `ai_provider`**: chat may run on exo (52415) while embeddings run on LM Studio (1234) simultaneously. The embeddings client must NOT inherit `lmstudio_base_url` or any chat-provider base_url.
- **D-05 (rejected alternative, recorded):** Do **not** retrofit Phase 42's `openai_compatible` `provider_map`/`ProviderRouter` for embeddings in this phase. `LiteLLMProvider` is chat-shaped; adding an `embed()` contract is scope creep with no second embedding backend to justify it. A minimal "just fix the default" patch was also rejected.

**pf2e→core handoff shape (SC-1)**
- **D-06:** core exposes a **narrow raw-embeddings passthrough endpoint** — `POST /embeddings` (input: texts → output: list of float vectors) — the direct mirror of Phase 42's `POST /provider/complete`. pf2e calls it via a new `SentinelCoreClient.embed()`.
- **D-07:** **pf2e retains ownership of its rules index and retrieval** — chunking, cosine scan, `RulesIndex`, and `_build_rules_index_safely()`'s graceful-503 degrade all stay in pf2e. Only the vector-computation call moves to core (swap `embed_texts`'s internal `litellm.aembedding` for the core HTTP call). Core does NOT own pf2e's rules corpus/index.

**Stale-index / re-embed on cutover (SC-3, SC-4)**
- **D-08:** Add an **explicit dimension-mismatch guard** in `SemanticRecall` (`recall.py:413`): never compute cosine across vectors of mismatched dimension — hard-skip (and log) entries whose stored dimension ≠ the active model's.
- **D-09:** Perform a **forced re-embed/re-sweep on cutover** so both indexes are populated and dimensionally consistent *before* SC-3/SC-4 are exercised. A one-time manual trigger is acceptable (owner runs the stack himself).

### Claude's Discretion
- Exact route path/verb and request/response schema of core's `POST /embeddings` (align with the existing `/provider/complete` conventions).
- Exact `embedding_*` field names and how the dimension is stored/derived in the sidecar index (`embedding_dim` field vs `len(vector)` at read time).
- The mechanism of the forced re-sweep trigger (startup hook, CLI, or a one-shot ops route) — provided both indexes are guaranteed populated on cutover.
- Whether `embedding_api_key` defaults to the existing `"lm-studio"` sentinel.
- Proposed `EMB-*` requirements family (assigned at planning), mapped to SC-1..SC-4. **Resolved:** ROADMAP.md/REQUIREMENTS.md already assign EMB-01..EMB-04 to this phase (see `<phase_requirements>` below).

### Deferred Ideas (OUT OF SCOPE)
- **Embeddings-provider fallback / full `provider_map` for embeddings** — only justified once a second embedding backend exists. Revisit if D-01's LM Studio path proves fragile.
- **Ollama nomic-embed-text as the embeddings backend** — clean headless-daemon alternative; adopt only if LM Studio's GUI model-loading is too operationally fragile for always-on use.
- **Persistent ANN vector index (FAISS/hnswlib/sqlite-vec/chroma)** — deferred per REQUIREMENTS.md; numpy cosine is sufficient below ~10k notes.
- **Core owning pf2e's rules RAG (index build + query in core)** — rejected for this phase (inverts module boundary); only revisit if a second module needs equivalent document RAG.

None of the above block Phase 43.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-------------------|
| EMB-01 | pf2e-module no longer calls an embeddings endpoint directly — embeddings for its rules index are obtained via sentinel-core (a narrow core embeddings endpoint + `SentinelCoreClient.embed()`); pf2e retains ownership of its rules index and retrieval | Pattern 2/3 (Architecture Patterns); exact call sites identified: `modules/pathfinder/app/llm.py::embed_texts` (internals swap only), `main.py`'s `_rule_embed_fn` closure and `rule_query.py`'s `deps.embed_texts` call (zero changes needed — signature preserved) |
| EMB-02 | sentinel-core is configured with a non-exo embeddings backend that actually serves `/v1/embeddings` for the configured embedding model, selectable independently of the chat `ai_provider` (chat=exo and embeddings=LM Studio can coexist) | Pitfall 1 (root-cause trace) + Code Examples (settings triplet + composition.py wiring fix at both call sites) |
| EMB-03 | `:pf rule` semantic retrieval works end-to-end — the rules index builds and returns relevant rules with no 503 degradation when the embeddings backend is up | Validation Architecture (EMB-03 row — existing `scripts/uat_rules.py` UAT); Architecture Patterns Pattern 3 (preserves pf2e's existing 503-degrade path unchanged) |
| EMB-04 | core's Phase-40 semantic recall produces/reads embeddings successfully against the same backend, with a dimension-mismatch guard that prevents stale/garbage cosine and no silent empty-index degradation | Summary (dimension guard already implemented + tested in `embedding_sidecar_index.py::eligible_entries`); Pitfall 3 (the exact mechanism of today's silent degradation); Don't Hand-Roll (existing startup re-sweep task satisfies the cutover requirement) |
</phase_requirements>

## Summary

This phase is smaller than it looks. Three of the four locked decisions (D-01/02, D-06/07, D-08) are **narrow, well-precedented changes to code that already has the shape it needs** — a base_url rewire, a route mirroring an existing route, and (surprisingly) a dimension guard that **already exists and already has a passing test**. The one genuinely new piece of wiring is the `embedding_*` settings triplet (D-03/D-04) and threading it through `composition.py` to the two places that currently read `settings.lmstudio_base_url`/`settings.embedding_model` for embeddings purposes: `Embeddings()` construction and `probe_embedding_model_loaded()`.

**Root cause, precisely:** `sentinel-core/app/config.py:36` sets `lmstudio_base_url: str = "http://host.docker.internal:52415/v1"` — port 52415 is exo's port, not LM Studio's (1234). `sentinel-core/app/clients/embeddings.py:14`'s `DEFAULT_LMSTUDIO_BASE_URL` constant is *also* 52415 and is only a fallback-of-a-fallback (used when `base_url` is falsy) — the actual live value flowing into `Embeddings()` today is `settings.lmstudio_base_url`, which is already wrong before the constant is ever consulted. Both must be corrected/replaced; fixing only the constant (embeddings.py:14) without also changing what `composition.py` passes in would do nothing (D-02's "narrow — a base_url rewire" framing in CONTEXT.md refers to both).

**Two independent bugs currently masking each other:** (1) `Embeddings()` is constructed with exo's base_url, so every `litellm.aembedding()` call 404/405s against exo. (2) `probe_embedding_model_loaded()` also reads `settings.lmstudio_base_url` and hits exo's `/api/v0/models` (an LM-Studio-only REST extension exo doesn't implement) — it fails closed to `embedding_model_loaded=False`, which makes `rebuild_embedding_index()` skip embedding entirely (`model_loaded=False` path) rather than raise. This is the exact mechanism behind EMB-04's "silent empty-index degradation": no exception, no log noise beyond one WARNING at startup — the sidecar index simply never gets populated.

**A load-bearing existing mechanism the plan should reuse, not rebuild:** `composition.py::initialize_startup()` already fires a **non-blocking background task** (`_rebuild_task = asyncio.create_task(_startup_rebuild())`) on every boot that calls `rebuild_embedding_index()` unconditionally. Once the `embedding_*` triplet points at LM Studio and the probe succeeds, **a plain container restart re-populates the core sidecar index** — D-09's "forced re-embed/re-sweep on cutover" requirement for the *core* side is already satisfied by code that ships today; no new re-sweep trigger needs to be built for core. pf2e's rules index is separately rebuilt at every pf2e container startup (`lifespan()` → `_build_rules_index_safely()`), so it too needs nothing beyond fixing the embed call underneath it. **D-09's "mechanism of the forced re-sweep trigger" (Claude's Discretion) is therefore answered: restart both containers.** No new ops route, CLI, or startup-hook code is needed for the re-sweep itself — only the base_url/settings plumbing that makes the existing rebuild succeed instead of skipping.

**D-08's dimension guard already exists.** `sentinel-core/app/services/embedding_sidecar_index.py::eligible_entries()` (lines 173–237) already takes a `query_dim: int` parameter and at lines 215–222 does exactly the CONTEXT.md-specified guard: `if len(raw) != query_dim: log.warning(...); continue` — skip, never raise, never cosine across mismatched dims. It is called from `SemanticRecall.search()` (`recall.py:562-567`) with `query_dim=len(qv)` (the live query's own embedding length). There is already a passing regression test: `sentinel-core/tests/test_embedding_sidecar_index.py::test_eligible_entries_skips_stale_model_and_dimension_mismatch` (line 162). **The planner should treat D-08 as "verify + extend coverage for the LM Studio cutover scenario," not "build a new guard."** The model-string check (`entry_model != active_model`, line 192) already gates *most* of what a dimension check would also catch (since MEM-05's exact-string skip means only same-named-model, different-dimension entries would ever reach the dimension check) — the dimension check is defense-in-depth for the case where the same `embedding_model` string is reused across a backend change that alters output dimensionality (e.g., an operator later reconfigures the same nomic model name to a truncated Matryoshka dimension). Document this nuance in the plan so it isn't rebuilt from scratch.

**Primary recommendation:** (1) Add `embedding_base_url`/`embedding_model` (reuse existing field)/`embedding_api_key` to `Settings`, defaulting to LM Studio's `http://host.docker.internal:1234/v1` / `text-embedding-nomic-embed-text-v1.5` / `"lm-studio"`. (2) In `composition.py`, change the `Embeddings(...)` construction and the `probe_embedding_model_loaded(...)` call to read the new `embedding_*` fields instead of `settings.lmstudio_base_url`/`settings.lmstudio_api_key`. (3) Add `POST /embeddings` as a new route module mirroring `app/routes/provider.py` exactly (same auth posture, same error-mapping pattern, same file layout), using `ctx.embedder` (already wired on `RouteContext`, already populated with `graph.embeddings.embed` in `initialize_startup()` — no new wiring needed there). (4) Add `SentinelCoreClient.embed()` in `shared/sentinel_client.py` mirroring `complete()`. (5) Swap `embed_texts()`'s internals in `modules/pathfinder/app/llm.py` to call `_core_client.embed()` instead of `litellm.aembedding()`, **preserving the existing `(texts, model, api_base=None)` signature** so both call sites (`main.py`'s `_rule_embed_fn` closure and `routes/rule.py`'s `RuleQueryDependencies.embed_texts` injection) require zero changes. (6) Fix/replace the two tests that currently assert the *wrong* (exo) default as correct behavior (see Pitfalls).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Embeddings backend selection/config | API/Backend (sentinel-core) | — | `Settings` + `composition.py` is the single source of truth for which backend serves embeddings (D-03/D-04) |
| Raw vector computation (litellm call) | API/Backend (sentinel-core) | — | Only `app/clients/` may hold vendor SDK access (AI-agnostic guardrail); `Embeddings.embed()` is the sole call site |
| `POST /embeddings` passthrough route | API/Backend (sentinel-core) | — | Direct mirror of `/provider/complete`; thin, no business logic, auth via existing `APIKeyMiddleware` |
| pf2e rules corpus, chunking, cosine retrieval, 503-degrade | API/Backend (pf2e-module) | — | D-07: pf2e retains full ownership; only the vector-compute call delegates outward |
| Core sidecar semantic-recall index (`ops/sweeps/embedding-index.json`) | API/Backend (sentinel-core) | Database/Storage (Obsidian vault via REST) | Sidecar is core's own memory feature (ADR-0004); vault is the persistence tier reached only through the Vault seam |
| Dimension-mismatch / model-mismatch skip | API/Backend (sentinel-core `recall.py`/`embedding_sidecar_index.py`) | — | Correctness guard belongs beside the cosine computation, not at the client boundary |
| Cutover re-embed trigger | API/Backend (both services' own startup lifespan) | — | Both services already rebuild their respective indexes at process boot; no new tier needed |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| litellm | (already pinned in `sentinel-core/pyproject.toml` — no version bump needed) | OpenAI-compatible `aembedding()` call against LM Studio | Already the project's sole AI-vendor abstraction; embeddings path already uses it — no new dependency |
| fastapi / pydantic | (already pinned) | New `POST /embeddings` route + request/response models | Matches `provider.py`'s existing pattern exactly |
| numpy | (already pinned) | Vector decode/cosine (unchanged) | Already used throughout `recall.py`/`rules.py` |

No new packages are introduced by this phase. `## Package Legitimacy Audit` is therefore N/A (see below).

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic-settings | (already pinned) | `embedding_*` settings triplet on `Settings` | Same mechanism as `exo_*`/`ollama_*` triplets already in `config.py` |

### Alternatives Considered
Not applicable — D-01/D-02/D-05 already resolved the backend choice and rejected the `provider_map`/full-fallback alternative in CONTEXT.md. Re-litigating is out of scope per this phase's research charter.

**Installation:** none — no new packages.

**Version verification:** N/A (no new packages; litellm/fastapi/numpy versions are unchanged by this phase and already installed in both containers).

## Package Legitimacy Audit

Not applicable — this phase introduces zero new third-party packages. Both the `sentinel-core` and `pathfinder` containers already depend on `litellm`, `fastapi`, `pydantic`/`pydantic-settings`, `numpy`, and `httpx`; the phase only adds new call sites and configuration fields, not new dependencies.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                                   ┌──────────────────────────────────────┐
                                   │   LM Studio  (host, port 1234)       │
                                   │   POST /v1/embeddings                │
                                   │   model: text-embedding-nomic-       │
                                   │          embed-text-v1.5  (768-dim)  │
                                   └───────────────▲───────────────────────┘
                                                   │ litellm.aembedding()
                                                   │ api_base=embedding_base_url
                                                   │ (host.docker.internal:1234/v1)
                              ┌────────────────────┴─────────────────────┐
                              │        sentinel-core (container)         │
                              │                                          │
  pf2e ── POST /embeddings ──▶│  app/routes/embeddings.py (NEW)          │
  (SentinelCoreClient.embed)  │    └─▶ ctx.embedder  (= Embeddings.embed) │
                              │           └─▶ app/clients/embeddings.py  │
                              │                 embed_texts()             │
                              │                                          │
                              │  SemanticRecall.search() (recall.py)     │
                              │    └─▶ embeddings.embed (query vec)      │
                              │    └─▶ embedding_sidecar_index.py        │
                              │          eligible_entries(query_dim=…)  │──▶ ops/sweeps/embedding-index.json
                              │          (model-mismatch skip +          │      (via Vault REST seam)
                              │           dimension-mismatch skip)       │
                              │                                          │
                              │  vault_sweeper.rebuild_embedding_index() │
                              │    fired non-blocking at every startup   │
                              │    (composition.py::initialize_startup) │
                              └──────────────────────────────────────────┘
                                            ▲
                                            │ X-Sentinel-Key (APIKeyMiddleware)
                                            │
                              ┌─────────────┴────────────────────────────┐
                              │        pf2e-module (container)           │
                              │                                          │
                              │  app/llm.py::embed_texts()  (INTERNALS   │
                              │    swapped: litellm.aembedding() →       │
                              │    _core_client.embed())                 │
                              │      called from:                        │
                              │      - main.py lifespan _rule_embed_fn   │
                              │        (startup: build_rules_index)      │
                              │      - routes/rule.py → rule_query.py    │
                              │        (per-query: embed user question)  │
                              │                                          │
                              │  app/rules.py RulesIndex (unchanged):     │
                              │    in-memory matrix, rebuilt every boot  │
                              │    → no cross-restart dimension drift    │
                              │      possible (D-07/D-09 rationale)      │
                              └───────────────────────────────────────────┘
```

Chat path (Phase 42, unchanged): pf2e → `POST /provider/complete` → `ctx.ai_provider` (exo, port 52415). Embeddings path (this phase): pf2e → `POST /embeddings` → `ctx.embedder` (LM Studio, port 1234). The two paths are fully independent per D-04 — nothing in this diagram touches `ai_provider`/`exo_*`.

### Recommended Project Structure
```
sentinel-core/app/
├── clients/embeddings.py       # UNCHANGED signature; DEFAULT_LMSTUDIO_BASE_URL
│                                #   constant either removed or repointed to 1234
│                                #   (see Pitfall 1) — Embeddings class itself needs
│                                #   no change, only what composition.py passes in
├── config.py                   # ADD: embedding_base_url, embedding_api_key
│                                #   (embedding_model already exists — reuse it)
├── composition.py               # CHANGE: Embeddings(...) construction (line ~395-401)
│                                #   and probe_embedding_model_loaded(...) call
│                                #   (line ~441-445) to read embedding_* fields
├── routes/
│   └── embeddings.py           # NEW — mirrors routes/provider.py exactly
├── main.py                      # ADD: app.include_router(embeddings_router)
├── services/
│   ├── recall.py                # UNCHANGED (dimension guard already present)
│   └── embedding_sidecar_index.py  # UNCHANGED (eligible_entries already guards dim)
└── state.py                     # UNCHANGED (RouteContext.embedder already exists)

modules/pathfinder/app/
├── llm.py                       # CHANGE: embed_texts() internals only —
│                                #   litellm.aembedding() → _core_client.embed()
│                                #   signature (texts, model, api_base=None) preserved
├── main.py                      # UNCHANGED call site (_rule_embed_fn closure)
├── rule_query.py                # UNCHANGED call site (deps.embed_texts(...))
└── routes/rule.py               # UNCHANGED (still injects embed_texts by reference)

shared/
└── sentinel_client.py           # ADD: SentinelCoreClient.embed() mirroring complete()
```

### Pattern 1: Narrow passthrough route (reuse of Phase 42's `/provider/complete` shape)
**What:** A route module with its own `APIRouter()`, request/response Pydantic models with explicit size caps, a single call into the pre-wired `RouteContext` capability, and a narrow except-clause mapping one typed internal exception to one HTTP status.
**When to use:** Any time a domain module needs a raw AI-vendor capability (chat, embeddings) that core already owns, without reusing any part of the `/message` pipeline (no recall, no injection filtering, no output scanning — callers already carry their own context).
**Example:**
```python
# Source: sentinel-core/app/routes/provider.py (existing, to mirror)
class ProviderCompleteRequest(BaseModel):
    messages: list[ProviderMessage] = Field(min_length=1, max_length=_MAX_MESSAGES)
    stop: list[str] | None = None
    temperature: float | None = None

@router.post("/provider/complete", response_model=ProviderCompleteResponse)
async def post_provider_complete(body: ProviderCompleteRequest, request: Request) -> ProviderCompleteResponse:
    ctx = get_route_context(request)
    if ctx.ai_provider is None:
        raise HTTPException(status_code=500, detail="ai_provider not configured")
    try:
        content = await ctx.ai_provider.complete(messages, stop=body.stop, temperature=body.temperature)
    except ProviderUnavailableError:
        raise HTTPException(status_code=503, detail="AI provider unavailable")
    return ProviderCompleteResponse(content=content, model=ctx.ai_provider_name or "")
```
Recommended mirror for embeddings (`sentinel-core/app/routes/embeddings.py`):
```python
_MAX_TEXTS = 200          # generous headroom over pf2e's 148-chunk corpus (app/rules.py load_rules_corpus)
_MAX_TEXT_LENGTH = 8_000  # nomic-embed-text-v1.5's practical input ceiling; mirrors _MAX_CONTENT_LENGTH pattern

class EmbeddingsRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=_MAX_TEXTS)

class EmbeddingsResponse(BaseModel):
    embeddings: list[list[float]]
    model: str

@router.post("/embeddings", response_model=EmbeddingsResponse)
async def post_embeddings(body: EmbeddingsRequest, request: Request) -> EmbeddingsResponse:
    ctx = get_route_context(request)
    try:
        vectors = await ctx.embedder(body.texts)
    except EmbeddingModelUnavailable:
        raise HTTPException(status_code=503, detail="Embedding backend unavailable")
    return EmbeddingsResponse(embeddings=vectors, model=ctx.settings.embedding_model if ctx.settings else "")
```
Note: `ctx.embedder` is `RouteContext.embedder`, already populated in `initialize_startup()` as `embedder=graph.embeddings.embed` — this route needs **zero new wiring** on `state.py`/`composition.py` beyond the `embedding_*` field fix.

### Pattern 2: Client-side mirror method (`SentinelCoreClient.embed()`)
**What:** A new method on the shared HTTP client following `complete()`'s raise-on-error posture (not `send_message()`'s swallow-to-string posture), because `embed_texts()` callers already have their own exception handling (`RuleQueryEmbeddingError`, `_build_rules_index_safely`'s catch-all).
**Example:**
```python
# Source: shared/sentinel_client.py (existing complete() to mirror, lines 74-108)
async def embed(self, texts: list[str], client: httpx.AsyncClient) -> dict:
    """POST /embeddings — thin embeddings passthrough to core.
    Mirrors complete()'s raise-on-error posture exactly."""
    resp = await client.post(
        f"{self._base_url}/embeddings",
        json={"texts": texts},
        headers={"X-Sentinel-Key": self._api_key},
        timeout=self._timeout,
    )
    resp.raise_for_status()
    return resp.json()  # {"embeddings": [[...], ...], "model": "..."}
```

### Pattern 3: Preserve caller signature while swapping internals (D-06/D-07's actual mechanism)
**What:** `embed_texts(texts, model, api_base=None)` in `modules/pathfinder/app/llm.py` keeps its exact signature so `main.py`'s `_rule_embed_fn` closure and `routes/rule.py`'s `RuleQueryDependencies.embed_texts` injection require **no changes**. Only the function body changes: instead of `litellm.aembedding(...)`, it opens a short-lived `httpx.AsyncClient` (matching the existing convention noted in `llm.py`'s module docstring for all 10 chat call sites) and calls `_core_client.embed(texts, client)`.
**When to use:** Exactly this phase's situation — a Strangler-Fig internal swap where the call graph must not change shape, only what's behind the leaf call.
**Example:**
```python
# modules/pathfinder/app/llm.py — embed_texts() new body (signature unchanged)
async def embed_texts(texts: list[str], model: str, api_base: str | None = None) -> list[list[float]]:
    if not isinstance(texts, list) or len(texts) == 0:
        raise ValueError("embed_texts: 'texts' must be a non-empty list")
    # model/api_base are now vestigial — core owns backend selection (D-04).
    # Kept in the signature only so call sites need zero changes this phase.
    async with httpx.AsyncClient() as client:
        result = await _core_client.embed(texts, client)
    vectors = result["embeddings"]
    if len(vectors) != len(texts):
        raise ValueError(f"embed_texts: expected {len(texts)} embeddings, got {len(vectors)}")
    return vectors
```

### Anti-Patterns to Avoid
- **Retrofitting `LiteLLMProvider`/`ProviderRouter` for embeddings (D-05, explicitly rejected):** `LiteLLMProvider.complete()` is chat-shaped (stop sequences, message roles). Adding an `embed()` contract there with no second embedding backend to justify a router is scope creep — CONTEXT.md already rejected this.
- **Building a new dimension-mismatch guard:** it already exists in `embedding_sidecar_index.py::eligible_entries()`. Re-implementing it elsewhere (e.g. in `SemanticRecall` directly) would create two sources of truth for the same invariant.
- **Building a new re-sweep trigger (ops route/CLI/cron):** both services already rebuild their embedding state at process startup. A restart *is* the cutover mechanism — adding a second mechanism duplicates behavior that already exists and is already tested (`test_rebuild_embedding_index_writes_index_with_all_fields`).
- **Passing `model=`/`api_base=` from pf2e through to core's `/embeddings` request:** D-04 makes embeddings backend selection fully independent and core-owned. Forwarding pf2e's `rules_embedding_model` config to core's endpoint would reintroduce a second place where model identity can drift from what core is actually configured with. Core's response should report back the model it actually used (for pf2e's cache/frontmatter provenance, mirroring `ProviderCompleteResponse.model`), not accept a client-requested override.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dimension-mismatch cosine guard | A new check in `SemanticRecall` or a new `embedding_dim` stored field | Existing `eligible_entries(..., query_dim=len(qv))` in `embedding_sidecar_index.py:173-237` | Already implemented, already tested (`test_eligible_entries_skips_stale_model_and_dimension_mismatch`); adding a second guard elsewhere risks divergent semantics |
| Cutover re-embed/re-sweep trigger | New ops route, CLI command, or scheduled job | Existing non-blocking startup task in `composition.py::initialize_startup()` (`_startup_rebuild()` → `rebuild_embedding_index()`) + pf2e's existing `lifespan()` → `_build_rules_index_safely()` | Both already run unconditionally at container boot; a `docker compose restart` after the config fix satisfies D-09 with zero new code |
| Embeddings-backend request/response envelope | A bespoke JSON shape | Mirror `ProviderCompleteRequest`/`ProviderCompleteResponse`'s exact conventions (`app/routes/provider.py`) | Keeps the two narrow gateway endpoints consistent for future maintainers; auth/error-mapping precedent already reviewed and shipped |
| Auth for the new route | New middleware or per-route key check | Existing `APIKeyMiddleware` (global, `app/main.py:44-53`) | Already covers every non-`/health` route; `/provider/complete`'s docstring explicitly notes this — same applies here |

**Key insight:** This phase's actual net-new code surface is small: one settings triplet, one composition.py wiring fix (two call sites), one new route file (~40 lines, template already exists), one new client method (~10 lines, template already exists), and an internals-only edit to one existing function. The temptation is to treat D-08/D-09 as design problems requiring new mechanisms; research shows they are already solved by code that ships today and only need the base_url fix to start actually running instead of silently no-op'ing.

## Common Pitfalls

### Pitfall 1: Fixing only `embeddings.py:14`'s constant, missing `config.py:36`'s field default
**What goes wrong:** CONTEXT.md's D-02 language ("the hardcoded `DEFAULT_LMSTUDIO_BASE_URL`... is the root cause") could be read as "change that one constant." But `composition.py:398` passes `settings.lmstudio_base_url or DEFAULT_LMSTUDIO_BASE_URL` — and `settings.lmstudio_base_url`'s tracked default (`config.py:36`) is **also** `http://host.docker.internal:52415/v1`. The constant is only consulted when `lmstudio_base_url` is falsy (empty string), which it never is (it has a non-empty default). Fixing only the constant changes nothing observable.
**Why it happens:** Two independent "port 52415" values exist in the codebase for historical reasons (the live `.env`'s `LMSTUDIO_BASE_URL` was pointed at exo during the Phase 42 debug session per `exo-model-notfound-502.md`, and that value flows through this same field).
**How to avoid:** The fix must (a) add a new dedicated `embedding_base_url` field (NOT reuse `lmstudio_base_url` — D-04 requires independence from chat) defaulting to `http://host.docker.internal:1234/v1`, and (b) change `composition.py` to construct `Embeddings(...)` from `settings.embedding_base_url` instead of `settings.lmstudio_base_url`. The `DEFAULT_LMSTUDIO_BASE_URL` constant in `embeddings.py` can then either be removed (nothing will ever call `Embeddings()` with a falsy base_url once `embedding_base_url` always has a default) or repointed to LM Studio's `1234` purely as defense-in-depth — recommend removing it and requiring `embedding_base_url` to always be non-empty via its Settings default, since keeping a stale fallback constant around is exactly how this bug was created in the first place.
**Warning signs:** `grep -n "lmstudio_base_url" sentinel-core/app/composition.py` still showing a hit anywhere in the embeddings-construction or embedding-probe code path after the change is a signal the fix is incomplete.

### Pitfall 2: Two existing tests assert the exo-port bug as correct behavior
**What goes wrong:** `sentinel-core/tests/test_embeddings.py::test_default_lmstudio_base_url_is_docker_reachable` (line 135) explicitly asserts `DEFAULT_LMSTUDIO_BASE_URL == "http://host.docker.internal:52415"`. `test_embeddings_falls_back_to_default_base_url_when_falsy` (line 147) asserts the `/v1` normalization against that same wrong constant. If the constant is removed or repointed without updating these tests, they will fail — correctly, but the failure needs to be recognized as "the test was locking in the bug" rather than treated as an unrelated regression.
**Why it happens:** These tests were written during the exo cutover (`T-lmstudio-provider-switch`) when 52415 genuinely was the intended shared chat+embeddings default; Phase 43 makes embeddings independent, invalidating that assumption.
**How to avoid:** Update or delete both tests as part of this phase's own diff (not a follow-up) — per the no-defer rule, a test asserting stale/incorrect behavior discovered while implementing this phase must be fixed in the same change, not deferred.
**Warning signs:** `pytest sentinel-core/tests/test_embeddings.py` failing after the config change is expected and correct; do not "fix" it by reverting the config change.

### Pitfall 3: `probe_embedding_model_loaded()` silently degrades instead of erroring — easy to miss in verification
**What goes wrong:** This function (`model_selector.py:533-587`) returns `False` on *any* exception (wrong host, wrong port, JSON schema mismatch) rather than raising. If `composition.py` isn't also updated to pass `settings.embedding_base_url` here, `embedding_model_loaded` stays `False` even after the `Embeddings()` client itself is correctly repointed — because this is a *second*, independent call site reading the *old* field. The visible symptom would be: `POST /embeddings` works fine (direct call), but the startup sidecar rebuild still skips (WARNING logged, index stays empty) — a partial fix that looks complete under manual smoke-testing of the new route but still fails EMB-04.
**Why it happens:** `probe_embedding_model_loaded` and `Embeddings()` construction are two separate reads of settings in `composition.py` (lines ~395-401 and ~437-445) — easy to update one and miss the other.
**How to avoid:** Grep `composition.py` for every occurrence of `settings.lmstudio_base_url` and `settings.lmstudio_api_key` in the embeddings-adjacent code (both the `Embeddings(...)` construction and the `probe_embedding_model_loaded(...)` call) and confirm both are switched to `embedding_base_url`. A unit test asserting `probe_embedding_model_loaded` is called with `settings.embedding_base_url` (not `lmstudio_base_url`) closes this gap.
**Warning signs:** `/health`'s `embedding_model_loaded` field (see `main.py:105-110`, health payload) still reads `false` after the fix and after LM Studio is confirmed reachable independently.

### Pitfall 4: pf2e's `rules_embedding_model`/`litellm_api_base` config drifting from core's `embedding_model`
**What goes wrong:** Per the recommended "vestigial params" approach (Pattern 3 above), pf2e's `model`/`api_base` arguments to `embed_texts()` stop being forwarded to core (core owns the model now). But pf2e's config.py still carries `rules_embedding_model` (used elsewhere — the *bare* model name is persisted into cached-ruling frontmatter for D-13 reuse-match comparisons per the config.py comment at line 36-39). If an operator changes `EMBEDDING_MODEL` in sentinel-core's `.env` without also updating pf2e's `RULES_EMBEDDING_MODEL`, cached-ruling frontmatter comparisons could silently reference a model name that no longer matches what's actually producing vectors.
**Why it happens:** Two independently-configured "model name" strings for what is now one physical backend, because pf2e's cache-key derivation (`_embedding_hash(model)` in `rule_query.py:73-74`) is a separate concern from vector computation and wasn't in this phase's decision scope to unify.
**How to avoid:** Document this as an operational note (not a code fix — out of scope per D-07/D-06, which keep pf2e's cache logic untouched): both `.env` files must set the same embedding model string. Consider a one-line comment update in pf2e's `config.py` near `rules_embedding_model` noting it must match sentinel-core's `EMBEDDING_MODEL`.
**Warning signs:** Ruling reuse-match cache entries silently stop matching after an operator changes only one side's embedding model config.

### Pitfall 5: nomic instruction prefixes (`search_query:`/`search_document:`) are not used by pf2e today — not a regression to fix, but don't accidentally "fix" it either
**What goes wrong:** `sentinel-core`'s embeddings usage (both `recall.py`'s `NOMIC_QUERY_PREFIX = "search_query: "` and `embedding_sidecar_index.py`'s `NOMIC_DOCUMENT_PREFIX = "search_document: "`) prefixes text before embedding, per nomic-embed-text-v1.5's documented usage convention. pf2e's `embed_texts()` call sites (`main.py`'s corpus-chunk embedding, `rule_query.py`'s query embedding) do **not** apply either prefix — this is pre-existing, unrelated to Phase 43's scope (D-07 keeps pf2e's retrieval logic byte-identical; only the internals of the vector-compute call move to core).
**Why it happens:** pf2e's rules-RAG was built independently of core's Phase-40 semantic-recall work and never adopted the same nomic convention.
**How to avoid:** Do not add these prefixes as part of this phase — that would be an uninstructed behavior change to pf2e's retrieval quality/scoring (D-07 explicitly scopes this out: "only the vector-computation call moves to core"). Flag as an Open Question / follow-up idea only.
**Warning signs:** None for this phase — just don't silently "improve" it while touching `embed_texts()`.

### Pitfall 6: `EmbeddingModelUnavailable` vs generic exceptions at the new route boundary
**What goes wrong:** `embed_texts()` in `sentinel-core/app/clients/embeddings.py` already translates litellm's "No models loaded" `BadRequestError` into `EmbeddingModelUnavailable` (an `InfrastructureError` subclass, `errors.py:156`) but re-raises *every other* exception (connection errors, timeouts, unrelated BadRequestErrors) untouched. The new `POST /embeddings` route must decide what HTTP status those get — `/provider/complete` only catches `ProviderUnavailableError`; anything else propagates as an unhandled 500 (FastAPI's default). Mirror that same narrow-catch posture (catch only `EmbeddingModelUnavailable` → 503) rather than adding a broad `except Exception` that would swallow genuine bugs.
**Why it happens:** Easy to over-engineer the new route's error handling beyond what its precedent (`provider.py`) does.
**How to avoid:** Catch exactly `EmbeddingModelUnavailable` → 503 "Embedding backend unavailable" (never echo the underlying exception text — same T-42-08 rationale already applied to `/provider/complete`, since it could embed `api_base`/`api_key`). Let anything else 500.
**Warning signs:** A test that expects a specific error message leaking internal `api_base`/`api_key` values in the HTTP response body.

## Code Examples

### Settings triplet (mirrors existing `exo_*` pattern)
```python
# Source: sentinel-core/app/config.py (existing exo_* triplet, lines 71-80, to mirror)
# NEW fields to add near embedding_model (line 47):
embedding_base_url: str = "http://host.docker.internal:1234/v1"
"""LM Studio embeddings backend (D-01/D-02). Independent of lmstudio_base_url
(the CHAT backend) and of exo_base_url — embeddings and chat may point at
different backends simultaneously (D-04). Override via EMBEDDING_BASE_URL."""

embedding_api_key: str = ""
"""Optional — litellm requires a non-empty api_key even for local endpoints
that don't validate it; blank defaults to "lm-studio" at the call site
(mirrors the existing lmstudio_api_key blank-default convention)."""

# embedding_model already exists at line 47 — reuse it, no rename needed.
```
Add `embedding_api_key` to the `load_secrets` `secret_map` (config.py:100-109) alongside `exo_api_key`/`lmstudio_api_key` for Docker-secrets parity.

### composition.py wiring fix (both call sites)
```python
# Source: sentinel-core/app/composition.py:395-401 (Embeddings construction) — CHANGE:
if embeddings is None:
    embeddings = Embeddings(
        http_client,
        settings.embedding_base_url,          # was: settings.lmstudio_base_url or DEFAULT_LMSTUDIO_BASE_URL
        settings.embedding_model,
        api_key=settings.embedding_api_key or "lm-studio",   # was: settings.lmstudio_api_key or "lm-studio"
    )

# Source: sentinel-core/app/composition.py:441-445 (probe) — CHANGE:
embedding_model_loaded = await probe_embedding_model_loaded(
    http_client,
    settings.embedding_base_url,   # was: settings.lmstudio_base_url
    settings.embedding_model,
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Embeddings client shares `lmstudio_base_url`/`lmstudio_api_key` with the chat backend | Dedicated `embedding_base_url`/`embedding_api_key` triplet, independent of `ai_provider` | This phase (D-03/D-04) | Chat and embeddings backends can now diverge (exo for chat, LM Studio for embeddings) without one silently breaking the other |
| pf2e computes its own vectors via direct `litellm.aembedding()` | pf2e calls `POST /embeddings` on sentinel-core; core owns the litellm call | This phase (D-06/D-07), mirrors Phase 42's chat handoff | Completes the "everything through Sentinel" gateway pattern for the last drifted subsystem |
| Sidecar index rebuild relies on operator noticing a stale/empty index | Existing non-blocking startup task already handles this; this phase makes it *actually succeed* by fixing the base_url it depends on | Startup task itself shipped in Phase 40; this phase is what makes it functional | No new re-sweep mechanism required — cutover is "restart the container" |

**Deprecated/outdated:**
- `DEFAULT_LMSTUDIO_BASE_URL` constant in `embeddings.py` — recommend removal (or explicit repoint + rename to something that doesn't imply "the" LM Studio default, since there will now be two independently-configured LM Studio-shaped backends: chat's `lmstudio_base_url` at 52415-if-misconfigured-there-too and embeddings' `embedding_base_url` at 1234).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `text-embedding-nomic-embed-text-v1.5` produces 768-dimensional vectors by default on LM Studio | Summary, Pitfall 4, Code Examples | If LM Studio serves a truncated Matryoshka dimension (64-768 configurable per Nomic's own docs) instead of the full 768, the dimension-mismatch guard would treat every entry as mismatched relative to whatever dimension the *query* embed call returns — self-consistent either way since both query and document embeds go through the same backend, so risk is low, but worth a one-time UAT dimension check (`test_lm_studio_embeddings_reachable` already reports `dim=` in its UAT output) |
| A2 | LM Studio's `POST /v1/embeddings` accepts a JSON list for `input` (true batch, one HTTP call for N texts) identically to OpenAI's embeddings API | Standard Stack, Code Examples | If LM Studio's implementation silently rejects list input or processes it sequentially with no behavior change to the caller, no functional impact — only a latency/throughput question, not a correctness one; `[CITED: lmstudio.ai/docs/developer/openai-compat]` confirms OpenAI-format compatibility generally but the fetched doc excerpt did not show the raw request/response JSON verbatim |
| A3 | No operator has already changed the live `.env`'s `EMBEDDING_MODEL`/`EMBEDDING_BASE_URL`-shaped values away from defaults independent of this phase | Code Examples | Low risk — `.env` is not git-tracked; the plan should include a step confirming the live `.env` gets the new `EMBEDDING_BASE_URL=http://host.docker.internal:1234/v1` var (mirroring how `exo-model-notfound-502.md` required a live `.env` edit for `MODEL_NAME`/`MODEL_PREFERRED`) |

**If this table is empty:** N/A — three assumptions logged above; all are low-risk per their own notes.

## Open Questions

1. **Should `embedding_api_key` default to `"lm-studio"` the way `lmstudio_api_key` implicitly does at the call site, or stay blank in Settings and rely on `Embeddings.__init__`'s existing `api_key or "lm-studio"` fallback?**
   - What we know: `Embeddings.__init__` (`embeddings.py:114`) already does `self._api_key = api_key or "lm-studio"` — a blank `embedding_api_key` setting flows through correctly today.
   - What's unclear: whether CONTEXT.md's "Claude's Discretion" bullet ("Whether `embedding_api_key` defaults to the existing `lm-studio` sentinel") wants the default expressed in `config.py` (visible in `.env.example`) or left implicit in the client.
   - Recommendation: leave `Settings.embedding_api_key: str = ""` (blank, matching `lmstudio_api_key`/`exo_api_key`'s existing pattern) and rely on the client-side fallback — consistent with every other provider triplet in the codebase.

2. **Does pf2e's rules corpus (148 chunks per the D-02-step-3 comment) fit under a reasonable `_MAX_TEXTS` cap on the new `/embeddings` route in one batch call?**
   - What we know: `build_rules_index()` calls `embed_fn(texts)` once with the full chunk list (`rules.py:363`).
   - What's unclear: exact current corpus size (comment says "148-chunk" as of Phase 33's docstring; may have grown).
   - Recommendation: set `_MAX_TEXTS` generously (200+) and verify against `len(load_rules_corpus(...))` during planning/execution; do not hardcode a cap below the actual corpus size or the startup rules-index build will 422 against its own gateway.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| LM Studio local server | EMB-02, EMB-03, EMB-04 | Not verifiable from this research session (requires live host check) | — | None — this is the chosen backend (D-01); if unreachable at execution time, `probe_embedding_model_loaded` degrades gracefully (index skip, not crash) but SC-2/SC-3/SC-4 will not be demonstrable until an operator confirms LM Studio is running with the nomic model loaded |
| exo (chat backend, port 52415) | Unaffected by this phase | Presumed available per Phase 42 completion | — | N/A — chat path is out of scope |
| `docker compose` container restart capability | D-09 cutover mechanism | Assumed available (existing deploy pattern per STATE.md) | — | None needed — this is the existing deploy mechanism, not a new dependency |

**Missing dependencies with no fallback:**
- LM Studio serving `text-embedding-nomic-embed-text-v1.5` on port 1234 must be operator-confirmed before SC-2..SC-4 can be verified end-to-end (this mirrors the exact "operator must load a model in exo" blocker documented in `exo-model-notfound-502.md`'s resolution — expect the same operational pattern here: code/config fix ships, full verification is gated on an operator action).

**Missing dependencies with fallback:**
- None — LM Studio is the sole configured backend per D-01 (Ollama is an explicitly deferred fallback per CONTEXT.md, not implemented this phase).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio (`asyncio_mode = "auto"`) — both `sentinel-core/pyproject.toml` and `modules/pathfinder/pyproject.toml` |
| Config file | `sentinel-core/pyproject.toml` (`[tool.pytest.ini_options]`), pf2e equivalent |
| Quick run command | `cd sentinel-core && pytest tests/test_embeddings.py tests/test_embedding_sidecar_index.py tests/test_vault_sweeper.py -x` / `cd modules/pathfinder && pytest tests/test_rule_query.py tests/test_rules_integration.py -x` |
| Full suite command | `cd sentinel-core && pytest` (421+ tests per debug-log baseline) / `cd modules/pathfinder && pytest` |

### Phase Requirement → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EMB-01 | pf2e no longer calls litellm directly for embeddings; `SentinelCoreClient.embed()` exists and is used | unit | `pytest modules/pathfinder/tests/test_rule_query.py -x` (extend to assert `_core_client.embed` called, not `litellm.aembedding`) | ✅ extend existing |
| EMB-01 | `test_ai_agnostic_guardrail`-style check that `modules/pathfinder/app/llm.py` no longer imports `litellm` for embeddings (chat already migrated in Phase 42) | unit | new test asserting no `litellm.aembedding` reference remains in `llm.py` | ❌ Wave 0 — new test, mirrors `sentinel-core/tests/test_ai_agnostic_guardrail.py`'s pattern but pf2e has no equivalent guardrail file yet |
| EMB-02 | `Settings.embedding_base_url` defaults to LM Studio port 1234, independent of `lmstudio_base_url`/`exo_base_url` | unit | `pytest sentinel-core/tests/test_embeddings.py -x` (replace the two exo-asserting tests per Pitfall 2) | ✅ extend existing (replace 2 tests) |
| EMB-02 | `composition.py` constructs `Embeddings(...)` and calls `probe_embedding_model_loaded(...)` with `embedding_base_url`, not `lmstudio_base_url` | unit | new test in a `test_composition.py`-style file (or extend existing composition tests if present) | ❌ Wave 0 — verify whether `sentinel-core/tests/` already has a composition test file to extend |
| EMB-03 | `:pf rule` end-to-end returns non-empty ranked rules, no 503 | integration/manual-only | `LIVE_TEST=1 python scripts/uat_rules.py` (existing `test_lm_studio_embeddings_reachable` + `test_http_rule_flows`) | ✅ existing UAT — requires live LM Studio + live sentinel-core + live pf2e |
| EMB-04 | Core semantic recall returns hits post-cutover (no silent empty-index) | integration/manual-only | Manual: restart sentinel-core container, confirm `/health`'s `embedding_model_loaded: true` and a subsequent `/message` recall query returns non-empty warm-tier hits from the rebuilt sidecar index | ❌ Wave 0 gap — no automated live-recall assertion exists; this is inherently a live-backend check per the existing `LIVE_TEST=1` convention |
| EMB-04 | Dimension-mismatch entries are skipped, not errored | unit | `pytest sentinel-core/tests/test_embedding_sidecar_index.py::test_eligible_entries_skips_stale_model_and_dimension_mismatch -x` | ✅ already exists and passes today |

### Sampling Rate
- **Per task commit:** the relevant quick-run subset above (embeddings.py/embedding_sidecar_index.py/vault_sweeper.py for core changes; rule_query.py/test_rules_integration.py for pf2e changes).
- **Per wave merge:** full suite in both `sentinel-core` and `modules/pathfinder`.
- **Phase gate:** full suite green in both containers, plus a manual/live confirmation of EMB-03/EMB-04 (LM Studio reachable, `:pf rule` query, `/health` embedding_model_loaded field) before `/gsd-verify-work` — these two success criteria are inherently unautomatable without a live LM Studio instance, matching the exact operational-verification pattern already documented in `exo-model-notfound-502.md`.

### Wave 0 Gaps
- [ ] `sentinel-core/tests/test_embeddings.py` — replace `test_default_lmstudio_base_url_is_docker_reachable` and `test_embeddings_falls_back_to_default_base_url_when_falsy` (currently assert the exo-port bug as correct)
- [ ] `sentinel-core/tests/` — new or extended composition-wiring test asserting `Embeddings(...)`/`probe_embedding_model_loaded(...)` read `embedding_base_url`, not `lmstudio_base_url` (check first whether a `test_composition.py` already exists to extend)
- [ ] `sentinel-core/tests/test_ai_agnostic_guardrail.py` — confirm the new `app/routes/embeddings.py` file does not need an `EXCLUDED_PATHS` addition (it should NOT import litellm directly — verify the guardrail test still passes with the new file present, no exclusion needed if written correctly)
- [ ] `modules/pathfinder/tests/` — new test asserting `embed_texts()` calls `_core_client.embed()` (mirrors whatever pattern Phase 42 used to test `complete()` call sites — check `test_rule_query.py`/`test_rules_integration.py` for the Phase 42 precedent of mocking `_core_client`)
- [ ] `scripts/uat_rules.py` — confirm `test_lm_studio_embeddings_reachable`'s hardcoded probe path (`f"{lmstudio_url}/embeddings"`) still matches after the cutover (it targets LM Studio directly, not through core — this UAT function itself needs no change, it's already correct per D-01, but confirm no regression)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes | Existing `APIKeyMiddleware` (`X-Sentinel-Key` header, `main.py:44-53`) already covers the new `/embeddings` route — no new auth code |
| V3 Session Management | no | Stateless service-to-service calls; no session concept in scope |
| V4 Access Control | no | Single shared API key model already in place project-wide; this phase adds no new access-control tier |
| V5 Input Validation | yes | New `EmbeddingsRequest` model must cap `texts` list length and per-text length (mirror `_MAX_MESSAGES`/`_MAX_CONTENT_LENGTH` pattern from `provider.py`) to bound worst-case LLM/embedding-backend cost from a single request |
| V6 Cryptography | no | No new crypto surface; existing secrets (`embedding_api_key`) flow through the already-reviewed Docker-secrets `_read_secret()` mechanism |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Unbounded batch size on `/embeddings` causing worst-case latency/cost DoS | Denial of Service | `Field(min_length=1, max_length=_MAX_TEXTS)` + per-text `max_length` cap, exact mirror of `provider.py`'s existing `_MAX_MESSAGES`/`_MAX_CONTENT_LENGTH` guard (already reviewed/shipped in Phase 42) |
| Leaking internal `api_base`/`api_key` in error responses | Information Disclosure | Catch only the typed `EmbeddingModelUnavailable` exception and return a generic detail string; never echo the underlying litellm/httpx exception text (same T-42-08 precedent already applied to `/provider/complete`) |
| Cross-service SSRF via a client-supplied `api_base` override | Tampering / Elevation of Privilege | Not applicable here — recommend the new route accept only `texts`, never a caller-supplied base_url/model override (D-04's "fully independent of chat, core-owned" already implies this; explicitly do NOT add a `base_url` field to `EmbeddingsRequest`) |

## Sources

### Primary (HIGH confidence)
- `[VERIFIED: local codebase]` `sentinel-core/app/clients/embeddings.py`, `app/config.py`, `app/composition.py`, `app/state.py`, `app/routes/provider.py`, `app/services/recall.py`, `app/services/embedding_sidecar_index.py`, `app/services/vault_sweeper.py`, `app/services/model_selector.py`, `app/errors.py`, `app/main.py` — read directly this session; all line numbers cited above are from these live files.
- `[VERIFIED: local codebase]` `modules/pathfinder/app/llm.py`, `app/main.py`, `app/rule_query.py`, `app/routes/rule.py`, `app/rules.py`, `app/config.py` — read directly this session.
- `[VERIFIED: local codebase]` `shared/sentinel_client.py`, `shared/sentinel_shared/embedding_codec.py` — read directly this session.
- `[VERIFIED: local codebase]` `sentinel-core/tests/test_embeddings.py`, `test_embedding_sidecar_index.py`, `test_vault_sweeper.py`, `test_ai_agnostic_guardrail.py`, `scripts/uat_rules.py` — read directly this session; confirms existing test coverage and the two tests asserting the exo-port bug (Pitfall 2).
- `[VERIFIED: local codebase]` `.planning/debug/exo-model-notfound-502.md` — confirms exo's real failure mode (404 "No instance found for model") and the operational-verification-gated-on-operator-action pattern this phase should expect to repeat.
- `[CITED: docs.litellm.ai/docs/embedding/async_embedding]` `litellm.aembedding()` async signature and list-input usage — via Context7 `/websites/litellm_ai`.

### Secondary (MEDIUM confidence)
- `[CITED: lmstudio.ai/docs/developer/openai-compat/embeddings]` LM Studio's `/v1/embeddings` endpoint is OpenAI-format-compatible, supports the `client.embeddings.create(input=[...], model=...)` batch pattern — fetched this session; exact raw JSON schema for error cases (e.g. "no model loaded") was not present in the fetched excerpt, so the existing codebase's own handling (`embeddings.py`'s `"no models loaded"` string match against litellm's `BadRequestError`) remains the authoritative behavior reference, not the LM Studio docs page.

### Tertiary (LOW confidence)
- `[ASSUMED]` nomic-embed-text-v1.5 defaults to 768-dimensional output on LM Studio (WebSearch-derived, cross-referenced against Nomic's own Matryoshka documentation showing 768 as the default/full dimension) — not verified against a live LM Studio instance this session; the existing UAT (`test_lm_studio_embeddings_reachable`) already reports the live `dim=` value, so this can be confirmed cheaply during execution rather than trusted blindly from research.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; every library involved is already pinned and in production use in this codebase.
- Architecture: HIGH — every route/client/config pattern this phase needs already has a direct, recently-shipped precedent (Phase 42's `/provider/complete` + `SentinelCoreClient.complete()`) to mirror line-for-line.
- Pitfalls: HIGH — root cause traced to exact file:line via direct code reading (not inference), including the subtle two-independent-call-sites bug (Pitfall 3) and the two tests that currently assert the bug as correct (Pitfall 2).

**Research date:** 2026-07-05
**Valid until:** 30 days (internal codebase research; stable unless the codebase itself changes underneath this phase before planning executes)
