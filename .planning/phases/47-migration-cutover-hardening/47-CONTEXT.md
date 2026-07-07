# Phase 47: Migration Cutover + Hardening - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Backfill every existing flat-7-classified note (`learning/`, `reference/`, `journal/`, `accomplishments/`) into the PARA/`_schema` structure — none grandfathered — while preserving embedding sidecar entries and wikilink integrity, then verify the MEM-0x + command-surface regression ledger is green and the full 404+ test suite still passes at this final milestone boundary.

**In scope:** the migration/cutover mechanism (a `:migrate` surface), the two-track move (Reduce vs direct), backlink handling for renamed notes, the pre/post `:graph` dangling-link gate, and the boundary hardening checks (ledger + suite green).

**Out of scope:** new note-authoring behavior (Phase 46), new taxonomy/namespaces (Phase 44), new schema/graph machinery (Phase 45). We are *moving existing content through machinery that already exists*, not building new capabilities.
</domain>

<decisions>
## Implementation Decisions

### Migration path (how flat-7 content reaches PARA)
- **D-01:** **Two-track migration.**
  - **Notes-bound** (`learning/`, `reference/`) → moved to `inbox/` (frontmatter preserved), then routed through the **6 Rs Reduce pipeline** → born-compliant `notes/{claim-slug}.md` (claim-style title + `_schema` block + ≥1 wikilink). This rewrites content and produces a new title/slug.
  - **Ops-bound** (`journal/` → `ops/journal/{YYYY-MM-DD}/`, `accomplishments/` → `ops/accomplishments/`) → **direct in-place, frontmatter-preserving move** (no Reduce, title unchanged).
- **Rationale:** routing notes-bound content through Reduce makes migrated notes consistent with the go-forward pipeline (born-compliant), at the cost of content rewrite + re-embed for those notes. Ops-bound content is structural/temporal and needs no rewrite.

### Safety model (the cutover run)
- **D-02:** **Dry-run + atomic rollback.** `:migrate --dry-run` first prints every planned move, `_schema` stapling, and backlink rewrite with NO writes. The real `:migrate` run is transactional: **on any failure, roll back all moves to the exact pre-migration state.** Mirrors the Phase 46 rollback-on-fail lesson (never leave the vault half-migrated). See [[phase46-pipeline-coldstart-gap]] lesson: never mock the gate; real-compliance verification is mandatory.
- **D-02a:** The atomic-rollback requirement means the migration must track the exact inverse of every REST operation it performs (move-back paths, restored frontmatter, reverted backlink edits) so a partial run can be fully undone.

### Wikilink integrity (keeping `[[links]]` resolving)
- **D-03:** **Two-track, matching the migration path.**
  - **Ops-bound (direct move):** title unchanged → **verify-then-trust**. Empirically confirm (step 0) that Obsidian resolves `[[wikilinks]]` by note *title*, not path, by moving one note and checking the link still resolves. If title-based and title unchanged, links survive the move for free.
  - **Notes-bound (Reduce, title changes):** **actively rewrite backlinks.** For each note routed through Reduce (`old-title` → new claim title), scan the vault for `[[old-title]]` references and rewrite them to the new claim title. Title-based resolution cannot save these because Reduce changes the title.
- **D-03a:** **Hard gate:** a pre/post `:graph` dangling-link count diff must show **zero new orphans** introduced by migration. If the diff shows new orphans, the migration **aborts and rolls back** (per D-02). This gate is the backstop for both tracks.

### Embeddings (re-embed policy)
- **D-04:** **Preserve in-place + embed-on-Reduce.** Matches whichever track a note takes:
  - **Direct-move (ops) notes:** frontmatter-preserving move carries `embedding_b64` / `embedding_model` with the file → **no re-embed**. Sidecar survives (satisfies PITFALLS Pitfall 3).
  - **Reduce-path (learning/reference) notes:** content is rewritten, so the old embedding is stale → **embed immediately at Reduce time** (do NOT wait for the sweep — `inbox/` is in `SWEEP_SKIP_PREFIXES` and would stay permanently unembedded).
- **D-04a:** Confirm during planning whether flat-7 notes carry existing embedding frontmatter at all; any note lacking an embedding is picked up by the normal sweep post-migration (no special handling).

### Boundary hardening (the "cutover" acceptance)
- **D-05:** At the phase boundary, verify the **MEM-01..MEM-09 + command-surface regression ledger** (standing since Phase 44) is green — confirming Pathfinder, Recall/semantic-recall/retention, and the restored 27-command surface remain intact — and the **full existing 404+ suite passes** after migration completes. This is a hard gate, not a report.
- **D-05a:** The MIG-03 regression ledger (44-CONTEXT) records any accepted behavior changes (e.g., recency-weighting differences once old journal/accomplishment notes move to `ops/`). Migration must reconcile against it, not silently diverge.

