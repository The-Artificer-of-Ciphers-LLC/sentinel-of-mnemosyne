---
phase: 41-typed-sessionsummary-retention
plan: "05"
subsystem: sentinel-core/consumers
tags: [lockstep, typed-sessions, session-summary, mem-08, mem-06, consumers, test-alignment]
dependency_graph:
  requires:
    - 41-01 (SessionSummary frozen dataclass)
    - 41-02 (get_recent_sessions typed to policy=)
    - 41-04 (RecalledContext.sessions: list[SessionSummary]; Plan 41-04 bridges removed)
  provides:
    - message_processing.py: clean s.body generator join (bridges removed)
    - status.py: explicit per-field SessionSummary comprehension (bridges removed)
    - test_message.py inline fake: policy=None signature (Protocol match)
    - test_status.py: SessionSummary mock + test_context_sessions_serializes_typed_fields
  affects:
    - sentinel-core/app/services/message_processing.py
    - sentinel-core/app/routes/status.py
    - sentinel-core/tests/test_message.py
    - sentinel-core/tests/test_status.py
tech_stack:
  added: []
  patterns:
    - lockstep retype: signature-only vs content-reconstruction+strengthening classification
    - generator expression join over typed field (s.body for s in recalled.sessions)
    - explicit per-field comprehension for JSON serialization (mirrors warm-tier idiom)
key_files:
  created: []
  modified:
    - sentinel-core/app/services/message_processing.py
    - sentinel-core/app/routes/status.py
    - sentinel-core/tests/test_message.py
    - sentinel-core/tests/test_status.py
decisions:
  - "Plan 41-04 bridges (isinstance guards + dataclasses.asdict) replaced with clean typed consumers; no more conditional branching in the hot path"
  - "status.py serializes 6 explicit SessionSummary fields (date/user_id/time/user_msg/sentinel_msg/path); body excluded from /context payload per T-41-13 (operator route, no new field exposure)"
  - "test_integration_obsidian_llm.py required no changes — Plan 41-04 already updated it (SessionSummary wrap + RetentionPolicy positional-arg assertion + KNOWN_SESSION content assertion)"
  - "test_auth.py:66 return_value=[] left unchanged — type-agnostic (empty list satisfies list[SessionSummary])"
metrics:
  duration: "2 min"
  completed: "2026-06-12"
  tasks_completed: 3
  files_modified: 4
---

# Phase 41 Plan 05: Consumer Lockstep — Typed SessionSummary Consumers + Test Alignment Summary

**One-liner:** Plan 41-04 bridges removed; `message_processing.py` and `status.py` retypedsed to read `SessionSummary` fields directly; all mock sites classified and aligned; full suite at 401 passed, 12 skipped.

## What Was Built

### Task 1: Retype RecalledContext.sessions consumers

**`sentinel-core/app/services/message_processing.py`** (lines 108-118):

Replaced the Plan 41-04 bridge (isinstance guard + conditional `.body` extraction) with a clean generator expression:

```python
# Before (bridge):
from app.services.recall import SessionSummary as _SessionSummary
session_bodies = [
    s.body if isinstance(s, _SessionSummary) else str(s)
    for s in recalled.sessions
]
context_parts.append("Recent session history:\n" + "\n---\n".join(session_bodies))

# After (lockstep):
context_parts.append(
    "Recent session history:\n" + "\n---\n".join(s.body for s in recalled.sessions)
)
```

The surrounding `truncate` → `wrap_context` path (lines 121-124) is left intact — typed session content still passes through the injection boundary (T-41-12 mitigate).

**`sentinel-core/app/routes/status.py`** (lines 51-66):

Replaced the Plan 41-04 bridge (`dataclasses.asdict()` with isinstance guard) with an explicit per-field comprehension mirroring the warm-tier idiom:

```python
# Before (bridge):
sessions_serialized = [
    _dc.asdict(s) if isinstance(s, _SessionSummary) else {"body": str(s)}
    for s in recalled.sessions
]

# After (lockstep — mirrors line-56 warm idiom):
"sessions": [
    {
        "date": s.date,
        "user_id": s.user_id,
        "time": s.time,
        "user_msg": s.user_msg,
        "sentinel_msg": s.sentinel_msg,
        "path": s.path,
    }
    for s in recalled.sessions
],
```

