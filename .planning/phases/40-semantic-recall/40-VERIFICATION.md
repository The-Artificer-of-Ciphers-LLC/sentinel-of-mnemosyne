---
phase: 40-semantic-recall
verified: 2026-06-11T00:00:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification: false
gaps: []
human_verification:
  - test: "Trigger a live sweep with a real Obsidian vault and then issue a paraphrase query via Discord"
    expected: "The note semantically matching the query appears in RecalledContext.warm even though keyword search would not return it"
    why_human: "Requires a live LM Studio embedding endpoint, a live Obsidian vault, and a real query — no deterministic programmatic proxy"
  - test: "Verify the .json path is accepted by the Obsidian Local REST API PUT /vault/ops/sweeps/embedding-index.json"
    expected: "The PUT returns 2xx and a subsequent GET retrieves the same JSON body unchanged"
    why_human: "The FakeVault round-trip test is authoritative for the seam contract; live Obsidian behavior is the outstanding UAT item documented in Plan 01"
---

# Phase 40: Semantic Recall Verification Report

**Phase Goal:** A `RetrievalStrategy` seam inside `Recall` with two adapters (`KeywordRecall` wrapping Obsidian BM25 and `SemanticRecall` reading note embeddings); the vault sweeper's per-note embeddings become live retrieval data via a sweeper-maintained `ops/sweeps/embedding-index.json` sidecar; keyword and semantic results merged via Reciprocal Rank Fusion (k=60).
**Verified:** 2026-06-11
**Status:** passed (automated evidence complete; 2 UAT items require a live vault)
**Re-verification:** No — initial verification

---

## Step 0: Previous Verification

None found. Initial mode.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A paraphrase/near-synonym query returns that note in `RecalledContext.warm` (keyword-only would miss it) | VERIFIED | `test_semantic_paraphrase_returns_correct_note` (line 517) and `test_end_to_end_paraphrase_recall` (line 778) both pass — fake embedder places query vector near `notes/a.md`, vault.find returns only `notes/b.md`; after RRF, `notes/a.md` is in warm with a real body |
| 2 | `SemanticRecall` reads embeddings from `ops/sweeps/embedding-index.json` — NO per-note Obsidian REST call at query time (reads index once via vault.read_note + TTL cache; index written by sweeper via vault.write_note — REST-only, no local filesystem) | VERIFIED | `_load_index_if_stale()` calls `await self._vault.read_note(self._config.index_path)` (recall.py:367) with a monotonic TTL guard; `write_note(EMBEDDING_INDEX_PATH, ...)` is the sole persistence call in vault_sweeper.py:340; `test_semantic_recall_no_per_note_rest` (line 560) asserts read_note call count ≤ 1 across two back-to-back searches within TTL; grep confirms no `tempfile`/`os.replace`/`os.path.getmtime` in either file |
| 3 | Notes whose `embedding_model` does not match the active embedding model are skipped; all-mismatch returns `[]` silently | VERIFIED | `SemanticRecall.search` line 471-474: exact-string `if not em or em != self._active_model: continue`; matched_model_count tracked; all-mismatch warning + `return []` at line 519-527; proven by `test_semantic_skips_mismatched_model` (line 616) and `test_semantic_all_mismatch_degrades_to_keyword` (line 643), both passing |
| 4 | Keyword and semantic results merged into one ranked list via RRF (k=60) before being returned in `RecalledContext.warm` | VERIFIED | `_rrf_merge()` implemented at recall.py:542-573; `RecallConfig.rrf_k = 60` (line 199); `_warm_search` calls `_rrf_merge(lists, k=self._config.rrf_k, top_n=self._config.warm_top_n)` (line 677); `test_rrf_merge_combines_both_strategies` (line 743) and `test_recall_warm_search_uses_rrf_when_both_strategies_present` (line 478) pass |

