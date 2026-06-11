# Phase 39: Extract the Recall Module - Pattern Map

**Mapped:** 2026-06-11
**Files analyzed:** 6 new/modified files
**Analogs found:** 6 / 6

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `sentinel-core/app/services/recall.py` | service / module | request-response (async gather) | `sentinel-core/app/services/message_processing.py` | exact — extracts from this file directly |
| `sentinel-core/tests/test_recall.py` | test | unit — FakeVault-backed | `sentinel-core/tests/test_message_processor.py` | exact — same test shape (FakeVault, direct class construction, pytest-asyncio) |
| `sentinel-core/app/services/message_processing.py` | service (trimmed) | request-response | self — existing file being modified | self-referential |
| `sentinel-core/app/routes/status.py` | route handler | request-response | `sentinel-core/app/routes/status.py` existing `/status` handler | role-match |
| `sentinel-core/app/composition.py` | wiring / DI | config | `sentinel-core/app/composition.py` lines 294–313 (`build_application`) | self-referential |
| `sentinel-core/app/state.py` | config / value type | config | `sentinel-core/app/state.py` `RouteContext` dataclass | self-referential |

---

## Pattern Assignments

### `sentinel-core/app/services/recall.py` (NEW — service, request-response)

**Analog:** `sentinel-core/app/services/message_processing.py`

**Imports pattern** (lines 1–18 of `message_processing.py`, adapted for `recall.py`):
```python
"""Recall module — owns hot-tier and warm-tier retrieval policy."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.vault import Vault
    from app.services.message_processing import MessageRequest

logger = logging.getLogger(__name__)
```

**Value types pattern** — frozen dataclasses (from `message_processing.py` lines 89–104):
```python
@dataclass(frozen=True)
class _ContextBudget:
    sessions_budget: int
    search_budget: int

@dataclass(frozen=True)
class MessageRequest:
    content: str
    user_id: str
    model_name: str
    context_window: int
    stop_sequences: list[str] | None
```
New types follow the same `@dataclass(frozen=True)` pattern:
```python
@dataclass(frozen=True)
class SearchResult:
    path: str
    score: float
    body: str

@dataclass(frozen=True)
class RecalledContext:
    self_context: list[str]
    sessions: list[str]
    warm: list[SearchResult]

@dataclass(frozen=True)
class RecallConfig:
    relevance_threshold: float = -200.0
    exclude_prefixes: tuple[str, ...] = ("ops/", "_trash/", "self/")
    sessions_ratio: float = 0.15
    search_ratio: float = 0.10
    recent_session_limit: int = 3
    self_paths: list[str] = field(default_factory=lambda: [
        "self/identity.md",
        "self/methodology.md",
        "self/goals.md",
        "self/relationships.md",
        "ops/reminders.md",
        "self/learning-areas.md",
    ])
    warm_top_n: int = 3
```

**Constructor pattern** (mirrors `MessageProcessor.__init__` at line 136):
```python
class Recall:
    def __init__(self, vault: "Vault", *, config: RecallConfig | None = None) -> None:
        self._vault = vault
        self._config = config or RecallConfig()
```

**`_allocate` pattern** (from `MessageProcessor._allocate_budgets` lines 143–148):
```python
@classmethod
def _allocate_budgets(cls, context_window: int) -> _ContextBudget:
    return _ContextBudget(
        sessions_budget=int(context_window * cls._SESSIONS_RATIO),
        search_budget=int(context_window * cls._SEARCH_RATIO),
    )
```
Translates to:
```python
def _allocate(self, budget: int) -> _ContextBudget:
    return _ContextBudget(
        sessions_budget=int(budget * self._config.sessions_ratio),
        search_budget=int(budget * self._config.search_ratio),
    )
```
Note: use `int()` (truncating), NOT `round()` — matches existing behavior exactly (Pitfall 3).

**Hot-tier asyncio.gather pattern** (from `_append_hot_tier` lines 204–210):
```python
gather_results = await asyncio.gather(
    *[self._vault.read_self_context(p) for p in self_paths],
    self._vault.read_self_context("sentinel/persona.md"),
    return_exceptions=True,
)
self_results = gather_results[: len(self_paths)]
persona_result = gather_results[-1]
```
For `Recall._hot_self()` — read ONLY the 6 self paths (no persona path). Persona stays in `MessageProcessor`:
```python
self_results = await asyncio.gather(
    *[self._vault.read_self_context(p) for p in self._config.self_paths],
    return_exceptions=True,
)
return [r for r in self_results if isinstance(r, str) and r.strip()]
```

