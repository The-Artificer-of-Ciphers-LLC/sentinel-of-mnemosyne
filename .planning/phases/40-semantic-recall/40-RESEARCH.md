# Phase 40: Semantic Recall - Research

**Researched:** 2026-06-11
**Domain:** Python async retrieval, cosine similarity ranking, hybrid search, JSON index, incremental rebuild
**Confidence:** HIGH (all findings grounded in codebase reads; external claims tagged accurately)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01/D-02:** SemanticRecall reads from `ops/sweeps/embedding-index.json` sidecar (zero per-note Obsidian REST calls at query time). Supersedes ADR-0004 "read from frontmatter" language; updating ADR-0004 with supersession note is a phase deliverable.
- **D-03:** Each index entry = `{ embedding_b64, embedding_model, content_hash }` keyed by note path.
- **D-04:** Sweeper gains responsibility for emitting `embedding-index.json` and writing `embedding_model` per note (it already writes `embedding_b64`).
- **D-05:** Incremental rebuild via content-hash: only re-embed notes whose content-hash changed; carry unchanged entries forward; prune entries for deleted/trashed notes.
- **D-06:** Index updates on periodic sweep AND via on-demand rebuild trigger (startup pass and/or admin endpoint — exact mechanism finalized in planning).
- **D-07:** On-disk format: JSON object keyed by path: `{ "path/to/note.md": { embedding_b64, embedding_model, content_hash }, ... }`.
- **D-08:** Atomic write: temp file + `os.replace()` on same filesystem.
- **D-09:** SemanticRecall loads index once into memory; reloads only when file mtime changes.
- **D-10:** Merge = RRF k≈60; each strategy contributes top-20 candidates; fused list capped at `warm_top_n=3`.
- **D-11:** Tunable cosine floor in RecallConfig gates semantic candidates before RRF; each strategy keeps own score semantics.
- **D-12:** Active model = `Embeddings` client's model id; comparison is exact-string against each entry's `embedding_model`.
- **D-13:** Missing/empty `embedding_model` treated as mismatch → skip.
- **D-14:** All-mismatch → SemanticRecall returns empty; Recall silently degrades to keyword-only + warning (reuse Phase 39 WR-03 path).
- **D-15:** SemanticRecall embeds the full raw message content as query. KeywordRecall keeps `_best_search_query`.
- **D-16:** Query embeddings LRU-cached by (query text, active model). Blank query skips embedding → returns no semantic results.
- **D-17:** Recall holds BOTH adapters and does RRF merge inline. Each adapter is a clean `RetrievalStrategy` Protocol: `async search(query, *, budget) -> list[SearchResult]`.
- **D-18:** SemanticRecall takes injected embed function; tests use FakeVault + fixture index + deterministic fake embedder.

### Claude's Discretion

- Exact default value of the cosine floor (start conservative; research/UAT tunes).
- Exact on-demand rebuild trigger mechanism (D-06) — startup pass, admin endpoint, or both.
- RRF tie-breaking and the precise `RecallConfig` field names for the new tunables.
- Internal layout of the in-memory index cache and the LRU cache sizing.

### Deferred Ideas (OUT OF SCOPE)

- Persistent ANN index (FAISS / hnswlib / chroma) — RetrievalStrategy adapter swap, future phase only.
- Binary / JSONL index format.
- Re-embed surfacing / operator metrics for model-mismatch.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MEM-03 | Sentinel recalls relevant vault content by meaning (semantic/vector search over note embeddings), not only exact keyword matches | SemanticRecall + cosine_similarity + decode_embedding from shared lib |
| MEM-04 | Keyword and semantic recall results are merged into one ranked recall set (hybrid retrieval) | RRF k=60 merge inside Recall._warm_search() |
| MEM-05 | Semantic recall reads embeddings from a sweeper-maintained index (no per-note HTTP read at query time) and skips notes whose embedding model no longer matches the active model | embedding-index.json sidecar + mtime cache + exact-string model compare |
</phase_requirements>

---

## Summary

Phase 40 wires the vault sweeper's already-computed note embeddings into live retrieval by introducing a `RetrievalStrategy` Protocol seam inside the existing `Recall` module. The seam has two adapters: `KeywordRecall` (lifting today's `_warm_search()` logic unchanged) and `SemanticRecall` (cosine search over a sweeper-maintained JSON index). Both adapters emit `list[SearchResult]` and `Recall` merges them via Reciprocal Rank Fusion (k=60) before trimming to `warm_top_n=3`.

The sweeper gains three new responsibilities in the same `run_sweep()` flow after step 3 (write-back): write `embedding_model` into each note's frontmatter (it already exists as `_embedding_model_id()`), compute a content-hash per note body, and emit/update `ops/sweeps/embedding-index.json` atomically. The index is the canonical source of truth for SemanticRecall — it never calls Obsidian REST at query time.

The four success criteria are measurable without a live LLM: a deterministic fake embedder returns controlled vectors such that a paraphrase query is geometrically closer to the right note than to others; the index fixture has exactly one entry per controlled path; model-mismatch tests swap the active model string; and the cosine floor test sets the threshold above the known fake similarity score.

**Primary recommendation:** Implement in three clean layers — (1) sweeper index emission, (2) SemanticRecall adapter, (3) Recall RRF orchestration — each independently testable. Do not mix layers.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Semantic similarity ranking | API/Service (`recall.py`) | Shared lib (`similarity.py`) | Recall owns retrieval policy per ADR-0003; cosine math lives in sentinel_shared |
| Embedding index emission | API/Service (`vault_sweeper.py`) | — | Sweeper already owns per-note embedding compute and write |
| Index loading + mtime cache | API/Service (`SemanticRecall`) | — | SemanticRecall owns its own in-memory state |
| RRF merge | API/Service (`Recall`) | — | ADR-0004: merge policy is a Recall-level decision |
| Query embedding (LRU cache) | API/Service (`SemanticRecall`) | Clients (`embeddings.py`) | SemanticRecall calls injected embed fn; Embeddings client provides it |
| Model-mismatch detection | API/Service (`SemanticRecall`) | — | Entry-level filter before cosine scan |
| Atomic index write | API/Service (`vault_sweeper.py`) | OS (`os.replace`) | Standard POSIX atomic rename |
| Active model id source | Clients (`embeddings.py`) | Config (`settings.embedding_model`) | `_default_model()` is the canonical active model id |

---

## Standard Stack

### Core (no new packages required)

