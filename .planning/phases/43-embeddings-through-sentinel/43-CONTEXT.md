# Phase 43: Embeddings Through Sentinel - Context

**Gathered:** 2026-07-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Extend Phase 42's **"everything through Sentinel"** restoration from the LLM **chat** path to the **embeddings** path. This is the embeddings-path parallel of the Phase 42 chat handoff.

Three concrete outcomes:
1. **pf2e-module stops embedding directly** — its rules-index embeddings/retrieval are obtained via sentinel-core (removes the direct-litellm drift in `modules/pathfinder/app/llm.py::embed_texts`).
2. **sentinel-core is wired to a real, non-exo embeddings backend** that actually serves `/v1/embeddings` for the configured embedding model.
3. **core's own Phase-40 semantic recall is restored** — it broke during the exo cutover because the embeddings client defaults to exo's port (52415), which returns 405 on `/v1/embeddings`.

**North-star (carried forward from Phase 42, per owner):** sentinel-core is the single AI gateway; domain modules own their local/domain logic and hand off all AI (vendor-SDK) work to core. Embeddings is the **last remaining drift** after Phase 42 migrated chat.

**In scope:**
- Repoint core's embeddings client off exo (port 52415) onto a real embeddings backend (LM Studio nomic).
- Independent embeddings-backend configuration (chat can stay on exo while embeddings run on LM Studio).
- A narrow core `POST /embeddings` passthrough endpoint + `SentinelCoreClient.embed()`; migrate pf2e's `embed_texts` off direct litellm.
- Dimension-mismatch safety + a forced re-embed/re-sweep on cutover so both indexes (core sidecar + pf2e rules) work immediately.

**Out of scope:**
- Persistent ANN vector index (numpy cosine is sufficient at personal-vault scale — deferred per REQUIREMENTS.md).
- Making embeddings its own full `provider_map`/fallback abstraction (rejected below — see D-05).
- Any change to the chat path (Phase 42 is complete).

</domain>

<decisions>
## Implementation Decisions

### Embeddings backend (SC-2)
- **D-01:** The non-exo embeddings backend is **LM Studio serving `text-embedding-nomic-embed-text-v1.5`** on its local server (default `http://host.docker.internal:1234/v1` from containers / `http://localhost:1234/v1` from host). This is already the code's default model (`embeddings.py::_default_model()`) and already has a reachability UAT (`scripts/uat_rules.py::test_lm_studio_embeddings_reachable` targets port 1234).
- **D-02:** The core fix is therefore **narrow — a base_url rewire, not a new backend**: the embeddings `api_base` must move off exo's port 52415 (the hardcoded `DEFAULT_LMSTUDIO_BASE_URL = "http://host.docker.internal:52415"` in `embeddings.py:14` is exo's port and is the root cause of the broken semantic recall). Ollama nomic-embed-text and hosted endpoints were considered and rejected for now (Ollama = a 3rd local daemon + 2nd nomic identity with zero code today; hosted = breaks local-first/privacy). Ollama remains the fallback if LM Studio's GUI-driven model-loading proves operationally fragile.

### Config independence (SC-2)
- **D-03:** Introduce a **dedicated `embedding_*` settings triplet** — `embedding_base_url` / `embedding_model` / `embedding_api_key` — in `sentinel-core/app/config.py::Settings`, wired at the compose root (`composition.py`). This mirrors the Phase 42 per-provider triplet pattern (`exo_*` / `ollama_*` / `llamacpp_*`, D-03 of Phase 42).
- **D-04:** Embeddings selection is **fully independent of the chat `ai_provider`**: chat may run on exo (52415) while embeddings run on LM Studio (1234) simultaneously. The embeddings client must NOT inherit `lmstudio_base_url` or any chat-provider base_url.
- **D-05 (rejected alternative, recorded):** Do **not** retrofit Phase 42's `openai_compatible` `provider_map` / `ProviderRouter` for embeddings in this phase. `LiteLLMProvider` is chat-shaped (`complete()`, stop-sequences); adding an `embed()` contract to it is scope creep with no second embedding backend to justify it. A minimal "just fix the default" patch was also rejected — it reintroduces the "embeddings is the one field without an api_key seam" inconsistency that caused this drift.

