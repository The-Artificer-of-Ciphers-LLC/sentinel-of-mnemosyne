# Phase 41: Typed SessionSummary + Retention - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-12
**Phase:** 41-typed-sessionsummary-retention
**Areas discussed:** Recency formula shape, Where recency applies, RetentionPolicy tunability, Old-session recall carrier

---

## Scope correction (pre-discussion)

The operator flagged that the recency-weighting formula being "deferred to post-v0.5.1" (as written in `REQUIREMENTS.md`) was **not authorized**. It was pulled back into Phase 41 scope as **MEM-09** and recorded durably in REQUIREMENTS.md / ROADMAP.md / PROJECT.md before the implementation discussion (commit `5615887`).

| Option | Description | Selected |
|--------|-------------|----------|
| Full recency-aware merge | Ship typed data + policy AND the recency formula in Phase 41; update docs out of "deferred" | ✓ |
| Typed data + policy only | Keep formula out, but as an explicit logged operator deferral | |

**User's choice:** Full recency-aware merge.

---

## Recency formula shape

| Option | Description | Selected |
|--------|-------------|----------|
| Exponential decay blend | Blend relevance with an exponential recency factor (tunable half-life); recent boosted, relevant-old can still surface | ✓ |
| Recency as tiebreaker | Relevance first; recency only nudges near-equal sessions | |
| Recency-dominant in window | Recent strongly outranks old; relevance secondary | |

**User's choice:** Exponential decay blend.
**Notes:** Behavioral target — recent beats old of equal relevance, but a clearly-relevant old session still surfaces. Half-life is tunable; ~7 days suggested as default for the planner to confirm.

---

## Where recency applies

| Option | Description | Selected |
|--------|-------------|----------|
| Hot ordering + warm merge | Recency weights both the hot recent-session list and session results in the warm RRF merge | ✓ |
| Hot-tier ordering only (⚠ under-delivers MEM-09) | Recency orders only the hot list; warm-recalled old sessions stay un-weighted | |

**User's choice:** Hot ordering + warm merge.
**Notes:** Selected option fully satisfies MEM-09; the alternative was flagged as a validated-requirement deviation.

---

## RetentionPolicy tunability

| Option | Description | Selected |
|--------|-------------|----------|
| Env-overridable | Defaults 3/2 in code, overridable via Settings env vars (like sweep_skip_prefixes); widen window without redeploy | ✓ |
| Code-only frozen defaults | RetentionPolicy(3,2) in code; change needs redeploy | |

**User's choice:** Env-overridable.
**Notes:** Env config, not vault-file tuning — stays within v0.5.1 scope (vault-file RecallConfig tuning remains deferred).

---

## Old-session recall carrier

| Option | Description | Selected |
|--------|-------------|----------|
| Existing conversation note, full body | Reuse the chat note already filed outside ops/ (NoteIntake) as the embedded recall carrier; researcher confirms it's wired + swept | ✓ |
| Distilled summary carrier note | Phase 41 writes a purpose-built summary note outside ops/ as the carrier | |

**User's choice:** Existing conversation note, full body.
**Notes:** `ops/` exclusion untouched in both options. Research gate (CONTEXT D-06): confirm the carrier is actually written every message, lives in a sweep-eligible + warm-recall-eligible namespace, and is embedded — close any gap rather than defer it.

## Claude's Discretion

- Exact decay curve constant / half-life value (default ~7 days unless evidence differs).
- Internal placement of the recency-weight helper (keep it a pure, unit-testable function).

## Deferred Ideas

- Persistent ANN vector index — operator-deferred in REQUIREMENTS.md (numpy cosine sufficient).
- Operator-tunable RecallConfig via a vault file — deferred; env-override is the in-scope middle ground.
- Cross-encoder reranking — deferred.
- (Nothing recency-related is deferred — MEM-09 is in scope this phase.)