| Library | Source | Purpose | Status |
|---------|--------|---------|--------|
| `numpy` | Already in `sentinel-core` (used by vault_sweeper) | Vectorized cosine scan, matrix ops | VERIFIED: already installed |
| `sentinel_shared.similarity.cosine_similarity` | Shared package | Query↔note cosine (overloaded 1D×1D → float, 2D×1D → ndarray) | VERIFIED: codebase read |
| `sentinel_shared.embedding_codec.decode_embedding` | Shared package | Decode base64→list[float] per index entry | VERIFIED: codebase read |
| `functools.lru_cache` | stdlib | LRU cache for query vectors keyed on (query_text, active_model) | VERIFIED: stdlib |
| `hashlib` | stdlib | SHA-256 content-hash for incremental rebuild | VERIFIED: stdlib |
| `tempfile` | stdlib | NamedTemporaryFile for atomic index write | VERIFIED: stdlib |
| `os.replace` | stdlib | Atomic rename (POSIX) — same filesystem as temp file | VERIFIED: stdlib |

**No new packages to install.** All functionality is already available in the project.

---

## Package Legitimacy Audit

> No external packages are being added in this phase. All building blocks are stdlib or already-installed project dependencies.

**Packages removed due to SLOP verdict:** none
**Packages flagged as suspicious:** none

---

## Architecture Patterns

### System Architecture Diagram

```
User message content
        │
        ├──────────────────────────────────────────────────────┐
        │                                                      │
        ▼                                                      ▼
 KeywordRecall                                     SemanticRecall
 _best_search_query()                              embed(search_query: <content>)
        │                                                      │  [LRU cache hit?]
        ▼                                                      ▼
 vault.find(query)                             load_index() [mtime check]
        │                                      for each entry:
        │                                        if embedding_model != active → skip
        ▼                                        decode_embedding(embedding_b64)
 filter(threshold, exclude_prefixes)             cosine_similarity(query_vec, note_vec)
 top-20 SearchResults                           filter(cosine >= cosine_floor)
                                                top-20 SearchResults
        │                                                      │
        └───────────────────┬───────────────────────────────────┘
                            │
                            ▼
                   RRF merge (k=60)
               score[path] += 1 / (60 + rank)
               for each strategy's top-20
                            │
                            ▼
               sort by RRF score desc
               trim to warm_top_n=3
                            │
                            ▼
               RecalledContext.warm [list[SearchResult]]
```

Separately, the vault sweeper runs on schedule or on demand:

```
run_sweep()
     │
     ├── walk_vault → classify → embed surviving bodies
     │
     ├── step 3: write_back per note
     │      fm["embedding_b64"] = encode_embedding(...)
     │      fm["embedding_model"] = _embedding_model_id()       ← NEW
     │      fm["content_hash"] = sha256(rest)                   ← NEW
     │
     └── step 3b (after write_back loop): emit_embedding_index()  ← NEW
            load existing index (or {})
            for each survivor: update entry if hash changed
            prune entries for trashed paths
            atomic write: tempfile → os.replace → ops/sweeps/embedding-index.json
```

### Recommended Project Structure

No new directories required. Changes land in existing files:

```
sentinel-core/app/services/
├── recall.py              # Add: RetrievalStrategy Protocol, KeywordRecall, SemanticRecall, RRF merge
└── vault_sweeper.py       # Add: content_hash write, embedding_model write (already exists in _embedding_model_id), index emission

shared/sentinel_shared/
└── embedding_codec.py     # No change needed — decode_embedding already correct

sentinel-core/tests/
└── test_recall.py         # Extend: 4 new test functions for success criteria + SemanticRecall unit tests

docs/adr/
└── 0004-semantic-recall.md  # Update: supersession note for D-01/D-02, change status proposed→accepted
```

### Pattern 1: RetrievalStrategy Protocol + Two Adapters

**What:** Protocol defines the interface; both adapters satisfy it; Recall holds both.

```python
# Source: ADR-0004 (interface sketch) + CONTEXT.md D-17
from typing import Protocol, runtime_checkable

@runtime_checkable
class RetrievalStrategy(Protocol):
    async def search(self, query: str, *, budget: int) -> list[SearchResult]: ...

class KeywordRecall:
    """Lifts today's _warm_search() logic verbatim."""
    def __init__(self, vault: "Vault", config: RecallConfig) -> None: ...
    async def search(self, query: str, *, budget: int) -> list[SearchResult]: ...

class SemanticRecall:
    """Reads embedding-index.json; embeds query via injected fn."""
    def __init__(
        self,
        index_path: str,           # absolute or vault-relative path to JSON sidecar
        embed_fn: Callable[[list[str]], Awaitable[list[list[float]]]],
        active_model: str,         # exact string from Embeddings._model (sans "openai/" prefix)
        config: RecallConfig,
    ) -> None: ...
    async def search(self, query: str, *, budget: int) -> list[SearchResult]: ...
```

### Pattern 2: RRF Merge

**What:** Combine two `list[SearchResult]` by note path; score = Σ 1/(k + rank_i); rank is 1-based.

**Reference implementation sketch:**

```python
# Source: Choudhury & Fuhr 2009 formula; empirical k=60 from literature [LOW confidence]
def _rrf_merge(
    lists: list[list[SearchResult]],
    *,
    k: int = 60,
    top_n: int = 3,
) -> list[SearchResult]:
    """Reciprocal Rank Fusion over multiple SearchResult lists.

    Each list contributes 1/(k + rank) to each path's cumulative score.
    Paths in only one list still get scored from that list.
    Final list is sorted descending by RRF score, trimmed to top_n.
    The returned SearchResult.score is the RRF score (not BM25 or cosine).
    """
    scores: dict[str, float] = {}
    bodies: dict[str, str] = {}
    for ranked_list in lists:
        for rank_0, result in enumerate(ranked_list):
            rank_1 = rank_0 + 1          # 1-based rank
            scores[result.path] = scores.get(result.path, 0.0) + 1.0 / (k + rank_1)
            bodies.setdefault(result.path, result.body)  # keep first body seen
    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [
        SearchResult(path=path, score=rrf_score, body=bodies[path])
        for path, rrf_score in fused[:top_n]
    ]
```

**Key subtleties:**
- A path in only one list still gets scored (does not need to be in both).
- Tie-breaking when two paths have identical RRF scores: use secondary sort on path string for determinism (important for tests).
- The final `SearchResult.score` carries the RRF score, not the original BM25 or cosine score. Downstream consumers (MessageProcessor) only use `.body`, so this is safe. Document in docstring.
- `warm_top_n` is already in `RecallConfig`; RRF merge uses it directly.

