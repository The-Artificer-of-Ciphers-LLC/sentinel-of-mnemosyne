---
phase: 40-semantic-recall
plan: "03"
subsystem: composition
tags: [semantic-recall, composition, wiring, startup, tdd]
dependency_graph:
  requires: ["40-01", "40-02"]
  provides: ["SemanticRecall wired in composition root", "startup index rebuild", "end-to-end tests"]
  affects: ["sentinel-core/app/composition.py", "sentinel-core/tests/test_recall.py", "sentinel-core/tests/test_composition.py"]
tech_stack:
  added: []
  patterns:
    - "SemanticRecall injected into Recall at composition root via if recall is None: guard"
    - "asyncio.create_task for non-blocking startup sweep trigger"
    - "active_model=settings.embedding_model (no openai/ prefix) per D-12"
key_files:
  created: []
  modified:
    - sentinel-core/app/composition.py
    - sentinel-core/tests/test_recall.py
    - sentinel-core/tests/test_composition.py
decisions:
  - "D-06: on-demand rebuild trigger is the EXISTING admin-gated POST /vault/sweep/start route (no new HTTP endpoint)"
  - "D-12: active_model=settings.embedding_model (bare model id, no openai/ prefix)"
  - "Startup rebuild task location: initialize_startup() after graph construction, where all sweep deps (vault, classifier, embedder) are in scope"
metrics:
  duration: "~15 minutes"
  completed: "2026-06-11"
  tasks_completed: 3
  tasks_total: 3
  files_modified: 3
---

# Phase 40 Plan 03: Composition Wiring Summary

**One-liner:** SemanticRecall wired into Recall at composition root with `active_model=settings.embedding_model` (no `openai/` prefix), Embeddings built before Recall, non-blocking startup index rebuild via `asyncio.create_task`, proven end-to-end by paraphrase and empty-query tests.

## What Was Built

### Task 1: Wire SemanticRecall at Composition Root

Modified `sentinel-core/app/composition.py`:

1. **Import added:** `from app.services.recall import Recall, RecallConfig, SemanticRecall` (combined into single import)
2. **Construction order fix:** Moved the `if embeddings is None:` block to BEFORE the `if recall is None:` guard so `embeddings.embed` is available when constructing `SemanticRecall` (critical dependency ordering, D-12)
3. **SemanticRecall wiring:** Inside the `if recall is None:` guard:
   ```python
   _config = RecallConfig()
   _semantic = SemanticRecall(
       vault,
       embed_fn=embeddings.embed,
       active_model=settings.embedding_model,  # NO openai/ prefix (D-12)
       config=_config,
   )
   recall = Recall(vault=vault, config=_config, semantic_strategy=_semantic)
   ```
4. **Test seam preserved:** When a caller passes `recall=...` explicitly (e.g. in tests), the guard is skipped — no wiring occurs.

**Key constraint honored (D-12):** `active_model=settings.embedding_model` uses the bare model id from settings (e.g. `"nomic-embed-text-v1.5"`). Using `embeddings._model` (which is `"openai/nomic-embed-text-v1.5"`) would make every exact-string comparison in SemanticRecall fail.

### Task 2: Non-Blocking Startup Index Rebuild (D-06)

Added to `initialize_startup()` in `composition.py`:

- `asyncio` imported at top of module
- After graph construction, `asyncio.create_task(_startup_rebuild())` is scheduled
- `_startup_rebuild()` calls `run_sweep(graph.vault, graph.note_classifier_fn, graph.embeddings.embed)` — the same sweep that `POST /vault/sweep/start` invokes
- On any failure, logs a WARNING and continues — never crashes startup (T-40-12)

**On-demand rebuild trigger (D-06):** The EXISTING admin-gated `POST /vault/sweep/start` route in `app/routes/note.py` already calls `start_sweep()` which calls `run_sweep()` which emits the embedding index. No new HTTP endpoint was added. The authz surface is unchanged (T-40-09: admin-only via `_is_admin_route`).

**Startup task location:** `initialize_startup()` after `build_application()` returns — this is the earliest point where `graph.vault`, `graph.note_classifier_fn`, and `graph.embeddings.embed` are all available as a coherent unit.

### Task 3: End-to-End Tests

Added to `sentinel-core/tests/test_recall.py`:

1. **`test_end_to_end_paraphrase_recall`:** Constructs a composed `Recall(semantic_strategy=SemanticRecall(...))` with FakeVault seeded with fixture index. Keyword search returns only `notes/b.md`; semantic search finds `notes/a.md` (cosine ≈ 0.90 > 0.50 floor). After RRF merge, `notes/a.md` appears in `warm` with a non-empty body read post-RRF. Proves MEM-03 + MEM-04 + MEM-05 end-to-end.

2. **`test_context_empty_query_skips_embedding`:** Calls `Recall.assemble(content="")` with a call-counting fake embedder. Asserts `embed_fn` is never invoked (D-16 end-to-end regression lock). Returns `warm=[]` without error.

Added to `sentinel-core/tests/test_composition.py`:

3. **`test_build_application_wires_semantic_recall_with_no_prefix_active_model`:** Calls `build_application(..., recall=None)` with `embedding_model="nomic-embed-text-v1.5"`. Asserts `graph.recall._semantic_strategy` is a `SemanticRecall` instance whose `_active_model` equals `settings.embedding_model` and does NOT start with `"openai/"` (T-40-11, D-12 regression lock).

## Commits

| Hash | Message |
|------|---------|
| `0127d9a` | `feat(40-03): wire SemanticRecall into Recall at composition root` |
| `f52dcd4` | `feat(40-03): add non-blocking startup embedding-index rebuild (D-06)` |
| `cce4f99` | `test(40-03): end-to-end paraphrase + empty-query regression + wiring assertion` |

## Verification Results

```
grep -c "semantic_strategy=" sentinel-core/app/composition.py  → 1 ✓
grep -c "active_model=settings.embedding_model" sentinel-core/app/composition.py  → 1 ✓
grep -c "create_task" sentinel-core/app/composition.py  → 1 ✓
grep -rc "rebuild-index" sentinel-core/app/routes/  → 0 (no new route) ✓
cd sentinel-core && uv run pytest tests/ -q  → 310 passed, 12 skipped ✓
```

Source-order assertion: `embeddings = Embeddings(...)` appears before `recall = Recall(...)` in `composition.py` — confirmed by automated check.

## Deviations from Plan

None — plan executed exactly as written.

The only noteworthy detail: two pre-existing `initialize_startup` tests emit `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` because `asyncio.create_task` now fires a real background sweep with the AsyncMock vault used in those tests. The warnings are benign (tests pass; the background task fails gracefully per T-40-12 design) and are intrinsic to the monkeypatched mock structure of those tests.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced beyond what the plan's threat model specifies. The admin-gated `POST /vault/sweep/start` route is the on-demand rebuild trigger (T-40-09 disposition: `mitigate`, existing `_is_admin_route` guard unchanged).

## Known Stubs

None — all three tasks produce fully-wired production paths and behavior-proving tests.

## Self-Check: PASSED

- `sentinel-core/app/composition.py` — modified, committed at `0127d9a`, `f52dcd4`
- `sentinel-core/tests/test_recall.py` — modified, committed at `cce4f99`
- `sentinel-core/tests/test_composition.py` — modified, committed at `cce4f99`
- Commits verified: `git log --oneline` confirms `0127d9a`, `f52dcd4`, `cce4f99` exist
- Full suite: 310 passed, 12 skipped, 2 warnings (warnings are non-failure, pre-existing test mock structure)