**Warm-tier filter/top-N pattern** (from `_append_warm_tier` lines 244–256):
```python
relevant_results = [
    r for r in search_results
    if r.get("score", float("-inf")) >= SEARCH_SCORE_THRESHOLD
    and not r.get("filename", "").startswith(_WARM_TIER_EXCLUDE_PREFIXES)
]
if not relevant_results:
    return

top_results = relevant_results[:3]
paths = [r.get("filename", "") for r in top_results]
raw_contents = await asyncio.gather(
    *[self._vault.read_note(p) for p in paths],
    return_exceptions=True,
)
```
`startswith` receives a `tuple[str, ...]` directly — `RecallConfig.exclude_prefixes` must be typed `tuple[str, ...]` (Pitfall 5).

**Module-level constants** (from `message_processing.py` lines 23–47) that move to `recall.py` unchanged:
```python
# Lines 37–47 — _SEARCH_STOPWORDS (frozenset) and _KEYWORD_SEARCH_THRESHOLD
_SEARCH_STOPWORDS = frozenset(...)
_KEYWORD_SEARCH_THRESHOLD = 5
```
Plus `_extract_keywords` (lines 50–59) and `_best_search_query` (lines 62–86) move verbatim.

---

### `sentinel-core/tests/test_recall.py` (NEW — test, unit)

**Analog:** `sentinel-core/tests/test_message_processor.py`

**File-level pattern** (lines 1–21 of `test_message_processor.py`):
```python
"""Behavioral tests for MessageProcessor.process().

Each test constructs a real MessageProcessor against fakes and calls
processor.process(MessageRequest(...)) directly. Assertions are strictly
behavioral: return values, raised MessageProcessingError.code, recorded calls
on fakes, caplog records.
"""
from __future__ import annotations

import pytest

from app.services.message_processing import (
    MessageProcessor,
    MessageRequest,
)
```
Adapted for `test_recall.py`:
```python
"""Behavioral tests for Recall.assemble().

Constructs Recall against FakeVault directly. No MessageProcessor, no AI
provider, no InjectionFilter needed.
"""
from __future__ import annotations

import pytest

from tests.fakes.vault import FakeVault
from app.services.recall import Recall, RecallConfig, RecalledContext, MessageRequest
```

**FakeVault construction pattern** (from `tests/fakes/vault.py` lines 27–59):
```python
vault = FakeVault(
    notes={"self/identity.md": "# I am ..."},
    dirs={"": ["self/"]},
)
# Or mutate after construction:
vault.notes["self/goals.md"] = "My goals..."
```

**Factory helper pattern** (from `test_message_processor.py` lines 91–117):
```python
def make_processor(*, persona=..., self_files=..., ...) -> tuple[MessageProcessor, FakeObsidian, FakeAIProvider]:
    obsidian = FakeObsidian(...)
    proc = MessageProcessor(vault=obsidian, ...)
    return proc, obsidian, ai

def make_request(content: str = "hello", context_window: int = 8192) -> MessageRequest:
    return MessageRequest(content=content, user_id="trekkie", ...)
```
For `test_recall.py`:
```python
def make_recall(*, notes: dict | None = None, config: RecallConfig | None = None) -> tuple[Recall, FakeVault]:
    vault = FakeVault(notes=notes or {})
    recall = Recall(vault=vault, config=config)
    return recall, vault

def make_request(content: str = "hello", budget: int = 8192) -> MessageRequest:
    return MessageRequest(
        content=content,
        user_id="trekkie",
        model_name="test-model",
        context_window=budget,
        stop_sequences=None,
    )
```

**Async test decoration** (from `test_message_processor.py`): tests use bare `async def` with pytest-asyncio. No `@pytest.mark.asyncio` decorator on individual tests — the `pyproject.toml` sets `asyncio_mode = "auto"`. Replicate this pattern.

**Score filtering test pattern** (Pitfall 4 from RESEARCH.md):
```python
async def test_warm_below_threshold_excluded():
    vault = FakeVault()
    # Override find() to return a result with score below threshold
    async def fake_find(query):
        return [{"filename": "notes/target.md", "score": -300.0, "matches": []}]
    vault.find = fake_find
    vault.notes["notes/target.md"] = "some content"
    recall = Recall(vault=vault)
    result = await recall.assemble(make_request("some"), budget=8192)
    assert result.warm == []
```

