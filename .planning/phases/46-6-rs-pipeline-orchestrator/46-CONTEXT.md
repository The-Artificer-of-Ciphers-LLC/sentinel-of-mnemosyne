# Phase 46: 6 Rs Pipeline Orchestrator - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the **real background orchestration** for the 6 Rs pipeline — cloned from the
proven vault-sweeper shape — so the pipeline commands actually walk `inbox/`, drive
per-phase structured LLM completions, and mutate `notes/`, replacing today's
**dead fixed-prompt stubs**. Requirements: **PIPE-01..07**.

Concretely, this phase delivers (per ARCHITECTURE.md "Phase C"):
- `app/services/pipeline_orchestrator.py` — background task, mirrors `vault_sweeper.run_sweep`
- `app/services/pipeline_status_store.py` — mirrors `sweep_status_store.py` (in-memory dict)
- `app/services/six_rs/{reduce,reflect,reweave,verify,rethink}.py` — one structured
  `acompletion_with_profile(response_format=json_schema)` per phase (Pattern 1), each with
  minimal fresh context (never the Hot/Warm recall tier)
- `app/routes/pipeline.py` — `POST /vault/pipeline/start`, `GET /vault/pipeline/status`
  (admin-gated, mirrors `/vault/sweep/*`)
- Rewire in `command_router.py` / `bot.py` / `core_gateway.py`: `:ralph`, `:pipeline`,
  `:reweave`, `:rethink`, `:refactor` swap from `_SUBCOMMAND_PROMPTS` fixed-prompt stubs to
  the new endpoint calls; add `call_core_pipeline_start/status`

**Command → phase mapping (from master-spec D-09 + ARCHITECTURE data-flow):**
| Command | Phases run (`mode`) |
|---|---|
| `:ralph` | Reduce + Reflect over the `inbox/` queue (the batch core) |
| `:pipeline` | Full sequence: Record → Reduce → Reflect → Reweave → Verify → Rethink |
| `:reweave` | Reweave backward pass only |
| `:rethink` / `:refactor` | Rethink triage only |

**Explicitly NOT in this phase (structure already locked / other phases):**
- `:capture`/`:seed` (Record) intake — **unchanged**, already writes `inbox/` (PIPE-01 already met)
- `:review`/`:connect`/`:graph`/`:stats`/`:check` read/analysis endpoints — **Phase 45 (shipped)**
- Migration/backfill of existing flat-7 content into `notes/` — **Phase 47**
- New Docker container / module registration — **rejected** (Anti-Pattern 6; runs in-process in `sentinel-core`)
- Any change to `POST /message`, `MessageProcessor`, or Recall — **rejected** (Anti-Pattern 3/4)

</domain>

<decisions>
## Implementation Decisions

### Reweave safety posture (PIPE-04)
- **D-01:** Reweave is **auto-apply append-only**. Each reweave candidate gets a bounded
  `## Reweave — {date}` section appended to the older note; **existing prose is never
  rewritten or deleted**. This is the safe posture for the transaction-less REST vault
  (full-body PUT, no atomic PATCH) under local-model quality bounds — it delivers the real
  backward-pass mutation PIPE-04 asks for without risking corruption of durable knowledge.
  Full prose-rewrite synthesis is **deferred**. The append must be **idempotent** — dedupe
  by the dated section marker so a re-run doesn't stack duplicate sections (follow the
  Phase 45 `attach_to_hub` idempotency precedent, D-03d).

### Verify-failure handling (PIPE-07)
- **D-02:** When a freshly-Reduced note fails compliance, **requeue it to `inbox/` with a
  bounded retry count** — it does **not** land in `notes/`. On the next run it is re-Reduced;
  after the retry cap it is left in `inbox/` marked `needs-attention` and surfaced in the
  outcome report (never silently dropped, never looped forever). This keeps the knowledge
  graph clean, which is the whole point of enforcing at Verify (PIPE-07), and reuses the
  existing `inbox/` queue as a natural dead-letter.
- **D-02a:** Compliance is checked with the **already-shipped `note_schema.check_note_compliance`**
  (Phase 45, `note_schema.py:121`) — `_schema` block present + claim-style title + ≥1 wikilink.
  The Verify phase does **not** re-implement the check; `six_rs/verify.py` only adds the
  optional claim-title natural-language assist (cheap heuristic or a single LLM call);
  everything else is pure-Python reuse.
- **D-02b:** Retry cap value is **Claude's discretion** (suggested default **2**); make it a
  named constant, not a magic number.

### Run UX & outcome reporting (PIPE-06 + roadmap "explicit outcome reporting")
- **D-03:** **Always-async + poll**, mirroring `:vault-sweep` **exactly**. `POST
  /vault/pipeline/start` returns a "started" ack immediately; the user polls `:pipeline`
  (status) the same way `:vault-sweep status` works. No synchronous/inline run path (rejected:
  Anti-Pattern 3 — a long inline run breaks the `POST` latency/token contract) and no
  core→Discord push-back (deferred — status is pull-only today; a push path is net-new plumbing).
