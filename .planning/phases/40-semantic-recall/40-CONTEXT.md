# Phase 40: Semantic Recall - Context

**Gathered:** 2026-06-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Make the vault sweeper's already-computed note embeddings **live retrieval data**. Introduce a
`RetrievalStrategy` seam **inside the existing `Recall` module** (delivered in Phase 39), with two
adapters — `KeywordRecall` (today's Obsidian BM25 via `vault.find()`) and `SemanticRecall` (cosine
over note embeddings) — and merge their results via Reciprocal Rank Fusion (k≈60) into
`RecalledContext.warm`.

Scope is fixed by ROADMAP / requirements **MEM-03, MEM-04, MEM-05**. This phase does NOT add a new
vault store, modify `app/vault.py`, or build an external vector service (those are explicitly
future / out of scope per ADR-0004).

</domain>

<decisions>
## Implementation Decisions

### Embedding data source (MEM-05)
- **D-01:** `SemanticRecall` reads embeddings from a **sweeper-maintained sidecar index** at
  `ops/sweeps/embedding-index.json`. The index is **loaded once** at query time (cached in memory) —
  **zero per-note Obsidian REST calls at query time**. This honors MEM-05.
- **D-02:** This **supersedes** ADR-0004's "read `embedding_b64` in place from note frontmatter"
  language. Part of this phase's deliverable is updating ADR-0004 with a supersession note recording
  the sidecar-index decision (the ADR is currently `status: proposed`).
- **D-03:** Each index entry carries: `path` + `embedding_b64` + `embedding_model` + a
  **content-hash** (the hash enables incremental rebuild and the model enables the mismatch-skip).

### Sweeper changes
- **D-04:** The sweeper gains responsibility for **emitting `ops/sweeps/embedding-index.json`** and
  for **writing `embedding_model`** per note (today it only writes `embedding_b64` to frontmatter).
- **D-05:** Index rebuild is **incremental via content-hash**: only (re)embed and update entries for
  notes whose content-hash changed since the last pass; carry unchanged entries forward; prune entries
  for trashed/deleted notes.
- **D-06:** Index updates happen on the periodic sweep **and** via an **on-demand rebuild trigger**
  (e.g. a startup pass and/or an admin endpoint). Steady state is eventual consistency — a note edited
  after the last sweep is not semantically findable with fresh content until the next sweep/rebuild.
  *Exact on-demand trigger mechanism (startup vs endpoint vs both) finalized in planning.*

### Index format, write, and load
- **D-07:** On-disk format is a **JSON object keyed by note path**:
  `{ "path/to/note.md": { embedding_b64, embedding_model, content_hash }, ... }`. Human-inspectable,
  git/Obsidian-diff friendly, fine at personal-vault scale. (Binary/JSONL deferred — the seam allows a
  swap later without touching `Recall`.)
- **D-08:** Writes are **atomic**: write to a temp file then `os.replace()`, so `SemanticRecall` never
  reads a half-written index mid-sweep (works alongside the existing sweep lockfile).
- **D-09:** `SemanticRecall` **loads the index once into memory and reloads only when the file mtime
  changes** (not re-read per query).

### Merge / ranking (MEM-04)
- **D-10:** Merge algorithm is **Reciprocal Rank Fusion, k≈60** (locked by ROADMAP). Each strategy
  contributes its **top-20** candidates into RRF; the fused list is capped at the existing
  **`warm_top_n = 3`** for `RecalledContext.warm` (Phase 39's output budget unchanged).
- **D-11:** A **tunable minimum cosine floor** (new field in `RecallConfig`, conservative default,
  tuned via research/UAT) gates semantic candidates *before* they enter the RRF pool — prevents
  weakly-similar notes from surfacing via rank alone. Each strategy keeps its own score semantics
  behind `SearchResult` (BM25 negative floor vs cosine 0–1); `Recall` owns normalization/merge.

### Model-mismatch handling (MEM-05)
- **D-12:** "Active embedding model" = the model id the **`Embeddings` client uses to embed the query**
  (its `_default_model()` / config). Comparison is **exact-string** against each index entry's
  `embedding_model`.
- **D-13:** Index entries with **no/empty `embedding_model` are treated as a mismatch and skipped**
  (safe interpretation of the skip-mismatched-model success criterion).
- **D-14:** When the model is switched and **all** entries mismatch (index full of old-model vectors),
  `SemanticRecall` returns empty and `Recall` **silently degrades to keyword-only + logs a warning** —
  reusing Phase 39's WR-03 graceful-degradation path. No user-facing signal / no re-embed surfacing.

### Query embedding
- **D-15:** `SemanticRecall` embeds the **full raw message content** as the query (natural language is
  the semantic advantage). `KeywordRecall` keeps using `_best_search_query` / `_extract_keywords` — the
  two strategies legitimately see different query forms.
- **D-16:** Query embeddings are **LRU-cached**, keyed by **(query text, active model)** so a model
  switch invalidates stale cache entries. An empty/blank query (e.g. the `/context/{user_id}` debug
  endpoint passes `content=""`) **skips embedding** and returns no semantic results.

### Strategy seam shape
- **D-17:** `Recall` **holds both adapters** (`KeywordRecall`, `SemanticRecall`) and performs the **RRF
  merge inline** — matching ADR-0004's "merge policy is a `Recall`-level decision." Each adapter stays a
  clean single-responsibility `RetrievalStrategy` (Protocol: `async search(query, *, budget) ->
  list[SearchResult]`). A future ANN index just replaces `SemanticRecall` without touching `Recall`.

### Test strategy
- **D-18:** `SemanticRecall` takes an **injected embed function** (mirroring how the sweeper injects
  `embed_texts`), so tests pass a **deterministic fake embedder** returning known vectors plus a
  **fixture `embedding-index.json`** via `FakeVault`. Tests must prove, with no live LM Studio:
  paraphrase/near-synonym returns the right note, cosine-floor gating, mismatched-model skip, and
  degrade-to-keyword. Extends Phase 39's `test_recall.py` surface.

### Claude's Discretion
- Exact default value of the cosine floor (start conservative; research/UAT tunes).
- Exact on-demand rebuild trigger mechanism (D-06) — startup pass, admin endpoint, or both.
- RRF tie-breaking and the precise `RecallConfig` field names for the new tunables.
- Internal layout of the in-memory index cache and the LRU cache sizing.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### ADRs (the design spine)
- `docs/adr/0004-semantic-recall.md` — THIS phase's canonical ADR (RetrievalStrategy seam, two
  adapters). **NOTE:** `status: proposed`; its "read embeddings in place from frontmatter" language is
  **superseded** by D-01/D-02 (sidecar index). Updating this ADR with a supersession note is part of
  the phase deliverable.