### Claude's Discretion
- The exact command name/flags for the migration surface (`:migrate` assumed) and whether dry-run output is human-readable text vs structured — planner/executor decide.
- Batch ordering (e.g., ops-bound direct moves before or after Reduce-path notes) — decide for whichever ordering makes the atomic-rollback bookkeeping simplest; ops-bound-first is a reasonable default since it is the lower-risk track.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Migration build order & pitfalls (from ROADMAP Phase 47 canonical refs)
- `.planning/research/ARCHITECTURE.md` — Phase D build order (where migration/cutover sits in the sequence).
- `.planning/research/PITFALLS.md` — "Pitfall-to-Phase Mapping" and the "Looks Done But Isn't" checklist. Directly load-bearing rows:
  - **Pitfall 2** — `recall.py`'s `_CARRIER_NAMESPACE_PREFIXES` goes stale vs the classifier taxonomy; make it a shared source of truth imported by both `note_classifier.py` and `recall.py`.
  - **Pitfall 3** — frontmatter-preserving move (not delete+recreate) or embeddings drop → O(N) re-embed; `inbox/` is in `SWEEP_SKIP_PREFIXES` (embed-on-Reduce, don't wait for sweep).
  - **Pitfall 7** — REST write+delete does NOT trigger Obsidian's automatic backlink rewriting; existing `[[wikilink]]`s to old paths dangle. Confirm title-based resolution empirically (D-03 step 0).
  - "Looks Done But Isn't" checklist (frontmatter diffs, carrier-allowlist test, dangling-link diff, concurrency guard, `_schema` draft-filing, MEM-ledger green).

### Prior-phase decisions this phase depends on
- `.planning/phases/44-vault-namespace-taxonomy-foundation/44-CONTEXT.md` — PARA namespace/taxonomy (the target structure); MIG-03 regression ledger definition.
- `.planning/phases/45-note-quality-schema-graph-analysis/45-CONTEXT.md` — `_schema` block format (D-01: trailing fenced block, separate from leading YAML), `:graph`/`:check` machinery, `ops/graph/links-index.json` sidecar (D-04).
- `.planning/phases/46-6-rs-pipeline-orchestrator/46-CONTEXT.md` — 6 Rs Reduce pipeline that notes-bound content is routed through; compliance definition (PIPE-02a: claim title + `_schema` + ≥1 wikilink).

### Requirements
- ROADMAP.md Phase 47 requirements: **MIG-01, MIG-02, MIG-03, MIG-04** — see `.planning/ROADMAP.md` §"Phase 47" and `.planning/REQUIREMENTS.md` for the MIG-0x text.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **6 Rs Reduce pipeline** (Phase 46 orchestrator) — reused verbatim to make notes-bound content born-compliant; migration invokes it rather than reimplementing filing.
- **`:graph` / `:check`** + `ops/graph/links-index.json` — dangling-link counting for the pre/post gate (D-03a).
- **Embedding frontmatter** (`embedding_b64`, `embedding_model`) — travels with a frontmatter-preserving move (D-04).
- **Vault REST access** — Vault is REST-only; all moves/reads/writes go through the Obsidian REST API (`write_note`/`read_note`), not a local mount. See [[vault-is-rest-only-persist-indexes-through-vault]].

### Established Patterns
- **Frontmatter-preserving move over delete+recreate** — the load-bearing invariant for embeddings and (for direct moves) wikilinks.
- **Sidecar-index pattern** — embedding index and `links-index.json` both mirror the vault; keep them consistent through the migration.
- **Rollback-on-fail + real-compliance verification** — carried from Phase 46 ([[phase46-pipeline-coldstart-gap]]): never mock the verification gate in orchestrator tests.

### Integration Points
- `note_classifier.py` ↔ `recall.py` shared carrier-namespace source of truth (Pitfall 2) — migration must not leave `_CARRIER_NAMESPACE_PREFIXES` hand-maintained/stale.
- Sweeper `SWEEP_SKIP_PREFIXES` — governs when migrated notes get embedded (drives the embed-on-Reduce decision, D-04).
- MEM-01..09 + command-surface regression ledger — the boundary gate (D-05).
</code_context>

<specifics>
## Specific Ideas

- User explicitly wants born-compliant migration for notes-bound content (accepts the content-rewrite/re-embed cost of routing through Reduce) rather than the cheaper "direct move + staple `_schema`" shortcut.
- User wants the vault never left half-migrated — atomic rollback over a resumable-ledger approach, even though rollback of REST moves is more work to build.
- User wants active backlink rewriting for the Reduce'd notes (correct regardless of how many inbound links exist), not gate-only or measure-first.
</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (This is the final phase of the milestone; no new capabilities were raised.)
</deferred>

---

*Phase: 47-Migration Cutover + Hardening*
*Context gathered: 2026-07-06*
