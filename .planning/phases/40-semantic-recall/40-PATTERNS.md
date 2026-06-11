# Phase 40: Semantic Recall - Pattern Map

**Mapped:** 2026-06-11
**Files analyzed:** 7
**Analogs found:** 7 / 7

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `sentinel-core/app/services/recall.py` | service | request-response | itself (existing) | self-modification |
| `sentinel-core/app/services/vault_sweeper.py` | service | batch / file-I/O | itself (existing) | self-modification |
| `shared/sentinel_shared/embedding_codec.py` | utility | transform | itself (existing) | reuse only |
| `shared/sentinel_shared/similarity.py` | utility | transform | itself (existing) | reuse only |
| `sentinel-core/app/clients/embeddings.py` | client | request-response | itself (existing) | reuse only |
| `sentinel-core/app/routes/status.py` | route | request-response | itself (existing) | self-modification |
| `sentinel-core/app/composition.py` | config | — | itself (existing) | self-modification |
| `sentinel-core/tests/test_recall.py` | test | — | itself (existing) | extend |
| `sentinel-core/tests/fakes/vault.py` | test | — | itself (existing) | extend |

---

## Pattern Assignments

### `sentinel-core/app/services/recall.py` — RetrievalStrategy Protocol + KeywordRecall + SemanticRecall + RRF

**Analog:** `sentinel-core/app/services/recall.py` (self — add symbols above/within the existing module)

#### Existing `RecallConfig` dataclass (lines 137–180)

The new `SemanticRecall`-related fields must follow the same `frozen=True` dataclass pattern.
All existing fields are preserved; append new fields after `warm_top_n`.

```python
@dataclass(frozen=True)
class RecallConfig:
    relevance_threshold: float = -200.0
    exclude_prefixes: tuple[str, ...] = ("ops/", "_trash/", "self/")
    sessions_ratio: float = 0.15
    search_ratio: float = 0.10
    recent_session_limit: int = 3
    self_paths: list[str] = field(default_factory=lambda: [...])
    warm_top_n: int = 3
    # NEW fields to add after this line:
    semantic_cosine_floor: float = 0.50
    semantic_top_k: int = 20
    keyword_top_k: int = 20
    rrf_k: int = 60
    semantic_lru_size: int = 128
    index_path: str = "ops/sweeps/embedding-index.json"
```

#### Existing `SearchResult` / `RecalledContext` value types (lines 110–135)

Both are `@dataclass(frozen=True)`. `SemanticRecall` returns `SearchResult(path=..., score=cosine, body="")`.
These types are unchanged — no new fields.

#### Existing `Recall.__init__` pattern (lines 207–209)

```python
def __init__(self, vault: "Vault", *, config: RecallConfig | None = None) -> None:
    self._vault = vault
    self._config = config or RecallConfig()
```

**Modified `__init__` must add strategy injection.** Pattern for the new signature:

```python
def __init__(
    self,
    vault: "Vault",
    *,
    config: RecallConfig | None = None,
    keyword_strategy: "RetrievalStrategy | None" = None,
    semantic_strategy: "RetrievalStrategy | None" = None,
) -> None:
    self._vault = vault
    self._config = config or RecallConfig()
    self._keyword_strategy = keyword_strategy or KeywordRecall(vault, self._config)
    self._semantic_strategy = semantic_strategy  # None = semantic disabled (graceful)
```

#### Existing `_warm_search` body (lines 241–294) — the seam being lifted

This is the exact body that becomes `KeywordRecall.search`. Copy it verbatim into `KeywordRecall.search`, then replace `_warm_search` with the RRF orchestrator:

```python
async def _warm_search(self, content: str) -> list[SearchResult]:
    if not content.strip():
        return []

    words = content.split()
    if len(words) > _KEYWORD_SEARCH_THRESHOLD:
        query = _best_search_query(content)
    else:
        query = content

    search_results = await self._vault.find(query)

    relevant = [
        r for r in search_results
        if r.get("score", float("-inf")) >= self._config.relevance_threshold
        and not r.get("filename", "").startswith(self._config.exclude_prefixes)
    ]
    if not relevant:
        return []

    top = relevant[: self._config.warm_top_n]
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
        results.append(
            SearchResult(path=r["filename"], score=r["score"], body=note_body)
        )
    return results
```

#### WR-03 graceful-degradation pattern (lines 310–333 in `assemble`)

The RRF orchestrator in `_warm_search` reuses this exact pattern with `asyncio.gather(return_exceptions=True)`:

```python
_self_raw, _sessions_raw, _warm_raw = await asyncio.gather(
    self._hot_self(),
    self._hot_sessions(request.user_id),
    self._warm_search(request.content),
    return_exceptions=True,
)
if isinstance(_self_raw, BaseException):
    logger.warning("recall tier failed: %r", _self_raw)
    self_context: list[str] = []
else:
    self_context = _self_raw
```

Apply the same pattern in the new `_warm_search` when gathering from both strategies:

```python
kw_result, sem_result = await asyncio.gather(
    self._keyword_strategy.search(content, budget=self._config.keyword_top_k),
    self._semantic_strategy.search(content, budget=self._config.semantic_top_k)
    if self._semantic_strategy is not None else _empty_coroutine(),
    return_exceptions=True,
)
for result in (kw_result, sem_result):
    if isinstance(result, BaseException):
        logger.warning("retrieval strategy failed: %r", result)
        lists.append([])
    else:
        lists.append(result)
```

#### `RetrievalStrategy` Protocol placement

Add above `Recall` class, after imports. Mirror the typing-only import guard already present:

```python
from typing import TYPE_CHECKING, Protocol, runtime_checkable, Callable, Awaitable

@runtime_checkable
class RetrievalStrategy(Protocol):
    async def search(self, query: str, *, budget: int) -> list[SearchResult]: ...
```

---

### `sentinel-core/app/services/vault_sweeper.py` — Index emission step 3b

**Analog:** `sentinel-core/app/services/vault_sweeper.py` (self — add after step 3 write-back loop)

#### Existing step 3 write-back loop (lines 374–383) — the insertion point

```python
if not dry_run:
    for idx, (path, fm, rest, _) in enumerate(survivors):
        try:
            if embeddings and idx < len(embeddings):
                fm["embedding_model"] = _embedding_model_id()   # already present
                fm["embedding_b64"] = encode_embedding(embeddings[idx])
            new_body = join_frontmatter(fm, rest)
            await client.write_note(path, new_body)
        except Exception as exc:
            report.errors.append(f"write_back {path}: {exc}")
```

**New step 3b goes immediately after this block** (before step 4 de-dup).
The sweeper already has `encode_embedding`, `_embedding_model_id()`, and `survivors`/`embeddings` in scope.

#### `_embedding_model_id()` (lines 76–88) — canonical active-model string

```python
def _embedding_model_id() -> str:
    try:
        from app.config import settings
        return settings.embedding_model     # NO "openai/" prefix
    except Exception:
        return "text-embedding-nomic-embed-text-v1.5"
```

This is the exact string `SemanticRecall.active_model` must compare against. Source of truth for model comparison key.

#### Existing vault write pattern (lines 436–445) — how the sweeper writes ops/ sidecar files

```python
log_path = f"ops/sweeps/{_today_str()}.md"
try:
    existing = await client.read_note(log_path)
    if existing:
        await client.patch_append(log_path, log_block)
    else:
        await client.write_note(log_path, f"# Sweep log {_today_str()}\n{log_block}")
except Exception as exc:
    logger.warning("sweep log write failed: %s", exc)
    report.errors.append(f"log: {exc}")
```

**CRITICAL — REST-only constraint (D-08):** The embedding index is written via `client.write_note()` (same REST PUT mechanism), NOT via `tempfile`/`os.replace`. The RESEARCH.md patterns 3 and 4 (mtime/filesystem) apply only to `SemanticRecall`'s reader side; the sweeper's writer side must use the Vault seam.

