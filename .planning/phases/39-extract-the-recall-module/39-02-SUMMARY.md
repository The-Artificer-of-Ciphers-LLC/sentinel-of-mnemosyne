---
phase: 39-extract-the-recall-module
plan: "02"
subsystem: memory/recall
tags: [recall, memory, message-processor, dependency-injection, refactor, python]
completed_at: "2026-06-11T00:00:00Z"

dependency_graph:
  requires:
    - "sentinel-core/app/services/recall.py :: Recall, RecallConfig, RecalledContext, SearchResult, SEARCH_SCORE_THRESHOLD (Plan 01)"
  provides:
    - "sentinel-core/app/services/message_processing.py :: trimmed MessageProcessor delegating to Recall, SEARCH_SCORE_THRESHOLD re-export"
    - "sentinel-core/app/composition.py :: AppGraph.recall, build_application(recall=), initialize_startup pins recall"
    - "sentinel-core/app/state.py :: RouteContext.recall field"
  affects:
    - "sentinel-core/app/services/note_intake.py (import of _WARM_TIER_EXCLUDE_PREFIXES redirected)"
    - "sentinel-core/tests/test_composition.py (fake_graph SimpleNamespaces updated with recall=None)"

tech_stack:
  added: []
  patterns:
    - "guard-then-construct DI pattern: if recall is None: recall = Recall(vault=vault)"
    - "optional kwarg with None default preserves existing 4-kwarg test construction sites"
    - "re-export at module tail to break circular import (recall.py -> message_processing.py)"

key_files:
  created: []
  modified:
    - sentinel-core/app/services/message_processing.py
    - sentinel-core/app/composition.py
    - sentinel-core/app/state.py
    - sentinel-core/app/services/note_intake.py
    - sentinel-core/tests/test_composition.py

decisions:
  - "SEARCH_SCORE_THRESHOLD and _WARM_TIER_EXCLUDE_PREFIXES re-exported at bottom of message_processing.py (not top) to break circular import cycle: message_processing defines MessageRequest first, then imports from recall.py which itself imports MessageRequest"
  - "budget computation delegated to self._recall._allocate(budget) rather than inlined literals so ratio constants live only in RecallConfig (MEM-02 complete)"
  - "recall param on MessageProcessor defaults to None -> Recall(vault=vault) so 4-kwarg test construction sites remain untouched (Test-Rewrite Ban)"
  - "RouteContext.recall typed as optional (Recall | None = None) so existing tests constructing RouteContext without recall compile and run unchanged"

metrics:
  duration_minutes: 25
  tasks_completed: 2
  tasks_total: 2
  files_created: 0
  files_modified: 5
---

# Phase 39 Plan 02: Wire MessageProcessor to Recall + DI Graph — Summary

**One-liner:** Trimmed MessageProcessor to delegate hot+warm tier assembly to Recall.assemble(), removed all relocated constants, and wired Recall through AppGraph/RouteContext via guard-then-construct; full suite stays green at 285 passed.

---

## What Was Built

### `sentinel-core/app/services/message_processing.py` (trimmed)

**Removed (relocated to recall.py in Plan 01):**
- `SEARCH_SCORE_THRESHOLD` literal (re-exported by name from recall.py)
- `_WARM_TIER_EXCLUDE_PREFIXES`, `_SEARCH_STOPWORDS`, `_KEYWORD_SEARCH_THRESHOLD`
- `_extract_keywords`, `_best_search_query`
- `_ContextBudget` dataclass
- `_SESSIONS_RATIO`, `_SEARCH_RATIO` class attributes
- `_allocate_budgets` classmethod
- `_append_hot_tier`, `_append_warm_tier` methods

**Added / modified:**
- `MessageProcessor.__init__` now accepts an optional `recall: Recall | None = None` keyword arg; defaults to `Recall(vault=vault)` — preserves all existing 4-kwarg test construction sites (Test-Rewrite Ban, no test edits needed for this param)
- `process()` rewritten to call `recalled = await self._recall.assemble(req, req.context_window)` for hot+warm assembly
- Per-tier budgets sourced from `self._recall._allocate(req.context_window)` — ratios live only in RecallConfig (MEM-02)
- Persona swap, injection filter, hot-tier and warm-tier presentation, `_format_search_results`, session summary, TokenBudget.check() all retained in MessageProcessor (D-04)
- `_format_search_results` adapted to consume `list[SearchResult]` (reads `r.path`, `r.body`) instead of raw dicts; exact output format preserved byte-for-byte

**Re-exports at module tail (circular import workaround):**
- `from app.services.recall import SEARCH_SCORE_THRESHOLD as SEARCH_SCORE_THRESHOLD`
- `from app.services.recall import _WARM_TIER_EXCLUDE_PREFIXES as _WARM_TIER_EXCLUDE_PREFIXES`

Both re-exports are placed at the bottom of the file so that `MessageRequest` (which `recall.py` needs) is defined before the import occurs, breaking the circular import cycle.

