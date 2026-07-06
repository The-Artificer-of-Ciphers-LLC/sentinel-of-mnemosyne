# Phase 44: Vault Namespace + Taxonomy Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-06
**Phase:** 44-vault-namespace-taxonomy-foundation
**Areas discussed:** Carrier-allowlist fate, inbox/ embed timing, PARA reroute table, self/ stubs + read, Migration-window behavior

---

## ① Carrier-allowlist fate (VAULT-03, Pitfall 2)

| Option | Description | Selected |
|--------|-------------|----------|
| A. Sessions-only collapse | Delete the stale topic allowlist; recency weighting stays episodic-sessions-only (MEM-09). notes/=authored (no decay); journal/accompl ops-excluded anyway | ✓ |
| B. Repoint to new paths | Keep the machinery, update prefixes — set becomes effectively empty/dead code | |
| C. Shared-source subset weighting | Derive carrier from one taxonomy module and keep weighting a warm-recallable subset of notes/ | |

**User's choice:** A. Sessions-only collapse
**Notes:** Migration removes every path the allowlist weighted; collapsing to the MEM-09 rule is the honest end state, not dead machinery. T-41-08 anti-omission principle preserved as a regression invariant (D-01a).

---

## ② inbox/ embed timing (VAULT-04, Pitfall 3)

| Option | Description | Selected |
|--------|-------------|----------|
| A. Sweeper embeds inbox/, out of keyword recall | Remove inbox/ from SWEEP_SKIP_PREFIXES, keep in exclude_prefixes. Matches ROADMAP SC-4 + Pitfall 3; fixes stale VAULT-04 wording | ✓ |
| B. Keep skipped; on-demand embed at Reduce | Matches literal VAULT-04 text; backlog stays unembedded; pulls Phase 46 Reduce path into 44 | |
| C. Embed + expose in recall | Remove from both lists — raw captures become recallable; breaks D-06 noise quarantine | |

**User's choice:** A. Sweeper embeds inbox/, out of keyword recall
**Notes:** Resolved a REQUIREMENTS-vs-ROADMAP contradiction — VAULT-04 text said the opposite of ROADMAP SC-4/Pitfall 3. Resolved in favor of ROADMAP; VAULT-04 wording corrected in REQUIREMENTS.md during this session (D-02a).

---

## ③ PARA reroute table (VAULT-02)

| Option | Description | Selected |
|--------|-------------|----------|
| A. ARCHITECTURE AFTER table + single source of truth | Verbatim reroute; 7-slug vocab unchanged; extract TOPIC_VAULT_PATH into one module recall.py's carrier logic imports too | ✓ |
| B. Keep journal/accompl top-level | Preserves their warm recall but contradicts SC-2 ('under ops/ subdirectories') | |
| C. Full PARA vocab swap | Classifier emits Projects/Areas/Resources/Archive — reclassification risk, not what ARCHITECTURE prescribes | |

**User's choice:** A. ARCHITECTURE AFTER table + single source of truth
**Notes:** Single source of truth (D-03b) is the structural fix for Pitfall 2's root cause (dual-maintenance drift). journal/accomplishment leaving warm recall (D-03c) is an intended consequence, coupled with ①A.

---

## ④ self/ stubs + read (VAULT-01/05)

| Option | Description | Selected |
|--------|-------------|----------|
| A. Lazy seeded-template stubs | D-14 lazy-create identity/methodology/goals/relationships as minimal guiding stubs on first startup read if missing. VAULT-05 read already satisfied by self_paths | ✓ |
| B. Empty placeholder stubs | Create blank files — zero tokens but no user guidance | |
| C. Eager startup migration | Create all dirs+stubs eagerly on boot — violates REST-only lazy-create convention | |

**User's choice:** A. Lazy seeded-template stubs
**Notes:** Flagged that VAULT-05's every-message self/ read is ~90% already implemented via RecallConfig.self_paths — the real delta is guaranteeing the four files exist (D-04a). Planner should not rebuild the read.

---

## Migration-window behavior (44→47)

| Option | Description | Selected |
|--------|-------------|----------|
| Accept transient, document it | Existing top-level journal/accomplishment notes lose recency weighting before Phase 47 migrates them; record in MIG-03 ledger as accepted, self-healing | ✓ |
| Temporary compat shim | Keep weighting old paths until Phase 47, then remove — no transient but throwaway code | |

**User's choice:** Accept transient, document it
**Notes:** Deliberate + aligned with MEM-09; self-heals at Phase 47. Recorded in MIG-03 regression ledger as a known accepted behavior change, not a silent regression (D-05).

## Claude's Discretion

- Home/name of the shared taxonomy module (D-03b) — note_classifier.py the natural home.
- Exact stub content wording (D-04) — token-bounded.
- `PROTECTED_NAMESPACES += templates/` — include if suite-safe.

## Deferred Ideas

None — discussion stayed within phase scope. Reduce-step on-demand embedding → Phase 46; `_schema`/wikilinks → Phase 45; flat-7 backfill → Phase 47.
