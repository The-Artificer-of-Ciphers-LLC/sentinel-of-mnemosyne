---
phase: 41-typed-sessionsummary-retention
plan: "04"
subsystem: sentinel-core/recall
tags: [tdd, recall, session-summary, retention-policy, recency-weight, warm-carrier, typed-sessions, mem-08, mem-09, mem-07, mem-06]
dependency_graph:
  requires:
    - 41-01 (SessionSummary, RetentionPolicy, recency_weight)
    - 41-02 (Vault seam: get_recent_sessions typed)
    - 41-03 (RetentionPolicy wired from settings at composition root)
  provides:
    - Recall.__init__ accepts policy=RetentionPolicy
    - RecalledContext.sessions: list[SessionSummary] (MEM-08)
    - _hot_sessions: typed + recency-sorted (most-recent first, MEM-09 place a)
    - _warm_search: carrier-namespace recency multiplier (MEM-09 place b, full set)
    - _CARRIER_NAMESPACE_PREFIXES constant (OQ1 resolution)
    - _path_date() helper (date extraction from journal/ and topic-dir paths)
    - inbox/ added to RecallConfig.exclude_prefixes default (D-06 document-and-accept)
    - RecallConfig.recent_session_limit removed (OQ2)
  affects:
    - sentinel-core/app/services/recall.py
    - sentinel-core/tests/test_recall.py
    - sentinel-core/app/services/message_processing.py (bridge)
    - sentinel-core/app/routes/status.py (bridge)
tech_stack:
  added: []
  patterns:
    - TDD RED→GREEN→REFACTOR for typed integration in Recall
    - exponential recency decay as RRF score multiplier (D-03 blend, not filter)
    - positive allowlist for carrier namespace (never negate exclude list, T-41-08)
    - fail-open _path_date + recency_weight (unparseable → weight 1.0, T-41-10)
    - bridge pattern for downstream consumers (message_processing.py, status.py)
key_files:
  created: []
  modified:
    - sentinel-core/app/services/recall.py
    - sentinel-core/tests/test_recall.py
    - sentinel-core/app/services/message_processing.py
    - sentinel-core/app/routes/status.py
decisions:
  - "OQ1 RESOLVED: session-derived warm result = warm SearchResult whose path startswith any of journal/, learning/, accomplishments/, references/ — the full non-ops/, non-inbox/ TOPIC_VAULT_PATH conversation-carrier set dated from path/frontmatter"
  - "OQ2 RESOLVED: RecallConfig.recent_session_limit REMOVED — hot_limit lives exclusively on RetentionPolicy; no dual source of truth"
  - "OQ3 RESOLVED: RetentionPolicy injected as a separate object into Recall (policy= kwarg); NOT threaded through RecallConfig"
  - "inbox/ MEM-07 gap: DOCUMENT-AND-ACCEPT (D-06) — low-confidence/unsure turns quarantined in inbox/ per sweep_skip_prefixes; forcing them into recall reintroduces the noise the exclusion suppresses; characterized by test_inbox_gap_not_recalled; inbox/ added to RecallConfig.exclude_prefixes default to align keyword search with semantic behavior"
  - "_path_date() fail-open: unparseable or missing date returns None → recency_weight(None) → 1.0 (no-op multiplier); malformed paths cannot crash the recall path (T-41-10)"
  - "Bridge pattern for Plan 41-05 consumers: message_processing.py extracts .body, status.py uses dataclasses.asdict(); full retype deferred to Plan 41-05 lockstep"
metrics:
  duration: "~25 min"
  completed: "2026-06-12"
  tasks_completed: 3
  files_modified: 4
---

# Phase 41 Plan 04: Recall Integration — Typed Sessions + Recency Summary

**One-liner:** `Recall` retyped end-to-end with `list[SessionSummary]`, injected `RetentionPolicy`, recency-sorted hot tier, and positive-allowlist warm-carrier recency weighting across the full carrier set (`journal/`, `learning/`, `accomplishments/`, `references/`).

## What Was Built

### `sentinel-core/app/services/recall.py`

**New constants and helpers:**

- `_CARRIER_NAMESPACE_PREFIXES = ("journal/", "learning/", "accomplishments/", "references/")` — the OQ1 resolution: a positive allowlist of every non-`ops/`, non-`inbox/` `TOPIC_VAULT_PATH` value that `NoteIntake.classify_and_apply` files conversation turns into. NOT derived by negating `_WARM_TIER_EXCLUDE_PREFIXES` (T-41-08 mitigation).

- `_path_date(path)` — extracts `YYYY-MM-DD` from two carrier path shapes:
  - `journal/{YYYY-MM-DD}/{slug}.md` → segment 1
  - `{base}/{slug}-{YYYY-MM-DD}.md` → trailing date in filename stem
  Returns `None` on parse failure (fail-open, T-41-10).

