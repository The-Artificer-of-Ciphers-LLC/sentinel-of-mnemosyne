---
phase: 41-typed-sessionsummary-retention
verified: 2026-06-12T14:21:38Z
status: passed
score: 20/20 must-haves verified
overrides_applied: 0
---

# Phase 41: Typed SessionSummary + Retention Verification Report

**Phase Goal:** Typed `SessionSummary` + tunable `RetentionPolicy`; sessions older than the hot window recalled via index instead of dropped.
**Verified:** 2026-06-12T14:21:38Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `recall.py` defines a frozen `SessionSummary` with date/user_id/time/user_msg/sentinel_msg/path/body fields | VERIFIED | `@dataclass(frozen=True) class SessionSummary` at line 186; all 7 fields confirmed |
| 2 | `recall.py` defines a frozen `RetentionPolicy` with `hot_limit=3` / `hot_window_days=2` defaults | VERIFIED | `@dataclass(frozen=True) class RetentionPolicy` at line 204; defaults confirmed in code and test |
| 3 | `recency_weight` returns 1.0 same-day, 0.5 at half_life_days, exponential decay, fail-open on bad date | VERIFIED | Module-level function at line 659; `test_recency_weight_curve` + `test_recency_weight_failopen_on_bad_date` pass |
| 4 | `Vault.get_recent_sessions` Protocol return is `list[SessionSummary]`, takes `policy: RetentionPolicy` | VERIFIED | `vault.py:133` — Protocol signature; `from __future__ import annotations` + TYPE_CHECKING import confirmed |
| 5 | `ObsidianVault.get_recent_sessions` parses notes into `SessionSummary` with all fields; uses `policy.hot_window_days` window and `policy.hot_limit` slice | VERIFIED | `vault.py:388-448`; `_parse_session_summary` at line 180 uses `split_frontmatter` (CR-01 fix applied); window loop `range(policy.hot_window_days)` and `candidates[:policy.hot_limit]` confirmed |
| 6 | `FakeVault.get_recent_sessions` returns `list[SessionSummary]`, respects `policy.hot_window_days` window filter and `policy.hot_limit` | VERIFIED | `tests/fakes/vault.py:91-130`; CR-02 fix applied — `window_dates` set computed from `policy.hot_window_days`; `test_retention_window_excludes_out_of_window_sessions` passes |
| 7 | `Settings.retention_hot_limit` defaults 3, `retention_hot_window_days` defaults 2; env vars `RETENTION_HOT_LIMIT` / `RETENTION_HOT_WINDOW_DAYS` override them | VERIFIED | `config.py:125-126`; `test_retention_defaults` + `test_retention_env_override` pass with int coercion confirmed |
| 8 | `composition.py` builds `RetentionPolicy(hot_limit=settings.retention_hot_limit, hot_window_days=settings.retention_hot_window_days)` and passes it unconditionally to `Recall(policy=_policy)` | VERIFIED | `composition.py:26,329-339`; `RetentionPolicy` imported from `app.services.recall`; unconditional `policy=_policy` confirmed |
| 9 | `RecalledContext.sessions` is `list[SessionSummary]` end-to-end | VERIFIED | `recall.py:231`; `test_assemble_returns_sessions` asserts `isinstance(s, SessionSummary)` + checks `.user_id` and `.body` |
| 10 | `Recall.__init__` accepts injected `RetentionPolicy` (policy=); `_hot_sessions` calls `get_recent_sessions(user_id, policy=self._policy)` | VERIFIED | `recall.py:750-761, 787-808`; `self._policy = policy or RetentionPolicy()` confirmed |
| 11 | `_hot_sessions` returns sessions sorted by `recency_weight(s.date)` descending (blend, not filter — older sessions remain) | VERIFIED | `recall.py:799-808`; `test_recency_order_hot` + `test_recency_order_is_blend_not_filter` pass |
| 12 | Warm-tier recency multiplies RRF score only for FULL carrier set (`journal/`, `learning/`, `accomplishments/`, `references/`); `self/` and `ops/` never weighted | VERIFIED | `_CARRIER_NAMESPACE_PREFIXES` at line 70-75; positive allowlist gate at line 868; `test_recency_warm_carrier_journal` + `test_recency_warm_carrier_topic_dir` + `test_recency_excludes_self` pass |
| 13 | Sessions older than `hot_window_days` are reachable via `RecalledContext.warm` through ANY conversation-carrier note (journal/ or topic dirs); `ops/` exclusion NOT relaxed | VERIFIED | `test_old_session_warm_reachable_journal` + `test_old_session_warm_reachable_topic_dir` pass; `test_warm_excludes_self_and_ops_prefixes` remains green |
| 14 | `RecallConfig.recent_session_limit` removed; `hot_limit` lives only on `RetentionPolicy` | VERIFIED | No field definition of `recent_session_limit` in `recall.py` (only comments referencing the removal); `test_retention_window_tunable` confirms `hot_limit` drives the count |
| 15 | `inbox/` MEM-07 gap is documented-and-accepted, characterized by test | VERIFIED | `RecallConfig.exclude_prefixes` includes `inbox/`; `test_inbox_gap_not_recalled` passes; 41-04-SUMMARY records the D-06 decision |
| 16 | `message_processing.py` joins `s.body` (not raw dataclasses); `wrap_context` injection boundary preserved | VERIFIED | `message_processing.py:108-121`; `non_empty_sessions` guard (CR-03 fix applied); `s.body for s in non_empty_sessions` then `wrap_context` at line 121 |
| 17 | `status.py` serializes `SessionSummary` fields explicitly (no raw dataclasses); `body` excluded; `recent_sessions_count` works | VERIFIED | `status.py:57-69`; explicit `{date, user_id, time, user_msg, sentinel_msg, path}` comprehension; `body` absent; `len(recalled.sessions)` at line 69; `test_context_sessions_serializes_typed_fields` + `body` absence assertion (WR-05 fix) pass |
| 18 | All mock sites for `get_recent_sessions` are aligned to typed contract | VERIFIED | `test_message.py`, `test_status.py`, `test_integration_obsidian_llm.py` all updated; `raising_sessions` stub signature fixed (WR-02); full suite 404 passed |
| 19 | Full test suite is green | VERIFIED | `uv run pytest -q` → 404 passed, 12 skipped, 0 failed |
| 20 | `_CARRIER_NAMESPACE_PREFIXES` is a positive allowlist, not derived by negating `_WARM_TIER_EXCLUDE_PREFIXES`; `_WARM_TIER_EXCLUDE_PREFIXES` unchanged | VERIFIED | `recall.py:54,68,70-75`; explicit comment at line 68; `_WARM_TIER_EXCLUDE_PREFIXES = ("ops/", "_trash/", "self/")` intact |

