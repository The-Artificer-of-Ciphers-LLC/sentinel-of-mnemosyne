---
phase: 39-extract-the-recall-module
verified: 2026-06-11T00:00:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
---

# Phase 39: Extract the Recall Module — Verification Report

**Phase Goal:** Retrieval becomes a first-class `Recall` module above the Vault seam, returning `RecalledContext`; `MessageProcessor` and `GET /context/{user_id}` both delegate to it. Behavior-preserving extraction — relevance threshold, namespace exclusions (incl. `ops/`), and per-tier context budgets move into an explicit `RecallConfig`.
**Verified:** 2026-06-11T00:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                              | Status     | Evidence                                                                                          |
|----|----------------------------------------------------------------------------------------------------|------------|---------------------------------------------------------------------------------------------------|
| 1  | `Recall.assemble()` is sole hot+warm assembly entry point; `MessageProcessor` has no inline tier methods | VERIFIED | recall.py:297 defines `assemble()`; message_processing.py grep confirms no `_append_hot_tier`, `_append_warm_tier`, `_allocate_budgets`; MP calls `self._recall.assemble()` at line 82 |
| 2  | `GET /context/{user_id}` delegates to `ctx.recall.assemble()` with null guard, no duplicated assembly | VERIFIED | status.py:48-50 — null guard `if ctx.recall is None: raise RuntimeError(...)`, then `await ctx.recall.assemble(fake_req, budget=ctx.context_window)` at line 50 |
| 3  | `RecallConfig` owns relevance threshold, namespace exclusions (incl. `ops/`), and per-tier budget ratios | VERIFIED | recall.py:137-180 — `RecallConfig` dataclass: `relevance_threshold=-200.0`, `exclude_prefixes=("ops/", "_trash/", "self/")`, `sessions_ratio=0.15`, `search_ratio=0.10` |
| 4  | `tests/test_recall.py` passes against `FakeVault` without `MessageProcessor`/AI provider         | VERIFIED | 8/8 tests pass in 0.06s; test file imports only `FakeVault`, `Recall`, `RecallConfig`, `RecalledContext`, `SearchResult`, `MessageRequest` — no processor or AI provider |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact                                                  | Expected                                         | Status   | Details                                                                         |
|-----------------------------------------------------------|--------------------------------------------------|----------|---------------------------------------------------------------------------------|
| `sentinel-core/app/services/recall.py`                   | Recall module with RecallConfig, assemble()      | VERIFIED | 317 lines; `Recall`, `RecallConfig`, `RecalledContext`, `SearchResult` defined; `allocate()` public (WR-02 fix applied); `_ContextBudget` removed from `__all__` (IN-01 fix applied) |
| `sentinel-core/app/services/message_processing.py`       | Delegates to Recall, no inline assembly logic    | VERIFIED | 215 lines; `self._recall.assemble()` at line 82; `self._recall.allocate()` at line 86; circular import broken via `TYPE_CHECKING` guard (CR-02 fix applied) |
| `sentinel-core/app/routes/status.py`                     | `/context/{user_id}` delegates to `ctx.recall.assemble()` | VERIFIED | 59 lines; null guard at line 48; `ctx.recall.assemble()` at line 50 (CR-01 fix applied) |
| `sentinel-core/tests/test_recall.py`                     | Behavioral tests against FakeVault only          | VERIFIED | 199 lines; 8 tests covering self_context, sessions, warm inclusion/exclusion, threshold, graceful degrade, custom config, empty-content guard |

### Key Link Verification

| From                          | To                                | Via                                    | Status   | Details                                                                             |
|-------------------------------|-----------------------------------|----------------------------------------|----------|-------------------------------------------------------------------------------------|
| `MessageProcessor`            | `Recall.assemble()`               | `self._recall.assemble(req, context_window)` at line 82 | WIRED | Both call and result consumed (`recalled = await ...`) |
| `MessageProcessor`            | `Recall.allocate()`               | `self._recall.allocate(req.context_window)` at line 86 | WIRED | Public method used; budgets consumed at lines 87-88 |
| `GET /context/{user_id}`      | `Recall.assemble()`               | `ctx.recall.assemble(fake_req, budget=...)` at line 50 | WIRED | Null guard at line 48; result serialized into JSONResponse |
| `Recall._warm_search()`       | `RecallConfig.exclude_prefixes`   | `self._config.exclude_prefixes` at line 264 | WIRED | Filter applied before constructing `SearchResult` |
| `Recall._warm_search()`       | `RecallConfig.relevance_threshold` | `self._config.relevance_threshold` at line 263 | WIRED | Score threshold gate applied |
| `MessageProcessor.__init__`   | `Recall` (lazy import, no module-level circular) | `from app.services.recall import Recall` inside `if recall is None` block at line 77 | WIRED | `TYPE_CHECKING` guard prevents module-level circular import (CR-02 fix) |

### Data-Flow Trace (Level 4)

