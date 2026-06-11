---
phase: 40-semantic-recall
reviewed: 2026-06-11T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - sentinel-core/app/services/recall.py
  - sentinel-core/app/services/vault_sweeper.py
  - sentinel-core/app/composition.py
  - sentinel-core/tests/test_recall.py
  - sentinel-core/tests/test_vault_sweeper.py
  - sentinel-core/tests/test_composition.py
  - sentinel-core/tests/test_message.py
  - sentinel-core/tests/test_recall_imports.py
  - docs/adr/0004-semantic-recall.md
findings:
  critical: 3
  warning: 6
  info: 3
  total: 12
status: issues_found
---

# Phase 40: Code Review Report

**Reviewed:** 2026-06-11T00:00:00Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 40 introduces a `RetrievalStrategy` seam inside `Recall`, a sweeper-maintained embedding sidecar index, `SemanticRecall` + `KeywordRecall` adapters, RRF merge, TTL cache, and composition wiring. The design is coherent and the Vault-seam principle (no local filesystem writes) is respected end to end.

Critical issues found: (1) the TTL cache has a time-of-check vs time-of-update race that can cause the index to be reloaded on every call under concurrent async pressure; (2) untrusted base64 content loaded from the vault sidecar is decoded without length/dimensionality validation, opening a silent incorrect-cosine path and a potential large-allocation amplification; (3) the `_emit_embedding_index` incremental rebuild has a logic inversion that causes every entry to be re-embedded on every sweep rather than being carried forward as intended. Two additional security-adjacent warnings concern the vec-cache being an unbounded plain dict (misdocumented as LRU), and JSON loaded from the vault index being passed to `np.asarray` without type validation. Three further quality warnings cover the `asyncio.create_task` in `initialize_startup` having no reference kept (task can be silently garbage-collected), the `_startup_rebuild` running `run_sweep` without supplying a `force_reclassify` argument (defaults False, likely wrong for a cold-start rebuild), and the inconsistency between the `_warm_search` single-strategy path which wraps `asyncio.gather` unnecessarily. Three info items flag a data corruption risk in test fixture data, missing `pytest.mark.asyncio` decorator coverage, and a dead `_ContextBudget` / `allocate` API.

---

## Critical Issues

### CR-01: TTL cache update window — index reloaded on every concurrent call

**File:** `sentinel-core/app/services/recall.py:351-360`

**Issue:** `_load_index_if_stale` checks `now - self._index_loaded_at <= ttl` at the top, but only updates `self._index_loaded_at` at the very bottom of the method (after the `await`). Because Python's asyncio is cooperative, any second coroutine that calls `_load_index_if_stale` while the first is suspended at `await self._vault.read_note(...)` will see `_index_loaded_at` still at its pre-load value (0.0 on cold start), pass the freshness check, and issue a redundant `read_note` call. Under bursts of concurrent messages this can trigger O(N-concurrent-requests) index reads instead of 1.

This is also a correctness issue: the assignment at line 360 occurs **after** the exception handler, so if `read_note` raises, `_index_loaded_at` stays at 0.0 permanently — meaning every subsequent call retries the failing read on every invocation (no backoff, no circuit-breaker).

**Fix:**
```python
async def _load_index_if_stale(self) -> None:
    now = time.monotonic()
    if now - self._index_loaded_at <= self._config.index_ttl_seconds:
        return
    # Stamp BEFORE the await so concurrent callers see a fresh timestamp
    # and skip the redundant read. Worst case: they use a briefly-stale
    # index. On failure we reset to a small backoff (e.g. 5 s) so the
    # next window retries without hammering the vault.
    self._index_loaded_at = now
    try:
        raw = await self._vault.read_note(self._config.index_path)
        self._index = json.loads(raw) if raw and raw.strip() else {}
    except Exception as exc:
        logger.warning("SemanticRecall: failed to load index at %r: %r",
                       self._config.index_path, exc)
        self._index = {}
        # Back off 5 s so a persistent vault failure doesn't spin
        self._index_loaded_at = time.monotonic() - self._config.index_ttl_seconds + 5.0
```