- **D-03a:** The `PipelineReport` (in-memory, via `pipeline_status_store`, mirroring
  `SweepReport`) exposes **explicit per-phase counts**: entries total/processed, reduced,
  hubs touched (Reflect), reweave edits applied, verify-failed/requeued, plus `status`
  (idle/running/complete) and `mode`. Exact field names are Claude's discretion but the
  per-phase counts are mandatory ("explicit outcome reporting").

### Concurrency guard (PIPE-06)
- **D-04:** **Shared lockfile — pipeline and sweep are mutually exclusive.** The pipeline
  reuses the existing `acquire_sweep_lock` / `release_sweep_lock` mechanism (lockfile at
  `ops/sweeps/_in-progress.md`, stale>1h force-takeover) as a single "vault-mutation in
  progress" mutex, so a sweep and a pipeline run can never overlap. This prevents the real
  `notes/` races (sweeper embedding a half-written note; a sweep relocation racing a pipeline
  write) that independent locks would allow. Progress reporting lives in a **separate
  in-memory `pipeline_status_store`** — the lockfile handles exclusion, the status store
  handles progress; they are orthogonal (the sweep already works this way).
- **D-04a:** When the lock is already held, `:ralph`/`:pipeline`/`:reweave`/`:rethink` return
  a clear "a vault operation is already in progress" message (mirror the sweep's
  concurrent-run refusal), not a silent no-op.

### Orchestration shape (carried forward from ARCHITECTURE.md — locked, not re-litigated)
- **D-05:** Each of the 6 Rs phases is an **independent structured completion** (Pattern 1),
  reusing `note_classifier.py`'s `acompletion_with_profile(response_format=json_schema)` +
  model-resolution pattern. "Fresh context per phase" = N narrow LLM calls with minimal
  payloads, **not** OS-level subagents and **never** `Recall.assemble()`'s Hot/Warm tier
  (Anti-Pattern 4).
- **D-06:** Background execution via the existing `AsyncioTaskRunner.schedule()`
  (`asyncio.create_task`) seam — same as `note_sweep_runner`. No new container (Anti-Pattern 6).
- **D-07:** Reflect reuses the **already-shipped-but-uncalled** `moc_maintenance.attach_to_hub`
  + `graph_analysis.hub_candidates` (Phase 45) with embedding-first / cosine-floor hub lookup
  (Pattern 4), LLM naming only as fallback. Phase 46 is where these Phase-45 modules get their
  first caller.

### Claude's Discretion
- Whether `routes/pipeline.py` is a new file or an extension of `routes/note.py` (ARCHITECTURE
  allows either) — follow the sweep-route precedent.
- Exact `PipelineReport` field names and the `mode` enum representation.
- Retry-cap constant value for D-02 (suggested 2) and the `needs-attention` marker format.
- Whether `six_rs/verify.py`'s claim-title assist is a pure heuristic or a single LLM call
  (D-02a) — cost/quality call for the planner.