---

### `sentinel-core/app/services/message_processing.py` (MODIFIED — trim hot/warm/allocate)

**What changes:** Remove `_append_hot_tier` (lines 195–234), `_append_warm_tier` (lines 236–263), `_allocate_budgets` (lines 143–148). Remove the inline constants that move to `recall.py` (lines 23–47 minus `SEARCH_SCORE_THRESHOLD` if it remains exported for backward-compat). Add `recall: Recall` constructor parameter.

**Constructor modification pattern** — extends the existing constructor (line 136):
```python
# Before:
def __init__(self, vault, ai_provider, injection_filter, output_scanner) -> None:
    self._vault = vault
    ...

# After (add recall as keyword-only):
def __init__(self, vault, ai_provider, injection_filter, output_scanner, *, recall: "Recall") -> None:
    self._vault = vault
    self._recall = recall
    ...
```

**`process()` delegation pattern** — replaces the two `await self._append_*` calls (lines 154–155):
```python
# Before:
await self._append_hot_tier(messages, req, budgets.sessions_budget)
await self._append_warm_tier(messages, req, budgets.search_budget)

# After:
recalled = await self._recall.assemble(req, req.context_window)
# Hot-tier: persona swap (stays in MessageProcessor per D-04)
persona_result = await self._vault.read_self_context("sentinel/persona.md")
if isinstance(persona_result, str) and persona_result.strip():
    messages[0] = {"role": "system", "content": persona_result}
else:
    logger.warning("Sentinel persona vault read returned empty; using fallback")
# Hot-tier: inject self-context + sessions from recalled
# (join + truncate + wrap logic stays here — it is presentation per D-04)
# Warm-tier: format recalled.warm via _format_search_results (stays here per D-04)
```

**`_format_search_results` stays in `message_processing.py`** (lines 265–279) — it formats `SearchResult` list for injection. Keep signature adaption:
```python
@staticmethod
def _format_search_results(
    results: list["SearchResult"], paths: list[str], contents: list
) -> str:
    ...
```
Or accept `list[SearchResult]` directly from `recalled.warm` — the planner decides the exact reshape.

**Import addition:**
```python
from app.services.recall import Recall, RecalledContext
```

---

### `sentinel-core/app/routes/status.py` (MODIFIED — `/context` delegating to Recall)

**Analog:** Same file, existing `/status` handler (lines 15–33)

**Existing GET handler pattern** (lines 15–33):
```python
@router.get("/status")
async def system_status(request: Request) -> JSONResponse:
    ctx = get_route_context(request)
    ...
    return JSONResponse({...})
```

**New `/context` handler pattern** replacing lines 36–67:
```python
@router.get("/context/{user_id}")
async def debug_context(
    request: Request,
    user_id: str = Path(..., pattern=r"^[a-zA-Z0-9_-]+$"),
) -> JSONResponse:
    ctx = get_route_context(request)
    fake_req = MessageRequest(
        content="",
        user_id=user_id,
        model_name="",
        context_window=ctx.context_window,
        stop_sequences=None,
    )
    recalled = await ctx.recall.assemble(fake_req, budget=ctx.context_window)
    return JSONResponse({
        "user_id": user_id,
        "self_context": recalled.self_context,
        "sessions": recalled.sessions,
        "warm": [{"path": r.path, "score": r.score} for r in recalled.warm],
        "recent_sessions_count": len(recalled.sessions),
    })
```

**Import additions:**
```python
from app.services.message_processing import MessageRequest
```
`asyncio` import can be removed if no longer needed.

---

### `sentinel-core/app/composition.py` (MODIFIED — DI wiring for Recall)

**Analog:** `sentinel-core/app/composition.py` lines 294–313 (how `vault`, `injection_filter`, `output_scanner`, `message_processor` are constructed)

**Existing guard-construct pattern** (lines 294–313):
```python
if vault is None:
    vault = ObsidianVault(
        http_client,
        settings.obsidian_api_url,
        settings.obsidian_api_key,
    )

if injection_filter is None:
    injection_filter = InjectionFilter()

if output_scanner is None:
    output_scanner = OutputScanner(ai_provider=ai_provider)

if message_processor is None:
    message_processor = MessageProcessor(
        vault=vault,
        ai_provider=ai_provider,
        injection_filter=injection_filter,
        output_scanner=output_scanner,
    )
```
Add `Recall` following the same pattern — construct before `MessageProcessor`:
```python
if recall is None:
    recall = Recall(vault=vault)

if message_processor is None:
    message_processor = MessageProcessor(
        vault=vault,
        ai_provider=ai_provider,
        injection_filter=injection_filter,
        output_scanner=output_scanner,
        recall=recall,
    )
```

