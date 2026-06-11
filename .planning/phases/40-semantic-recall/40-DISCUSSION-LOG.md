# Phase 40: Semantic Recall - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-11
**Phase:** 40-Semantic Recall
**Areas discussed:** Data source + ADR reconcile, Cosine floor + RRF merge, Model-mismatch handling, Query embedding input, Index format + atomic write + load, Index freshness + rebuild, Strategy seam shape, Test strategy

---

## Data source + ADR reconcile

| Option | Description | Selected |
|--------|-------------|----------|
| Sidecar index (per MEM-05) | Sweeper maintains `ops/sweeps/embedding-index.json`; SemanticRecall loads it once; zero per-note REST at query time; update ADR-0004 supersession note | ✓ |
| In-place frontmatter (per ADR-0004) | Read `embedding_b64` from each note's frontmatter at query time (O(N) REST); violates MEM-05 | |
| You decide | — | |

**User's choice:** Sidecar index (per MEM-05)
**Notes:** Surfaced a real conflict — ROADMAP/MEM-05 lock a sidecar index, but ADR-0004 (status: proposed) describes in-place frontmatter reads. ROADMAP is the fixed boundary; ADR-0004 to be updated with a supersession note as part of the phase.

| Option | Description | Selected |
|--------|-------------|----------|
| path + embedding + model + content-hash | Most capable; enables model-mismatch skip + incremental rebuild | ✓ |
| path + embedding + model | Enough for query + skip; full rewrite each pass | |
| path + embedding only | Smallest; model read elsewhere, likely defeats no-REST goal | |

**User's choice:** path + embedding + model + content-hash

---

## Cosine floor + RRF merge

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — tunable floor in RecallConfig | Drop notes below a minimum cosine before RRF; conservative default tuned by research/UAT | ✓ |
| No floor — rely on RRF + top_n trim | Let every embedded note into RRF | |
| You decide | — | |

**User's choice:** Yes — tunable floor in RecallConfig

| Option | Description | Selected |
|--------|-------------|----------|
| Top-10 each → RRF → warm_top_n=3 | Smaller pools, less compute | |
| Top-20 each → RRF → warm_top_n=3 | Wider pools, better fusion on larger vaults | ✓ |
| You decide | — | |

**User's choice:** Top-20 each → RRF → warm_top_n=3
**Notes:** RRF algorithm + k≈60 locked by ROADMAP; discussion was only about gating + pool sizes.

---

## Model-mismatch handling

| Option | Description | Selected |
|--------|-------------|----------|
| Silent degrade + log warning | Return empty → keyword-only fallback (WR-03 path) + warning; no user-facing change | ✓ |
| Degrade + surface a re-embed signal | Same fallback plus visible "N notes need re-embedding" signal | |
| You decide | — | |

**User's choice:** Silent degrade + log warning

| Option | Description | Selected |
|--------|-------------|----------|
| Embeddings client model; missing = skip | Active model = Embeddings client id; exact compare; missing embedding_model treated as mismatch | ✓ |
| Config value; missing = include | Dedicated config key; missing model assumed compatible (lenient) | |
| You decide | — | |

**User's choice:** Embeddings client model; missing = skip

---

## Query embedding input

| Option | Description | Selected |
|--------|-------------|----------|
| Full raw message content | Embed whole user message; KeywordRecall keeps _best_search_query | ✓ |
| Same extracted-keywords string | Embed stopword-stripped keywords; discards semantic signal | |
| You decide | — | |

**User's choice:** Full raw message content

| Option | Description | Selected |
|--------|-------------|----------|
| Once per message, no cache | One embed() per recall (cost ADR-0004 already accepted) | |
| Cache query vectors (LRU) | Memoize embeddings keyed by query text | ✓ |
| You decide | — | |

**User's choice:** Cache query vectors (LRU)
**Notes:** Claude specified the cache key as (query text, active model) so a model switch invalidates stale entries; empty/blank query skips embedding.

---

## Index format + atomic write + load

| Option | Description | Selected |
|--------|-------------|----------|
| JSON object keyed by path | Human-inspectable, trivial atomic write, fine at personal scale | ✓ |
| JSONL (one note per line) | Append/stream-friendly; loses whole-file atomicity + keyed lookup | |
| Binary (npz / msgpack) | Smallest/fastest but opaque; overkill now | |

**User's choice:** JSON object keyed by path

| Option | Description | Selected |
|--------|-------------|----------|
| Atomic temp+rename; cache in memory, reload on mtime | Safe write; load once, re-read only when mtime changes | ✓ |
| Atomic temp+rename; re-read every query | Always current, more IO per recall | |
| You decide | — | |

**User's choice:** Atomic temp+rename; cache in memory, reload on mtime

---

## Index freshness + rebuild

| Option | Description | Selected |
|--------|-------------|----------|
| Incremental via content-hash | Only re-embed/update changed notes; carry unchanged forward; prune deleted | ✓ |
| Full rewrite every pass | Re-embed every note each sweep | |
| You decide | — | |

**User's choice:** Incremental via content-hash

| Option | Description | Selected |
|--------|-------------|----------|
| Sweep-only; eventual consistency | Index reflects last sweep only | |
| Sweep + on-demand rebuild trigger | Also rebuild outside the periodic sweep (startup pass / admin endpoint) | ✓ |
| You decide | — | |

**User's choice:** Sweep + on-demand rebuild trigger
**Notes:** Exact on-demand mechanism (startup vs endpoint vs both) deferred to planning.

---

## Strategy seam shape

| Option | Description | Selected |
|--------|-------------|----------|
| Recall holds both; RRF inline in Recall | Recall owns [keyword, semantic] + does RRF; matches ADR "merge is Recall-level" | ✓ |
| HybridRetrieval wrapper behind single seam | Wrapper composes both + RRF; injected as single strategy | |
| You decide | — | |

**User's choice:** Recall holds both; RRF inline in Recall

---

## Test strategy

| Option | Description | Selected |
|--------|-------------|----------|
| FakeVault + fixture index + injected fake embedder | Deterministic; proves paraphrase-hit, floor gating, model-skip, degrade-to-keyword; extends test_recall.py | ✓ |
| Live LM Studio integration test | High fidelity but non-deterministic, slow, needs service | |
| You decide | — | |

**User's choice:** FakeVault + fixture index + injected fake embedder

---

## Claude's Discretion

- Exact default value of the cosine floor (start conservative; tuned via research/UAT).
- Exact on-demand rebuild trigger mechanism (startup pass / admin endpoint / both).
- RRF tie-breaking and precise `RecallConfig` field names for new tunables.
- In-memory index cache layout and LRU cache sizing.

## Deferred Ideas

- Persistent ANN index (FAISS / hnswlib / chroma) — later adapter-only swap behind the seam.
- Binary / JSONL index format — revisit only if JSON size becomes a problem at scale.
- Re-embed surfacing / operator metrics for model mismatch — rejected this phase; possible future observability work.
