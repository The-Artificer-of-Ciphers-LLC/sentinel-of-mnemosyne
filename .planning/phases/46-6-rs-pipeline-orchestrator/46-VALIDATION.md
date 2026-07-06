---
phase: 46
slug: 6-rs-pipeline-orchestrator
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-06
---

# Phase 46 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Detailed per-task map is filled by the planner / nyquist-auditor from RESEARCH.md's `## Validation Architecture`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | sentinel-core/pyproject.toml |
| **Quick run command** | `cd sentinel-core && .venv/bin/python -m pytest tests/test_pipeline_orchestrator.py tests/test_six_rs_*.py -q` |
| **Full suite command** | `cd sentinel-core && .venv/bin/python -m pytest tests/` |
| **Estimated runtime** | ~30–60 seconds (full core suite) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command (new pipeline/six_rs tests)
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green (550+ passing baseline maintained)
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _to be filled by planner from RESEARCH.md ## Validation Architecture_ | | | PIPE-01..07 | | | unit | | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_pipeline_orchestrator.py` — RED stubs for the orchestrator (mode dispatch, shared-lock guard, PipelineReport counts)
- [ ] `tests/test_six_rs_reduce.py` / `_reflect.py` / `_reweave.py` / `_verify.py` / `_rethink.py` — per-phase stage stubs
- [ ] FakeVault fixtures — mirror existing `test_vault_sweeper` / `test_note_classifier` conftest patterns
- [ ] pytest already installed (sentinel-core `.venv`) — no framework install needed

*Planner to finalize against RESEARCH.md's validation architecture.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live `:ralph`/`:pipeline` run mutates the real Obsidian vault (writes `notes/` with `_schema`, updates MOC) | PIPE-02, PIPE-03 | Requires live Obsidian REST + LM Studio; not exercised by FakeVault unit tests | Run `:ralph` in Discord after seeding `inbox/`; confirm `notes/{slug}.md` appears with a trailing `_schema` block + wikilink and the MOC hub is updated |
| Async run status is pollable and reports real per-phase counts | PIPE-06 | End-to-end Discord + background task timing | Start a pipeline, poll `:pipeline` status; confirm counts advance and a final success/partial/failure outcome is reported |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