**Score:** 20/20 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `sentinel-core/app/services/recall.py` | `SessionSummary`, `RetentionPolicy`, `recency_weight`, `_CARRIER_NAMESPACE_PREFIXES`, `_path_date`, typed `RecalledContext.sessions`, policy-injected `Recall` | VERIFIED | All symbols present; `recent_session_limit` correctly removed (comments only) |
| `sentinel-core/app/vault.py` | Protocol `get_recent_sessions(policy: RetentionPolicy) -> list[SessionSummary]`; `ObsidianVault` impl with `_parse_session_summary`; CR-01 `split_frontmatter` fix | VERIFIED | `from __future__ import annotations`, TYPE_CHECKING import, `_parse_session_summary` uses `split_frontmatter` at line 242 |
| `sentinel-core/tests/fakes/vault.py` | `FakeVault.get_recent_sessions` typed + `hot_window_days` filter (CR-02); `read_recent_sessions` alias | VERIFIED | Lines 91-130; window date filter present; alias at line 130 |
| `sentinel-core/app/config.py` | `retention_hot_limit: int = 3`, `retention_hot_window_days: int = 2` | VERIFIED | Lines 125-126 |
| `sentinel-core/app/composition.py` | `RetentionPolicy` import; `_policy` built from settings; unconditional `policy=_policy` | VERIFIED | Lines 26, 329-339 |
| `sentinel-core/tests/test_recall.py` | 4 Plan-01 tests + 10 Plan-04 tests + CR-02 window test + behavioral replacements for source-grep tests | VERIFIED | All named tests present and passing |
| `sentinel-core/tests/test_obsidian_vault.py` | Typed contract tests; `_parse_session_summary` tests; CR-01 behavioral test for dashes-in-frontmatter | VERIFIED | Lines 145-230; all tests pass |
| `sentinel-core/tests/test_config.py` | `test_retention_defaults`, `test_retention_env_override` | VERIFIED | Both present and passing |
| `sentinel-core/app/services/message_processing.py` | `s.body` join; `non_empty_sessions` guard (CR-03); `wrap_context` preserved | VERIFIED | Lines 108-121 |
| `sentinel-core/app/routes/status.py` | Explicit SessionSummary field serialization; `body` excluded; corrected comment (WR-03); `body` absence assertion test (WR-05) | VERIFIED | Lines 50-71 |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `vault.py` Protocol | `SessionSummary / RetentionPolicy` | `TYPE_CHECKING` import from `app.services.recall` | VERIFIED | Lines 36-37; `from __future__ import annotations` at line 21 ensures lazy annotation resolution |
| `ObsidianVault.get_recent_sessions` | `policy.hot_window_days / policy.hot_limit` | window range + slice in `_inner()` | VERIFIED | Lines 405, 430 |
| `FakeVault.get_recent_sessions` | `policy.hot_window_days / policy.hot_limit` | `window_dates` set + `[:policy.hot_limit]` | VERIFIED | Lines 104, 122 |
| `composition.py` | `Recall(policy=_policy)` | `settings.retention_hot_*` → `RetentionPolicy(...)` → `Recall(policy=_policy)` | VERIFIED | Lines 329-339 |
| `Recall._hot_sessions` | `recency_weight(s.date)` | `sorted(..., key=lambda s: recency_weight(s.date, now=now), reverse=True)` | VERIFIED | Lines 802-808 |
| `Recall._warm_search` | `_CARRIER_NAMESPACE_PREFIXES` positive allowlist | `r.path.startswith(_CARRIER_NAMESPACE_PREFIXES)` gate at line 868 | VERIFIED | Lines 860-875 |
| `message_processing.py` | `injection_filter.wrap_context` | `s.body` join → `truncate` → `wrap_context` (injection boundary preserved) | VERIFIED | Lines 112-121 |
| `status.py` | `recalled.sessions` | explicit `[{...} for s in recalled.sessions]` comprehension; `body` excluded | VERIFIED | Lines 57-67 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `message_processing.py` | `recalled.sessions` | `Recall.assemble` → `_hot_sessions` → `vault.get_recent_sessions` | `ObsidianVault` reads `ops/sessions/{date}/{user_id}-*.md` HTTP responses; `FakeVault` reads in-memory notes dict | FLOWING |
| `status.py` | `recalled.sessions` | Same `Recall.assemble` path | Same vault path; serialized as explicit field dict | FLOWING |
| `RecalledContext.warm` (carrier recency) | `merged` list from `_rrf_merge` | `_warm_search` → keyword + semantic strategies → RRF → recency reweighting via `_path_date` | Real vault HTTP reads for surviving paths; recency weight derived from path date | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Plan-01: `recency_weight` curve + value-type construction | `pytest tests/test_recall.py -k "recency_weight or session_summary or retention_policy" -q` | 4 passed | PASS |
| Plan-04: full recency/retention/inbox integration | `pytest tests/test_recall.py -k "recency or retention or old_session_warm or inbox_gap or assemble_returns_sessions" -q` | 14 passed | PASS |
| Plan-03: config env-override | `pytest tests/test_config.py -k retention -q` | 2 passed | PASS |
| Full suite gate | `pytest -q` | 404 passed, 12 skipped, 0 failed | PASS |