### CR-02: Untrusted embedding vectors decoded without dimension validation — silent wrong-cosine and allocation amplification

**File:** `sentinel-core/app/services/recall.py:429-436`

**Issue:** `decode_embedding(entry.get("embedding_b64", ""))` is called on content loaded from `ops/sweeps/embedding-index.json`, which is written by the vault sweeper but read back over the Vault REST seam — content that could be tampered with, truncated, or structurally malformed by any entity with write access to the vault. No validation of the returned vector's dimensionality or element type is performed before passing it to `np.asarray` and then to `cosine_similarity`. Two sub-risks:

1. **Silent wrong-cosine:** a note's vector might have a different dimension than the query vector. `np.asarray(raw)` of length 0 is caught by the `if not raw` check, but any non-zero incorrect dimension passes through. `cosine_similarity` in `sentinel_shared/similarity.py` constructs a `(N, M)` dot product — when query is `(1, 768)` and document is `(1, 512)`, the `@` operator raises a shape mismatch rather than returning a silent bad score. This converts a tampered entry into an unhandled exception that bubbles past the `candidates.append` line, and because there is no per-entry exception handler in the loop (lines 418-442), one bad entry crashes the entire `SemanticRecall.search` call.

2. **Allocation amplification:** an attacker (or corrupted sweep) with write access to the index could embed a 50 MB base64 string under one path key. `decode_embedding` will `np.frombuffer` it unconditionally. There is no size cap.

**Fix:**
```python
raw = decode_embedding(entry.get("embedding_b64", ""))
if not raw:
    logger.warning("SemanticRecall: zero-length embedding for %r, skipping", path)
    continue
# Dimension guard: query vector dimension is known after _get_query_vec
if len(raw) != len(query_vec):
    logger.warning(
        "SemanticRecall: dimension mismatch for %r (%d vs %d), skipping",
        path, len(raw), len(query_vec),
    )
    continue
nv = np.asarray(raw, dtype=np.float32)
```

Additionally, cap base64 string length before decoding:
```python
raw_b64 = entry.get("embedding_b64", "")
if len(raw_b64) > 1_000_000:  # ~750K floats — far above any realistic model dim
    logger.warning("SemanticRecall: suspiciously large embedding for %r, skipping", path)
    continue
raw = decode_embedding(raw_b64)
```


### CR-03: `_emit_embedding_index` incremental-rebuild logic inversion — re-embeds every note on every sweep

**File:** `sentinel-core/app/services/vault_sweeper.py:299-326`

**Issue:** The carry-forward logic at lines 299-303 correctly copies unchanged entries from `existing_index` into `new_index` for paths still in `active_paths`. However, the update loop at lines 307-326 then **unconditionally iterates over all survivors** and, for each one, re-checks the hash and model. The bug is on lines 314-319: when `content_hash == existing_entry["content_hash"]` AND `embedding_model == active_model`, the code writes `new_index[path] = existing_entry` — which is correct — but it does so **after** the embedder has already been called with that body at line 486 (`bodies = [NOMIC_DOCUMENT_PREFIX + s[2] for s in survivors]`). The embedding was already computed and charged; the carry-forward only avoids writing a new value, but the O(N) embedding call still fires.