### pf2e→core handoff shape (SC-1)
- **D-06:** core exposes a **narrow raw-embeddings passthrough endpoint** — `POST /embeddings` (input: texts → output: list of float vectors) — the direct mirror of Phase 42's `POST /provider/complete`. pf2e calls it via a new `SentinelCoreClient.embed()` (client already exists in `modules/pathfinder/app/llm.py` from Phase 42).
- **D-07:** **pf2e retains ownership of its rules index and retrieval** — chunking, cosine scan, `RulesIndex`, and `_build_rules_index_safely()`'s graceful-503 degrade all stay in pf2e. Only the vector-computation call moves to core (swap `embed_texts`'s internal `litellm.aembedding` for the core HTTP call). Core does NOT own pf2e's rules corpus/index (that would invert the module boundary and give core pf2e-specific state).

### Stale-index / re-embed on cutover (SC-3, SC-4)
- **D-08:** Add an **explicit dimension-mismatch guard** in `SemanticRecall` (`recall.py:413`): never compute cosine across vectors of mismatched dimension — hard-skip (and log) entries whose stored dimension ≠ the active model's. This is strictly stronger than the existing MEM-05 `embedding_model` string-skip (exo's prior output dimension is unverified; nomic is 768-dim).
- **D-09:** Perform a **forced re-embed / re-sweep on cutover** so both indexes are populated and dimensionally consistent *before* SC-3/SC-4 are exercised. A one-time manual trigger is acceptable (owner runs the stack himself). Rationale: "lazy skip only" fails the phase's own success criteria — SC-3/SC-4 require RAG and recall to work *now*, not eventually; and pf2e's in-memory rules index is rebuilt at startup, so "lazy" never applies to it.

### Claude's Discretion
- Exact route path/verb and request/response schema of core's `POST /embeddings` (align with the existing `/provider/complete` conventions).
- Exact `embedding_*` field names and how the dimension is stored/derived in the sidecar index (`embedding_dim` field vs `len(vector)` at read time).
- The mechanism of the forced re-sweep trigger (startup hook, CLI, or a one-shot ops route) — provided both indexes are guaranteed populated on cutover.
- Whether `embedding_api_key` defaults to the existing `"lm-studio"` sentinel.