**Score: 4/4 truths verified**

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `sentinel-core/app/services/recall.py` | `RetrievalStrategy` Protocol, `KeywordRecall`, `SemanticRecall`, `_rrf_merge`, 7 new `RecallConfig` fields, `NOMIC_QUERY_PREFIX` | VERIFIED | All symbols present and substantive; `class SemanticRecall` at line 312, `class KeywordRecall` at line 256, `_rrf_merge` at line 542, `RetrievalStrategy` Protocol at line 236, `NOMIC_QUERY_PREFIX = "search_query: "` at line 228, all 7 `RecallConfig` fields confirmed |
| `sentinel-core/app/services/vault_sweeper.py` | `EMBEDDING_INDEX_PATH`, `NOMIC_DOCUMENT_PREFIX`, `_content_hash`, `_emit_embedding_index` | VERIFIED | All 4 symbols present — lines 77, 85, 113, 261 respectively; `_emit_embedding_index` is 84 lines of substantive logic including read, incremental carry-forward, prune, and write |
| `sentinel-core/tests/test_recall.py` | `make_fixture_index`, 6+ success-criteria deterministic tests | VERIFIED | 25 test functions total; the 6 named Plan-02 tests + 2 Plan-03 end-to-end tests all present and passing; `make_fixture_index` helper confirmed at test_recall.py |
| `sentinel-core/tests/test_vault_sweeper.py` | 6 index-emission tests including incremental rebuild, prune, document prefix, round-trip | VERIFIED | 6 new tests at lines 656–883: `test_sweep_emits_embedding_index`, `test_sweep_writes_embedding_model_to_index`, `test_sweep_index_incremental_carry_forward`, `test_sweep_index_prunes_trashed`, `test_sweep_embeds_with_document_prefix`, `test_index_path_roundtrips_through_vault_seam` — all passing |
| `sentinel-core/app/composition.py` | `SemanticRecall` wired with `active_model=settings.embedding_model`; `Embeddings` before `Recall`; `asyncio.create_task` startup rebuild | VERIFIED | Lines 329-335: `_semantic = SemanticRecall(vault, embed_fn=embeddings.embed, active_model=settings.embedding_model, config=_config)` then `recall = Recall(vault=vault, config=_config, semantic_strategy=_semantic)`; `embeddings` block at line 314 is before `recall` block at line 322; `asyncio.create_task(_startup_rebuild())` at line 457 |
| `sentinel-core/tests/test_composition.py` | Wiring assertion: built `Recall` carries `SemanticRecall` with no-prefix `active_model` | VERIFIED | `test_build_application_wires_semantic_recall_with_no_prefix_active_model` at line 254, passing |
| `docs/adr/0004-semantic-recall.md` | Supersession note + `Status: accepted` | VERIFIED | Line 3: `**Status:** accepted`; line 13: `section below is **superseded** by the sidecar-index decision adopted in Phase 40 Context D-01/D-02` |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `vault_sweeper.run_sweep` | `ops/sweeps/embedding-index.json` | `client.write_note(EMBEDDING_INDEX_PATH, ...)` after step-3 write-back | WIRED | vault_sweeper.py:340 — single REST PUT inside `_emit_embedding_index`, guarded by `not dry_run`; called at line 520 |
| `SemanticRecall._load_index_if_stale` | `ops/sweeps/embedding-index.json` | `vault.read_note(self._config.index_path)` with TTL | WIRED | recall.py:367 — reads through Vault seam; `config.index_path = "ops/sweeps/embedding-index.json"` matches `EMBEDDING_INDEX_PATH` |
| `Recall._warm_search` | `_rrf_merge` | RRF over `[keyword_results, semantic_results]` | WIRED | recall.py:677: `merged = _rrf_merge(lists, k=self._config.rrf_k, top_n=self._config.warm_top_n)` |
| `SemanticRecall.search` | `cosine_similarity` via `sentinel_shared` | per-entry decode then cosine vs query vector | WIRED | recall.py:505: `sim = float(cosine_similarity(qv, nv))`; `cosine_similarity` count = 2 (import + call) |
| `build_application` | `Recall(semantic_strategy=SemanticRecall(...))` | composition root inside `if recall is None:` | WIRED | composition.py:322-335: guard + construction confirmed; `active_model=settings.embedding_model` (no prefix) |
| `_emit_embedding_index` | `_embedding_model_id()` | per-entry `embedding_model` field | WIRED | vault_sweeper.py:321: `active_model = _embedding_model_id()` inside the loop; written into `new_index[path]["embedding_model"]` at line 334 |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `SemanticRecall.search` | `self._index` | `vault.read_note(config.index_path)` → `json.loads` | Yes — real JSON written by sweeper | FLOWING |
| `Recall._warm_search` | `warm` list | `_rrf_merge([kw, sem])` → body reads for post-RRF survivors | Yes — bodies read via `vault.read_note` for each survivor | FLOWING |
| `_emit_embedding_index` | `new_index` written | `encode_embedding(embeddings[idx])` from real embedder | Yes — embedder output; no static returns | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 3 targeted test files pass | `uv run pytest tests/test_recall.py tests/test_vault_sweeper.py tests/test_composition.py -q` | 61 passed, 2 warnings | PASS |
| Full test suite passes | `uv run pytest -q` | 311 passed, 12 skipped, 2 warnings in 15.34s | PASS |
| `RecallConfig` defaults correct | `python -c "from app.services.recall import RecallConfig; c=RecallConfig(); assert c.rrf_k==60 and c.semantic_cosine_floor==0.50 and c.index_path=='ops/sweeps/embedding-index.json' and c.index_ttl_seconds==60.0"` | exit 0 (confirmed by plan task check passing) | PASS |
| No forbidden filesystem calls | `grep -rn "tempfile|os\.replace|os\.path\.getmtime" recall.py vault_sweeper.py` | Only comment/docstring mentions in vault_sweeper.py (lines 82, 284) — zero executable occurrences | PASS |
| `write_note(EMBEDDING_INDEX_PATH` call count | `grep -c "write_note(EMBEDDING_INDEX_PATH"` | 1 (vault_sweeper.py:340) | PASS |
| `_rrf_merge` defined and called | `grep -c "_rrf_merge" recall.py` | 3 (definition + 2 references) | PASS |
| `cosine_similarity` used | `grep -c "cosine_similarity" recall.py` | 2 (import + call) | PASS |
| ADR-0004 status accepted + supersession note | `grep -E "Status: accepted|supersed" adr/0004-semantic-recall.md` | Both present | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| MEM-03 | 40-02, 40-03 | Recall relevant vault content by meaning (semantic/vector search), not only keyword matches | SATISFIED | `test_semantic_paraphrase_returns_correct_note` proves a note keyword-only would miss is returned via SemanticRecall + RRF; `test_end_to_end_paraphrase_recall` proves this through the fully-composed path |
| MEM-04 | 40-02, 40-03 | Keyword and semantic recall results merged into one ranked recall set (hybrid retrieval) | SATISFIED | `_rrf_merge` implements RRF (k=60); `Recall._warm_search` calls it with both strategy results; `test_rrf_merge_combines_both_strategies` passes |
| MEM-05 | 40-01, 40-02 | Semantic recall reads from sweeper-maintained index (no per-note HTTP at query time); skips notes whose embedding model no longer matches | SATISFIED | SemanticRecall reads index once per TTL via `vault.read_note`; sweeper writes index via `vault.write_note`; exact-string model match enforced; `test_semantic_recall_no_per_note_rest`, `test_semantic_skips_mismatched_model`, `test_semantic_all_mismatch_degrades_to_keyword` all pass |

