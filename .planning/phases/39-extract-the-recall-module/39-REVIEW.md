---
phase: 39-extract-the-recall-module
reviewed: 2026-06-11T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - sentinel-core/app/services/recall.py
  - sentinel-core/app/services/message_processing.py
  - sentinel-core/app/composition.py
  - sentinel-core/app/state.py
  - sentinel-core/app/routes/status.py
  - sentinel-core/tests/test_recall.py
  - sentinel-core/tests/test_status.py
  - sentinel-core/tests/test_message.py
findings:
  critical: 2
  warning: 3
  info: 2
  total: 7
status: resolved
---

# Phase 39: Code Review Report

**Reviewed:** 2026-06-11
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

This phase extracts hot/warm-tier retrieval from `MessageProcessor` into a new `Recall` module. The
refactor is mostly clean — constants are faithfully ported, the persona boundary is respected, and
`status.py` delegates without duplication. Two critical defects were found: a null-dereference crash
on the `GET /context/{user_id}` path when `recall` is `None` on `RouteContext`, and a circular
import at module load time that creates a fragile load-order dependency. Three warnings cover an
empty `SearchResult` being silently appended to results, `_allocate` being called through a name-
mangled private boundary, and a missing `return_exceptions` guard on the outer `asyncio.gather` in
`assemble()`. Two info-level notes cover dead re-exports and a test constant import that bypasses the
canonical source.

---

## Critical Issues

### CR-01: `ctx.recall.assemble()` crashes with `AttributeError` when `recall` is `None`

**File:** `sentinel-core/app/routes/status.py:48`

**Issue:** `RouteContext.recall` is typed `Recall | None` with a default of `None` (state.py line 60).
The `debug_context` handler calls `ctx.recall.assemble(...)` directly with no null guard. Any test or
deployment path that constructs a `RouteContext` without explicitly supplying a `recall=` argument
(e.g., minimal health-check routes, future test stubs) will crash with `AttributeError: 'NoneType'
object has no attribute 'assemble'` instead of returning a meaningful HTTP error. The existing test
fixture in `test_status.py` always passes `recall=Recall(vault=app.state.vault)`, so the crash is
masked from the test suite — it would surface in production if `route_ctx` is ever constructed
without a `recall` (e.g., if the startup order changes or a degraded-startup path omits it).

**Fix:** Add a null guard and return a 503 (or raise an `HTTPException`) before dereferencing:

```python
@router.get("/context/{user_id}")
async def debug_context(
    request: Request,
    user_id: str = Path(..., pattern=r"^[a-zA-Z0-9_-]+$"),
) -> JSONResponse:
    ctx = get_route_context(request)
    if ctx.recall is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Recall not configured")
    recalled = await ctx.recall.assemble(fake_req, budget=ctx.context_window)
    ...
```

Alternatively, make `recall` a required (non-optional) field in `RouteContext`, which forces every
construction site to supply it and removes the entire class of null-dereference errors.

---

### CR-02: Circular import at module load time — load-order dependent

**File:** `sentinel-core/app/services/recall.py:188`

**Issue:** `recall.py` performs a **module-level** (non-guarded) import of `MessageRequest` from
`message_processing` at line 188:

```python
from app.services.message_processing import MessageRequest  # noqa: E402
```

`message_processing.py` in turn imports from `recall.py` at its own module level (line 213–214):

```python
from app.services.recall import SEARCH_SCORE_THRESHOLD as SEARCH_SCORE_THRESHOLD
from app.services.recall import _WARM_TIER_EXCLUDE_PREFIXES as _WARM_TIER_EXCLUDE_PREFIXES
```

This creates a **real circular dependency at import time**, not just a conceptual one. Python's
import machinery tolerates this in CPython today because, at the moment `recall.py` line 188 is
executed, `MessageRequest` has already been defined in `message_processing`'s partially-initialised
module object (since `recall.py` is imported from the bottom of `message_processing.py`, after
`MessageRequest` is defined). However:

1. The correctness of this depends entirely on import order. If anything changes the order in which
   Python processes these two modules (e.g., a new top-level import, a pytest import scan, a
   `importlib.reload`), the `ImportError` / `AttributeError` surface changes unpredictably.