Index write pattern to copy:

```python
INDEX_PATH = "ops/sweeps/embedding-index.json"

async def _emit_embedding_index(client, survivors, embeddings, active_paths: set[str]) -> None:
    """Load existing index, update entries for survivors, prune deleted, write via vault."""
    try:
        raw = await client.read_note(INDEX_PATH)
        existing_index: dict = json.loads(raw) if raw.strip() else {}
    except Exception:
        existing_index = {}

    new_index: dict = {}
    # Carry forward unchanged entries for paths that are still active
    for path, entry in existing_index.items():
        if path in active_paths:
            new_index[path] = entry
        # else: pruned (trashed/deleted)

    for idx, (path, fm, rest, _) in enumerate(survivors):
        if embeddings and idx < len(embeddings):
            content_hash = _content_hash(rest)
            existing = existing_index.get(path, {})
            if (existing.get("content_hash") == content_hash
                    and existing.get("embedding_model") == _embedding_model_id()):
                new_index[path] = existing        # carry forward unchanged
            else:
                new_index[path] = {
                    "embedding_b64": encode_embedding(embeddings[idx]),
                    "embedding_model": _embedding_model_id(),
                    "content_hash": content_hash,
                }

    try:
        await client.write_note(INDEX_PATH, json.dumps(new_index, ensure_ascii=False))
    except Exception as exc:
        logger.warning("sweep: embedding index write failed: %s", exc)
        report.errors.append(f"index_emit: {exc}")
```

New helper to add alongside `_embedding_model_id`:

```python
import hashlib

def _content_hash(text: str) -> str:
    """SHA-256 of the frontmatter-stripped note body, first 16 hex chars."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
```

**D-09 / index load in SemanticRecall:** Because the index is written via REST, `SemanticRecall` cannot use `os.path.getmtime()`. Instead, use a TTL (e.g. 60 s) or a version note at `ops/sweeps/embedding-index.version` containing a timestamp/hash written by the sweeper after each index emit. SemanticRecall reads this cheap version note to detect staleness without loading the full index. Planner must decide: TTL (simpler) vs version-note (more precise).

---

### `sentinel-core/app/clients/embeddings.py` — Active-model string (reuse only)

**No changes.** Used as the `embed_fn` injected into `SemanticRecall`.

Key facts for the planner:
- `Embeddings.embed(texts) -> list[list[float]]` is the async callable to inject.
- `Embeddings._model` stores `"openai/text-embedding-nomic-embed-text-v1.5"` (with prefix).
- `SemanticRecall.active_model` must be sourced from `settings.embedding_model` (no prefix), NOT from `Embeddings._model`.
- Composition: `SemanticRecall(..., embed_fn=graph.embeddings.embed, active_model=settings.embedding_model, ...)`.

```python
# composition.py line 323-329 — existing Embeddings construction:
if embeddings is None:
    embeddings = Embeddings(
        http_client,
        settings.lmstudio_base_url or DEFAULT_LMSTUDIO_BASE_URL,
        settings.embedding_model,          # stored WITHOUT "openai/" — class adds it
        api_key=settings.lmstudio_api_key or "lm-studio",
    )
```

---

### `sentinel-core/app/composition.py` — Wire SemanticRecall into Recall

**Analog:** `sentinel-core/app/composition.py` lines 311–313 (existing Recall construction)

Current pattern:
```python
if recall is None:
    recall = Recall(vault=vault)
```

New pattern (add `SemanticRecall` construction before `Recall`):

```python
if recall is None:
    from app.services.recall import SemanticRecall, KeywordRecall
    semantic = SemanticRecall(
        embed_fn=embeddings.embed,
        active_model=settings.embedding_model,   # no "openai/" prefix
        vault=vault,                              # for post-RRF body reads
        config=recall_config,                    # or RecallConfig()
    )
    recall = Recall(vault=vault, semantic_strategy=semantic)
```

