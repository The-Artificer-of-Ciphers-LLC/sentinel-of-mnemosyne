---
phase: 41-typed-sessionsummary-retention
plan: "01"
subsystem: sentinel-core/recall
tags: [tdd, value-types, recall, session-summary, retention-policy, recency-weight]
dependency_graph:
  requires: []
  provides:
    - SessionSummary frozen dataclass in app/services/recall.py
    - RetentionPolicy frozen dataclass in app/services/recall.py
    - recency_weight pure helper in app/services/recall.py
  affects:
    - sentinel-core/tests/test_recall.py
tech_stack:
  added: []
  patterns:
    - frozen dataclass value type (existing recall.py pattern)
    - exponential decay recency weighting with midnight-normalised date comparison
    - fail-open error handling for hostile vault input (T-41-01)
key_files:
  created: []
  modified:
    - sentinel-core/app/services/recall.py
    - sentinel-core/tests/test_recall.py
decisions:
  - recency_weight normalises `now` to midnight UTC before computing age_days so a same-day YYYY-MM-DD always yields age_days=0 and weight=1.0 regardless of the time component of `now`
  - RecallConfig.recent_session_limit preserved (not removed) — deferral to Plan 04 lockstep with _hot_sessions consumer
  - RetentionPolicy is a standalone frozen dataclass, NOT a field of RecallConfig (OQ3 resolution)
metrics:
  duration: "3 min"
  completed: "2026-06-12"
  tasks_completed: 3
  files_modified: 2
---

# Phase 41 Plan 01: Typed Value Contracts (SessionSummary + RetentionPolicy + recency_weight) Summary

**One-liner:** Frozen `SessionSummary` and `RetentionPolicy` dataclasses plus `recency_weight` exponential-decay helper added to `recall.py`, pinned by RED→GREEN TDD tests.

## What Was Built

Three new symbols exported from `sentinel-core/app/services/recall.py`:

1. **`SessionSummary`** (`@dataclass(frozen=True)`) — 7-field typed value type: `date: str`, `user_id: str`, `time: str`, `user_msg: str`, `sentinel_msg: str`, `path: str`, `body: str`. Mirrors the session note shape from `message_processing._build_session_summary`. The body field carries the full raw markdown (back-compat carrier for Plans 02–04).

2. **`RetentionPolicy`** (`@dataclass(frozen=True)`) — 2-field injection value: `hot_limit: int = 3`, `hot_window_days: int = 2`. Resolves OQ2 (replaces `RecallConfig.recent_session_limit` staged removal) and OQ3 (standalone type, NOT a `RecallConfig` field).

3. **`recency_weight(date_str, *, now, half_life_days=7.0) -> float`** — pure module-level function placed beside `_rrf_merge`. Exponential curve `0.5 ** (age_days / half_life_days)`; midnight-normalises `now` so same-day dates yield exactly 1.0; fail-open on `(ValueError, TypeError)` returns 1.0 per T-41-01.

## TDD Gate Compliance

- **RED commit:** `e4cfa47` — 4 failing tests via ImportError (symbols not yet defined)
- **GREEN commit:** `d1cc7ab` — all 4 new tests pass; 40 total tests green

| Gate | Commit | Status |
|------|--------|--------|
| RED (`test(41-01)`) | e4cfa47 | PASS |
| GREEN (`feat(41-01)`) | d1cc7ab | PASS |

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | RED — failing tests for recency_weight curve and value-type construction | e4cfa47 | tests/test_recall.py |
| 2 | GREEN — define SessionSummary, RetentionPolicy, recency_weight | d1cc7ab | app/services/recall.py |
| 3 | REFACTOR — confirm no circular import and full recall suite stays green | (no new files) | verified 40/40 green |

## Verification Evidence

```
cd sentinel-core && uv run pytest tests/test_recall.py -q
........................................
40 passed in 0.23s
```

```
cd sentinel-core && PYTHONPATH="../shared:." uv run python -c "import app.services.recall; print('Import OK')"
Import OK
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] recency_weight midnight normalisation**
- **Found during:** Task 2 GREEN run
- **Issue:** `recency_weight("2026-06-12", now=datetime(2026, 6, 12, 12, 0, 0, ...))` returned 0.952 instead of 1.0 because the noon `now` was 0.5 days ahead of midnight `2026-06-12`
- **Fix:** Normalise `now` to midnight UTC via `now.replace(hour=0, minute=0, second=0, microsecond=0)` before computing `age_days`; YYYY-MM-DD dates are day-granularity so sub-day precision is noise
- **Files modified:** `sentinel-core/app/services/recall.py`
- **Commit:** d1cc7ab

## Known Stubs

None. All value types are fully defined with correct field types and defaults. No placeholder values.

## Threat Flags

None. No new network endpoints, auth paths, or schema changes at trust boundaries were introduced. `recency_weight` has the fail-open guard (T-41-01) that pins hostile-date DoS mitigation.

## Self-Check: PASSED

- `sentinel-core/app/services/recall.py` — EXISTS, contains `class SessionSummary`, `class RetentionPolicy`, `def recency_weight`
- `sentinel-core/tests/test_recall.py` — EXISTS, contains 4 new test functions
- Commit `e4cfa47` — EXISTS (RED)
- Commit `d1cc7ab` — EXISTS (GREEN)
- `uv run pytest tests/test_recall.py -q` — 40 passed
