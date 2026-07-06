---
phase: 44
slug: vault-namespace-taxonomy-foundation
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-06
---

# Phase 44 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Detailed dimensions/test surface live in `44-RESEARCH.md` (## Validation Architecture).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `sentinel-core/` (pytest) — confirm exact config at Wave 0 |
| **Quick run command** | `cd sentinel-core && pytest -q` (or keyword-scoped `-k` subset for the file under change) |
| **Full suite command** | `cd sentinel-core && pytest` |
| **Estimated runtime** | TBD — measure at Wave 0 (baseline: 471 tests collected) |

---

## Sampling Rate

- **After every task commit:** Run the keyword-scoped quick command for the touched module (`recall`, `vault_sweeper`, `note_classifier`, `note_intake`, `message`).
- **After every plan wave:** Run the full suite `cd sentinel-core && pytest` — **must stay green (471+ baseline)**.
- **Before `/gsd-verify-work`:** Full suite green AND MEM-01..MEM-09 characterization tests green (SC-5 hard gate).
- **Max feedback latency:** TBD (measure at Wave 0).

---

## Per-Task Verification Map

*Filled by the planner. Every task addressing VAULT-01..05 (and the D-06/D-07 fixes) maps to an automated pytest command here. See `44-RESEARCH.md` for the named tests (7 rewrites + 4 new Wave-0 characterizing tests) and their line cites.*

Characterization is folded INTO each plan (test-first task-level TDD), not a separate RED wave — the SC-5 "no red window / green at every wave boundary" mandate forbids leaving the suite red at a wave boundary, so every plan lands its new/rewritten tests together with the code that makes them green.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 44-01-01 | 01 | 1 | VAULT-02 | T-44-01-01 | closed vocab unchanged; single reviewed routing source | unit (tdd) | `cd sentinel-core && pytest tests/test_note_classifier.py tests/test_vault_sweep_plan.py -q` | ❌ W0 (new tests) | ⬜ pending |
| 44-01-02 | 01 | 1 | VAULT-03 | T-44-01-02 | recency weighting sessions-only (no weight-by-omission) | unit (tdd) | `cd sentinel-core && pytest tests/test_recall.py -q` | ⚠️ 3 rewrites + 1 new | ⬜ pending |
| 44-01-03 | 01 | 1 | MIG-03 (D-05) | — | accepted transient recorded, not silent | artifact | `test -f .planning/v0.6.0-REGRESSION-LEDGER.md && grep -q 'MEM-09' .planning/v0.6.0-REGRESSION-LEDGER.md && grep -q 'D-05' .planning/v0.6.0-REGRESSION-LEDGER.md` | ❌ new | ⬜ pending |
| 44-02-01 | 02 | 1 | VAULT-04 | T-44-02-01 | inbox/ embedded but excluded from BOTH warm tiers | unit (tdd) | `cd sentinel-core && pytest tests/test_vault_sweeper.py -k "skip or inbox" -q && pytest tests/test_recall.py -k inbox_gap -q` | ⚠️ 2 flips + 1 new | ⬜ pending |
| 44-02-02 | 02 | 1 | VAULT-04 (D-07) | T-44-02-02 | control-queue file never relocated | unit (tdd) | `cd sentinel-core && pytest tests/test_vault_sweeper.py -k "relocate or pending or control" -q` | ❌ new | ⬜ pending |
| 44-02-03 | 02 | 1 | VAULT-01 | T-44-02-04 | templates/ move-protected; existing guards intact | unit (tdd) | `cd sentinel-core && pytest tests/test_obsidian_vault.py -k "protect" -q` | ⚠️ extend | ⬜ pending |
| 44-03-01 | 03 | 2 | VAULT-04 (D-03b) | T-44-03-01 | single warm-exclusion source of truth (incl. inbox/) | unit (tdd) | `cd sentinel-core && pytest tests/test_recall.py tests/test_message.py -q` | ✅ existing | ⬜ pending |
| 44-03-02 | 03 | 2 | VAULT-02 (D-06) | T-44-03-02 | dead redirect retired; behavior asserted, not silent | unit (tdd) | `cd sentinel-core && pytest tests/test_message.py -k "chat_note or searchable or redirect" -q` | ⚠️ 2 rewrites | ⬜ pending |
| 44-04-01 | 04 | 3 | VAULT-01, VAULT-05 | T-44-04-01 | four-path stub allowlist; read_self_context unchanged | unit (tdd) | `cd sentinel-core && pytest tests/test_recall.py -k "self_stub or self_paths or self_context" -q` | ❌ new | ⬜ pending |
| 44-04-02 | 04 | 3 | VAULT-05 | T-44-04-03 | self-heal through the message path; stubs are DATA | integration (tdd) | `cd sentinel-core && pytest tests/test_message.py -k "self" -q` | ❌ new | ⬜ pending |
| ALL | 01-04 | boundary | SC-5 | — | full suite + MEM-01..09 stay green | full suite | `cd sentinel-core && pytest` (471 collected; a dropped count is a failure) | ✅ existing | ⬜ pending |

---

## Wave 0 Requirements

- [ ] Characterization tests for the two locked traps + three research-surfaced hazards, RED-before-fix (per `44-RESEARCH.md`): carrier-allowlist recency removal (D-01), inbox/ sweeper embedding (D-02), taxonomy reroute incl. hardcoded `journal/{today}` literal, `is_in_topic_dir()` family collapse, `_safe_file_chat_note` retirement (D-06), `_`-prefixed inbox control-file relocation guard (D-07).
- [ ] 7 existing tests rewritten (not just re-run) per `44-RESEARCH.md` names/line cites.
- [ ] MEM-01..MEM-09 characterization confirmed green as the no-regression baseline before any edit.

*Existing pytest infrastructure covers execution — no framework install needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live vault stub auto-creation through Obsidian REST | VAULT-01 | Vault is REST-only; no local mount in-repo, real REST endpoint needed | After deploy, confirm `self/{identity,methodology,goals,relationships}.md` stubs appear in the live Obsidian vault where previously missing |

*Semantic recall ranking-quality (VAULT-03) is asserted via deterministic recency-weight unit tests, not manual inspection.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify (pytest command per task; no separate RED wave — characterization is folded into each plan test-first)
- [x] Sampling continuity: every task has an automated verify; full suite at every wave boundary
- [x] Wave 0 gaps covered: the 4 new characterization tests + 7 rewrites are distributed into the plans that land the code they exercise (no orphan RED wave)
- [x] No watch-mode flags (all commands are single-shot `pytest`)
- [ ] Feedback latency measured at first task execution (baseline: 471 tests collected)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned (planner) — execution pending