**`build_application` keyword-arg test seam (lines 239–254):** The function already accepts `recall=None` and `embeddings=None` as overridable kwargs. Add `semantic_strategy=None` or construct SemanticRecall inside the `if recall is None:` guard — tests override by passing a fully constructed `Recall` with a `FakeSemanticRecall`.

**`AppGraph` dataclass (lines 68–93):** No new fields needed — `recall` already holds the wired instance.

---

### `sentinel-core/app/routes/status.py` — Empty-query path for `/context/{user_id}`

**No interface change.** The endpoint already calls `recall.assemble(fake_req, budget=...)` with `content=""` (line 41–50). D-16 requires that `SemanticRecall.search("")` returns `[]` without calling `embed_fn`. This is handled inside SemanticRecall — the route needs no modification.

Current pattern to preserve (lines 35–59):
```python
@router.get("/context/{user_id}")
async def debug_context(request: Request, user_id: str = Path(..., pattern=r"^[a-zA-Z0-9_-]+$")) -> JSONResponse:
    ctx = get_route_context(request)
    fake_req = MessageRequest(content="", user_id=user_id, ...)
    recalled = await ctx.recall.assemble(fake_req, budget=ctx.context_window)
    return JSONResponse({
        "user_id": user_id,
        "self_context": recalled.self_context,
        "sessions": recalled.sessions,
        "warm": [{"path": r.path, "score": r.score} for r in recalled.warm],
        ...
    })
```

The `"score"` in the warm list will carry the RRF score after Phase 40. No format change needed.

---

### `sentinel-core/tests/test_recall.py` — Extend with 6 new test functions

**Analog:** Existing tests in `sentinel-core/tests/test_recall.py`

#### Helper pattern to copy (lines 24–43)

```python
def make_recall(*, notes=None, config=None):
    vault = FakeVault(notes=notes or {})
    recall = Recall(vault=vault, config=config)
    return recall, vault

def make_request(content="hello", budget=8192):
    return MessageRequest(content=content, user_id="trekkie", model_name="test-model",
                          context_window=budget, stop_sequences=None)
```

New helper needed for SemanticRecall tests (add alongside `make_recall`):

```python
import json, os, tempfile
from sentinel_shared.embedding_codec import encode_embedding

def make_fixture_index(note_paths, note_vecs, model="test-model-v1"):
    return {
        path: {
            "embedding_b64": encode_embedding(vec),
            "embedding_model": model,
            "content_hash": "deadbeef00000000",
        }
        for path, vec in zip(note_paths, note_vecs)
    }

def write_fixture_index(index: dict) -> str:
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(index, f)
    return path

async def fake_embedder(texts):
    results = []
    for text in texts:
        if "search_query:" in text:
            results.append([0.9, 0.436, 0.0])
        else:
            results.append([1.0, 0.0, 0.0])
    return results
```

#### WR-03 degradation test pattern (lines 206–239) — copy for all-mismatch test

```python
async def test_assemble_degrades_gracefully_when_sessions_tier_raises():
    vault = FakeVault(notes={...})
    async def raising_sessions(user_id, limit=3):
        raise RuntimeError("simulated session tier failure")
    vault.get_recent_sessions = raising_sessions
    recall = Recall(vault=vault)
    result = await recall.assemble(make_request(...), budget=8192)
    assert result.sessions == []
    assert ...  # other tiers still populated
```

Apply same pattern for `test_semantic_all_mismatch_degrades`: SemanticRecall returns `[]` (not raises); keyword results still appear in `result.warm`.

#### `vault.find` monkey-patch pattern (lines 125–133, 259–274)

```python
async def fake_find(query: str) -> list[dict]:
    return [{"filename": "notes/target.md", "score": -300.0, "matches": []}]
vault.find = fake_find  # type: ignore[method-assign]
```

