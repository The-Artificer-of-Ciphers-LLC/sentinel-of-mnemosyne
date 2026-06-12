---
phase: 41
slug: typed-sessionsummary-retention
status: ready
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-12
---

# Phase 41 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: 41-RESEARCH.md §"Validation Architecture" (Test Framework, Phase Requirements → Test Map, Sampling Rate) and the per-task `-k` selectors enumerated in plans 41-01..41-05.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8 + pytest-asyncio (`asyncio_mode="auto"`) |
| **Config file** | `sentinel-core/pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd sentinel-core && uv run pytest tests/test_recall.py -x -q` |
| **Full suite command** | `cd sentinel-core && uv run pytest -q` |
| **Estimated runtime** | ~41 seconds (full suite) |

---

## Sampling Rate

- **After every task commit:** Run `cd sentinel-core && uv run pytest tests/test_recall.py -x -q`
- **After every plan wave:** Run `cd sentinel-core && uv run pytest tests/test_recall.py tests/test_message.py tests/test_obsidian_vault.py tests/test_status.py tests/test_config.py -q`
- **Before `/gsd-verify-work`:** Full suite must be green — `cd sentinel-core && uv run pytest -q`
- **Max feedback latency:** ~41 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 41-01-01 | 01 | 1 | MEM-08 / MEM-06 / MEM-09 | T-41-01 | RED — recency_weight curve + value-type construction tests fail (symbols undefined) | unit (TDD red) | `cd sentinel-core && uv run pytest tests/test_recall.py -k "recency_weight or session_summary or retention_policy" -q -rfE` | ✅ tests/test_recall.py | ⬜ pending |
| 41-01-02 | 01 | 1 | MEM-08 / MEM-06 / MEM-09 | T-41-01 | recency_weight fails open (1.0) on malformed/hostile date; frozen value types | unit (TDD green) | `cd sentinel-core && uv run pytest tests/test_recall.py -k "recency_weight or session_summary or retention_policy" -x -q` | ✅ tests/test_recall.py | ⬜ pending |
| 41-01-03 | 01 | 1 | MEM-08 / MEM-06 / MEM-09 | T-41-01 | No circular import; existing list[str] contract still green (no regression) | unit (refactor) | `cd sentinel-core && uv run python -c "import app.services.recall" && uv run pytest tests/test_recall.py -q` | ✅ tests/test_recall.py | ⬜ pending |
| 41-02-01 | 02 | 2 | MEM-08 / MEM-06 / MEM-07 | T-41-03 / T-41-04 / T-41-05 | `_parse_session_summary` parses defensively (V5, never raises); user_id filter preserved; only get_recent_sessions retyped | unit | `cd sentinel-core && uv run python -c "import app.vault, app.services.recall" && uv run pytest tests/test_obsidian_vault.py -q` | ✅ tests/test_obsidian_vault.py | ⬜ pending |
| 41-02-02 | 02 | 2 | MEM-08 / MEM-06 | T-41-03 / T-41-04 | FakeVault typed in lockstep; adapter tests assert parsed SessionSummary fields (strengthen, not weaken); empty-on-error preserved | unit | `cd sentinel-core && uv run pytest tests/test_obsidian_vault.py -k session_summary -q && uv run pytest tests/test_obsidian_vault.py -q` | ✅ tests/test_obsidian_vault.py, tests/fakes/vault.py | ⬜ pending |
| 41-03-01 | 03 | 2 | MEM-06 | T-41-06 | Env vars RETENTION_HOT_* coerced to int by pydantic-settings; defaults preserve current behavior | unit | `cd sentinel-core && uv run pytest tests/test_config.py -k retention -x -q` | ✅ tests/test_config.py (new) | ⬜ pending |
| 41-03-02 | 03 | 2 | MEM-06 | T-41-07 | RetentionPolicy injected as separate object (OQ3); composition imports cleanly; widening window stays same-user/same-namespace | wiring (import check) | `cd sentinel-core && uv run python -c "import app.composition; from app.services.recall import RetentionPolicy; print(RetentionPolicy(hot_limit=1, hot_window_days=1))"` | ✅ app/composition.py | ⬜ pending |
| 41-04-01 | 04 | 3 | MEM-08 / MEM-09 / MEM-07 / MEM-06 | T-41-08 / T-41-09 / T-41-10 / T-41-11 | RED — 10 named tests (typed sessions, recency hot-order, warm carrier full-set, excludes-self, old-session-warm journal+topic, retention window, inbox gap) fail; named-test count gate prevents false RED | unit (TDD red) | `cd sentinel-core && uv run pytest tests/test_recall.py -k "recency or retention or old_session_warm or inbox_gap or assemble_returns_sessions" -q -rf` | ✅ tests/test_recall.py | ⬜ pending |
| 41-04-02 | 04 | 3 | MEM-08 / MEM-09 / MEM-07 / MEM-06 | T-41-08 / T-41-09 / T-41-10 | GREEN — `_CARRIER_NAMESPACE_PREFIXES` positive allowlist (journal/ + learning/ + accomplishments/ + references/); self/ + ops/ never weighted; recent_session_limit removed; exclusion list unchanged | unit (TDD green) | `cd sentinel-core && uv run pytest tests/test_recall.py -q` | ✅ tests/test_recall.py | ⬜ pending |
| 41-04-03 | 04 | 3 | MEM-08 / MEM-09 / MEM-07 / MEM-06 | T-41-09 / T-41-11 | Recency sites self-documenting (D-03/D-02/OQ1 comments); inbox gap recorded as document-and-accept (D-06); recent_session_limit gone | unit (refactor) | `cd sentinel-core && uv run pytest tests/test_recall.py -q && ! grep -n "recent_session_limit" app/services/recall.py` | ✅ tests/test_recall.py | ⬜ pending |
| 41-05-01 | 05 | 4 | MEM-08 / MEM-06 | T-41-12 / T-41-14 | Consumers join s.body through wrap_context (injection boundary preserved); status.py serializes explicit SessionSummary fields | wiring (import check) | `cd sentinel-core && uv run python -c "import app.services.message_processing, app.routes.status"` | ✅ app/services/message_processing.py, app/routes/status.py | ⬜ pending |
| 41-05-02 | 05 | 4 | MEM-08 / MEM-06 | T-41-12 / T-41-13 | ~19 mock sites aligned to typed contract; content assertions strengthened not weakened; line-166 policy= call shape | unit (lockstep) | `cd sentinel-core && uv run pytest tests/test_message.py tests/test_status.py tests/test_integration_obsidian_llm.py tests/test_auth.py -q` | ✅ tests/test_message.py, tests/test_status.py, tests/test_integration_obsidian_llm.py, tests/test_auth.py | ⬜ pending |
| 41-05-03 | 05 | 4 | MEM-08 / MEM-06 | T-41-12 | Phase integration gate — full suite green end-to-end; no test skipped/xfailed to pass | integration (phase gate) | `cd sentinel-core && uv run pytest -q` | ✅ (full suite) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Requirement → Concrete Command Map (MEM-06/07/08/09)

