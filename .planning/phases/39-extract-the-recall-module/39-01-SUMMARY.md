---
phase: 39-extract-the-recall-module
plan: "01"
subsystem: memory/recall
tags: [recall, memory, retrieval, refactor, python]
completed_at: "2026-06-11T14:06:32Z"

dependency_graph:
  requires: []
  provides:
    - "sentinel-core/app/services/recall.py :: Recall, RecallConfig, RecalledContext, SearchResult, SEARCH_SCORE_THRESHOLD, MessageRequest"
    - "sentinel-core/tests/test_recall.py :: 8 behavioral tests for Recall.assemble()"
  affects:
    - "sentinel-core/app/services/message_processing.py (upstream source — read but not modified)"

tech_stack:
  added: []
  patterns:
    - "frozen dataclass value types (SearchResult, RecalledContext, RecallConfig)"
    - "asyncio.gather(..., return_exceptions=True) for parallel vault reads"
    - "pytest-asyncio auto mode (no per-test decorator)"
    - "FakeVault method-assignment override for threshold/find() tests"

key_files:
  created:
    - sentinel-core/app/services/recall.py
    - sentinel-core/tests/test_recall.py
  modified: []

decisions:
  - "ops/reminders.md kept in RecallConfig.self_paths despite ops/ being in exclude_prefixes — the exclusion applies only to warm-tier vault.find() results, not the self_paths allowlist (D-02, Pitfall 2)"
  - "_warm_search returns [] early when content.strip() is empty, before calling vault.find() — avoids matching all notes on empty queries (Pitfall 8 Option A)"
  - "_allocate uses int() truncation not round() to preserve exact existing budget arithmetic (Pitfall 3)"
  - "MessageRequest re-exported from recall.py via top-level import so callers can import it from either module"
  - "sentinel/persona.md path absent from recall.py entirely — MessageProcessor retains its own direct vault.read_self_context call (D-04)"

metrics:
  duration_minutes: 30
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 0
---

# Phase 39 Plan 01: Create the Recall Module — Summary

**One-liner:** Extracted hot/warm retrieval policy from MessageProcessor into standalone `Recall` module with `RecallConfig` consolidating all inline constants, plus 8 FakeVault-backed behavioral tests proving behavior preservation.

---

## What Was Built

### `sentinel-core/app/services/recall.py` (325 lines)

New module that owns retrieval policy as a first-class, independently testable service.

**Value types:**
- `SearchResult(path, score, body)` — frozen dataclass; warm-tier result with raw vault content
- `RecalledContext(self_context, sessions, warm)` — pure value type returned by `assemble()`; never contains chat messages or injection-wrapped text
- `RecallConfig` — frozen dataclass consolidating all formerly-inline policy constants (MEM-02):
  - `relevance_threshold = -200.0` (was `SEARCH_SCORE_THRESHOLD`)
  - `exclude_prefixes = ("ops/", "_trash/", "self/")` (was `_WARM_TIER_EXCLUDE_PREFIXES`)
  - `sessions_ratio = 0.15`, `search_ratio = 0.10` (was `MessageProcessor._SESSIONS_RATIO/_SEARCH_RATIO`)
  - `recent_session_limit = 3` (was hard-coded in `get_recent_sessions` call)
  - `self_paths` (was hard-coded list in `_append_hot_tier`)
  - `warm_top_n = 3` (was hard-coded `[:3]`)
- `_ContextBudget(sessions_budget, search_budget)` — budget split value type (moved from message_processing.py)

**Module-level constants moved verbatim:** `SEARCH_SCORE_THRESHOLD`, `_WARM_TIER_EXCLUDE_PREFIXES`, `_SEARCH_STOPWORDS`, `_KEYWORD_SEARCH_THRESHOLD`, `_extract_keywords`, `_best_search_query`

**`Recall` class methods:**
- `__init__(vault, *, config=None)` — dependency injection via vault Protocol
- `async assemble(request, budget) -> RecalledContext` — public entry point; gathers all three tiers concurrently
- `async _hot_self() -> list[str]` — reads exactly 6 `self_paths` (no `sentinel/*.md`)
- `async _hot_sessions(user_id) -> list[str]` — delegates to `vault.get_recent_sessions`
- `async _warm_search(content) -> list[SearchResult]` — early-exit on empty content; filters by threshold + exclude_prefixes; translates raw dicts to `SearchResult` at this boundary
- `_allocate(budget) -> _ContextBudget` — uses `int()` truncation to preserve exact existing arithmetic

**Re-export:** `MessageRequest` re-exported from `app.services.message_processing` so consumers can import it from either module.

### `sentinel-core/tests/test_recall.py` (197 lines)

8 behavioral tests driving `Recall.assemble()` directly against `FakeVault`. Zero references to `MessageProcessor`, AI provider, or injection filter (success criterion #4).

| Test | What it proves |
|------|----------------|
| `test_assemble_returns_self_context` | self_context populated from seeded self notes; ops/reminders.md IS returned (Pitfall 2) |
| `test_assemble_returns_sessions` | sessions populated from ops/sessions/* matching user_id |
| `test_warm_includes_above_threshold_non_excluded` | notes scoring ≥ -200.0 in notes/ appear in warm |
| `test_warm_excludes_self_and_ops_prefixes` | ops/, self/, _trash/ prefixes never appear in warm |
| `test_warm_excludes_below_threshold` | score=-300.0 result (via find() override) excluded from warm |
| `test_empty_vault_graceful_degrade` | empty vault → all lists empty, no exceptions |
| `test_recall_config_respected` | custom RecallConfig.exclude_prefixes drives filtering (MEM-02) |
| `test_empty_content_skips_find` | content="" → warm=[] without calling vault.find() |

**Test run result:** 8 passed in 0.08s (`uv run pytest tests/test_recall.py -x`)

---

## Constraints Honored

| Constraint | Status |
|-----------|--------|
| D-04: `sentinel/persona.md` never in recall.py | PASS — no "persona" in source code |
| D-04: No InjectionFilter/TokenBudget in recall.py | PASS — zero references |
| D-06/ADR-0002: vault.py unmodified | PASS — `git diff -- sentinel-core/app/vault.py` is empty |
| Pitfall 2: ops/reminders.md in self_paths | PASS — test 1 asserts it |
| Pitfall 3: int() truncation not round() | PASS — no round() in recall.py |
| Pitfall 8 Option A: empty content skips find() | PASS — test 8 proves it |
| MEM-02: constants in RecallConfig | PASS — all 7 constants consolidated |

---

## Deviations from Plan

None. Plan executed exactly as written.

---

## Threat Surface Scan

No new external surface introduced. `Recall` consumes only the existing `Vault` Protocol. No new endpoints, no auth boundaries, no new untrusted input paths.

The warm-tier namespace exclusion (T-39-01) is preserved verbatim in `RecallConfig.exclude_prefixes` and applied via `str.startswith(tuple)` — proven by tests 4 and 7.

---

## Self-Check

### Files exist

- `/Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/app/services/recall.py` — FOUND (325 lines)
- `/Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/tests/test_recall.py` — FOUND (197 lines)

### Commits exist

- `fa527c1` — feat(39-01): create Recall module with value types, RecallConfig, and Recall class
- `20f71c7` — test(39-01): add test_recall.py — 8 behavioral tests for Recall.assemble() against FakeVault

### Test run

```
8 passed in 0.08s
```

## Self-Check: PASSED