Use the same pattern for `KeywordRecall`-only test cases: monkey-patch `vault.find` on the `FakeVault` instance to control keyword results.

---

### `sentinel-core/tests/fakes/vault.py` — No structural changes needed

**FakeVault already implements `write_note` / `read_note` (lines 134–138):**

```python
async def read_note(self, path: str) -> str:
    return self.notes.get(path, "")

async def write_note(self, path: str, body: str) -> None:
    self.notes[path] = body
```

To seed a fixture embedding index in tests:
```python
vault = FakeVault()
vault.notes["ops/sweeps/embedding-index.json"] = json.dumps(make_fixture_index(...))
```

No new methods needed. SemanticRecall reads the index via `vault.read_note()` — FakeVault's existing implementation satisfies this.

**If SemanticRecall reads the index via local filesystem instead of Vault:** provide the index path from a `write_fixture_index(...)` temp file. Both patterns are supported depending on which side of the REST-vs-filesystem question the planner resolves.

---

## Shared Patterns

### Graceful-degradation (WR-03)
**Source:** `sentinel-core/app/services/recall.py` lines 310–333 (`assemble`) + lines 206–239 (`test_recall.py`)
**Apply to:** New `_warm_search` RRF orchestrator; `SemanticRecall.search` all-mismatch path; `_emit_embedding_index` write failure.

```python
result, = await asyncio.gather(strategy.search(...), return_exceptions=True)
if isinstance(result, BaseException):
    logger.warning("retrieval strategy failed: %r", result)
    lists.append([])
else:
    lists.append(result)
```

### Vault seam for ops/ writes
**Source:** `sentinel-core/app/services/vault_sweeper.py` lines 426–445
**Apply to:** `_emit_embedding_index` — all writes to `ops/sweeps/embedding-index.json` go through `client.write_note()`, never `open()`.

### `frozen=True` dataclass for config
**Source:** `sentinel-core/app/services/recall.py` lines 137–180
**Apply to:** All new `RecallConfig` fields.

### Lazy settings import in module helpers
**Source:** `sentinel-core/app/services/vault_sweeper.py` lines 76–88 (`_embedding_model_id`) and 62–70 (`_active_skip_prefixes`)
**Apply to:** Any new module-level helpers that need settings; always wrap in `try/except` with a hardcoded fallback.

### Protocol injection for testability
**Source:** `sentinel-core/app/services/vault_sweeper.py` lines 225–233 (`run_sweep` signature)
**Apply to:** `SemanticRecall.__init__` takes `embed_fn: Callable[[list[str]], Awaitable[list[list[float]]]]`; tests pass `fake_embedder`; production passes `embeddings.embed`.

### `asyncio.gather` for concurrent strategy calls
**Source:** `sentinel-core/app/services/recall.py` lines 310–315 (`assemble`)
**Apply to:** `_warm_search` RRF orchestrator calling both strategies concurrently.

---

## Critical Finding: REST-Only Vault (A6)

RESEARCH.md open question 4 / D-08 REVISED: the vault has no Docker volume mount — all vault I/O goes through Obsidian REST. This has two consequences:

1. **Sweeper writes index via `client.write_note()`** — not `tempfile`/`os.replace`. Pattern is the sweep-log write at lines 426–445 of `vault_sweeper.py`.
2. **SemanticRecall cannot use `os.path.getmtime()`** — there is no local filesystem path for the index. Cache invalidation must use TTL or a cheap version-note read. Planner must decide.

The RESEARCH.md Pattern 3 (mtime cache) and Pattern 4 (atomic write with `os.replace`) are inapplicable. Only the REST-based patterns from `vault_sweeper.py` apply.

---

## No Analog Found

None — all files have direct analogs or are self-modifications of existing codebase files.

---

## Metadata

**Analog search scope:** `sentinel-core/app/`, `sentinel-core/tests/`, `shared/sentinel_shared/`
**Files read:** 9
**Pattern extraction date:** 2026-06-11
