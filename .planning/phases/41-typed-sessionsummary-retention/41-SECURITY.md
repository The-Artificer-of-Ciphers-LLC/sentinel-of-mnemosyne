---
phase: 41
slug: typed-sessionsummary-retention
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-12
---

# Phase 41 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail. Register authored at plan time (5 plans); auditor verified mitigations against implementation.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| vault markdown → SessionSummary.date | Date string from a vault note path/frontmatter flows into `recency_weight` | Untrusted vault content |
| Obsidian REST response → SessionSummary | Untrusted vault markdown (session note body + path) parsed into a typed value at the ObsidianVault edge | Untrusted vault content |
| env var → Settings.retention_* | Operator-supplied env values configure the hot-window retention policy | Operator-controlled config |
| typed SessionSummary → RecalledContext → MessageProcessor | Recalled session data crosses the Recall interface as typed values | Recalled user data |
| carrier note date → recency multiplier | Path-derived date (journal/ or topic-dir suffix) drives the warm-tier score multiplier | Untrusted vault content |
| recalled session body → LLM message list | Typed session content joined and injected into the prompt; must stay inside the injection_filter boundary | Recalled user data → LLM |
| recalled session → status JSON | Typed session fields serialized into the authenticated `/context` HTTP response | Recalled user data → operator |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-41-01 | DoS | `recency_weight(date_str)` on malformed/hostile date | mitigate | `recall.py:677-686` catches `(ValueError, TypeError)` → returns `1.0` (fail-open); `test_recency_weight_failopen_on_bad_date` | closed |
| T-41-02 | Tampering | crafted far-future date to dominate ranking | accept | `recall.py:685` `max(0.0, age_days)` clamps future → 1.0; recency is a blend multiplier (D-01), not an override; single-user vault | closed |
| T-41-03 | DoS | `_parse_session_summary` on malformed/hostile note | mitigate | `vault.py:198-265` field extraction wrapped `try/except`; short paths → `None`; CR-01 fix uses canonical `split_frontmatter` (line 242); `_safe_request(..., [], ...)` coerces residual failure to `[]`; tests at test_obsidian_vault.py:182,196,201 | closed |
| T-41-04 | Info Disclosure | session note for user A leaking into user B recall | mitigate | `vault.py:422` & `fakes/vault.py:118` preserve `f"{user_id}-" in filename`; only `ops/sessions/` for requested user_id; `test_assemble_returns_sessions` | closed |
| T-41-05 | Elevation/scope creep | widening Vault reopen beyond `get_recent_sessions` | mitigate | only `get_recent_sessions` retyped (vault.py:133); other Protocol methods untouched; `_WARM_TIER_EXCLUDE_PREFIXES` unchanged | closed |
| T-41-06 | Tampering/DoS | hostile env `RETENTION_HOT_LIMIT=-1` or huge value | mitigate | `config.py:125-126` typed `int`; pydantic-settings `ValidationError` on non-int; candidate set bounded by date-window loop regardless of `hot_limit` (never unbounded read); `test_retention_defaults`/`test_retention_env_override`. See Documentation Note. | closed |
| T-41-07 | Info Disclosure | widening `hot_window_days` surfacing older data | accept | Intended MEM-06 capability; window only reaches requesting user's own `ops/sessions/`; `ops/` exclusion still gates warm search | closed |
| T-41-08 | Info Disclosure | recency weighting applied to `self/` or authored notes | mitigate | `recall.py:70-75` `_CARRIER_NAMESPACE_PREFIXES` positive allowlist; `recall.py:868` positive `startswith` test, NOT a negation; `self/`/`ops/` never multiplied; `test_recency_excludes_self` | closed |
| T-41-09 | Info Disclosure | relaxing `ops/` exclusion leaking operational notes | mitigate | `_WARM_TIER_EXCLUDE_PREFIXES` (recall.py:54) and `RecallConfig.exclude_prefixes` (recall.py:250) unchanged; old-session reachability only via carriers; `test_warm_excludes_self_and_ops_prefixes` + `test_old_session_warm_reachable_journal`/`_topic_dir` | closed |
| T-41-10 | DoS | malformed date/carrier path crashing recall tiers | mitigate | `recency_weight` & `_path_date` fail open; `assemble` uses `return_exceptions=True` coercing failed tier to `[]`; `test_assemble_degrades_gracefully_when_sessions_tier_raises` (WR-02-corrected stub) | closed |
| T-41-11 | Info Disclosure | `inbox/` MEM-07 gap silently dropping turns | mitigate | `recall.py:250` `exclude_prefixes` includes `"inbox/"`; `test_inbox_gap_not_recalled` (explicit, not silent); D-06 document-and-accept in 41-04-SUMMARY | closed |
| T-41-12 | Tampering (prompt injection) | typed session body joined into prompt bypassing `wrap_context` | mitigate | `message_processing.py:112-121` join feeds `truncate` → `wrap_context`; injection boundary intact; `test_injection_filter_applied_to_user_input` | closed |
| T-41-13 | Info Disclosure | status JSON leaking SessionSummary internals | accept | `/context/{user_id}` behind `X-Sentinel-Key` (main.py:44-51); `status.py:57-67` serializes only date/user_id/time/user_msg/sentinel_msg/path — `body` excluded (WR-05 asserts absence); `test_context_requires_auth` | closed |
| T-41-14 | DoS | non-string `s.body` breaking `str.join` | mitigate | `SessionSummary.body: str` on frozen dataclass; parser always sets `body` to str; CR-03 empty-body guard (message_processing.py:112); `test_empty_body_session_does_not_introduce_stray_separator` | closed |
| T-41-SC (×5) | Tampering (supply chain) | npm/pip/cargo installs | accept | Zero packages installed across all 5 plans; all imports pre-existing; no new package in uv.lock | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-41-01 | T-41-02 | Far-future date weight capped at 1.0; recency is a blend multiplier, cannot evict strongly-relevant results; single-user vault, no external write path to session dates | operator (gsd-secure-phase) | 2026-06-12 |
| AR-41-02 | T-41-07 | Widening `hot_window_days` is the intended MEM-06 operator capability; expansion reaches only the requesting user's `ops/sessions/`; `ops/` exclusion still blocks warm search | operator (gsd-secure-phase) | 2026-06-12 |
| AR-41-03 | T-41-11 | `inbox/` MEM-07 gap: low-confidence turns deliberately noise-quarantined; characterized by `test_inbox_gap_not_recalled`; accepted per D-06 | operator (gsd-secure-phase) | 2026-06-12 |
| AR-41-04 | T-41-13 | `/context/{user_id}` is an authenticated operator debug route serializing only fields the operator already owns; `body` excluded | operator (gsd-secure-phase) | 2026-06-12 |
| AR-41-05 | T-41-SC | Zero packages installed across all 5 plans; supply-chain attack surface unchanged | operator (gsd-secure-phase) | 2026-06-12 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-12 | 15 | 15 | 0 | gsd-security-auditor (verify-mode, register authored at plan time) |

---

## Documentation Note (T-41-06)

The T-41-06 plan-time mitigation text states a negative value yields a Python empty-slice (`[:-1]` / empty range). This is imprecise: `list[:-1]` returns N-1 items (not empty); `range(-1)` is empty. The security property "never unbounded read" holds regardless because the candidate set is bounded by the date-window loop. Not a security gap; correct the plan text in a future iteration.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-12