The deeper issue is that `survivors` is built from **all non-skipped notes** (i.e. notes whose `sweep_pass` doesn't match). Since `_should_skip` only skips a note when its `sweep_pass == current_pass` AND `embedding_b64` is set, every note with a body change (or a new `sweep_pass`) is classified again and added to `survivors` — and all survivors' bodies are sent to the embedder at line 486 regardless of whether their content hash matches. The incremental carry-forward only affects the index write, not the embedding call. This means the `NOMIC_DOCUMENT_PREFIX` addition (intended as a one-time re-embed) actually fires on every note on every sweep because the `sweep_pass` always changes.

To be fair: the hash-based carry-forward in `_emit_embedding_index` does avoid writing a different `embedding_b64` when the hash matches, so the index file stays stable. But the embedding API is called for every survivor unconditionally — negating the cost savings of the incremental design.

**Fix:** Filter `survivors` to only pass bodies that genuinely need re-embedding to the embedder:

```python
# Separate survivors into those needing re-embed vs. carry-forward
needs_embed: list[tuple[int, tuple]] = []  # (original_idx, survivor_tuple)
for idx, s in enumerate(survivors):
    path, _fm, rest, _cls = s
    content_hash = _content_hash(rest)
    existing = existing_index.get(path, {})
    if (existing.get("content_hash") == content_hash
            and existing.get("embedding_model") == _embedding_model_id()):
        # Carry forward — no embedding needed
        new_index[path] = existing
    else:
        needs_embed.append((idx, s))

if needs_embed:
    bodies_to_embed = [NOMIC_DOCUMENT_PREFIX + s[2] for _, s in needs_embed]
    try:
        fresh_vecs = await embedder(bodies_to_embed)
    except Exception as exc:
        ...
    for (orig_idx, (path, _fm, rest, _cls)), vec in zip(needs_embed, fresh_vecs):
        new_index[path] = {
            "embedding_b64": encode_embedding(vec),
            "embedding_model": _embedding_model_id(),
            "content_hash": _content_hash(rest),
        }
```

Note: the existing test `test_sweep_index_incremental_carry_forward` asserts the stable note's `content_hash` and `embedding_b64` are preserved, and that the changed note is re-embedded. The current code passes both assertions only because the carry-forward in `_emit_embedding_index` restores the old `embedding_b64` for the stable note — but the embedder is still called with all bodies, making the test's "stable note body must NOT appear in second batch" assertion a correctness check that the current code **fails** (the stable note's body IS sent to the embedder on the second sweep).

---

## Warnings

### WR-01: Vec cache misdocumented as LRU — is actually FIFO with silent eviction of hot keys

**File:** `sentinel-core/app/services/recall.py:383-387`

**Issue:** The comment at line 382 reads "Bounded FIFO eviction when cache is full (Pitfall 9)" and the docstring calls it an "LRU cache" at line 197. The implementation is FIFO (`next(iter(self._vec_cache))` evicts the insertion-order-first key). In CPython 3.7+ dict preserves insertion order, so `next(iter(…))` evicts the oldest-inserted key — which is correct FIFO but incorrect LRU. For a repeated query with 128 other unique queries between repeats, the cache provides zero benefit. The `semantic_lru_size` config field name is also misleading.

More importantly, the `_vec_cache` is a plain `dict` — it is NOT bounded by `functools.lru_cache` which is thread/async-safe for size management. Two concurrent coroutines could both check `len >= lru_size`, both evict an entry, and both insert, leaving the dict momentarily at `lru_size + 1`. Under asyncio this is safe (GIL between awaits), but the invariant is fragile.

**Fix:** Use `functools.lru_cache` on a sync wrapper, or use `cachetools.LRUCache` if already a dependency. Alternatively, rename the field and comment to reflect the actual FIFO eviction semantics and document that it is intentional.


### WR-02: `asyncio.create_task` return value discarded — task can be garbage-collected before completion

**File:** `sentinel-core/app/composition.py:454`

**Issue:** `asyncio.create_task(_startup_rebuild())` fires the background sweep but does not retain a reference to the returned `Task` object. Per Python asyncio documentation, tasks without a retained reference can be garbage-collected before completing, silently cancelling the startup index rebuild. This is a documented Python gotcha (referenced in asyncio docs since 3.10).

**Fix:**
```python
# In initialize_startup, retain a strong reference to prevent GC:
_startup_task = asyncio.create_task(_startup_rebuild())
# Attach to app.state so it lives for the lifespan duration:
app.state._startup_sweep_task = _startup_task
```


### WR-03: `_startup_rebuild` calls `run_sweep` without `force_reclassify=True` — cold-start sweep skips all pre-marked notes

**File:** `sentinel-core/app/composition.py:442-448`

**Issue:** `_startup_rebuild` calls `run_sweep(graph.vault, graph.note_classifier_fn, graph.embeddings.embed)` with default arguments, including `force_reclassify=False`. `_should_skip` returns `True` for any note whose `sweep_pass` frontmatter matches the current sweep id AND which already has `topic` and `embedding_b64`. Since every sweep generates a new `sweep_id` (via `_iso_utc()`), no existing note will match the new sweep_id — so `force_reclassify` does not actually matter for classification. However, if notes have been previously embedded with a different model (e.g., after a model upgrade), the `_should_skip` check returns True (sweep_pass mismatch = don't skip), the note IS classified, added to survivors, and sent to the embedder. This means `force_reclassify=False` is equivalent to `force_reclassify=True` here for re-embedding — so the issue is less severe than it appears. However, the intent documented in the comment ("non-blocking startup index rebuild so a cold start becomes semantically searchable") specifically targets the scenario where an index does not exist. For this cold-start purpose, the current behavior is correct. Still, not passing `force_reclassify=True` makes the call semantically unclear and inconsistent with all other `run_sweep` invocations in the test suite, which use `force_reclassify=True`.

**Fix:** Pass `force_reclassify=True` explicitly to make intent clear:
```python
await _run_sweep(
    graph.vault,
    graph.note_classifier_fn,
    graph.embeddings.embed,
    force_reclassify=True,
)
```


### WR-04: `_warm_search` single-strategy branch wraps `asyncio.gather` unnecessarily, masking exception type

**File:** `sentinel-core/app/services/recall.py:587-590`

**Issue:** When `self._semantic_strategy is None`, the code does:
```python
raw_kw = await asyncio.gather(kw_coro, return_exceptions=True)
raw_kw = raw_kw[0]
```
`asyncio.gather` with a single coroutine and `return_exceptions=True` returns a 1-element list. Then `raw_kw = raw_kw[0]` unpacks it. This is unnecessary overhead (gather over one coroutine) and, more critically, when the keyword strategy raises, `raw_kw[0]` will be the exception — but then `raw_sem = []` is set unconditionally. The subsequent loop over `(raw_kw, raw_sem)` does check `isinstance(raw, BaseException)`, so it would degrade gracefully. However: if `raw_kw` itself is `[]` (empty list, not an exception), `lists.append([])` adds an empty list — correct. But if `raw_kw` happens to be a `BaseException`, the code correctly degrades. The extra indirection makes this code harder to audit and can mask future regressions. Directly `await`ing the single coroutine and wrapping with try/except is clearer.

**Fix:**
```python
if self._semantic_strategy is not None:
    raw_kw, raw_sem = await asyncio.gather(kw_coro, sem_coro, return_exceptions=True)
else:
    try:
        raw_kw = await kw_coro
    except BaseException as exc:
        raw_kw = exc
    raw_sem = []
```


### WR-05: `json.loads` of vault index does not validate top-level structure — a non-dict JSON value silently corrupts `self._index`

**File:** `sentinel-core/app/services/recall.py:355-357`

**Issue:**
```python
self._index = json.loads(raw) if raw and raw.strip() else {}
```
If the vault contains a valid JSON value at `ops/sweeps/embedding-index.json` that is NOT a dict (e.g. `null`, `[]`, or `"string"`), `json.loads` succeeds and `self._index` is set to a non-dict. The subsequent `for path, entry in self._index.items()` (line 418) then raises `AttributeError: 'NoneType' object has no attribute 'items'` (for `null`) or `ValueError: not enough values to unpack` (for a list), which is caught by the outer `except Exception` in `_warm_search` (via WR-03 graceful degrade), but silently returns `[]` rather than logging a meaningful warning.

The same issue exists in `_emit_embedding_index` at line 293, though it only reads on load and iterates with `.items()` — a non-dict JSON value at that path would crash and be caught by the outer `except Exception` that appends to `report.errors`.

**Fix:**
```python
parsed = json.loads(raw) if raw and raw.strip() else {}
self._index = parsed if isinstance(parsed, dict) else {}
if not isinstance(parsed, dict):
    logger.warning(
        "SemanticRecall: index at %r is not a JSON object (got %s), resetting",
        self._config.index_path, type(parsed).__name__,
    )
```


### WR-06: `_emit_embedding_index` does not validate that `embeddings` list length matches `survivors` length before indexing

**File:** `sentinel-core/app/services/vault_sweeper.py:307-310`

**Issue:**
```python
for idx, (path, _fm, rest, _cls) in enumerate(survivors):
    if idx >= len(embeddings):
        break
```
The `break` exits the loop silently when `len(embeddings) < len(survivors)`. This is a partial guard, but it means that if the embedder returns fewer vectors than expected (a short read from a batched API, partial failure, or off-by-one), the remaining survivors are silently excluded from the index without any warning being logged and without `report.errors` being updated. A note that was successfully classified will not appear in the index, causing SemanticRecall to miss it.

**Fix:** Add an explicit warning when lengths diverge:
```python
if embeddings is not None and len(embeddings) != len(survivors):
    logger.warning(
        "sweep: embedder returned %d vectors for %d survivors — index will be partial",
        len(embeddings), len(survivors),
    )
    report.errors.append(
        f"index_emit: embedder returned {len(embeddings)} vecs for {len(survivors)} survivors"
    )
```

---

## Info

### IN-01: Test fixture data contains a space in base64 string — will corrupt round-trip assertion

**File:** `sentinel-core/tests/test_vault_sweeper.py:893`

**Issue:** The fixture dict in `test_index_path_roundtrips_through_vault_seam` contains:
```python
"embedding_b64": "AAAAAACAP wAAAAAAAA==",
```
There is a space character inside the base64 string (`"AP wAAAA"`). `base64.b64decode` called on this string will raise `binascii.Error: Non-base64 digit found` when `validate=True` (default in Python 3.12+ with stricter padding) or silently ignore the space in older versions — which means the test may pass or fail depending on Python version. The round-trip test only checks `json.loads(round_tripped) == original` — it does not actually decode the embedding — so the bad base64 string does not affect the round-trip assertion itself. However, any test or production code that calls `decode_embedding` on this value will fail or produce a wrong result.

**Fix:** Remove the space from the base64 string:
```python
"embedding_b64": "AAAAAAAAgD8AAAAAAAAAAAAAAAA=",  # [0.0, 1.0, 0.0] as float32
```


### IN-02: `Recall.allocate` and `_ContextBudget` are defined but never called — dead API

**File:** `sentinel-core/app/services/recall.py:537-542`

**Issue:** `Recall.allocate(budget)` and `_ContextBudget` are defined but `allocate` is never called within `Recall.assemble` or anywhere else in the reviewed codebase. The docstring for `assemble` states "Per-tier truncation is the responsibility of `MessageProcessor`" — consistent with never calling `allocate`. The budget-splitting logic is dead code. This misleads future readers who might assume the budget is actually applied at the Recall layer.

**Fix:** Remove `allocate` and `_ContextBudget` from `recall.py`, or add a comment explicitly labelling them as a future API stub. If `MessageProcessor` is meant to call `allocate` in a future phase, add a `# TODO(phase-NN): called by MessageProcessor` comment to reduce confusion.


### IN-03: Test file `test_recall.py` line 501 imports from itself

**File:** `sentinel-core/tests/test_recall.py:501`

**Issue:**
```python
from tests.test_recall import make_request
```
This is a self-import inside a test function (`test_recall_warm_search_uses_rrf_when_both_strategies_present`). `make_request` is defined at the module level of the same file; the import is redundant and unusual. It works because Python caches the module in `sys.modules`, but the pattern looks like a copy-paste artifact. It also adds a dependency on the test module's own import path, which may break under certain pytest collection configurations.

**Fix:** Remove the self-import — `make_request` is already available in the local module scope:
```python
# Replace:
from tests.test_recall import make_request
empty_result = await recall.assemble(make_request(content=""), budget=8192)

# With (no import needed — make_request is defined in this module):
empty_result = await recall.assemble(make_request(content=""), budget=8192)
```

---

_Reviewed: 2026-06-11T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