### `sentinel-core/app/composition.py`

- Added eager `from app.services.recall import Recall` import
- Added `recall: "Recall"` to `AppGraph` frozen dataclass
- Added `recall: "Recall | None" = None` keyword parameter to `build_application`
- Added guard-then-construct: `if recall is None: recall = Recall(vault=vault)` (before `message_processor` block, after `vault` is resolved)
- Passed `recall=recall` to `MessageProcessor(...)` construction
- Included `recall=recall` in `AppGraph(...)` return
- Added `recall=graph.recall` to `RouteContext(...)` construction in `initialize_startup`

### `sentinel-core/app/state.py`

- Added `from app.services.recall import Recall` under `TYPE_CHECKING`
- Added `recall: "Recall | None" = None` optional field to `RouteContext` dataclass — defaults to `None` so existing tests constructing `RouteContext` without this field continue to work

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `note_intake.py` imported `_WARM_TIER_EXCLUDE_PREFIXES` from `message_processing`**
- **Found during:** Task 1 (first test run after rewrite)
- **Issue:** `app/services/note_intake.py` line 24 imported `_WARM_TIER_EXCLUDE_PREFIXES` from `message_processing` which was removed in this plan
- **Fix:** Updated import to `from app.services.recall import _WARM_TIER_EXCLUDE_PREFIXES`
- **Files modified:** `sentinel-core/app/services/note_intake.py`
- **Commit:** `9722519`

**2. [Rule 3 - Blocking] `test_message.py` imported `_WARM_TIER_EXCLUDE_PREFIXES` from `message_processing` inside a test function**
- **Found during:** Task 1 (second test run)
- **Issue:** `tests/test_message.py` line 1259 contained a local `from app.services.message_processing import _WARM_TIER_EXCLUDE_PREFIXES` inside `test_chat_note_path_passes_warm_tier_exclusion_filter`
- **Fix:** Added `_WARM_TIER_EXCLUDE_PREFIXES` to the module-tail re-exports in `message_processing.py` (alongside `SEARCH_SCORE_THRESHOLD`) — no test edits needed
- **Files modified:** `sentinel-core/app/services/message_processing.py`
- **Commit:** `9722519`

**3. [Rule 3 - Blocking] `test_composition.py` fake_graph SimpleNamespace missing `recall` field**
- **Found during:** Task 2 (first test run after DI wiring)
- **Issue:** Three `fake_graph = SimpleNamespace(...)` calls in `test_composition.py` lacked a `recall` attribute; `initialize_startup` now accesses `graph.recall`
- **Fix:** Added `recall=None` to each of the three fake_graph SimpleNamespaces
- **Files modified:** `sentinel-core/tests/test_composition.py`
- **Commit:** `6a2c143`

---

## Test Results

```
285 passed, 12 skipped in 13.75s
```

Baseline was 285 passed, 12 skipped — zero regressions.

Key regression nets:
- `tests/test_message_processor.py`: 20 passed (behavior-preserving unit tests)
- `tests/test_message.py`: 25 passed (through-/message integration tests)

---

## Threat Surface Scan

No new external surface. This is an internal refactor — no new endpoints, no new auth boundaries, no new untrusted input paths. The injection_filter wrapping of both hot-tier and warm-tier content is preserved unchanged in MessageProcessor (T-39-03 mitigated). The warm-tier namespace exclusion (T-39-04) is preserved via delegation to Recall.assemble() which applies RecallConfig.exclude_prefixes.

---

## Known Stubs

None. All data flows are wired end-to-end.

---

## Self-Check

### Files exist
- `/Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/app/services/message_processing.py` — FOUND
- `/Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/app/composition.py` — FOUND
- `/Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/app/state.py` — FOUND

### Commits exist
- `9722519` — refactor(39-02): trim MessageProcessor to delegate to Recall; re-export moved constants
- `6a2c143` — feat(39-02): wire Recall through DI graph (AppGraph, build_application, RouteContext)

### Verification checks

| Check | Result |
|-------|--------|
| `self._recall.assemble` in message_processing.py | line 82 — PASS |
| `_append_hot_tier`, `_append_warm_tier` absent | 0 matches — PASS |
| Non-comment lines with `0.15\|0.10\|-200.0\|_SEARCH_STOPWORDS` | 0 — PASS |
| `read_self_context("sentinel/persona.md")` in message_processing.py | line 94 — PASS |
| `_format_search_results` in message_processing.py | lines 121, 166 — PASS |
| `recall: "Recall"` in AppGraph | line 89 — PASS |
| `if recall is None` guard | line 311 — PASS |
| `recall=recall` in composition.py (>=2) | lines 320, 369 — PASS |
| `recall=graph.recall` in initialize_startup | line 393 — PASS |
| `recall:` in RouteContext | line 60 — PASS |
| vault.py unmodified | empty diff — PASS |
| Full suite | 285 passed, 12 skipped — PASS |

## Self-Check: PASSED
