---
phase: 45
slug: note-quality-schema-graph-analysis
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-06
---

# Phase 45 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Full per-task map is populated by the planner (PLAN.md `<verify>` blocks) and Wave 0 test stubs.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (Python, project `.venv`) |
| **Config file** | `sentinel-core/` (system python3 has no pytest — MUST use the venv interpreter) |
| **Quick run command** | `cd sentinel-core && .venv/bin/python -m pytest tests/ -q` |
| **Full suite command** | `cd sentinel-core && .venv/bin/python -m pytest tests/` |
| **Estimated runtime** | ~30–60 seconds |
| **Green baseline (must not regress)** | 473 passed / 12 skipped |

---

## Sampling Rate

- **After every task commit:** Run the quick run command scoped to the touched test module(s).
- **After every plan wave:** Run the full suite command.
- **Before `/gsd-verify-work`:** Full suite must be green at 473+ passed (read-mostly phase — the 473/12 baseline must hold, no existing test may change behavior).
- **Max feedback latency:** ~60 seconds.

---

## Per-Task Verification Map

*Populated during planning (each PLAN.md task carries `<acceptance_criteria>` + `<verify>`) and Wave 0. Rows below are the success-criteria → validation mapping the planner must honor.*

| SC | Requirement | Behavior to validate | Test Type | Notes |
|----|-------------|----------------------|-----------|-------|
| SC-1 | NOTE-01 | A note carries a trailing `_schema` block (type + hub membership) + claim-style title + ≥1 wikilink; `note_schema.py` parses the trailing block via regex-from-end | unit | Round-trip: block stays LAST in file (see Wave 0 landmine) |
| SC-2 | NOTE-02 | Hub materializes on the 2nd note clearing cosine floor 0.50; append-never-duplicate; idempotent read-then-append keyed on `notes/{slug}.md`; new wikilink inserted BEFORE the hub's own trailing `_schema` block | unit + integration | Assert second join does not duplicate hub; assert trailing-block invariant preserved |
| SC-3 | NOTE-03 | `:graph`/`:stats` report orphans, backlink counts, link density from `ops/graph/links-index.json` sidecar (no full walk per call); hybrid freshness incremental + lazy rebuild-if-stale | unit + integration | Include out-of-band hand-edit path (sidecar stale → lazy rebuild corrects) |
| SC-4 | NOTE-03 | `:check` lists notes missing `_schema` / claim-title / wikilink; claim-title test is structural only (H1 present, not bare slug) — no LLM | unit | Deterministic; assert zero LLM calls |
| SC-5 | (all) | Read-mostly: `POST /message`, `Recall`, semantic recall unchanged; full suite stays green | regression | Full-suite green at 473/12; no write-path enforcement added |

---

## Wave 0 Requirements

- [ ] Characterizing test for `note_classifier` routing (`learning`/`reference` → `inbox/`) — locks the "no notes/ write path in P45" invariant that makes inspect-only safe.
- [ ] Wikilink → path resolution fixture (title-based vs filename-stem) — research Open Question 2; cannot be verified against a live Obsidian instance, so pin the rule with a fixture test.
- [ ] Trailing-`_schema`-block invariant test — appending a wikilink to a hub must NOT push content after the trailing block.
- [ ] Shared fixtures reuse `tests/fakes/vault.py` `FakeVault` (canonical test double) and module-constant patching pattern.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Rendering of `_schema` fenced block + hub MOC in the live Obsidian desktop app | NOTE-01/02 | Requires a real Obsidian instance + REST plugin; not reproducible in the automated suite | After deploy, open a `notes/` note and a materialized hub in Obsidian Reading View; confirm the `_schema` block renders as a gray code block and wikilinks resolve |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
