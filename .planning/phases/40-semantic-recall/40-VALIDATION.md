---
phase: 40
slug: semantic-recall
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-11
---

# Phase 40 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Detailed per-task map and Wave 0 stubs are populated by the planner/executor.
> See `40-RESEARCH.md` § Validation Architecture for the validation points proving the 4 success criteria.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `sentinel-core/pyproject.toml` |
| **Quick run command** | `cd sentinel-core && uv run pytest tests/test_recall.py -q` |
| **Full suite command** | `cd sentinel-core && uv run pytest -q` |
| **Estimated runtime** | ~{N} seconds (planner to confirm) |

---

## Sampling Rate

- **After every task commit:** Run `cd sentinel-core && uv run pytest tests/test_recall.py -q`
- **After every plan wave:** Run `cd sentinel-core && uv run pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** {N} seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| {N}-01-01 | 01 | 1 | MEM-{XX} | — | {expected behavior or "N/A"} | unit | `{command}` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky — planner populates one row per task.*

---

## Wave 0 Requirements

- [ ] `sentinel-core/tests/test_recall.py` — extend with SemanticRecall + RRF + model-skip + degrade cases (MEM-03/04/05)
- [ ] Fixture `embedding-index.json` + deterministic fake embedder (injected) for SemanticRecall tests
- [ ] `sentinel-core/tests/fakes/` (FakeVault) — ensure it can serve a fixture index note

*Framework already present — no install needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Paraphrase query returns the right note against a real LM Studio embedding model | MEM-03 | Cosine-floor default needs empirical UAT tuning with the live nomic-embed model | UAT: save a note, query a paraphrase, confirm it appears in `/context/{user_id}` warm results |

*All deterministic behaviors have automated verification; only cosine-floor calibration is manual/UAT.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < {N}s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