| Requirement | Concrete pytest command(s) |
|-------------|----------------------------|
| **MEM-06** (tunable retention policy) | `cd sentinel-core && uv run pytest tests/test_config.py -k retention -x` · `cd sentinel-core && uv run pytest tests/test_recall.py -k retention -x` |
| **MEM-07** (old sessions recalled via carrier, ops/ not relaxed) | `cd sentinel-core && uv run pytest tests/test_recall.py -k "old_session_warm" -x` · `cd sentinel-core && uv run pytest tests/test_recall.py::test_warm_excludes_self_and_ops_prefixes -x` |
| **MEM-08** (typed SessionSummary across the Recall interface) | `cd sentinel-core && uv run pytest tests/test_obsidian_vault.py -k session_summary -x` · `cd sentinel-core && uv run pytest tests/test_recall.py::test_assemble_returns_sessions -x` |
| **MEM-09** (recency-weighted merge, episodic-only) | `cd sentinel-core && uv run pytest tests/test_recall.py -k "recency_weight_curve or recency_order or recency_warm or recency_excludes_self" -x` |

---

## Wave 0 Requirements

- [x] `tests/test_recall.py` — exists; new cases authored RED-first in plans 41-01 (recency_weight curve, value-type construction) and 41-04 (recency hot-order, warm carrier full-set, excludes-self, old-session-warm journal+topic, retention window, inbox-gap characterization). `test_assemble_returns_sessions` (line 118) strengthened, not added.
- [x] `tests/test_obsidian_vault.py` — exists; `test_get_recent_sessions_returns_list` (line 119) updated to typed contract + frontmatter-parse case added (plan 41-02).
- [x] `tests/test_config.py` — NEW file created in plan 41-03 (retention defaults + env-override cases).
- [x] `tests/fakes/vault.py` — typed `get_recent_sessions` + alias in lockstep (plan 41-02).
- [x] Lockstep stubs (NOT new files): `tests/test_message.py` (~17 mock sites + inline fake signature), `tests/test_auth.py`, `tests/test_integration_obsidian_llm.py` (lines 38/166/196), `tests/test_status.py` (line 21) — aligned in plan 41-05.
- [x] Framework install — none needed; pytest + pytest-asyncio already in `pyproject.toml`.

*All MISSING test references are created RED-first inside the plan that owns them (TDD plans 41-01/41-03/41-04 author the failing test before the implementation); no separate Wave 0 scaffold plan is required because the phase's test files already exist and each new case is introduced by its owning plan's RED task.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|

*None — all phase behaviors have automated verification. The entire phase runs against `FakeVault` + stubbed `embed_fn` (RESEARCH §Environment Availability); no live Obsidian/LM Studio service is required to validate any requirement.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (each authored RED-first by its owning plan)
- [x] No watch-mode flags
- [x] Feedback latency < 41s (quick command targets the single recall file)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