**`RecallConfig` changes:**

- `recent_session_limit: int = 3` REMOVED (OQ2 complete). `hot_limit` lives exclusively on `RetentionPolicy`.
- `exclude_prefixes` default extended with `"inbox/"` (D-06 document-and-accept): inbox/ notes are in `sweep_skip_prefixes`, never embedded; excluding from keyword warm search aligns the two retrieval paths.

**`RecalledContext` change:**

- `sessions: list[str]` → `sessions: list[SessionSummary]` (MEM-08).

**`Recall.__init__`:**

- New `policy: RetentionPolicy | None = None` keyword parameter; sets `self._policy = policy or RetentionPolicy()` (MEM-06, OQ3).

**`_hot_sessions`:**

- Return type changed to `list[SessionSummary]` (typed, not raw strings).
- Calls `await self._vault.get_recent_sessions(user_id, self._policy)` (uses injected policy, not RecallConfig.recent_session_limit).
- Returns `sorted(summaries, key=lambda s: recency_weight(s.date, now=...), reverse=True)` — blend: all sessions are present, most-recent first (MEM-09 place a, D-03).

**`_warm_search`:**

- Post-RRF, applies place (b) recency weighting: each `merged` survivor whose `path.startswith(_CARRIER_NAMESPACE_PREFIXES)` gets its score multiplied by `recency_weight(_path_date(path), now=...)`. Non-carrier notes (including `self/`, `ops/`, `notes/`) are untouched — D-02 episodic-only, positive allowlist.
- Re-sorts `reweighted` by adjusted score before body reads, so final order reflects recency.
- Decision comments inline: D-03, D-02, OQ1, T-41-08, T-41-10 named at both sites.

### `sentinel-core/tests/test_recall.py`

Ten new/strengthened behavioral tests (see TDD Gate Compliance):

| Test | Behavior Pinned |
|------|-----------------|
| `test_assemble_returns_sessions` (strengthened) | sessions is `list[SessionSummary]`; `.user_id == "trekkie"`, `.body` contains seeded text |
| `test_recency_order_hot` | policy= injection; most-recent session first |
| `test_recency_order_is_blend_not_filter` | older session still present (not dropped) |
| `test_recency_warm_carrier_journal` | journal/ carrier note dated today ranks above adversarially-first-ranked old note |
| `test_recency_warm_carrier_topic_dir` | learning/ / accomplishments/ (non-journal) carrier weighting |
| `test_recency_excludes_self` | old carrier note recency-weighted DOWN; today non-carrier unchanged; self/ never in warm |
| `test_old_session_warm_reachable_journal` | old session reachable via journal/ carrier (MEM-07); ops/ excluded |
| `test_old_session_warm_reachable_topic_dir` | old session via references/ carrier (full carrier set, not journal-only) |
| `test_retention_window_tunable` | hot_limit=1 vs hot_limit=5 — policy controls count (OQ2 removed recent_session_limit) |
| `test_inbox_gap_not_recalled` | inbox/ content absent from warm (D-06 document-and-accept characterization) |

### Rule 1 Bridge: `message_processing.py` and `status.py`

`RecalledContext.sessions` being `list[SessionSummary]` broke two downstream consumers that read it as `list[str]`:

- `message_processing.py:110`: `"\n---\n".join(recalled.sessions)` raised `TypeError: sequence item 0: expected str instance, SessionSummary found`
- `status.py:55`: `"sessions": recalled.sessions` would serialize incorrectly to JSON

Applied minimal bridges until Plan 41-05 retypes both consumers in lockstep:
- `message_processing.py`: extracts `.body` from each `SessionSummary`; falls back to `str(s)` for future-proofing
- `status.py`: uses `dataclasses.asdict(s)` for `SessionSummary` objects

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (`test(41-04)`) | bbf9d6d | PASS — 10 named tests fail, 39 prior tests green |
| GREEN (`feat(41-04)`) | 5c53e95 | PASS — 49 recall tests green, 400 suite green |
| REFACTOR (`refactor(41-04)`) | facda43 | PASS — no behavior change, decision-ID comments |

## Resolved Open Questions

### OQ1: Carrier Namespace (RESOLVED)

`"session-derived warm result"` = a warm `SearchResult` whose `path.startswith()` any of:
- `"journal/"` — daily journal entries
- `"learning/"` — topic learning notes
- `"accomplishments/"` — accomplishment notes
- `"references/"` — reference notes

These are every non-`ops/`, non-empty, non-`inbox/` value in `TOPIC_VAULT_PATH` (`note_classifier.py:57-65`) — i.e., every directory `NoteIntake.classify_and_apply` files conversation turns into. Dated from path: `journal/{YYYY-MM-DD}/...` or `{base}/{slug}-{YYYY-MM-DD}.md`. Gate is a POSITIVE allowlist — never by negating `_WARM_TIER_EXCLUDE_PREFIXES`.

