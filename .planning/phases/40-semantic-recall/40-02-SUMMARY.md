---
phase: 40-semantic-recall
plan: "02"
subsystem: recall
tags: [semantic-recall, rrf, cosine, retrieval-strategy, vault-seam, tdd, hybrid-search]
dependency_graph:
  requires:
    - EMBEDDING_INDEX_PATH (from Plan 01 vault_sweeper.py)
    - NOMIC_DOCUMENT_PREFIX (plan 01 — mirrors NOMIC_QUERY_PREFIX added here)
    - FakeVault.read_note/write_note (tests/fakes/vault.py — unchanged)
  provides:
    - RetrievalStrategy (Protocol)
    - KeywordRecall
    - SemanticRecall
    - _rrf_merge
    - NOMIC_QUERY_PREFIX
    - RecallConfig (7 new fields)
    - Recall.__init__ keyword_strategy / semantic_strategy kwargs
    - Recall._warm_search (rewritten as RRF orchestrator)
  affects:
    - sentinel-core/app/services/recall.py
    - sentinel-core/tests/test_recall.py
    - docs/adr/0004-semantic-recall.md
tech_stack:
  added: [json, time, numpy (existing), sentinel_shared.embedding_codec.decode_embedding, sentinel_shared.similarity.cosine_similarity]
  patterns:
    - RetrievalStrategy Protocol (@runtime_checkable, async search(query, *, budget))
    - TTL-based in-memory index cache via vault.read_note() (D-09 REVISED, REST-only)
    - Bounded dict query-vec cache keyed on (query, active_model) (D-16, Pitfall 9)
    - Model-mismatch skip + all-mismatch silent degrade (D-12/D-13/D-14 + WR-03 reuse)
    - Cosine floor gate before RRF (D-11, semantic_cosine_floor=0.50 default)
    - Reciprocal Rank Fusion k=60 (1/(k+rank_1based) per list)
    - Body-read post-RRF trim (A5 — 3 reads not 20)
    - TDD RED/GREEN per task (Task 2 drove implementation; Task 3 proves 4 success criteria)
key_files:
  created: []
  modified:
    - sentinel-core/app/services/recall.py
    - sentinel-core/tests/test_recall.py
    - docs/adr/0004-semantic-recall.md
decisions:
  - "index_path='ops/sweeps/embedding-index.json' — matches EMBEDDING_INDEX_PATH from Plan 01 exactly; both sides reference the same vault-seam REST path"
  - "TTL-cache (not mtime) for index freshness — vault is REST-only, os.path.getmtime is unavailable; 60s TTL default (index_ttl_seconds) satisfies D-09 REVISED"
  - "SemanticRecall takes vault reference for _load_index_if_stale; bodies read by Recall._warm_search post-RRF (A5) — keeps SemanticRecall single-responsibility"
  - "NOMIC_QUERY_PREFIX='search_query: ' module constant mirrors NOMIC_DOCUMENT_PREFIX in Plan 01 sweeper"
  - "cosine_floor=0.50 default (conservative, UAT-tunable per RESEARCH Pattern 7); note_B cosine≈0.436 is excluded, note_A cosine≈0.90 is included in fixture vectors"
  - "Body-read post-RRF: SemanticRecall returns body='' stubs; Recall reads real bodies for post-RRF survivors only (warm_top_n reads, not semantic_top_k reads)"
  - "ADR-0004 status: proposed -> accepted; supersession note records sidecar-index replaces frontmatter-read approach"
metrics:
  duration: "~25m"
  completed: "2026-06-11"
  tasks_completed: 3
  files_modified: 3
---

# Phase 40 Plan 02: SemanticRecall + RRF Orchestrator Summary

**One-liner:** `RetrievalStrategy` Protocol seam with `KeywordRecall` adapter (verbatim lift) and `SemanticRecall` (TTL-cached sidecar index via vault.read_note, cosine floor, model-mismatch skip) merged via Reciprocal Rank Fusion (k=60) inside `Recall._warm_search`; all 4 phase success criteria proven by deterministic tests with no live LM Studio.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | RecallConfig tunables, RetrievalStrategy Protocol, KeywordRecall adapter | 694d0b9 | `recall.py` |
| 2 RED | Failing tests for SemanticRecall + _rrf_merge behaviors | d2ea834 | `test_recall.py` |
| 2 GREEN | SemanticRecall, _rrf_merge, Recall._warm_search RRF orchestrator | 0b6cf0a | `recall.py` |
| 3 | 6 success-criteria tests + ADR-0004 supersession note | 47e807c | `test_recall.py`, `0004-semantic-recall.md` |