All three phase requirement IDs fully accounted for and satisfied.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `test_composition.py` (lines 160, 194) | — | `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` | Info | Pre-existing test mock structure issue documented in Plan 03 SUMMARY; tests pass; background task fires with AsyncMock vault and fails gracefully per T-40-12 design — not a production code defect |

No TBD/FIXME/XXX/HACK/PLACEHOLDER markers found in files modified by this phase. No stub return patterns in production code. No hardcoded empty data in live code paths.

---

## CR-03 Known Partial (from 40-REVIEW.md)

The post-execution code review identified CR-03: incremental rebuild still re-embeds unchanged notes (efficiency deviation from D-05) — the embed-call skip was not implemented. This was evaluated and **explicitly deferred** as a follow-up efficiency improvement; it is not a correctness or security bug. The index IS maintained incrementally for what it writes (entries with matching hash+model are carried forward). Only the optimization of skipping the `embedder()` call for unchanged notes is deferred. This does not affect any of the 4 success criteria.

---

## Human Verification Required

### 1. Live Paraphrase Query End-to-End

**Test:** With a running Obsidian vault and LM Studio embedding model loaded, trigger a sweep, then send a Discord message that paraphrases a vault note's content without using its exact keywords.
**Expected:** The note appears in `RecalledContext.warm` in the response.
**Why human:** Requires live LM Studio embedding endpoint, live Obsidian REST API, and real user query — no deterministic programmatic proxy exists.

### 2. Obsidian REST .json Path Acceptance

**Test:** PUT `ops/sweeps/embedding-index.json` to the live Obsidian Local REST API, then GET it back.
**Expected:** 2xx on PUT, GET returns the same JSON body unchanged.
**Why human:** The FakeVault proves the seam contract is extension-agnostic at the interface level. Live Obsidian behavior is the outstanding UAT item; the documented fallback (switch to `.md` fenced JSON) is a one-line constant change if the live API rejects `.json`.

---

## Gaps Summary

No blocking gaps. All 4 success criteria are verified by deterministic tests against fake embedder + fixture index with no live external services. The 2 human verification items above are UAT-level live-system checks, not code defects — the implementation is complete and fully wired.

---

_Verified: 2026-06-11_
_Verifier: Claude (gsd-verifier)_