2. The `# noqa: E402` comment is a smell that this import is already known to be problematic.
3. `recall.py` already uses `TYPE_CHECKING` guards for the `Vault` type, proving the author knows
   the pattern — it was not applied here.

`MessageRequest` is a data class with no dependency on `Recall`. Moving its definition to a thin
shared module (e.g., `app.services.types` or `app.models`) would sever the cycle cleanly.

**Fix (preferred):** Move `MessageRequest` to `app/services/types.py` (or keep it in
`message_processing.py`) and import it into `recall.py` only under `TYPE_CHECKING`:

```python
# recall.py
if TYPE_CHECKING:
    from app.services.message_processing import MessageRequest
```

Then expose it for callers through `message_processing.py` directly (where it already lives), and
remove the re-export from `recall.py` entirely. If the re-export is required for caller convenience,
document the fragile order constraint explicitly and add an integration-level import test.

---

## Warnings

### WR-01: Empty-body `SearchResult` silently appended — may inject blank vault blocks

**File:** `sentinel-core/app/services/recall.py:286-299`

**Issue:** In `_warm_search`, when both `read_note` fails (returns empty string or raises) **and**
the search result has no `matches`, the fallback produces `note_body = ""`. A `SearchResult` with
`body=""` is still appended to `results` and returned. Downstream in `MessageProcessor._format_search_results`
(message_processing.py line 174–179), the check `if isinstance(body, str) and body.strip()` means
the empty-body result produces `f"- **{filename}**"` — a bare filename bullet with no content —
which is then injected into the LLM prompt as a "Relevant vault notes:" block. This is vacuous
context noise, not graceful degrade. The filtering of empty bodies should happen here, before
constructing the `SearchResult`.

**Fix:**

```python
# Only append if we have actual content
if note_body:
    results.append(SearchResult(path=r["filename"], score=r["score"], body=note_body))
```

---

### WR-02: `MessageProcessor` calls `self._recall._allocate()` — violates name-mangling convention

**File:** `sentinel-core/app/services/message_processing.py:86`

**Issue:**

```python
budgets = self._recall._allocate(req.context_window)
```

`_allocate` carries a single-underscore name indicating it is private to the `Recall` class.
`MessageProcessor` is a separate class in a separate module accessing a private method across the
class boundary. This is not blocked by Python (single underscore is convention, not enforcement),
but it:

1. Couples `MessageProcessor` to `Recall`'s internal allocation API, making the private method part
   of the de facto public contract without declaring it so.
2. Creates a silent failure mode if `self._recall` is a mock or stub that does not implement
   `_allocate` — the test suite's `_LazyTestProcessor` (test_message.py line 79–86) constructs a
   real `Recall`, so it currently works, but any future stub will silently break.

**Fix:** Promote `_allocate` to a public method `allocate(budget: int) -> _ContextBudget` (or return
the budgets directly from `assemble()`), or compute the budgets inline in `MessageProcessor` from the
public `RecallConfig` constants:

```python
# Option A: promote to public
budgets = self._recall.allocate(req.context_window)

# Option B: compute directly without crossing the boundary
cfg = self._recall._config  # still private, but less surprising
sessions_budget = int(req.context_window * cfg.sessions_ratio)
search_budget = int(req.context_window * cfg.search_ratio)
```

The cleanest long-term fix is to have `assemble()` return `(RecalledContext, _ContextBudget)` so
callers never need to call `_allocate` separately.

---

### WR-03: `assemble()` outer `asyncio.gather` does not use `return_exceptions=True` — exceptions propagate immediately

**File:** `sentinel-core/app/services/recall.py:316-320`

**Issue:**

```python
self_context, sessions, warm = await asyncio.gather(
    self._hot_self(),
    self._hot_sessions(request.user_id),
    self._warm_search(request.content),
)
```