### Pattern 3: SemanticRecall In-Memory Index Cache

**What:** Load `embedding-index.json` once; reload only when file mtime changes. [VERIFIED: codebase — consistent with D-09]

```python
import json
import os
import time
from functools import lru_cache

class SemanticRecall:
    def __init__(self, ...) -> None:
        self._index_path = index_path
        self._index: dict[str, dict] = {}      # keyed by note path
        self._index_mtime: float = 0.0
        # LRU cache for query vectors — keyed on (query_text, active_model)
        # Size 128 handles a session's worth of unique messages without bloat
        self._vec_cache: dict[tuple[str, str], list[float]] = {}

    def _load_index_if_stale(self) -> None:
        """Check mtime; reload only if changed."""
        try:
            mtime = os.path.getmtime(self._index_path)
        except FileNotFoundError:
            self._index = {}
            self._index_mtime = 0.0
            return
        if mtime != self._index_mtime:
            with open(self._index_path, encoding="utf-8") as f:
                self._index = json.load(f)
            self._index_mtime = mtime
```

**Note on `functools.lru_cache` vs manual dict cache:** `lru_cache` does not support async methods or unhashable keys (lists). Use a plain `dict` with an explicit max-size eviction (e.g. pop oldest when len > 128). The LRU requirement is for cache *invalidation on model change*, which is achieved by keying on `(query_text, active_model)` — a model change means a different key, so old entries are simply never hit. Eviction on size prevents unbounded growth.

### Pattern 4: Atomic Index Write (Sweeper)

**What:** Write temp file in same directory as target, then `os.replace()`. [VERIFIED: stdlib + websearch confirmed same-filesystem requirement]

```python
import hashlib
import json
import os
import tempfile
from pathlib import Path

def _write_index_atomic(index: dict, target_path: str) -> None:
    """Atomically write the embedding index JSON to target_path."""
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(index, ensure_ascii=False, indent=None)
    # Same directory → same filesystem → os.replace() is atomic rename on POSIX
    fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(target))
    except Exception:
        os.unlink(tmp_path)   # clean up on failure
        raise
```

**Obs:** `tempfile.mkstemp` is preferred over `NamedTemporaryFile` because it gives an fd before the file has any content, preventing race conditions. Use `os.fdopen` to write through the fd.

### Pattern 5: Content-Hash for Incremental Rebuild

**What:** SHA-256 of the raw note body text (frontmatter-stripped rest, same string already passed to the embedder). [ASSUMED — but consistent with how sweeper already uses `rest` in bodies list]

```python
import hashlib

def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]  # 16 hex chars is plenty
```

Use 16 hex chars (64 bits). Collision probability at personal-vault scale (~10K notes) is negligible. Store as `content_hash` in the index entry.

### Pattern 6: Nomic-embed Prefix Convention

The configured model is `text-embedding-nomic-embed-text-v1.5`. This model requires task instruction prefixes to achieve good embedding quality. [CITED: huggingface.co/nomic-ai/nomic-embed-text-v1.5]

| Task | Prefix |
|------|--------|
| Index vault note bodies | `search_document: <note body>` |
| Embed user query | `search_query: <message content>` |

**Implementation note:** The sweeper already passes raw body text to `embedder(bodies)`. To add the prefix, the sweeper must prepend `"search_document: "` to each body before calling the embedder. Similarly, SemanticRecall must prepend `"search_query: "` to the query before calling `embed_fn`.

**Important:** The stored `embedding_b64` values in existing frontmatter were computed WITHOUT the prefix (the sweeper did not add it). The content-hash-based incremental rebuild will naturally re-embed all existing notes once the prefix is added, because the hash of `"search_document: " + body` differs from the hash of `body` alone. This triggers a full re-embed on first post-upgrade sweep — which is the correct behavior, since prefixless and prefixed embeddings are not comparable.

**D-15 interaction:** SemanticRecall embeds the full raw message (D-15). With the prefix convention, SemanticRecall sends `"search_query: " + content` to `embed_fn`. The content is already the full raw message per D-15 — just prepend the prefix token.

**Claude's Discretion note:** Whether to add the nomic prefix in this phase or defer it (keeping the existing prefix-free convention) is a planning decision. Adding it now is more correct but triggers a full re-embed on first sweep. Deferring keeps backward compat with existing embeddings. Recommend planning note: add prefixes, document the one-time re-embed, and tune cosine floor after re-embed.

### Pattern 7: Cosine Floor Calibration

**What:** A tunable minimum cosine similarity threshold gates semantic candidates before they enter the RRF pool.

**Realistic cosine similarity ranges for nomic-embed-text-v1.5:** [ASSUMED — grounded in general embedding model behavior; verify via UAT]

| Relationship | Expected cosine range |
|--------------|-----------------------|
| Near-paraphrase (same concept, different words) | 0.70–0.90 |
| Topically related (same domain, different concept) | 0.50–0.70 |
| Weakly related / noise | 0.30–0.50 |
| Unrelated | < 0.30 |

**Conservative default:** `0.50` — admits topically related notes while blocking noise. This is a Claude's Discretion value and MUST be UAT-verified. If the live vault produces too many false positives at 0.50, raise to 0.60–0.65. If near-paraphrases are missed, lower to 0.40.