---

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|---------------|-------------|--------|----------|
| MEM-06 | Plans 01, 02, 03, 04 | Tunable retention policy (not fixed 3-turn / two-day limit) | SATISFIED | `RetentionPolicy(hot_limit, hot_window_days)` + env vars `RETENTION_HOT_LIMIT` / `RETENTION_HOT_WINDOW_DAYS`; `recent_session_limit` removed; tests verify env override + tunable window |
| MEM-07 | Plans 02, 04 | Sessions older than hot window recalled via index instead of dropped | SATISFIED | `test_old_session_warm_reachable_journal` + `test_old_session_warm_reachable_topic_dir` pass; inbox/ gap documented-and-accepted per D-06 |
| MEM-08 | Plans 01, 02, 04, 05 | Session data crosses Recall interface as typed values | SATISFIED | `SessionSummary` frozen dataclass; Protocol + ObsidianVault + FakeVault all return `list[SessionSummary]`; `RecalledContext.sessions: list[SessionSummary]`; consumers join `s.body`; status serializes typed fields |
| MEM-09 | Plans 01, 04 | Recalled sessions weighted by recency (episodic-only, never Self/authored) | SATISFIED | `recency_weight` exponential decay; `_hot_sessions` sorted by recency; `_warm_search` applies recency only to `_CARRIER_NAMESPACE_PREFIXES` (positive allowlist); `test_recency_excludes_self` pins the D-02 boundary |

