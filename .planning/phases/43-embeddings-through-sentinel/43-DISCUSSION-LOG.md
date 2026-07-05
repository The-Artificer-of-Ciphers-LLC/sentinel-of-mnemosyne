# Phase 43: Embeddings Through Sentinel - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-05
**Phase:** 43-embeddings-through-sentinel
**Areas discussed:** Embeddings backend choice, Config independence, pf2e→core handoff shape, Stale-index / re-embed
**Mode:** advisor (research-backed comparison tables; calibration tier: standard; advisor model: sonnet)

---

## A. Embeddings backend choice (SC-2)

| Option | Description | Selected |
|--------|-------------|----------|
| LM Studio nomic | Serve `text-embedding-nomic-embed-text-v1.5` on LM Studio :1234. Already the code default + has a reachability UAT; fix = repoint off exo's 52415. | ✓ |
| Ollama nomic-embed-text | Daemon auto-loads (no GUI), but adds a 3rd local AI service + 2nd nomic identity with no code today. | |
| Dedicated/hosted endpoint | Best quality, no local contention — breaks local-first/offline + privacy. | |

**User's choice:** LM Studio nomic (recommended)
**Notes:** Codebase already targets this implicitly (`_default_model()` → nomic; UAT on :1234). Real fix is the base_url rewire, not a new backend. Ollama kept as fallback if LM Studio's GUI model-loading proves fragile.

---

## B. Config independence (SC-2)

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated `embedding_*` triplet | `embedding_base_url`/`embedding_model`/`embedding_api_key` at composition.py, mirroring Phase 42's exo_*/ollama_* pattern. | ✓ |
| Full `embedding_provider` selector | Reuse Phase 42 `openai_compatible` provider_map/fallback. Purest north-star match but LiteLLMProvider is chat-shaped — retrofitting embed() is scope creep. | |
| Minimal patch | Fix hardcoded base_url + one env var. Smallest diff but reintroduces the "embeddings is the exception" inconsistency; no api_key seam. | |

**User's choice:** Dedicated `embedding_*` triplet (recommended)
**Notes:** It is the Phase 42 framework applied to embeddings, without inventing an embedding-provider abstraction before a 2nd embedding backend justifies it.

---

## C. pf2e→core handoff shape (SC-1)

| Option | Description | Selected |
|--------|-------------|----------|
| Raw `/embeddings` passthrough | core POST /embeddings (texts→vectors) + `SentinelCoreClient.embed()`; pf2e keeps RulesIndex/cosine/503-degrade. Exact mirror of Phase 42 `/provider/complete`. | ✓ |
| Core owns rules RAG | pf2e ships docs/queries; core builds+queries index. Inverts module boundary — core holds pf2e-specific index state. | |
| Hybrid seam | Passthrough now + documented extension point for core-owned retrieval later. Speculative; only if a 2nd RAG consumer is on the roadmap. | |

**User's choice:** Raw `/embeddings` passthrough (recommended)
**Notes:** Literal match to SC-1 and the Phase 42 precedent — core owns AI-vendor access, pf2e keeps rules-domain logic. Only `embed_texts` internals change.

---

## D. Stale-index / re-embed on cutover (SC-3, SC-4)

| Option | Description | Selected |
|--------|-------------|----------|
| Dimension guard + forced re-embed | `embedding_dim` check in SemanticRecall (never cosine across mismatched dims) + forced re-sweep/rebuild on cutover so both indexes work immediately. | ✓ |
| Forced re-sweep, no dim check | One re-embed pass; rely on the `embedding_model` string-skip. No structural guard against same-dim garbage cosine. | |
| Lazy skip only | Rely solely on MEM-05 model-mismatch skip; re-embed over time. Fails SC-3/SC-4 (works only eventually; pf2e index rebuilt at startup, not lazy). | |

**User's choice:** Dimension guard + forced re-embed (recommended)
**Notes:** Only option satisfying "works immediately" (SC-3/SC-4) AND closing the dim-mismatch correctness gap — exo's prior output dim is unverified; nomic is 768.

---

## Claude's Discretion

- Exact route path/verb + request/response schema for `POST /embeddings` (align with `/provider/complete`).
- Exact `embedding_*` field names; how dimension is stored/derived in the sidecar index.
- Re-sweep trigger mechanism (startup hook / CLI / one-shot ops route).
- Whether `embedding_api_key` defaults to the existing `"lm-studio"` sentinel.
- Proposed `EMB-*` requirements family (assigned at planning), mapped to SC-1..SC-4.

## Deferred Ideas

- Embeddings-provider fallback / full provider_map for embeddings (needs a 2nd embedding backend).
- Ollama nomic-embed-text as backend (fallback if LM Studio proves operationally fragile).
- Persistent ANN vector index (deferred per REQUIREMENTS.md; numpy cosine sufficient < ~10k notes).
- Core owning pf2e's rules RAG (rejected — inverts module boundary; revisit only if a 2nd module needs document RAG).
