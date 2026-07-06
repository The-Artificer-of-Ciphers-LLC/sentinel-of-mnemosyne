---
phase: 44
slug: vault-namespace-taxonomy-foundation
status: draft
nyquist_compliant: false
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

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 44-01-01 | 01 | 0 | VAULT-01..05 | — | N/A | characterization | `cd sentinel-core && pytest -k "recall or sweeper or classifier"` | ❌ W0 | ⬜ pending |

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency measured at Wave 0
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