| Artifact              | Data Variable   | Source                                  | Produces Real Data | Status   |
|-----------------------|-----------------|-----------------------------------------|--------------------|----------|
| `status.py` debug_context | `recalled` (`RecalledContext`) | `ctx.recall.assemble()` → Vault reads | Yes — Vault I/O calls in `_hot_self`, `_hot_sessions`, `_warm_search` | FLOWING |
| `message_processing.py` `process()` | `recalled` (`RecalledContext`) | `self._recall.assemble()` → Vault reads | Yes — same Vault I/O path | FLOWING |

### Behavioral Spot-Checks

| Behavior                                          | Command                                              | Result            | Status |
|---------------------------------------------------|------------------------------------------------------|-------------------|--------|
| test_recall.py all 8 tests pass                   | `uv run pytest tests/test_recall.py -v`              | 8 passed in 0.06s | PASS   |
| Full suite 287 passed, 12 skipped                 | `uv run pytest -q`                                   | 287 passed, 12 skipped in 13.99s | PASS |
| `RecallConfig` has correct default field values   | Python introspection via `uv run python3 -c`         | `relevance_threshold=-200.0`, `exclude_prefixes=('ops/', '_trash/', 'self/')`, ratios confirmed | PASS |
| `Recall.allocate` is public (not `_allocate`)     | `hasattr(Recall, 'allocate')` → True                 | True              | PASS   |
| `_ContextBudget` absent from `__all__`            | `__all__` check                                      | `['Recall', 'RecallConfig', 'RecalledContext', 'SearchResult', 'SEARCH_SCORE_THRESHOLD']` — `_ContextBudget` absent | PASS |
| Circular import broken — recall importable first  | `from app.services import recall` before message_processing | No ImportError | PASS |

### Requirements Coverage

| Requirement | Phase | Description                                                                                                  | Status    | Evidence                                                                                      |
|-------------|-------|--------------------------------------------------------------------------------------------------------------|-----------|-----------------------------------------------------------------------------------------------|
| MEM-01      | 39    | Single Recall module for every message; `/context/{user_id}` uses same module; no duplicated assembly logic | SATISFIED | `MessageProcessor.process()` line 82 and `status.py` line 50 both delegate to `Recall.assemble()`; no inline assembly in either file |
| MEM-02      | 39    | Recall policy (threshold, namespace exclusions incl. `ops/`, per-tier budgets) as explicit config not inline constants | SATISFIED | `RecallConfig` dataclass at recall.py:137-180; all 4 policy dimensions consolidated; `message_processing.py` reads budgets via `self._recall.allocate()` |

### Anti-Patterns Found

| File                                       | Line | Pattern                                      | Severity | Impact                                                                                                     |
|--------------------------------------------|------|----------------------------------------------|----------|------------------------------------------------------------------------------------------------------------|
| `app/services/message_processing.py`       | 213-214 | `# noqa: E402` bottom-of-file re-exports    | Info     | Deliberate load-order technique to break circular import; comment at line 207-212 explicitly documents the reasoning. Not a blocker — the circular import itself was fixed via `TYPE_CHECKING` guard (CR-02). Re-exports remain for backward compatibility. |
| `app/services/recall.py`                   | 284-290 | Empty-body `SearchResult` still appended when snippet is also empty | Warning (WR-01 unresolved) | `note_body = ""` when both full read and snippet fail; the `SearchResult` with empty body is appended. Downstream `_format_search_results` renders it as a bare filename bullet. Not a blocker for phase goal (assembly is functional), but WR-01 from code review was not applied. |

**WR-01 status note:** The code review recommended filtering empty-body results before constructing `SearchResult`. The current code at recall.py:284-290 still appends the result even when `note_body = ""`. This is a minor quality regression relative to the WR-01 recommendation, but does NOT block the phase goal — the assembly, delegation, and config extraction succeed. The full suite passes. This is a warning, not a blocker.

### Human Verification Required

None. All four success criteria are verifiable programmatically and confirmed above.

### Gaps Summary

No gaps. All four success criteria are VERIFIED:

1. `Recall.assemble()` is the sole hot+warm entry point — `MessageProcessor` has no inline tier methods.
2. `GET /context/{user_id}` delegates to `ctx.recall.assemble()` with null guard (CR-01 fix applied).
3. `RecallConfig` consolidates all policy: relevance threshold (`-200.0`), namespace exclusions (`ops/`, `_trash/`, `self/`), and per-tier budget ratios (`sessions_ratio=0.15`, `search_ratio=0.10`).
4. `tests/test_recall.py` passes 8/8 tests against `FakeVault` with no `MessageProcessor` or AI provider dependency.

The full suite is green: **287 passed, 12 skipped**.

All four code-review critical fixes were applied: CR-01 (null guard on `ctx.recall`), CR-02 (`TYPE_CHECKING` guard breaking the circular import), WR-02 (`_allocate` promoted to public `allocate`), and IN-01 (`_ContextBudget` removed from `__all__`). WR-01 (empty-body SearchResult filter) and WR-03 (outer `asyncio.gather` `return_exceptions`) were not applied but neither blocks the phase goal.

---

_Verified: 2026-06-11T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
