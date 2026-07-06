# Phase 46: 6 Rs Pipeline Orchestrator - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-06
**Phase:** 46-6 Rs Pipeline Orchestrator
**Areas discussed:** Reweave safety posture, Verify-failure handling, Run UX & outcome report, Concurrency vs sweeper

**Mode:** advisor (comparison-table-first). Calibration tier: `standard` (2–4 options).
Owner classified technical (terse-direct); no plain-language reframing applied.

**Framing note:** ARCHITECTURE.md's "Phase C" is unusually prescriptive — the orchestrator
structure, status store, `six_rs/` package, admin-gated routes, and six anti-patterns were
already locked and carried forward without re-asking. Discussion focused only on the four
behavior/safety decisions ARCHITECTURE.md leaves open.

---

## Reweave safety posture

| Option | Description | Selected |
|--------|-------------|----------|
| Append-only | Auto-apply a bounded `## Reweave — {date}` section; never rewrite existing prose | ✓ |
| Propose-only | Write suggestions to a report/`ops/reweave/`; human applies | |
| Full auto-edit | Rewrite the note body with synthesized updates | |

**User's choice:** Append-only (recommended)
**Notes:** Safe posture for the transaction-less full-body-PUT vault + local model; delivers the
real PIPE-04 backward-pass mutation while keeping original prose immutable. Full-rewrite synthesis
deferred. Append must be idempotent (dedupe by dated marker, per Phase 45 `attach_to_hub`).

---

## Verify-failure handling

| Option | Description | Selected |
|--------|-------------|----------|
| Requeue to inbox + retry cap | Don't land in `notes/`; re-Reduce next run; after N fails mark needs-attention in report | ✓ |
| Land + flag in report | Write to `notes/` anyway, set `_schema.status: unverified`, list it | |
| Auto-retry once, then requeue | Re-run Reduce once with a corrective prompt, then fall back to requeue | |

**User's choice:** Requeue to inbox + retry cap (recommended)
**Notes:** Matches PIPE-07 (enforce at Verify, keep graph clean); reuses `inbox/` as a dead-letter.
Compliance via already-shipped `note_schema.check_note_compliance` (Phase 45). Retry cap value is
Claude's discretion (suggested 2). Auto-retry-with-corrective-prompt noted as a future enhancement.

---

## Run UX & outcome report

| Option | Description | Selected |
|--------|-------------|----------|
| Async + poll, mirror `:vault-sweep` | "Started" ack; poll `:pipeline` status; per-phase counts | ✓ |
| Sync under a threshold | Tiny inbox runs inline and returns full report; larger goes async | |
| Async + auto-post completion | Async ack, then orchestrator posts report back to Discord | |

**User's choice:** Async + poll, mirror `:vault-sweep` (recommended)
**Notes:** Reuses the proven admin-gated pull-status shape, zero new plumbing; `PipelineReport`
carries explicit per-phase counts. Sync branch rejected (Anti-Pattern 3, breaks POST latency
contract). Push-back deferred (needs net-new core→bot path).

---

## Concurrency vs sweeper

| Option | Description | Selected |
|--------|-------------|----------|
| Shared lockfile, mutually exclusive | Reuse `acquire_sweep_lock`; separate in-memory status store | ✓ |
| Independent lockfile + cross-check | Own lockfile, refuse to start while sweep lock held | |
| Independent lockfiles, may overlap | Own lockfile guarding only a 2nd pipeline; sweep+pipeline can race | |

**User's choice:** Shared lockfile, mutually exclusive (recommended)
**Notes:** Pipeline writes `notes/`, sweeper embeds `notes/` — must not overlap. Shared lockfile
gives mutual exclusion for free; progress lives in a separate in-memory `pipeline_status_store`.
Locked-out commands return a clear "operation in progress" message (mirror the sweep).

## Claude's Discretion

- `routes/pipeline.py` new file vs extension of `routes/note.py`.
- `PipelineReport` field names + `mode` enum representation.
- Verify retry-cap constant value (suggested 2) + `needs-attention` marker format.
- `six_rs/verify.py` claim-title assist: pure heuristic vs single LLM call.
- Reweave "recently referenced but stale" candidate-discovery heuristic (PIPE-04 reuses SemanticRecall).

## Deferred Ideas

- Full prose-rewrite reweave (revisit after append-only proven).
- Verify auto-retry with corrective prompt (fold onto the retry-count mechanism later).
- Core→Discord completion push (needs net-new push path).
- Flat-7 content migration/backfill → Phase 47.