The inner `_hot_self()` gather uses `return_exceptions=True` (line 238), so a failing
`vault.read_self_context` degrades gracefully. The inner `_warm_search()` gather also uses
`return_exceptions=True` (line 280). However, the **outer** gather in `assemble()` does NOT use
`return_exceptions=True`. If `_hot_sessions()` raises (e.g., a network error in production that
is not caught by `ObsidianVault`'s `_safe_request` wrapper), the entire `assemble()` call raises,
propagating to `MessageProcessor.process()` as an uncaught exception that results in HTTP 500
rather than graceful degradation.

The pre-refactor code did not call `get_recent_sessions` inside a gather without exception
handling, so this represents a narrowing of the graceful-degrade envelope post-refactor.

**Fix:** Either wrap `assemble()` in a try/except in `MessageProcessor`, or use
`return_exceptions=True` on the outer gather with explicit exception-to-empty-list coercion:

```python
results = await asyncio.gather(
    self._hot_self(),
    self._hot_sessions(request.user_id),
    self._warm_search(request.content),
    return_exceptions=True,
)
self_context = results[0] if isinstance(results[0], list) else []
sessions    = results[1] if isinstance(results[1], list) else []
warm        = results[2] if isinstance(results[2], list) else []
return RecalledContext(self_context=self_context, sessions=sessions, warm=warm)
```

---

## Info

### IN-01: `_ContextBudget` exported in `__all__` despite being an implementation-private type

**File:** `sentinel-core/app/services/recall.py:197`

**Issue:** `_ContextBudget` carries a leading underscore (private by convention) but is listed in
`__all__`, exporting it as part of the module's public API. `__all__` and the leading underscore
signal opposite things about the intended visibility of this type.

**Fix:** Remove `"_ContextBudget"` from `__all__`, or rename the class to `ContextBudget` if it
truly belongs in the public contract.

---

### IN-02: `test_message.py` imports `_WARM_TIER_EXCLUDE_PREFIXES` from `message_processing` instead of `recall`

**File:** `sentinel-core/tests/test_message.py:1265, 1284, 1305`

**Issue:** Multiple test assertions import `_WARM_TIER_EXCLUDE_PREFIXES` from
`app.services.message_processing`:

```python
from app.services.message_processing import _WARM_TIER_EXCLUDE_PREFIXES
```

After this phase's refactor, the canonical source of truth for `_WARM_TIER_EXCLUDE_PREFIXES` is
`app.services.recall`. `message_processing` only re-exports it (line 214). Tests consuming the
re-export will continue to pass (the value is the same object), but the import points to the
wrong canonical source. If `message_processing` ever drops the re-export, these tests break
silently until the next test run.

**Fix:** Update the imports to reference the canonical source:

```python
from app.services.recall import _WARM_TIER_EXCLUDE_PREFIXES
```

---

_Reviewed: 2026-06-11_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

## Resolution (2026-06-11)

All findings reviewed against the actual code and the pre-refactor original. 4 genuine defects fixed; 3 dispositioned as preserved-behavior / by-design. Full suite after fixes: **287 passed, 12 skipped**.

| ID | Verdict | Resolution |
|----|---------|------------|
| CR-02 | Real circular import | FIXED — `MessageRequest` import moved under `TYPE_CHECKING` in `recall.py`; new subprocess regression test `tests/test_recall_imports.py`. Commit `e4059a6` |
| CR-01 | Real (type lied; not a prod crash — `build_application` always wires recall) | FIXED — explicit `None` guard before `ctx.recall.assemble()` in `status.py:48-49`. Commit `937dd08` |
| WR-02 | Real private-method coupling | FIXED — `Recall._allocate` promoted to public `allocate()`; caller updated. Commit `d43bafc` |
| IN-01 | Real minor | FIXED — `_ContextBudget` removed from `recall.__all__`. Commit `c820060` |
| WR-03 | NOT a regression | PRESERVED — original used sequential awaits with identical exception propagation; inner gathers use `return_exceptions=True` in both. Adding it to the outer gather would make behavior more lenient than the original (out of scope for a behavior-preserving extraction). |
| WR-01 | NOT a regression | PRESERVED — original `_format_search_results` also emitted a bare filename for empty bodies; refactor preserves that behavior. |
| IN-02 | Working as designed | KEPT — the `message_processing` re-export of `_WARM_TIER_EXCLUDE_PREFIXES` exists precisely so existing tests keep importing it (Test-Rewrite Ban). |
