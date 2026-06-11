---
phase: 39
slug: extract-the-recall-module
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-11
---

# Phase 39 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.23 (`asyncio_mode = "auto"`) |
| **Config file** | `sentinel-core/pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd sentinel-core && uv run pytest tests/test_recall.py tests/test_message_processor.py tests/test_status.py -x` |
| **Full suite command** | `cd sentinel-core && uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~30 seconds (quick), ~90 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 39-01-01 | 01 | 1 | MEM-02 | T-39-01 | warm namespace exclusion (`ops/`,`_trash/`,`self/`) preserved verbatim in RecallConfig | unit | `cd sentinel-core && uv run python -c "from app.services.recall import RecallConfig; c=RecallConfig(); assert c.exclude_prefixes==('ops/','_trash/','self/')"` | ❌ W1 (recall.py) | ⬜ pending |
| 39-01-02 | 01 | 1 | MEM-01, MEM-02 | T-39-01 / T-39-02 | Recall.assemble reproduces hot/warm behavior; persona never enters RecalledContext; exclusions enforced | unit | `cd sentinel-core && uv run pytest tests/test_recall.py -x` | ❌ W1 (test_recall.py) | ⬜ pending |
| 39-02-01 | 02 | 2 | MEM-01, MEM-02 | T-39-03 / T-39-04 / T-39-05 | MessageProcessor delegates to Recall; injection_filter.wrap_context + TokenBudget retained (D-04) | unit + integration | `cd sentinel-core && uv run pytest tests/test_message_processor.py tests/test_message.py -x` | ✅ | ⬜ pending |
| 39-02-02 | 02 | 2 | MEM-01 | T-39-03 | Recall injected via guard-then-construct DI seam; full graph wires correctly | integration | `cd sentinel-core && uv run pytest tests/ -x -q` | ✅ | ⬜ pending |
| 39-03-01 | 03 | 3 | MEM-01 | T-39-06 / T-39-07 | /context delegates to shared Recall; user_id pattern validation preserved; no duplicated assembly | integration | `cd sentinel-core && uv run pytest tests/test_status.py -x` | ✅ | ⬜ pending |
| 39-03-02 | 03 | 3 | MEM-01 | T-39-06 | test fixtures supply recall; both shared callers green | integration | `cd sentinel-core && uv run pytest tests/ -x -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `sentinel-core/tests/test_recall.py` — NEW test file (Plan 01, Wave 1); covers `Recall.assemble()` behavior against `FakeVault` for MEM-01 and MEM-02 (8 behavioral tests). This is the only new test infrastructure required.

*All other test infrastructure already exists: `test_message_processor.py`, `test_message.py`, `test_status.py` are kept (Test-Rewrite Ban) and serve as the behavior-preserving regression net. `FakeVault` already implements the full Vault Protocol.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|

*None — all phase behaviors have automated verification. This is a behavior-preserving internal refactor; every success criterion is provable via pytest against `FakeVault` or the kept through-`/message` suites. No UI, no external service, no human-only step.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify (every task has an automated command)
- [ ] Wave 0 covers all MISSING references (only `test_recall.py` is new)
- [ ] No watch-mode flags (all commands are `-x` one-shot runs)
- [ ] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