`recent_sessions_count: len(recalled.sessions)` unchanged. `body` excluded from the HTTP payload (T-41-13 accept — operator route, fields are the operator's own sessions).

### Task 2: Lockstep mock-site alignment

**Lockstep tally:**

| Site | File | Line | Classification | Change |
|------|------|------|----------------|--------|
| inline fake `get_recent_sessions` | test_message.py | 1143 | Signature-only | `limit: int = 3` → `policy=None` |
| ~17 `return_value = []` AsyncMock sites | test_message.py | 30,251,262,276,369,416,438,686,706,775,830,879,927,972,1038,1088 | Signature-only (type-agnostic) | No change — empty list satisfies `list[SessionSummary]` |
| `return_value = []` | test_auth.py | 66 | Signature-only (type-agnostic) | No change |
| `mock_obsidian.get_recent_sessions` fixture | test_status.py | 21 | Content reconstruction + strengthening | `["session1"]` → `[SessionSummary(date=..., body="session1")]` |
| `test_context_sessions_serializes_typed_fields` | test_status.py | new | New assertion strengthening | Added; checks all 6 serialized fields in the /context response |
| SessionSummary wrap + RetentionPolicy assertion + KNOWN_SESSION content | test_integration_obsidian_llm.py | 40-50, 180-183, 188 | Already updated (Plan 41-04) | No change required |

**Explicit no-weakening statement:** Every change in this plan is either:
- A signature-only alignment (empty-list mock sites that are type-agnostic — no content assertion to weaken)
- A content reconstruction into a `SessionSummary(...)` value (not a looser mock)
- An assertion strengthening (new `test_context_sessions_serializes_typed_fields` adds 6 field checks where previously only `recent_sessions_count` type was verified)

No shipped-feature assertion was weakened. The `KNOWN_SESSION in all_content` assertion (test_integration_obsidian_llm.py:188) was preserved intact — it still passes because `message_processing.py` now joins `s.body == KNOWN_SESSION` and the joined context flows through `wrap_context` to the LLM messages array. The `RetentionPolicy` positional-arg call-shape assertion (lines 180-183) was also preserved — it was already using the typed contract from Plan 41-04.

### Task 3: Phase integration gate

```
cd sentinel-core && uv run pytest -q
401 passed, 12 skipped in 14.91s
```

Full suite green. Baseline was 400 passed, 12 skipped. The +1 is `test_context_sessions_serializes_typed_fields` (new strengthening test added in Task 2).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Retype the two RecalledContext.sessions consumers | 7379b0f | app/services/message_processing.py, app/routes/status.py |
| 2 | Lockstep-align the ~19 get_recent_sessions mock sites | b505075 | tests/test_message.py, tests/test_status.py |
| 3 | Phase integration gate — full suite green + lockstep record | (no new files) | verified 401/401 green |

## Verification Evidence

```
cd sentinel-core && uv run pytest tests/test_message.py tests/test_status.py tests/test_integration_obsidian_llm.py tests/test_auth.py -q
54 passed, 2 warnings in 2.03s

cd sentinel-core && uv run pytest -q
401 passed, 12 skipped in 14.91s
```

Injection boundary (T-41-12): `message_processing.py` lines 121-124 (`truncate` + `wrap_context`) are intact — verified by the integration test `test_recent_sessions_injected_into_llm_prompt` which checks the LLM messages array contains `KNOWN_SESSION` content (the full round-trip through the injection filter).

## Deviations from Plan

### Plan 41-04 pre-completed `test_integration_obsidian_llm.py`

- **Found during:** Task 2 read-first scan
- **Impact:** `test_integration_obsidian_llm.py` already had `SessionSummary` import + mock reconstruction + `RetentionPolicy` positional-arg assertion + `KNOWN_SESSION` content assertion as part of Plan 41-04's Rule 1 bridge fix (GREEN commit 5c53e95). No changes required in this plan.
- **Classification:** Scope reduction (not a deviation from correctness); lockstep record captures this explicitly.

## Known Stubs

None. All Plan 41-04 bridges (`isinstance` guards, `dataclasses.asdict()`, conditional fallbacks) are removed. The consumers are fully typed end-to-end.

## Threat Flags

None. Per the plan's threat model:
- T-41-12 (prompt injection bypass): mitigated — `wrap_context` path verified intact by integration tests
- T-41-13 (status JSON leaking internals): accepted — operator-authenticated route; only 6 named fields serialized (not `body`), consistent with what the operator already sees
- T-41-14 (non-string body breaking join): mitigated by Plan 41-01's frozen dataclass (`body: str`); no runtime guard needed

## Self-Check: PASSED

- `sentinel-core/app/services/message_processing.py` — EXISTS, contains `s.body for s in recalled.sessions` (no bridge)
- `sentinel-core/app/routes/status.py` — EXISTS, contains explicit comprehension with `s.date`, `s.user_id`, `s.time`, `s.user_msg`, `s.sentinel_msg`, `s.path`
- `sentinel-core/tests/test_message.py:1143` — `policy=None` signature
- `sentinel-core/tests/test_status.py` — `SessionSummary` import + reconstructed mock + `test_context_sessions_serializes_typed_fields`
- Commit `7379b0f` — EXISTS (Task 1)
- Commit `b505075` — EXISTS (Task 2)
- `uv run pytest -q` — 401 passed, 12 skipped