### Proposed requirements family
- Phase 43 requirements are TBD in ROADMAP.md. Propose an **`EMB-*`** family during planning (e.g. EMB-01 pf2e handoff, EMB-02 non-exo backend config independence, EMB-03 rules-index end-to-end, EMB-04 semantic-recall restored + dim guard) mapped to SC-1..SC-4.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### North-star + phase lineage
- `.planning/phases/42-first-class-exo-provider/42-CONTEXT.md` — the "everything through Sentinel" north-star, the chat-gateway pattern this phase parallels, and the explicit embeddings split rationale (its `<deferred>` section is effectively this phase's charter).
- `.planning/ROADMAP.md` — Phase 43 (goal + SC-1..SC-4) and Phase 4 (AI Provider framework); Phase 42 detail for the `/provider/complete` + `SentinelCoreClient` precedent.
- `docs/adr/0004-semantic-recall.md` — the semantic-recall architecture: sidecar index `ops/sweeps/embedding-index.json` (`{embedding_b64, embedding_model, content_hash}`), TTL-cached read, per-entry model-mismatch skip (MEM-05), `decode_embedding`, RetrievalStrategy seam.

### sentinel-core (code being changed)
- `sentinel-core/app/clients/embeddings.py` — `Embeddings` client + `embed_texts()` + `_default_model()`. **Line 14** `DEFAULT_LMSTUDIO_BASE_URL = "http://host.docker.internal:52415"` is exo's port — the root-cause bug (D-02). Already handles LM Studio "no models loaded" → `EmbeddingModelUnavailable`.
- `sentinel-core/app/config.py` — `Settings`; add the `embedding_*` triplet (D-03). Existing fields: `ai_provider`, `ai_fallback_provider`, `lmstudio_base_url`, `embedding_model`, `ollama_*`, `llamacpp_*`, `exo_*`.
- `sentinel-core/app/composition.py` — compose root; inject the embeddings client's base_url/model/api_key here (D-03/D-04). `build_provider_router()` is the sibling chat wiring (do not entangle embeddings into it — D-05).
- `sentinel-core/app/services/recall.py` — `SemanticRecall` (lines 413–592); add the dimension-mismatch guard (D-08).
- `sentinel-core/app/services/vault_sweeper.py` — `rebuild_embedding_index` (writes the sidecar index); the forced re-sweep path (D-09). Test: `sentinel-core/tests/test_vault_sweeper.py::test_rebuild_embedding_index_writes_index_with_all_fields`.
- `sentinel-core/app/main.py` — where the new narrow `POST /embeddings` route lands (alongside the Phase 42 `/provider/complete`).

### pf2e-module (drift being corrected — embeddings path)
- `modules/pathfinder/app/llm.py` — `embed_texts()` (~lines 410–489): the direct-litellm embeddings drift to migrate onto `SentinelCoreClient.embed()` (D-06). `SentinelCoreClient` already lives here (Phase 42).
- `modules/pathfinder/app/main.py` — `_build_rules_index_safely()`: keeps its graceful-503 degrade; only the embed call underneath changes (D-07).

### exo behavior + verification
- `.planning/debug/exo-model-notfound-502.md` — exo runtime behavior (no `/v1/embeddings`, 404/405 failure mode).
- `scripts/uat_rules.py` — `test_lm_studio_embeddings_reachable` (targets LM Studio `:1234/v1/embeddings` with `text-embedding-nomic-embed-text-v1.5`) — the reachability precheck this phase makes pass.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Embeddings` client / `embed_texts()` (`embeddings.py`): already OpenAI-compatible (`openai/` prefix, `/v1` normalization, `api_key` param present-but-hardcoded). Needs an injected, exo-independent `api_base` (D-02/D-03/D-04), not a rewrite.
- `SentinelCoreClient` (`modules/pathfinder/app/llm.py`): the Phase 42 core HTTP client — gains an `embed()` method (D-06).
- pf2e `RulesIndex` + `_build_rules_index_safely()` + cosine scan: stay as-is; only the embed seam changes (D-07).
- MEM-05 model-mismatch skip in `SemanticRecall`: the dimension guard (D-08) is additive on top of it.

### Established Patterns
- Per-provider settings triplet (`exo_base_url`/`exo_model`/`exo_api_key`, `ollama_*`, `llamacpp_*`) — `embedding_*` follows it (D-03).
- Phase 42 narrow gateway: `POST /provider/complete` (core, domain-agnostic) + `SentinelCoreClient.complete()` (pf2e) — `POST /embeddings` + `.embed()` is the exact mirror (D-06).
- Graceful-degradation on missing capability (`_build_rules_index_safely()` → 503) — preserved (D-07).
- Sidecar-index + TTL-cache + per-entry `embedding_model` (ADR-0004 / MEM-05) — extended with a dimension check (D-08).

### Integration Points
- `composition.py` — embeddings client construction (inject base_url=LM Studio 1234, model, api_key).
- New `POST /embeddings` route in `sentinel-core/app/main.py`.
- Outbound: core → LM Studio `:1234/v1/embeddings`; pf2e → core `/embeddings` (compose `depends_on: sentinel-core healthy` already present).
- Cutover re-sweep touches both `ops/sweeps/embedding-index.json` (via `rebuild_embedding_index`) and pf2e's startup rules-index build.

</code_context>

<specifics>
## Specific Ideas

- LM Studio local server: default port **1234** (`/v1/embeddings`), model `text-embedding-nomic-embed-text-v1.5`, **768 dims** (nomic). Contrast exo on **52415** (chat only, no `/v1/embeddings`).
- The existing UAT `test_lm_studio_embeddings_reachable` (port 1234, nomic model) is the acceptance smoke test SC-2 should make green.
- Owner accepts a one-time manual re-index trigger on cutover (runs the stack himself).
- Owner's Phase 42 design-intent quote still governs: *"the design was everything goes through the sentinel (hence the name) but something drifted and put it in pf2e."* — embeddings is the last such drift.

</specifics>

<deferred>
## Deferred Ideas

- **Embeddings-provider fallback / full `provider_map` for embeddings** — only justified once a second embedding backend exists (e.g. LM Studio ↔ Ollama embedding fallback). Revisit if D-01's LM Studio path proves fragile.
- **Ollama nomic-embed-text as the embeddings backend** — clean headless-daemon alternative; adopt only if LM Studio's GUI model-loading is too operationally fragile for always-on use.
- **Persistent ANN vector index (FAISS/hnswlib/sqlite-vec/chroma)** — deferred per REQUIREMENTS.md; numpy cosine is sufficient below ~10k notes; the RetrievalStrategy seam allows a later swap.
- **Core owning pf2e's rules RAG (index build + query in core)** — rejected for this phase (inverts module boundary); only revisit if a second module needs equivalent document RAG.

None of the above block Phase 43.

</deferred>

---

*Phase: 43-embeddings-through-sentinel*
*Context gathered: 2026-07-05*
