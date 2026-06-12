---
phase: 40-semantic-recall
plan: "07"
subsystem: vault-sweeper / recall / embedding-index
tags: [recall, semantic, embedding-index, tdd, single-source, round-trip, stale-skip]
dependency_graph:
  requires:
    - phase: 40-04
      provides: "_emit_embedding_index stale:true degraded-index invariant"
  provides:
    - vault_sweeper._encode_index_body (case-insensitive extension-aware encoder)
    - vault_sweeper._decode_index_body (case-insensitive extension-aware decoder)
    - RecallConfig.index_path derived from EMBEDDING_INDEX_PATH (single physical source)
    - SemanticRecall.search stale-skip (reader-side MEM-05 completion)
    - both-extensions .json/.md/.MD round-trip regression tests
  affects:
    - 40-06 (live UAT Test 3 becomes a confirmation of a pre-tested .md one-flip change)
tech-stack:
  added: []
  patterns:
    - Single-physical-source-of-truth constant: RecallConfig.index_path imports EMBEDDING_INDEX_PATH
    - Case-insensitive extension-aware fenced-JSON encode/decode for Obsidian REST compatibility
    - Reader-side stale-skip: entry.get('stale') truthy → continue before decode/cosine
    - Self-healing empty: _decode_index_body returns {} on any parse failure (T-40-30)
key-files:
  created: []
  modified:
    - sentinel-core/app/services/vault_sweeper.py
    - sentinel-core/app/services/recall.py
    - sentinel-core/tests/test_vault_sweeper.py
    - sentinel-core/tests/test_recall.py
key-decisions:
  - "_encode_index_body/_decode_index_body live in vault_sweeper.py (the writer module); recall.py imports _decode_index_body_from_sweeper to avoid duplication"
  - "Case-insensitivity via path.lower().endswith('.md') — covers .md, .MD, .Md variants"
  - "Stale-skip placed BEFORE the model-match check — cheapest possible; stale entries never increment matched_model_count"
  - "Literal 'ops/sweeps/embedding-index' removed from recall.py docstrings to satisfy single-source grep guard"
  - "No import cycle: vault_sweeper does not import recall, so recall importing EMBEDDING_INDEX_PATH from vault_sweeper is safe"
requirements-completed: [MEM-03, MEM-05]
duration: 25min
completed: "2026-06-11"
---

# Phase 40 Plan 07: Extension-Aware Index Encode/Decode + Stale-Skip Summary

**Single-source index-path constant, case-insensitive .md/.json round-trip encode/decode, and reader-side stale:true skip — making .md a pre-tested one-flip change and closing the MEM-05 recall-correctness gap.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-06-11T00:00:00Z
- **Completed:** 2026-06-11T00:25:00Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 4

## Accomplishments

- `_encode_index_body` and `_decode_index_body` helpers added to `vault_sweeper.py`: case-insensitive extension-aware fenced-JSON encode/decode so `.md` paths produce a valid Obsidian note body and `.json` paths behave exactly as before
- `RecallConfig.index_path` now derives from the imported `EMBEDDING_INDEX_PATH` constant — the literal lives in exactly one module; writer and reader cannot diverge by construction (round-2 item D)
- `SemanticRecall.search` skips any entry where `entry.get("stale")` is truthy before decode/cosine — completing the reader-side of 40-04's degraded-index invariant (round-3 / MEM-05)
- Both-extensions round-trip regression tests: `.json`, `.md`, and `.MD` (case-insensitive) all prove write→read equality

## Task Commits

TDD RED → GREEN pattern followed:

1. **RED — Task 1 + Task 2 tests:** `005af5f` (test(40-07): add failing tests for extension-aware encode/decode + stale-skip)
2. **GREEN — Task 1:** `00bea21` (feat(40-07): single-source index path + case-insensitive extension-aware encode/decode)
3. **GREEN — Task 2:** `97b5ce0` (feat(40-07): SemanticRecall.search skips stale:true index entries (MEM-05 reader-side))

## Files Created/Modified

- `sentinel-core/app/services/vault_sweeper.py` — Added `_encode_index_body`, `_decode_index_body`; updated `_emit_embedding_index` to use both helpers (write and existing-index read)
- `sentinel-core/app/services/recall.py` — Import `EMBEDDING_INDEX_PATH` from vault_sweeper; `RecallConfig.index_path` derives from it; `SemanticRecall._load_index_if_stale` delegates to `_decode_index_body`; `SemanticRecall.search` stale-skip added
- `sentinel-core/tests/test_vault_sweeper.py` — 12 new tests: encode/decode helpers, .json/.md/.MD round-trips
- `sentinel-core/tests/test_recall.py` — 11 new tests: constant-equality guard, no-duplicate-literal grep guard, .json/.md/.MD recall round-trips, stale-skip (stale excluded / non-stale unaffected / all-stale → [])

## Decisions Made

- `_encode_index_body`/`_decode_index_body` live in `vault_sweeper.py` (the writer owns encoding); `recall.py` imports `_decode_index_body` as `_decode_index_body_from_sweeper` — no duplication
- Stale-skip placed **before** the model-mismatch check — cheapest possible skip; stale entries never increment `matched_model_count` (intentional: they don't count toward the all-mismatch degrade signal)
- `path.lower().endswith(".md")` for case-insensitivity — covers `.md`, `.MD`, `.Md` variants
- Literal `ops/sweeps/embedding-index` removed from `SemanticRecall` docstring to satisfy the single-source grep guard test

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## Verification

- `grep -c "ops/sweeps/embedding-index" app/services/recall.py` == 0 (no duplicate literal)
- `grep -c "EMBEDDING_INDEX_PATH" app/services/recall.py` == 4 (imported and used)
- `grep -c "stale" app/services/recall.py` == 5 (reader-side skip present)
- `uv run pytest tests/test_vault_sweeper.py tests/test_recall.py -q` → 87 passed
- `uv run pytest -q` → 382 passed, 12 skipped (full suite green, no regression)

## Known Stubs

None — all new functionality is fully wired.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes beyond what the plan specified.

## Next Phase Readiness

- 40-06 live UAT Test 3 (`.json` vs `.md` path decision) is now a one-line constant flip in `EMBEDDING_INDEX_PATH` that has been pre-tested end-to-end
- The stale-skip closes the MEM-05 recall-correctness gap — degraded runs (40-04) can no longer surface stale embeddings at query time

---
*Phase: 40-semantic-recall*
*Completed: 2026-06-11*

## Self-Check: PASSED

**Files verified present:**
- sentinel-core/app/services/vault_sweeper.py — FOUND (contains _encode_index_body, _decode_index_body)
- sentinel-core/app/services/recall.py — FOUND (contains EMBEDDING_INDEX_PATH import, stale skip)
- sentinel-core/tests/test_vault_sweeper.py — FOUND
- sentinel-core/tests/test_recall.py — FOUND

**Commits verified:**
- 005af5f — FOUND (test(40-07))
- 00bea21 — FOUND (feat(40-07) Task 1 GREEN)
- 97b5ce0 — FOUND (feat(40-07) Task 2 GREEN)