- `docs/adr/0003-recall-module.md` — Recall module boundary, `RecalledContext` return contract, scope
  fences. The seam lives *inside* `Recall`.
- `docs/adr/0002-vault-seam-location.md` — Vault seam; must NOT be modified. Reading embeddings uses
  existing Vault primitives / the sidecar index, not a Protocol change.

### Requirements
- `.planning/REQUIREMENTS.md` — **MEM-03** (semantic recall), **MEM-04** (hybrid merge), **MEM-05**
  (sweeper-maintained index, no per-note HTTP at query time, skip mismatched model).

### Core code touched / reused
- `sentinel-core/app/services/recall.py` — `Recall`, `SearchResult`, `RecalledContext`, `RecallConfig`,
  and the private `_warm_search()` that this phase lifts to the injected strategy + RRF merge.
- `sentinel-core/app/services/vault_sweeper.py` — currently writes `embedding_b64`; gains
  `embedding-index.json` emission, `embedding_model` write, and content-hash incremental rebuild.
- `sentinel-core/app/clients/embeddings.py` — `Embeddings` client / `embed_texts`; source of the
  query embedder and the "active model" id.
- `shared/sentinel_shared/embedding_codec.py` — `encode_embedding` / `decode_embedding` (decode is
  currently dead in core; SemanticRecall becomes its first core caller).
- `shared/sentinel_shared/similarity.py` — `cosine_similarity` (reuse for query↔note ranking).
- `sentinel-core/app/routes/status.py` — `/context/{user_id}` debug endpoint (empty-query path, D-16).
- `sentinel-core/tests/test_recall.py` + `sentinel-core/tests/fakes/` (`FakeVault`) — the test surface
  to extend (D-18).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Embeddings` / `embed_texts` (app/clients/embeddings.py): query embedding for `SemanticRecall`; also
  defines the "active model" used for mismatch comparison.
- `decode_embedding` (shared/sentinel_shared/embedding_codec.py): decodes `embedding_b64` from index
  entries — gains its first core-side caller this phase.
- `cosine_similarity` (shared/sentinel_shared/similarity.py): query↔note similarity ranking.
- `RecallConfig` (app/services/recall.py): home for the new tunables (cosine floor, pool sizes).
- `FakeVault` + `test_recall.py`: deterministic test harness to extend.

### Established Patterns
- **Vault seam (ADR-0002):** all persistence goes through the `Vault` Protocol; do not bypass or modify
  `app/vault.py`.
- **Recall owns retrieval policy (ADR-0003):** constants live in `RecallConfig`, not inline (MEM-02).
- **Graceful degradation (Phase 39 WR-03):** per-tier failure → log warning, return empty list. D-14
  reuses this for the all-mismatch / empty-index case.
- **Injected dependencies for testability:** sweeper already injects its embed fn; SemanticRecall
  follows the same pattern (D-18).
- **Sweeper is non-destructive & idempotent:** lockfile sentinel at `ops/sweeps/_in-progress.md`; the
  atomic index write (D-08) fits this.

### Integration Points
- `Recall.__init__` gains the two strategies; `_warm_search()` becomes the RRF orchestration over them.
- `vault_sweeper` gains the index-emission + `embedding_model` write + incremental-rebuild step.
- The sidecar index lives under `ops/sweeps/` — already in `RecallConfig.exclude_prefixes` (`ops/`) and
  already skipped by the sweeper, so it won't pollute recall candidates.

</code_context>

<specifics>
## Specific Ideas

- Index path is exactly `ops/sweeps/embedding-index.json` (ROADMAP-specified).
- RRF constant k≈60 (ROADMAP-specified).
- Query-vector cache keyed on (query text, active model) so model switches invalidate cleanly.

</specifics>

<deferred>
## Deferred Ideas

- **Persistent ANN index (FAISS / hnswlib / chroma):** ADR-0004 anticipates this as a later
  adapter-only swap behind the `RetrievalStrategy` seam. Out of scope now (PRD "start simple" — O(N)
  cosine scan over the in-memory index is acceptable at personal-vault scale).
- **Binary / JSONL index format:** revisit only if JSON size becomes a problem at larger vault scale.
- **Re-embed surfacing / operator metrics** for model-mismatch: explicitly rejected for this phase
  (D-14 stays silent-degrade); could be a future observability phase.

None of the above belong in Phase 40.

</deferred>

---

*Phase: 40-Semantic Recall*
*Context gathered: 2026-06-11*
