# ADR-0004 — Semantic recall: a RetrievalStrategy seam inside Recall, and the sweeper's embeddings go live

**Status:** accepted
**Date:** 2026-06-11
**Implemented:** 2026-06-11 (Phase 40, Plans 01–02)
**Related:** ADR-0003 (Recall module), ADR-0002 (Vault seam location)

---

## Supersession Note (D-01/D-02 — Phase 40)

The "read embeddings in place from note frontmatter" data-source language in the original Decision
section below is **superseded** by the sidecar-index decision adopted in Phase 40 Context D-01/D-02:

**Superseded text:** "SemanticRecall reads embeddings **in place** from note frontmatter (the sweeper
already writes them)"

**Superseding decision:**
- The vault sweeper emits a single sidecar index at `ops/sweeps/embedding-index.json` (keyed by
  vault-relative note path; each entry carries `{ embedding_b64, embedding_model, content_hash }`).
- `SemanticRecall` reads this index **once** via `vault.read_note("ops/sweeps/embedding-index.json")`
  and caches it in memory behind a short TTL (60 s default). This produces **zero per-note Obsidian
  REST calls at query time** — satisfying MEM-05.
- The index is persisted through the Vault seam: the sweeper writes it via `vault.write_note()` (a
  single REST PUT per sweep — atomic replace at the API level). No `tempfile`/`os.replace` (the
  vault is REST-only; no Docker volume mount — D-08 REVISED / A6).
- Freshness is maintained by TTL (not local-file mtime, which is unavailable over REST — D-09
  REVISED). One index read per TTL window satisfies MEM-05.
- The per-note `embedding_b64` frontmatter field (written by the sweeper since Phase 38) is still
  maintained but is no longer the retrieval path for SemanticRecall — the sidecar index is the
  canonical source of truth.

**Why changed:** Research confirmed the vault is REST-only (Obsidian Local REST API via Docker;
no local filesystem mount visible to sentinel-core). The "read embeddings in place from frontmatter"
approach would have required N per-note REST reads at query time — directly violating MEM-05. The
sidecar-index + TTL-cache approach satisfies MEM-05 with at most one REST read per TTL window.
The per-entry `embedding_model` field enables exact-string model-mismatch detection (D-12/D-13)
and silent degrade when all entries are stale (D-14 / WR-03 pattern reuse).

**Original design narrative preserved below** — this supersession note records only the data-source
change; the `RetrievalStrategy` Protocol shape, adapter names, and merge-policy decisions are
unchanged and implemented as described.

---

## Context

The Sentinel is "not a second brain" because the one mechanism that would make it one is half-built.
The vault sweeper computes an embedding for every surviving note and writes `embedding_b64` into the
note's YAML frontmatter — but **nothing in `sentinel-core` ever reads it back.** `decode_embedding`
has zero callers in core (its only real use is the separate Pathfinder PF2e rules index). Warm-tier
retrieval is 100% Obsidian's `/search/simple/` BM25 endpoint: conjunctive-AND (every term must match),
negative scores, a `-200` floor. Near-misses and paraphrases are dropped. `vault.find()` returns raw
Obsidian wire dicts, and its own comment (MEM-08) anticipates a "keyword→vector switch."

PRD §9 names "a lightweight vector index" as the eventual retrieval mechanism and says *"start simple
(grep/search), optimize later."* This phase makes the switch real — the embeddings already on disk
become a queryable recall path.

## Decision

Introduce a **`RetrievalStrategy`** seam **inside the `Recall` module** (ADR-0003). The warm search that
ADR-0003 deliberately kept as a private `Recall._warm_search()` (one adapter = a hypothetical seam) is
lifted to an injected strategy now that a **second adapter** justifies it (LANGUAGE.md: two adapters =
a real seam).

- Two adapters: **`KeywordRecall`** (wraps `vault.find()` — today's Obsidian BM25 behavior) and
  **`SemanticRecall`** (embeds the query via the existing `Embeddings` client, decodes each note's
  `embedding_b64` via the currently-dead `decode_embedding`, ranks by cosine).
- The typed **`SearchResult`** that ADR-0003 absorbs at Recall's edge becomes the strategy's return
  type — both adapters emit it. Each strategy owns its own score semantics behind that type
  (BM25's negative floor vs cosine 0–1); `Recall` merges/normalizes into `RecalledContext.warm`.
- `SemanticRecall` reads embeddings **in place** from note frontmatter (the sweeper already writes
  them) — no new store, no Protocol change. Per PRD §9 "start simple": an O(N-notes) scan is fine at
  personal-vault scale; the seam lets a persistent ANN index (FAISS/hnswlib/chroma) replace the scan
  later without touching `Recall`.
- Merge policy (keyword ∪ semantic, deduped by path; or semantic-with-keyword-fallback) is a
  `Recall`-level decision resolved in planning. The seam supports hybrid; the default is not locked here.

### Interface sketch (illustrative — not yet implemented)

```python
class RetrievalStrategy(Protocol):
    async def search(self, query: str, *, budget: int) -> list[SearchResult]: ...

class KeywordRecall:   # vault.find() (Obsidian BM25) -> list[SearchResult]   (today's behavior)
class SemanticRecall:  # embed(query) + cosine over note embedding_b64 (decode_embedding) -> list[SearchResult]

# Recall (ADR-0003) gains an injected strategy; _warm_search() delegates to it:
class Recall:
    def __init__(self, vault: Vault, *, strategy: RetrievalStrategy = KeywordRecall(...)) -> None: ...
```

## Considered Options

- **Keep keyword-only retrieval.** Rejected: it is the cause of the "can't find what I saved" symptom,
  it leaves the per-note embedding cost entirely wasted, and it contradicts the PRD's retrievable-memory
  contract.
- **Build a separate vector store / external service now.** Rejected for this step: the embeddings
  already live in note frontmatter — read them in place first (PRD "start simple"). The strategy seam
  means swapping to an ANN index later is an adapter change, not a `Recall` change.
- **Introduce the strategy seam back in Candidate 1.** Rejected there (ADR-0003): one adapter is a
  hypothetical seam. It belongs here, where `SemanticRecall` is the genuine second adapter.
- **Type `vault.find()` in the Vault Protocol.** Not required: `SemanticRecall` does not go through
  `find()` (it reads frontmatter via existing primitives); `KeywordRecall` keeps using `find()` as-is.
  The Protocol stays unchanged unless a persistent index method is later added.

## Relationship to other ADRs

Depends on **ADR-0003** — the seam lives *inside* `Recall`; this ADR is unplannable until `Recall`
exists. Respects **ADR-0002** — reading embeddings in place uses existing Vault primitives, so
`app/vault.py` does not change. If a persistent index backing is later added, it would be a peer
"future backing" exactly as ADR-0002 anticipates, not a reach past the seam.

## Consequences

- The write↔read gap closes — the sweeper's embeddings become live retrieval data.
- Two adapters make the seam real; recall stops being conjunctive-AND-fragile.
- Cost: one query embedding per message (the `Embeddings` client already exists), and an O(N) cosine
  scan per query until an ANN index is added — acceptable at personal-vault scale, flagged for later.
- Score-threshold reconciliation (BM25 negative floor vs cosine 0–1) moves behind per-strategy
  semantics; `Recall` owns the merge. Resolved in planning.
- `Status: proposed` — design record only; no production code written.