**`AppGraph` field addition pattern** (lines 67–89, `AppGraph` dataclass):
```python
@dataclass(frozen=True)
class AppGraph:
    settings: "Settings"
    ...
    message_processor: "MessageProcessor"
    ...
```
Add: `recall: "Recall"` field to `AppGraph`.

**`build_application` signature extension** (line 236): add `recall: "Recall | None" = None` as a keyword-only parameter alongside the existing fakes (same position pattern as `injection_filter`, `output_scanner`).

**Import addition:**
```python
from app.services.recall import Recall
```

---

### `sentinel-core/app/state.py` (MODIFIED — add `recall` to `RouteContext`)

**Analog:** `sentinel-core/app/state.py` lines 45–58 (`RouteContext` dataclass)

**Existing field pattern** (lines 45–58):
```python
@dataclass(frozen=True)
class RouteContext:
    vault: "Vault"
    processor: "MessageProcessor | None" = None
    settings: "Settings | None" = None
    http_client: "httpx.AsyncClient | None" = None
    context_window: int = 4096
    lmstudio_stop_sequences: list[str] = field(default_factory=list)
    classify: Callable[[str], Awaitable[Any]] = _missing_classifier
    embedder: Callable[[list[str]], Awaitable[list[float]]] = _missing_embedder
    module_registry: dict[str, Any] = field(default_factory=dict)
    ai_provider_name: str | None = None
```
Add `recall` as an optional field with `None` default (keeps backward-compat with existing tests that construct `RouteContext` directly without it):
```python
recall: "Recall | None" = None
```

**TYPE_CHECKING import addition** (lines 27–32 of `state.py`):
```python
if TYPE_CHECKING:
    import httpx
    from app.config import Settings
    from app.services.message_processing import MessageProcessor
    from app.services.recall import Recall   # ADD
    from app.vault import Vault
```

**`initialize_startup` wiring** (lines 367–384 of `composition.py`):
```python
app.state.route_ctx = RouteContext(
    vault=graph.vault,
    processor=graph.message_processor,
    settings=graph.settings,
    http_client=graph.http_client,
    context_window=graph.context_window,
    ...
    recall=graph.recall,   # ADD
)
```

---

## Shared Patterns

### Frozen dataclass for value types
**Source:** `sentinel-core/app/services/message_processing.py` lines 89–104
**Apply to:** `SearchResult`, `RecalledContext`, `RecallConfig` in `recall.py`
```python
@dataclass(frozen=True)
class _ContextBudget:
    sessions_budget: int
    search_budget: int
```

### `asyncio.gather(..., return_exceptions=True)` for parallel vault reads
**Source:** `sentinel-core/app/services/message_processing.py` lines 204–208
**Apply to:** `Recall._hot_self()`, `Recall._warm_search()` note body fetches
```python
gather_results = await asyncio.gather(
    *[self._vault.read_self_context(p) for p in self_paths],
    return_exceptions=True,
)
```

### Guard-then-construct DI wiring
**Source:** `sentinel-core/app/composition.py` lines 294–313
**Apply to:** `Recall` construction in `build_application()`
```python
if recall is None:
    recall = Recall(vault=vault)
```

### pytest-asyncio `auto` mode (no per-test decorator)
**Source:** `sentinel-core/pyproject.toml` (`asyncio_mode = "auto"`)
**Apply to:** All `async def test_*` functions in `test_recall.py`
Bare `async def test_...():` — no `@pytest.mark.asyncio`.

### TYPE_CHECKING guard for forward references
**Source:** `sentinel-core/app/state.py` lines 27–32, `sentinel-core/app/composition.py` lines 38–49
**Apply to:** `recall.py` (Vault reference), `state.py` (Recall reference), `composition.py` (Recall reference)
```python
if TYPE_CHECKING:
    from app.vault import Vault
```

---

## No Analog Found

All files have close analogs in this repo. No external pattern invention needed.

---

## Metadata

**Analog search scope:** `sentinel-core/app/services/`, `sentinel-core/app/routes/`, `sentinel-core/app/`, `sentinel-core/tests/`, `sentinel-core/tests/fakes/`
**Files read:** 8
**Pattern extraction date:** 2026-06-11