**RecallConfig additions (suggested field names — Claude's Discretion):**

```python
@dataclass(frozen=True)
class RecallConfig:
    # ... existing fields unchanged ...
    semantic_cosine_floor: float = 0.50
    """Minimum cosine similarity for a semantic candidate to enter the RRF pool."""
    semantic_top_k: int = 20
    """Number of top semantic candidates sent into RRF (per D-10)."""
    keyword_top_k: int = 20
    """Number of top keyword candidates sent into RRF (per D-10)."""
    rrf_k: int = 60
    """RRF k constant (smoothing factor). k=60 is the empirically validated default."""
    semantic_lru_size: int = 128
    """Max number of query embeddings cached in-process (keyed on query+model)."""
    index_path: str = "ops/sweeps/embedding-index.json"
    """Relative path to the sweeper-maintained embedding index sidecar."""
```

### Anti-Patterns to Avoid

- **Reading embedding index per query:** SemanticRecall must not open `embedding-index.json` on every `search()` call. The mtime check is O(1); file open + JSON decode is O(N entries). Always use the mtime-gated cache. [VERIFIED: D-09]
- **Calling vault.find() from SemanticRecall:** SemanticRecall reads the sidecar only; it never calls Vault Protocol methods. The Protocol stays unchanged (ADR-0002/ADR-0003). [VERIFIED: CONTEXT.md D-01, ADR-0002]
- **Cross-model RRF:** All RRF candidates must be from the same sweep pass. If SemanticRecall returns empty (all-mismatch), RRF receives `[keyword_results, []]` — the `[]` contributes nothing and the keyword list wins by itself. This is correct behavior. [VERIFIED: D-14]
- **Mutable RecallConfig:** `RecallConfig` is `frozen=True` — all new fields must follow this pattern. [VERIFIED: codebase read]
- **Bypassing Vault seam for index reads:** The index is a plain filesystem file, not an Obsidian note. SemanticRecall reads it directly via `open()` / `os.path.getmtime()`. This is not a Vault seam violation — the sidecar index is an internal operational artifact, not a user-authored vault note. [VERIFIED: ADR-0002 analysis — ADR-0002 governs Obsidian REST access, not internal ops files]
- **Zero-vector inputs to cosine_similarity:** `cosine_similarity` already handles zero-norm vectors (returns 0.0). But embed_fn returning an all-zero vector for blank input must be caught before entering the cosine scan — the blank-query early-exit (D-16) prevents this.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cosine similarity | Custom dot-product loop | `sentinel_shared.similarity.cosine_similarity` | Already handles 1D×1D, 2D×1D, zero-norm; tested in project |
| base64↔float32 decode | Custom struct.unpack | `sentinel_shared.embedding_codec.decode_embedding` | Handles list/ndarray/str inputs; already used by sweeper |
| Atomic file write | `open(target, 'w')` directly | `tempfile.mkstemp` + `os.replace` | Direct write is not atomic; partial write corrupts the index mid-sweep |
| LRU cache | Custom dict with complex eviction | Simple bounded dict (max size check) | `functools.lru_cache` doesn't support async or unhashable keys; simple bounded dict is 10 lines |
| RRF from scratch | Custom ranking algorithm | The 5-line pattern in this research | RRF is a well-understood formula with one subtle off-by-one (rank is 1-based) |

---

## Common Pitfalls

### Pitfall 1: float32 Base64 Decode Byte-Order and Shape

**What goes wrong:** `np.frombuffer(raw, dtype=np.float32)` returns a read-only array on some numpy builds. Callers that mutate it (e.g. `arr /= np.linalg.norm(arr)`) get `ValueError: assignment destination is read-only`.
**Why it happens:** `np.frombuffer` returns a view into the bytes buffer, which is immutable.
**How to avoid:** After `decode_embedding(s)`, wrap in `np.asarray(decoded, dtype=np.float32)` (always returns a mutable copy). The existing `decode_embedding` returns `list[float]`, so `np.asarray(list_result)` already produces a mutable array. Do not call `np.frombuffer` directly in SemanticRecall; delegate to `decode_embedding`.
**Warning signs:** `ValueError: assignment destination is read-only` in cosine_similarity or any normalization path.

### Pitfall 2: numpy dtype mismatch in cosine_similarity

**What goes wrong:** `cosine_similarity` called with mixed dtypes (float32 vs float64) produces a float64 result. The `cosine_similarity` implementation casts both inputs to float32 via `np.asarray(a, dtype=np.float32)`, so this is already handled — but if a future caller bypasses `cosine_similarity` and does raw dot-products, dtype drift can happen.
**How to avoid:** Always use `sentinel_shared.similarity.cosine_similarity`, never raw numpy dot products. The function is the SPOT.

### Pitfall 3: mtime float precision and cache staleness

**What goes wrong:** `os.path.getmtime()` returns a float. On some filesystems (FAT32, some network mounts) mtime has 1-2 second resolution. A sweep that writes the index and a SemanticRecall that checks mtime within the same second may see `mtime == self._index_mtime` and not reload.
**Why it happens:** Sub-second filesystem precision is filesystem-dependent.
**How to avoid:** At personal-vault scale (single Mac, local SSD, HFS+), mtime has nanosecond resolution. This is not a practical problem. Document as a known limitation. For production hardening: store a hash of the file content alongside mtime; reload if either changes. But this adds read overhead — defer until it's observed as a problem.
**Warning signs:** SemanticRecall returns stale results after a sweep completes within a sub-second window.

### Pitfall 4: Empty/Zero-Vector Handling

**What goes wrong:** A blank query bypasses `embed_fn` (D-16), but if a note's `embedding_b64` decodes to an empty list `[]` (e.g. corruption or encode_embedding of an empty list), `np.asarray([])` has shape `(0,)` and dot-product with the query vector raises or returns nonsense.
**Why it happens:** `decode_embedding` returns `[]` on empty string or decode failure (logged at WARNING). The in-memory index still has this entry.
**How to avoid:** After loading and decoding each entry, skip entries where `len(decoded) == 0`. Add a guard:

```python
vec = np.asarray(decode_embedding(entry["embedding_b64"]), dtype=np.float32)
if vec.size == 0:
    logger.warning("skipping entry %r: zero-length embedding", path)
    continue
```

### Pitfall 5: Cross-Model Cosine Comparison

**What goes wrong:** Index has entries from model A; active model is model B. If mismatch check is skipped or case-insensitive, cosine of a model-A embedding against a model-B query vector is geometrically meaningless (spaces are not comparable). Can produce results that happen to have high cosine by chance.
**Why it happens:** Model-string comparison done incorrectly (e.g. lowercase normalization, startswith).
**How to avoid:** Exact-string match per D-12: `entry["embedding_model"] == active_model`. No normalization. If the configured model id changes casing in a future settings update, both sides change together.

### Pitfall 6: Sweep Lockfile + Index Write Race

**What goes wrong:** SemanticRecall is mid-read of `embedding-index.json` when the sweeper starts an atomic write (temp + os.replace). On POSIX, `os.replace()` is atomic — the reader either gets the old file or the new file, never a partial write. This is safe.
**Why it happens:** This is NOT a problem because `os.replace` is atomic on POSIX (POSIX rename is guaranteed atomic). The existing lockfile (`ops/sweeps/_in-progress.md`) prevents overlapping sweeps; it does not need to coordinate with SemanticRecall readers.
**Warning signs:** This pitfall is listed for clarity — it is already correctly handled by the D-08 decision.

### Pitfall 7: Prefix Embedding Incompatibility

**What goes wrong:** Existing frontmatter `embedding_b64` values were computed WITHOUT the `search_document:` prefix. If SemanticRecall queries with `search_query: <content>` but the index still has prefix-free document embeddings, the cosine scores are lower but not zero — the comparison is valid-ish but suboptimal. Worse: if some notes are re-embedded with prefixes and others are not (mid-migration), the index is in a mixed state.
**Why it happens:** Adding prefix convention mid-deployment without a full re-embed.
**How to avoid:** The content-hash incremental rebuild naturally re-embeds everything once the prefix is added to the sweeper (because `"search_document: " + body` has a different hash than `body`). The single-pass re-embed happens on the first live sweep after the upgrade. Document this in planning.

### Pitfall 8: on-demand rebuild trigger and Vault seam

**What goes wrong:** An admin endpoint that directly calls `run_sweep()` or writes to `embedding-index.json` without going through the vault abstraction layer could violate ADR-0002.
**Why it happens:** Confusion about what the Vault seam governs.
**How to avoid:** The Vault seam (ADR-0002) governs Obsidian REST API access (`app/vault.py`). The embedding index is a local filesystem file under `ops/sweeps/` — it is NOT an Obsidian note (not stored via Obsidian REST). Direct filesystem access from `vault_sweeper.py` is already the pattern for the sweep lockfile and sweep log. An on-demand rebuild trigger that calls `run_sweep()` (which goes through the vault client for note reads/writes but uses direct filesystem for the sidecar) is not a seam violation.

### Pitfall 9: `lru_cache` on async or unhashable inputs

**What goes wrong:** Attempting `@lru_cache` on an `async def` method or with a list argument (e.g. `list[str]`) raises `TypeError: unhashable type: 'list'`.
**Why it happens:** `functools.lru_cache` requires all arguments to be hashable.
**How to avoid:** Use a plain bounded dict keyed on `(query_text: str, active_model: str)` — both strings are hashable. The "LRU" eviction property is not strictly necessary; a FIFO-evict-on-max-size dict is sufficient and simpler:

```python
def _get_or_embed(self, query: str) -> list[float]:
    key = (query, self._active_model)
    if key in self._vec_cache:
        return self._vec_cache[key]
    # call embed_fn synchronously wrapped or await it in the async caller
    # ... (this is called from async context)
```

The caller is `async def search()` — query vector fetch must be `await`ed; the cache lookup itself is sync. Populate cache after awaiting embed_fn.

---

## Code Examples

### Exact: Recall._warm_search → RRF orchestration

The current `_warm_search` is a single private method. After refactor:

```python
# Source: CONTEXT.md D-17, D-10, D-11; codebase read of recall.py
async def _warm_search(self, content: str) -> list[SearchResult]:
    """Orchestrate both strategies and merge via RRF."""
    if not content.strip():
        return []

    # Both strategies search concurrently; exceptions degrade gracefully (WR-03 reuse)
    kw_result, sem_result = await asyncio.gather(
        self._keyword_strategy.search(content, budget=self._config.keyword_top_k),
        self._semantic_strategy.search(content, budget=self._config.semantic_top_k),
        return_exceptions=True,
    )

    lists: list[list[SearchResult]] = []
    for result in (kw_result, sem_result):
        if isinstance(result, BaseException):
            logger.warning("retrieval strategy failed: %r", result)
            lists.append([])
        else:
            lists.append(result)

    return _rrf_merge(lists, k=self._config.rrf_k, top_n=self._config.warm_top_n)
```

### Exact: KeywordRecall.search (lifted from _warm_search verbatim)

```python
# Source: recall.py lines 241-294 (verbatim lift)
class KeywordRecall:
    def __init__(self, vault: "Vault", config: RecallConfig) -> None:
        self._vault = vault
        self._config = config

    async def search(self, query: str, *, budget: int) -> list[SearchResult]:
        """Keyword search via vault.find() — today's behavior, unchanged."""
        words = query.split()
        if len(words) > _KEYWORD_SEARCH_THRESHOLD:
            search_q = _best_search_query(query)
        else:
            search_q = query

        search_results = await self._vault.find(search_q)
        relevant = [
            r for r in search_results
            if r.get("score", float("-inf")) >= self._config.relevance_threshold
            and not r.get("filename", "").startswith(self._config.exclude_prefixes)
        ]
        if not relevant:
            return []

        top = relevant[:budget]
        paths = [r.get("filename", "") for r in top]
        raw_contents = await asyncio.gather(
            *[self._vault.read_note(p) for p in paths],
            return_exceptions=True,
        )

        results: list[SearchResult] = []
        for r, path, body in zip(top, paths, raw_contents):
            if isinstance(body, str) and body.strip():
                note_body = body
            else:
                matches = r.get("matches", [])
                note_body = matches[0].get("context", "").strip() if matches else ""
            if not note_body.strip():
                continue
            results.append(SearchResult(path=r["filename"], score=r["score"], body=note_body))
        return results
```

### Exact: SemanticRecall.search skeleton

```python
# Source: CONTEXT.md D-09, D-12, D-13, D-14, D-15, D-16, D-18
class SemanticRecall:
    def __init__(
        self,
        index_path: str,
        embed_fn: Callable[[list[str]], Awaitable[list[list[float]]]],
        active_model: str,
        config: RecallConfig,
    ) -> None:
        self._index_path = index_path
        self._embed_fn = embed_fn
        self._active_model = active_model  # exact string, no "openai/" prefix
        self._config = config
        self._index: dict[str, dict] = {}
        self._index_mtime: float = 0.0
        self._vec_cache: dict[tuple[str, str], list[float]] = {}

    def _load_index_if_stale(self) -> None:
        try:
            mtime = os.path.getmtime(self._index_path)
        except FileNotFoundError:
            self._index = {}
            self._index_mtime = 0.0
            return
        if mtime != self._index_mtime:
            with open(self._index_path, encoding="utf-8") as f:
                self._index = json.load(f)
            self._index_mtime = mtime

    async def _get_query_vec(self, query: str) -> list[float] | None:
        """Embed query with nomic prefix; use LRU dict cache."""
        key = (query, self._active_model)
        if key in self._vec_cache:
            return self._vec_cache[key]
        prefixed = f"search_query: {query}"
        try:
            vecs = await self._embed_fn([prefixed])
            vec = vecs[0] if vecs else []
        except Exception as exc:
            logger.warning("SemanticRecall: embed_fn failed: %r", exc)
            return None
        if not vec:
            return None
        # Bounded cache eviction
        if len(self._vec_cache) >= self._config.semantic_lru_size:
            oldest = next(iter(self._vec_cache))
            del self._vec_cache[oldest]
        self._vec_cache[key] = vec
        return vec

    async def search(self, query: str, *, budget: int) -> list[SearchResult]:
        """Cosine search over in-memory index. Returns empty on blank query or all-mismatch."""
        if not query.strip():
            return []

        self._load_index_if_stale()
        if not self._index:
            logger.warning("SemanticRecall: index is empty or absent at %r", self._index_path)
            return []

        query_vec = await self._get_query_vec(query)
        if query_vec is None:
            return []
        qv = np.asarray(query_vec, dtype=np.float32)

        candidates: list[tuple[float, str, str]] = []  # (cosine, path, body_placeholder)
        matched_model_count = 0

        for path, entry in self._index.items():
            em = entry.get("embedding_model", "")
            if not em or em != self._active_model:
                continue  # D-12/D-13: skip mismatch and missing
            matched_model_count += 1

            raw = decode_embedding(entry.get("embedding_b64", ""))
            if not raw:
                logger.warning("SemanticRecall: zero-length embedding for %r, skipping", path)
                continue
            nv = np.asarray(raw, dtype=np.float32)
            sim = float(cosine_similarity(qv, nv))
            if sim < self._config.semantic_cosine_floor:
                continue
            candidates.append((sim, path, ""))

        if matched_model_count == 0 and self._index:
            logger.warning(
                "SemanticRecall: all %d index entries mismatch active model %r — degrading to keyword-only",
                len(self._index), self._active_model,
            )
            return []  # D-14: silent degrade

        candidates.sort(key=lambda t: t[0], reverse=True)
        top = candidates[:budget]

        # Read note bodies for top candidates (reuse Phase 39 pattern)
        # NOTE: SemanticRecall does NOT have vault access — it needs the caller (Recall)
        # to supply bodies, OR it returns path+score and Recall does the read.
        # Design choice (Claude's Discretion): return stub SearchResults with score only;
        # Recall._warm_search reads bodies after RRF trim. This avoids reading N=20 notes
        # when only warm_top_n=3 survive RRF.
        # For simplicity: SemanticRecall returns path+cosine+body="" and Recall reads bodies
        # for the final top_n results. OR: SemanticRecall reads bodies itself (pre-trim cost).
        # Recommended: Recall reads bodies after RRF (cheaper at N=20 → top_n=3).
        return [
            SearchResult(path=path, score=sim, body="")  # body filled by Recall post-RRF
            for sim, path, _ in top
        ]
```

**Body-read design note (Claude's Discretion):** The sketch above shows SemanticRecall returning `body=""`. The Recall `_warm_search` then reads bodies for the post-RRF top-3. This is cheaper (3 reads vs 20 reads) and avoids giving SemanticRecall a vault reference. The alternative is SemanticRecall accepting a vault reference and reading all 20 bodies pre-RRF. The recommended approach is to delay reads until after RRF trim.

### Exact: Sweeper index emission (new step 3b in run_sweep)

```python
# Source: vault_sweeper.py run_sweep() step 3 location (line ~376); CONTEXT.md D-05, D-07, D-08
# Called immediately after the write_back loop in step 3.

INDEX_PATH = "ops/sweeps/embedding-index.json"

async def _emit_embedding_index(
    vault_client,
    survivors: list[tuple[str, dict, str, object]],
    embeddings: list[list[float]],
    existing_index: dict,
    active_paths: set[str],
) -> dict:
    """Build updated embedding index and write atomically.

    existing_index: previously loaded index (or {}) for carry-forward.
    active_paths: set of paths that survived the sweep (not trashed).
    Returns the new index dict.
    """
    new_index = {}
    # Carry forward unchanged entries (D-05)
    for path, entry in existing_index.items():
        if path in active_paths:
            new_index[path] = entry
        # else: pruned (trashed or missing)

    # Update/insert entries for survivors with embeddings
    for idx, (path, fm, rest, _) in enumerate(survivors):
        if embeddings and idx < len(embeddings):
            content_hash = _content_hash(rest)
            # Only re-embed if hash changed (incremental rebuild D-05)
            existing = existing_index.get(path, {})
            if existing.get("content_hash") == content_hash and existing.get("embedding_model") == _embedding_model_id():
                new_index[path] = existing  # carry forward unchanged
            else:
                new_index[path] = {
                    "embedding_b64": encode_embedding(embeddings[idx]),
                    "embedding_model": _embedding_model_id(),
                    "content_hash": content_hash,
                }

    # Atomic write (D-08)
    _write_index_atomic(new_index, INDEX_PATH)
    return new_index
```

---

## Runtime State Inventory

> This is not a rename/refactor phase. No runtime state inventory required.
> The index file `ops/sweeps/embedding-index.json` does not exist yet — it is created by this phase.

---

## State of the Art

| Old Approach | Current Approach | Relevance |
|--------------|------------------|-----------|
| Conjunctive-AND BM25 (every term must match) | Hybrid: BM25 + cosine over embeddings, merged via RRF | This is exactly what this phase implements |
| O(N) cosine scan | O(N) cosine scan is acceptable at personal-vault scale; ANN (FAISS/hnswlib) when N>10K | ANN is deferred per REQUIREMENTS.md |
| Per-query frontmatter reads | Sidecar index loaded once, mtime-gated cache | D-01/D-09 |

**Deprecated/outdated for this phase:**
- ADR-0004 "read `embedding_b64` in place from note frontmatter" — superseded by D-01/D-02. The ADR must be updated with a supersession note as a phase deliverable.

---

## Validation Architecture

> `nyquist_validation` not explicitly false in config.json — validation section is included.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (already in use; async via pytest-asyncio) |
| Config file | `sentinel-core/pytest.ini` or `pyproject.toml` (check existing setup) |
| Quick run command | `pytest sentinel-core/tests/test_recall.py -x -q` |
| Full suite command | `pytest sentinel-core/tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MEM-03 | Paraphrase query returns correct note via cosine, not BM25 | unit | `pytest sentinel-core/tests/test_recall.py::test_semantic_paraphrase_returns_correct_note -x` | ❌ Wave 0 |
| MEM-03 | SemanticRecall reads index sidecar — zero Obsidian REST at query time | unit | `pytest sentinel-core/tests/test_recall.py::test_semantic_recall_no_vault_call -x` | ❌ Wave 0 |
| MEM-04 | Keyword + semantic results merged via RRF before warm list returned | unit | `pytest sentinel-core/tests/test_recall.py::test_rrf_merge_combines_both_strategies -x` | ❌ Wave 0 |
| MEM-05 | SemanticRecall skips notes whose embedding_model != active model | unit | `pytest sentinel-core/tests/test_recall.py::test_semantic_skips_mismatched_model -x` | ❌ Wave 0 |
| MEM-05 | All-mismatch degrades to keyword-only silently (reuse WR-03 path) | unit | `pytest sentinel-core/tests/test_recall.py::test_semantic_all_mismatch_degrades -x` | ❌ Wave 0 |
| MEM-05 | Cosine floor gates weak candidates out of RRF pool | unit | `pytest sentinel-core/tests/test_recall.py::test_cosine_floor_excludes_weak_candidates -x` | ❌ Wave 0 |
| MEM-05 | Sweeper writes embedding_model to index (verified via fixture index) | unit | `pytest sentinel-core/tests/test_vault_sweeper.py::test_sweep_writes_embedding_model_to_index -x` | ❌ Wave 0 |

### Success Criteria → Test Mapping

| Success Criterion | Test |
|-------------------|------|
| 1. Paraphrase query returns note in warm (keyword-only would miss it) | `test_semantic_paraphrase_returns_correct_note`: fake embedder returns deterministic vectors where query_vec is close to note_A_vec but NOT to note_B_vec; fake keyword search returns only note_B; fused result includes note_A. |
| 2. SemanticRecall reads from embedding-index.json, no per-note Obsidian REST | `test_semantic_recall_no_vault_call`: mock vault.find with a counter; SemanticRecall's search() is called directly with a fixture index file; vault.read_note call count remains at post-RRF trim count only. |
| 3. Notes with mismatched embedding_model skipped | `test_semantic_skips_mismatched_model`: fixture index has entries with model="old-model"; active_model="new-model"; search returns []. |
| 4. RRF merge produces unified warm list | `test_rrf_merge_combines_both_strategies`: keyword returns [A, B], semantic returns [C, A]; fused result has A ranked first (appeared in both lists = highest RRF score), then C and B. |

### Deterministic Fake Embedder Pattern

```python
# Source: CONTEXT.md D-18; test pattern recommendation
import numpy as np
from sentinel_shared.embedding_codec import encode_embedding

def make_fixture_index(note_paths: list[str], note_vecs: list[list[float]], model: str) -> dict:
    """Build a fixture embedding-index.json dict for tests."""
    return {
        path: {
            "embedding_b64": encode_embedding(vec),
            "embedding_model": model,
            "content_hash": "deadbeef00000000",
        }
        for path, vec in zip(note_paths, note_vecs)
    }

# In a test:
# note_vec = [1.0, 0.0, 0.0]  # note A lives on x-axis
# query_vec = [0.9, 0.436, 0.0]  # query is close to note A (cosine ≈ 0.9)
# unrelated_vec = [0.0, 1.0, 0.0]  # note B lives on y-axis (cosine with query ≈ 0.44)

async def fake_embedder(texts: list[str]) -> list[list[float]]:
    """Return deterministic vectors based on text content."""
    results = []
    for text in texts:
        if "search_query:" in text:
            results.append([0.9, 0.436, 0.0])   # query vector
        else:
            results.append([1.0, 0.0, 0.0])     # note vector (won't be called for docs)
    return results
```

**How to write a fixture index file for test isolation:**

```python
import json, os, tempfile

def write_fixture_index(index: dict) -> str:
    """Write fixture index to a temp file; return path."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(index, f)
    return path
```

### Sampling Rate

- **Per task commit:** `pytest sentinel-core/tests/test_recall.py -x -q`
- **Per wave merge:** `pytest sentinel-core/tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `sentinel-core/tests/test_recall.py` — extend with 6 new test functions (all MEM-03/04/05 above)
- [ ] Fixture index helper (inline in test file or in `tests/fakes/`)
- [ ] `test_vault_sweeper.py` — extend with index emission test

---

## Security Domain

> This phase adds no authentication, session management, or access control. It reads a local sidecar file and calls an already-injected embed function. ASVS review is minimal.

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes | Blank query early-exit; decode_embedding returns [] on failure; cosine floor prevents noise candidates |
| V6 Cryptography | no | SHA-256 for content-hash is non-cryptographic here (collision resistance only); no secrets involved |

**Known Threat Patterns:**

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed embedding-index.json (injection via vault note content) | Tampering | json.load raises on invalid JSON; IndexError / KeyError on missing fields must be caught per-entry |
| Path traversal via index keys | Tampering | Index keys are vault-relative paths; SemanticRecall reads bodies via Recall (which uses Vault Protocol); index keys that start with exclude_prefixes are still filtered by KeywordRecall's exclude_prefixes logic. SemanticRecall should also apply exclude_prefixes to index keys. |

---

## Open Questions

1. **Nomic prefix in this phase?**
   - What we know: nomic-embed-text-v1.5 requires `search_document:`/`search_query:` prefixes for best quality. Existing embeddings in frontmatter are prefix-free.
   - What's unclear: whether to add prefixes now (triggering a one-time re-embed on first sweep) or defer to a follow-on cleanup phase.
   - Recommendation: Add prefixes in this phase. The content-hash incremental rebuild handles the re-embed naturally. Document the one-time sweep requirement. Tune cosine floor after re-embed.

2. **On-demand rebuild trigger mechanism (D-06)**
   - What we know: D-06 says "startup pass and/or admin endpoint"; exact mechanism is Claude's Discretion for planning.
   - What's unclear: whether to add an admin endpoint (more flexible, requires route) or just call `run_sweep()` on startup (simpler, but adds startup latency).
   - Recommendation: Add a startup pass (non-blocking, via `asyncio.create_task`) AND expose a `POST /vault/sweep/rebuild-index` admin endpoint. The startup pass catches cold-start gaps; the endpoint supports manual refresh.

3. **SemanticRecall body-read responsibility**
   - What we know: SemanticRecall can return `body=""` (deferring reads to Recall post-RRF), or it can read all 20 candidate bodies before returning.
   - What's unclear: which layer owns the vault.read_note calls for semantic candidates.
   - Recommendation: Recall reads bodies after RRF trim (3 reads vs 20). SemanticRecall returns SearchResult with `body=""` and a non-zero score. Recall's `_warm_search` reads bodies for the final top-3 after merge. This requires Recall to call `vault.read_note` for semantic results — same as it does for keyword results today. Clean and cheap.

4. **`index_path` as absolute vs vault-relative**
   - What we know: The sweeper writes the index to the vault (via `client.write_note(log_path, ...)`). But `write_note` goes through Obsidian REST. The sidecar should be a plain filesystem file (for mtime-based cache and atomic write).
   - What's unclear: where the index file lives on disk. If the vault is the Obsidian vault directory on the Mac's filesystem, `ops/sweeps/embedding-index.json` is a path within that directory. If the sweeper writes it via Obsidian REST (`write_note`), SemanticRecall cannot do a local filesystem `os.path.getmtime` on it.
   - Recommendation: The embedding index must be written as a local filesystem file (direct `open()`), NOT via Obsidian REST. The sweeper must know the local vault path (env var or config) to compute the absolute path for the temp-write. Alternatively, it can write to a path within the Docker container's mounted vault volume. This is a configuration concern — planning must address how `index_path` is configured (env var vs hardcoded default under a configurable `VAULT_PATH`).

5. **`active_model` string in SemanticRecall**
   - What we know: `Embeddings._model` stores `"openai/text-embedding-nomic-embed-text-v1.5"` (with provider prefix). The sweeper writes `_embedding_model_id()` which returns `settings.embedding_model` (WITHOUT provider prefix, e.g. `"text-embedding-nomic-embed-text-v1.5"`).
   - What's unclear: SemanticRecall must compare against the SAME string that the sweeper writes into `embedding_model`. The sweeper uses `_embedding_model_id()` which returns `settings.embedding_model` (no prefix). SemanticRecall must receive the no-prefix version for comparison.
   - Recommendation: SemanticRecall's `active_model` parameter is sourced from `settings.embedding_model` (no prefix), not from `Embeddings._model`. In `composition.py`: `SemanticRecall(..., active_model=settings.embedding_model, ...)`. The sweeper writes the same value via `_embedding_model_id()`. This is consistent.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| numpy | SemanticRecall cosine scan | ✓ | already installed in sentinel-core | — |
| hashlib | Content-hash incremental rebuild | ✓ | stdlib | — |
| tempfile + os.replace | Atomic index write | ✓ | stdlib | — |
| LM Studio (embedding model) | Live UAT of cosine floor | ✗ (not checked) | runtime | UAT-only; tests use fake embedder |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Default cosine floor of 0.50 is appropriate for nomic-embed-text-v1.5 | Cosine Floor Calibration | Too low → noise in warm results; too high → semantic recall misses real paraphrases. UAT tunes it. |
| A2 | Nomic-embed GGUF on LM Studio respects `search_query:` prefix in the same way as the HF model | Nomic Prefix Convention | If LM Studio ignores prefixes, quality is still okay (just suboptimal). Risk is LOW. |
| A3 | `content_hash` of the frontmatter-stripped `rest` variable (used by the embedder) is the right thing to hash for incremental rebuild | Content-Hash section | If raw body (including frontmatter) is hashed instead, frontmatter-only edits trigger unnecessary re-embeds but correctness is preserved. Risk is LOW. |
| A4 | `os.path.getmtime()` precision is adequate on macOS local SSD for mtime-based cache invalidation | Pitfall 3 | Sub-second resolution edge case — essentially irrelevant at personal-vault scale with normal sweep intervals. Risk is LOW. |
| A5 | SemanticRecall should return `body=""` and let Recall read bodies post-RRF | Open Question 3 | If this is wrong, Recall must pass a vault reference to SemanticRecall, which complicates dependency graph. Easily reversible. |
| A6 | The embedding index is written as a local filesystem file, not via Obsidian REST | Open Question 4 | If Obsidian vault is only accessible via REST (no local mount), local filesystem write fails. High risk — must be confirmed in planning. |

---

## Sources

### Primary (HIGH confidence — codebase reads)
- `sentinel-core/app/services/recall.py` — full content; SearchResult, RecallConfig, Recall, _warm_search, WR-03 pattern
- `sentinel-core/app/services/vault_sweeper.py` — full content; run_sweep flow, _embedding_model_id, encode_embedding, step 3 write-back location
- `sentinel-core/app/clients/embeddings.py` — Embeddings class, _default_model(), embed_texts, model prefixing convention
- `shared/sentinel_shared/embedding_codec.py` — decode_embedding/encode_embedding exact behavior
- `shared/sentinel_shared/similarity.py` — cosine_similarity overload, zero-norm handling
- `sentinel-core/tests/test_recall.py` — existing test surface, WR-01/WR-03 tests
- `sentinel-core/tests/fakes/vault.py` — FakeVault API surface, notes dict, find() behavior
- `sentinel-core/app/composition.py` — Recall/Embeddings construction, AppGraph
- `sentinel-core/app/config.py` — embedding_model default, settings structure
- `docs/adr/0003-recall-module.md` — ADR-0003 Recall module contract
- `docs/adr/0004-semantic-recall.md` — ADR-0004 original language (now superseded by D-01/D-02)
- `.planning/phases/40-semantic-recall/40-CONTEXT.md` — all 18 locked decisions

### Secondary (MEDIUM confidence — web search confirmed on authoritative source)
- [nomic-ai/nomic-embed-text-v1.5 on Hugging Face](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) — prefix convention (search_query:/search_document:) confirmed as required
- RRF formula Σ 1/(k+rank_i), k=60 empirical optimum — confirmed across multiple sources including [Azure AI Search documentation](https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking)

### Tertiary (LOW confidence — web search only)
- Cosine similarity ranges for nomic-embed in RAG contexts (A1 assumption)
- os.replace + tempfile atomic write pattern (well-established but not verified against Python docs directly)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in project; no new packages
- Architecture patterns: HIGH — grounded in codebase reads + ADR analysis
- RRF formula: MEDIUM — confirmed via web search on authoritative sources (Azure AI Search uses same formula)
- Cosine floor default: LOW — ASSUMED; must be UAT-verified
- Nomic prefix behavior on LM Studio GGUF: LOW — ASSUMED; indirect evidence from HF model card

**Research date:** 2026-06-11
**Valid until:** 2026-07-11 (stable domain; numpy/json/os are not fast-moving)