## What Was Built

### RecallConfig — 7 new frozen fields (consumed by Plan 03 composition wiring)

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `semantic_cosine_floor` | float | 0.50 | Cosine floor gate before RRF (D-11, UAT-tunable) |
| `semantic_top_k` | int | 20 | Semantic candidates into RRF (D-10) |
| `keyword_top_k` | int | 20 | Keyword candidates into RRF (D-10) |
| `rrf_k` | int | 60 | RRF k constant (ROADMAP-specified) |
| `semantic_lru_size` | int | 128 | Bounded query-vec cache max size |
| `index_path` | str | `"ops/sweeps/embedding-index.json"` | Vault-seam key for sidecar index (= Plan 01's EMBEDDING_INDEX_PATH) |
| `index_ttl_seconds` | float | 60.0 | TTL for in-memory index cache (REST-only; no mtime) |

### NOMIC_QUERY_PREFIX = "search_query: "

Module constant matching NOMIC_DOCUMENT_PREFIX from Plan 01 sweeper. Prepended to query text before `embed_fn` call so nomic-embed-text-v1.5 sees the task-instruction prefix.

### RetrievalStrategy Protocol

```python
@runtime_checkable
class RetrievalStrategy(Protocol):
    async def search(self, query: str, *, budget: int) -> list[SearchResult]: ...
```

`@runtime_checkable` enables `isinstance(strategy, RetrievalStrategy)` for test assertions.

### KeywordRecall(vault, config)

Verbatim lift of `Recall._warm_search` keyword logic: `_best_search_query` extraction, `relevance_threshold` + `exclude_prefixes` filter, parallel `read_note` per top-budget paths, WR-01 empty-body skip, `SearchResult` construction. Slices to `budget` (not `warm_top_n`) so the RRF pool size is caller-controlled.

### SemanticRecall(vault, *, embed_fn, active_model, config)

**Constructor signature** (Plan 03 composition wiring):
```python
SemanticRecall(
    vault=vault,
    embed_fn=embeddings.embed,
    active_model=settings.embedding_model,  # no "openai/" prefix (D-12)
    config=recall_config,
)
```

**Key behaviors:**
- `_load_index_if_stale()`: monotonic TTL check; reads `vault.read_note(config.index_path)` on stale; JSON parse failure resets `_index = {}` (T-40-05 mitigated)
- `_get_query_vec(query)`: prepends `NOMIC_QUERY_PREFIX`, calls `embed_fn`, bounded dict cache (Pitfall 9)
- `search(query, *, budget)`: blank → `[]` without embed call (D-16); load index; empty → `[]`; get query vec; iterate entries with `exclude_prefixes` fence (T-40-07), exact-string `embedding_model` match (D-12/D-13), `decode_embedding` + `cosine_similarity` + floor gate; all-mismatch warning + `[]` (D-14); sort + slice to budget; return stubs with `body=""`
- Bodies deferred to `Recall._warm_search` post-RRF (A5: ≤ warm_top_n reads, not semantic_top_k reads)

### _rrf_merge(lists, *, k, top_n)

```python
score[path] += 1.0 / (k + rank_1based)  # for each list and each path in that list
```

Tie-break on path string for deterministic ordering. `body` from first list where path appeared. Returns `list[SearchResult]` with RRF scores (downstream consumers use `.body` only).

### Recall._warm_search — RRF Orchestrator

```python
# asyncio.gather with return_exceptions=True (WR-03 reuse)
# → _rrf_merge([kw, sem], k=rrf_k, top_n=warm_top_n)
# → read bodies for post-RRF survivors
# → WR-01 empty-body skip
```

`semantic_strategy=None` → keyword-only graceful mode (Phase-39 behavior preserved exactly). Both strategies run concurrently; exceptions coerced to `[]` with WARNING.

### Recall.__init__ new kwargs

```python
Recall(vault, *, config=None, keyword_strategy=None, semantic_strategy=None)
```

`keyword_strategy` defaults to `KeywordRecall(vault, config)`. `semantic_strategy=None` = semantic disabled (graceful keyword-only). Plan 03 passes `semantic_strategy=SemanticRecall(...)`.

## Test Surface — 22 Tests (all passing)

| Group | Count | Description |
|-------|-------|-------------|
| Phase-39 behavioral | 10 | Original warm/self/sessions/config/empty/WR-01/WR-03 tests |
| Task 2 behaviors | 6 | blank-query, TTL cache, cosine floor, model mismatch, RRF merge, orchestrator integration |
| Task 3 success criteria | 6 | Named tests for all 4 phase success criteria + coverage of tunable floor and degrade path |

**No live LM Studio.** All tests use `FakeVault` with `vault.notes[config.index_path] = json.dumps(make_fixture_index(...))` and deterministic `fake_embedder` returning controlled vectors.

## Cosine Floor Default and Calibration

Default `semantic_cosine_floor = 0.50` is conservative per RESEARCH Pattern 7. Fixture vectors validate the boundary:
- `note_A = [1.0, 0.0, 0.0]`: cosine with query `[0.9, 0.436, 0.0]` ≈ **0.90** → above 0.50 → included
- `note_B = [0.0, 1.0, 0.0]`: cosine with query ≈ **0.436** → below 0.50 → excluded

UAT at 0.50 default; raise to 0.60–0.65 if noise; lower to 0.40 if paraphrases missed. Field in `RecallConfig` (frozen=True) — tunable via composition without code change.

## Body-Read Post-RRF Design

`SemanticRecall.search` returns `SearchResult(path, score, body="")`. `Recall._warm_search` reads real bodies only for the post-RRF survivors (≤ `warm_top_n = 3` reads vs `semantic_top_k = 20` reads). This keeps `SemanticRecall` single-responsibility and avoids reading N=20 notes when only 3 survive RRF.

## REST-Only Constraint Honored

`grep -nE "os\.path\.getmtime|tempfile|os\.replace" sentinel-core/app/services/recall.py` → no matches. Index loaded exclusively via `vault.read_note(self._config.index_path)` through the Vault seam (ADR-0002).

## ADR-0004 Update

Status changed `proposed` → `accepted`. Supersession note records:
- "Read embeddings in place from note frontmatter" language superseded by D-01/D-02 sidecar-index decision
- Explains why: REST-only vault means N per-note reads would violate MEM-05
- Documents the sidecar write path (`vault.write_note` in sweeper) and read path (`vault.read_note` in SemanticRecall + TTL)
- Original design narrative preserved for history

## Deviations from Plan

None — plan executed exactly as written. All acceptance criteria from Tasks 1, 2, and 3 met on first implementation attempt.

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns beyond those in the plan's threat model. All T-40-05 through T-40-08 mitigations implemented:

| Threat | Mitigation |
|--------|------------|
| T-40-05: malformed index JSON | `json.loads` in `try/except` → `{}` on failure; per-entry `.get()` access |
| T-40-06: oversized/empty embedding | `decode_embedding` returns `[]` on failure; zero-length guard before cosine |
| T-40-07: ops/self/_trash paths in index | `exclude_prefixes` fence on index keys before model check |
| T-40-08: cross-model cosine comparison | Exact-string `embedding_model == active_model` (no normalization) |

## Self-Check

### Files exist:
- sentinel-core/app/services/recall.py — FOUND (modified)
- sentinel-core/tests/test_recall.py — FOUND (modified)
- docs/adr/0004-semantic-recall.md — FOUND (modified)

### Commits exist:
- 694d0b9 — feat(40-02): add RecallConfig tunables, RetrievalStrategy Protocol, KeywordRecall adapter
- d2ea834 — test(40-02): add failing RED tests for SemanticRecall, _rrf_merge, RRF orchestrator
- 0b6cf0a — feat(40-02): implement SemanticRecall, _rrf_merge, RRF orchestrator in _warm_search
- 47e807c — test(40-02): add 6 deterministic success-criteria tests; accept ADR-0004 with supersession note

### Tests:
- `cd sentinel-core && uv run pytest tests/test_recall.py -q` → 22 passed
- `grep -nE "os\.path\.getmtime|tempfile|os\.replace" sentinel-core/app/services/recall.py` → no matches
- `grep -c "_rrf_merge" sentinel-core/app/services/recall.py` → 3 (defined + called twice)
- `grep -c "cosine_similarity" sentinel-core/app/services/recall.py` → 2
- `grep -q "accepted" docs/adr/0004-semantic-recall.md` → match
- `grep -qiE "supersed" docs/adr/0004-semantic-recall.md` → match

## Self-Check: PASSED

All created/modified files exist. All 4 commits present in git log. 22/22 recall tests pass. REST-only constraint honored. ADR-0004 accepted with supersession note.