- Reweave candidate-discovery specifics (PIPE-04 says "reusing SemanticRecall for candidate
  discovery") — the exact "recently referenced but stale" heuristic in `graph_analysis`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & build order (primary — read first)
- `.planning/research/ARCHITECTURE.md` — **"Phase C" build order** (lines 414–426); the target-state
  diagram (lines 67–124); the Phase-C component/integration tables (lines 481–491); **Pattern 1**
  (6 Rs = independent structured completions, lines 210–250); **Pattern 2** (background task, not
  request-time, lines 252–278); **Pattern 4** (embedding-first hub lookup, lines 302–317); and
  **Anti-Patterns 1, 3, 4, 6** (lines 522–606) which lock the structural decisions this phase must
  honor.

### Original design spec
- `docs/2nd-brain-original-design/10-CONTEXT-master-spec.md` — **D-09** (6 Rs pipeline definition +
  command→phase mapping, lines 160–174); **D-13** (`:ralph` = Reduce+Reflect batch core); **D-15**
  (`:reweave` backward-pass semantics). NOTE: D-13/D-15 describe the *old* single-prompt-to-chatbot
  model — this phase deliberately **supersedes** that with real backend orchestration (the roadmap
  goal + ARCHITECTURE Anti-Pattern 1). Read them for the *intent* of each command, not the mechanism.

### Prior-phase context (constraints this phase builds on)
- `.planning/phases/45-note-quality-schema-graph-analysis/45-CONTEXT.md` — Phase 45 shipped
  `note_schema.py` (`check_note_compliance`), `graph_analysis.py`, and `moc_maintenance.py`
  (`attach_to_hub`, hub-lookup at `semantic_cosine_floor = 0.50`); D-05 (`_schema` trailing-block
  format). These are the Verify + Reflect building blocks — **reuse, do not reimplement**.
- `.planning/research/PITFALLS.md` §Pitfall 6 — enforce at Verify, never at file-time (basis for
  PIPE-07 and D-02).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (verified present in tree, 2026-07-06)
- **Sweep template to clone (the whole shape):**
  - `sentinel-core/app/services/vault_sweeper.py` — `run_sweep()` (`:412`), `SweepReport` model
    (`:132-143`), `get_status`/`_set_status` wrappers (`:756-761`), `LOCKFILE_PATH =
    "ops/sweeps/_in-progress.md"` (`:99`).
  - `sentinel-core/app/services/note_sweep_runner.py` — `start_sweep()` (`:33`) route wrapper;
    schedules background task via `runner.schedule(_runner())` (`:150`).
  - `sentinel-core/app/services/sweep_status_store.py` — in-memory `_SWEEP_STATUS` dict (`:5-12`),
    `get_sweep_status` (`:15`), `set_sweep_status_from_report` (`:19`). **Mirror as
    `pipeline_status_store.py`.**
  - `sentinel-core/app/services/task_runner.py` — `AsyncioTaskRunner.schedule()` (`:14-16`,
    `asyncio.create_task`). No persistent queue / no retry — the orchestrator owns any retry logic (D-02).
  - `sentinel-core/app/routes/note.py:135-190` — `POST /vault/sweep/start` (admin-gated) +
    `GET /vault/sweep/status`. **Mirror for `routes/pipeline.py`.**
- **Concurrency (D-04):** `sentinel-core/app/vault.py` — `acquire_sweep_lock()` (`:692-714`, writes
  `{started_at, host}` frontmatter, stale>3600s takeover) + `release_sweep_lock()` (`:716-720`).
  **Reuse this exact lock as the shared vault-mutation mutex.**
- **Per-phase LLM pattern (D-05):** `sentinel-core/app/services/note_classifier.py` — the
  `acompletion_with_profile(response_format=json_schema)` + model-resolution template each
  `six_rs/*` module copies.
- **Verify (D-02a):** `sentinel-core/app/services/note_schema.py:121` — `check_note_compliance(body,
  filename_slug) -> dict` (already shipped, Phase 45).
- **Reflect (D-07):** `sentinel-core/app/services/moc_maintenance.py` (`attach_to_hub`, shipped
  Phase 45, **not yet called by anything** — Phase 46 is its first caller) +
  `sentinel-core/app/services/graph_analysis.py` (`hub_candidates`).
- **Inbox seam (Record→Reduce):** `sentinel-core/app/services/inbox.py` — `INBOX_PATH =
  "inbox/_pending-classification.md"` (`:44`), `append_entry()` (`:170-198`), `parse_inbox()`
  (`:122-138`). The orchestrator's Reduce phase consumes these entries.

### Established Patterns
- **Discord→core gateway:** `interfaces/discord/core_gateway.py` — `call_core_sweep_start()`
  (`:78-95`) / `call_core_sweep_status()` (`:98-115`) are the exact template for the new
  `call_core_pipeline_start/status`.
- **Dispatch:** `interfaces/discord/command_router.py:39-183` `handle_subcommand()`; the pipeline
  verbs currently resolve to `_SUBCOMMAND_PROMPTS` fixed prompts in `bot.py:182-186` — **remove
  those entries** when rewiring (mirrors Phase 45-07 "drop dead prompts").
- **Idempotent write-back:** Phase 45 `attach_to_hub` re-append-under-marker (D-03d) — apply the
  same shape to reweave's dated-section append (D-01).

### Integration Points
- New `pipeline_orchestrator.py` + `pipeline_status_store.py` + `six_rs/*` + `routes/pipeline.py`
  wired into `RouteContext`/composition alongside the sweep (same pattern as Recall in Phase 39).
- **Zero coupling** to `MessageProcessor` / `POST /message` / Recall / Pathfinder module (deliberate).

</code_context>

<specifics>
## Specific Ideas

- All four open decisions were resolved to the recommended (safest / lowest-plumbing) option:
  append-only reweave, requeue-on-verify-fail, async-poll UX mirroring the sweep, and a shared
  lockfile with the sweeper.
- The guiding constraint throughout: this is a **backend-orchestration** problem on a
  **transaction-less REST vault** driven by a **local model** — favor deterministic Python
  orchestration + schema-validated per-phase completions over "hand the model one big prompt."
- `moc_maintenance.attach_to_hub` shipping in Phase 45 but never being called is the tell that
  Phase 45 built the Reflect *output seam* ahead of the orchestrator that would use it — Phase 46
  connects it.

</specifics>

<deferred>
## Deferred Ideas

- **Full prose-rewrite reweave** (true synthesis that edits existing note bodies) — deferred from
  D-01; revisit once append-only reweave is proven safe against the live vault + local model.
- **Verify auto-retry with a corrective prompt** (the option-C enhancement to D-02) — fold in later
  as an extra LLM call on top of the requeue-with-retry-count mechanism.
- **Core→Discord completion push** (auto-post the outcome report instead of manual `:pipeline`
  poll) — deferred from D-03; needs a net-new core→bot push path.
- **Migration/backfill of existing flat-7 content** into PARA/`notes/` with `_schema` — **Phase 47**.

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 46-6 Rs Pipeline Orchestrator*
*Context gathered: 2026-07-06*