### OQ2: recent_session_limit (RESOLVED)

`RecallConfig.recent_session_limit` REMOVED. `hot_limit` lives exclusively on `RetentionPolicy`. Single source of truth.

### OQ3: Policy Injection (RESOLVED)

`RetentionPolicy` injected as `policy=` kwarg on `Recall.__init__`, stored as `self._policy`. NOT threaded through `RecallConfig`.

### D-06: inbox/ MEM-07 Gap (DOCUMENT-AND-ACCEPT)

Low-confidence/`unsure` turns are appended to `inbox/_inbox.md` by `NoteIntake` and are in `sweep_skip_prefixes` (`config.py:115`). They are never embedded and therefore not recoverable via `SemanticRecall` once they age out of the hot window. This is an **accepted gap** because:
1. `inbox/` is deliberate noise quarantine — forcing it into recall reintroduces the noise the exclusion exists to suppress.
2. `searchable_only=True` only redirects filed notes away from `ops/`; it does not redirect the inbox branch.

**Recorded decision:** `inbox/` added to `RecallConfig.exclude_prefixes` default to align keyword search with semantic behavior. Gap characterized by `test_inbox_gap_not_recalled`. No code to force-close — explicit operator-visible record per AI Deferral Ban.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | RED — 10 failing tests for typed sessions, recency, carrier, inbox gap | bbf9d6d | tests/test_recall.py |
| 2 | GREEN — retype, inject policy, recency both tiers, remove recent_session_limit | 5c53e95 | app/services/recall.py, app/services/message_processing.py, app/routes/status.py |
| 3 | REFACTOR — decision-ID inline comments at both recency sites | facda43 | app/services/recall.py |

## Verification Evidence

```
cd sentinel-core && uv run pytest tests/test_recall.py -q
.................................................
49 passed in 0.54s

cd sentinel-core && uv run pytest tests/test_composition.py -q
..........
10 passed in 2.34s  (3 previously-red composition tests now GREEN)

cd sentinel-core && uv run pytest -q
400 passed, 12 skipped in 14.56s  (no regressions)

grep -c "recent_session_limit:" app/services/recall.py
0  (field removed; only docstring references remain)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] RecalledContext.sessions retype broke message_processing.py and status.py**
- **Found during:** Task 2 GREEN full-suite run
- **Issue:** `message_processing.py:110` called `"\n---\n".join(recalled.sessions)` on `list[SessionSummary]` → `TypeError`. `status.py:55` put `list[SessionSummary]` directly into JSON dict.
- **Fix:** Bridge in `message_processing.py` extracts `.body` from SessionSummary; bridge in `status.py` uses `dataclasses.asdict()`. Both bridges are explicitly labeled as Plan 41-05 lockstep deferral.
- **Files modified:** `app/services/message_processing.py`, `app/routes/status.py`
- **Commit:** 5c53e95

## Known Stubs

None for this plan's produced artifacts. The bridge in `message_processing.py` and `status.py` is an intentional inter-wave staging pattern (same as the Plan 02 `_hot_sessions` bridge) — it is documented in both the commit and the SUMMARY, not a silent stub.

## Threat Flags

None. All T-41-08 through T-41-11 mitigations from the plan's threat model are implemented and pinned by tests:
- T-41-08 (self/ recency leak): `_CARRIER_NAMESPACE_PREFIXES` positive allowlist; `test_recency_excludes_self`
- T-41-09 (ops/ relaxation): `_WARM_TIER_EXCLUDE_PREFIXES` unchanged; `test_warm_excludes_self_and_ops_prefixes` + `test_old_session_warm_reachable_*` kept green
- T-41-10 (malformed date DoS): `_path_date()` fail-open + `recency_weight` fail-open; graceful-degrade test preserved
- T-41-11 (inbox gap silent): D-06 document-and-accept recorded here and in decisions; `test_inbox_gap_not_recalled`

## Self-Check: PASSED

- `sentinel-core/app/services/recall.py` — EXISTS, contains `_CARRIER_NAMESPACE_PREFIXES`, `_path_date`, `list[SessionSummary]`, `policy=`, recency sort in `_hot_sessions`, carrier weighting in `_warm_search`
- `sentinel-core/tests/test_recall.py` — EXISTS, 49 tests, all pass
- `sentinel-core/app/services/message_processing.py` — EXISTS, bridge present
- `sentinel-core/app/routes/status.py` — EXISTS, bridge present
- Commit `bbf9d6d` — EXISTS (RED)
- Commit `5c53e95` — EXISTS (GREEN)
- Commit `facda43` — EXISTS (REFACTOR)
- `uv run pytest tests/test_recall.py -q` — 49 passed
- `uv run pytest tests/test_composition.py -q` — 10 passed (3 previously-red now green)
- `uv run pytest -q` — 400 passed, 12 skipped