All four requirements marked `[x]` (satisfied) in REQUIREMENTS.md.

---

### Anti-Patterns Found

None. Scanned all 10 modified source and test files for `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, `PLACEHOLDER` markers — zero results. No stub implementations, no `return null`/`return []` without data flow, no hardcoded empty props in rendering paths.

---

### Code-Review Fix Pass Factored In

The post-plan review pass (commits 4c49b56..9e6ffa4, documented in `41-REVIEW-FIX.md`) addressed 7 findings:

| Finding | File(s) | Fix | Verified |
|---------|---------|-----|---------|
| CR-01: fragile `find("---")` body-boundary scan | `vault.py` | Replaced with `split_frontmatter` at line 242; behavioral test `test_parse_session_summary_frontmatter_value_containing_dashes` added | VERIFIED |
| CR-02: `FakeVault` ignored `policy.hot_window_days` | `fakes/vault.py` | `window_dates` set added; `test_retention_window_excludes_out_of_window_sessions` pins behavior | VERIFIED |
| CR-03: stray `\n---\n` separators on empty-body sessions | `message_processing.py` | `non_empty_sessions` guard at line 112; behavioral test added in `test_message_processor.py` | VERIFIED |
| IN-02: two source-grep tests replaced with behavioral equivalents | `test_recall.py` | `test_recall_no_duplicate_index_literal_behavioral` + `test_recall_embedding_index_path_is_actually_read` | VERIFIED |
| WR-02: `raising_sessions` stub had wrong signature | `test_recall.py` | Updated to `(user_id: str, policy: RetentionPolicy) -> list[SessionSummary]` | VERIFIED |
| WR-03: misleading comment in `status.py` | `status.py` | Comment accurately describes intentional `body` exclusion | VERIFIED |
| WR-05: missing `body` absence assertion in `test_context_sessions_serializes_typed_fields` | `test_status.py` | Negative assertion `assert "body" not in session_dict` added | VERIFIED |

---

### Human Verification Required

None. All must-haves are verifiable by static analysis, import checks, and the test suite.

---

### Gaps Summary

No gaps. All 20 must-have truths verified against the actual codebase. The code-review fix pass that landed after the original plans addressed all identified review findings; the full suite (404 passed / 12 skipped) confirms no regressions.

---

_Verified: 2026-06-12T14:21:38Z_
_Verifier: Claude (gsd-verifier)_
