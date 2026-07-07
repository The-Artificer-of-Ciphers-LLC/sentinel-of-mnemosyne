# Phase 47: Migration Cutover + Hardening - Research

**Researched:** 2026-07-07
**Domain:** Vault migration/cutover on a REST-only Obsidian vault — two-track content move (Reduce-pipeline reuse vs. frontmatter-preserving relocate), atomic rollback, wikilink-integrity gate, embedding-sidecar preservation, milestone-boundary regression hardening.
**Confidence:** HIGH for all codebase-grounded findings below (every claim is cited to a live `file:line` read directly from `sentinel-core`/`interfaces/discord` in this session). MEDIUM for the two scope gaps flagged in Common Pitfalls (they are inferences from reading the actual entrypoints, not something any prior phase doc states explicitly). LOW/ASSUMED only where marked (vault scale counts, physical `references/` vs `reference/` directory name).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01 Two-track migration.** Notes-bound (`learning/`, `reference/`) → moved to `inbox/` (frontmatter preserved), then routed through the **6 Rs Reduce pipeline** → born-compliant `notes/{claim-slug}.md`. Ops-bound (`journal/` → `ops/journal/{YYYY-MM-DD}/`, `accomplishments/` → `ops/accomplishments/`) → **direct in-place, frontmatter-preserving move** (no Reduce, title unchanged).
- **D-02 Safety.** `:migrate --dry-run` preview, then transactional run with **atomic rollback** on any failure. Must track the inverse of every REST op to undo a partial run. (D-02a: the atomic-rollback requirement means tracking the exact inverse of every REST operation — move-back paths, restored frontmatter, reverted backlink edits.)
- **D-03 Wikilinks two-track.** Ops-bound direct moves use **verify-then-trust** (title unchanged). Reduce-path notes (title changes) get **active backlink rewriting**. Hard gate: pre/post `:graph` zero-new-orphans (else abort + rollback).
- **D-04 Embeddings.** Preserve-in-place for direct moves (`embedding_b64` frontmatter travels with file); embed-on-Reduce for the rewritten notes (`inbox/` is in `SWEEP_SKIP_PREFIXES` — **note: this is stale text in CONTEXT.md; see Pitfall/Correction below** — so waiting = never embedded).
- **D-05 Boundary hardening.** MEM-01..09 + command-surface regression ledger green + full 404+ suite green — hard gates.
- **D-05a.** The MIG-03 regression ledger (44-CONTEXT) records any accepted behavior changes (e.g., recency-weighting differences once old journal/accomplishment notes move to `ops/`). Migration must reconcile against it, not silently diverge.

### Claude's Discretion

- Exact command name/flags for the migration surface (`:migrate` assumed) and whether dry-run output is human-readable text vs structured.
- Batch ordering (ops-bound direct moves before or after Reduce-path notes) — ops-bound-first is a reasonable default (lower-risk track, simplifies rollback bookkeeping).

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope (final phase of the v0.6.0 milestone).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MIG-01 | Existing flat-7-classified notes are backfilled into the PARA/`_schema` structure with wikilinks | Reduce-path invocation mechanics (§"How to invoke Reduce for backfill"); ops-bound `relocate()` reuse (§"Frontmatter-preserving move") |
| MIG-02 | The embedding sidecar index and wikilink integrity are preserved through migration (no recall regression) | §"Embedding sidecar is path-keyed" (critical correction to D-04's plain reading); §"`:graph`'s notes/-only scope" (critical correction to D-03a's plain reading) |
| MIG-03 | A MEM-0x + command-surface regression ledger is verified at every phase boundary | §"The regression ledger — exact verification mechanics" |
| MIG-04 | Pathfinder module and recall/embeddings remain intact post-migration (existing 404+ test suite stays green) | §"Full-suite baseline" in Validation Architecture |
</phase_requirements>

## Summary

This phase does not need new libraries or new architecture — it needs to **correctly wire three already-shipped subsystems together** (the Phase 46 pipeline orchestrator, the Phase 45 links/graph sidecar, and the sweeper's `relocate()` primitive) and add one new thing: an atomic-rollback transaction wrapper around a `:migrate` command. Three of my findings **correct a plain reading of the locked CONTEXT.md decisions** and are load-bearing for planning:

1. **The Phase 46 orchestrator does NOT walk `inbox/` as a directory.** `pipeline_orchestrator._run_pipeline`/`_run_ralph` read a single queue file (`inbox/_pending-classification.md`, parsed via `inbox.parse_inbox()`). Physically `relocate()`-ing a `learning/*.md` file into `inbox/foo.md` produces a file the orchestrator will **never see**. The correct backfill mechanism is: read each notes-bound note's body, `inbox.append_entry()` it into the queue as a synthetic capture, delete the original, then call the *existing* `pipeline_orchestrator.run(vault, mode="pipeline")` unmodified.
2. **`:graph`/`:check`'s dangling-link computation only ever walks `NOTES_ROOT` ("notes/").** `links_sidecar_index.build_links_index` calls `walk_vault(vault, root=NOTES_ROOT)` — `ops/` is structurally invisible to it. D-03a's "pre/post `:graph` dangling-link diff" hard gate is therefore **only a real backstop for the Reduce-path (notes-bound) track**; it provides zero signal for ops-bound moves. The ops-bound "verify-then-trust" claim needs its own lightweight verification (a targeted vault-wide wikilink scan for the moved note's title), not reliance on `:graph`.
3. **The embedding sidecar (`ops/sweeps/embedding-index.json`) is keyed by path, and is the thing `SemanticRecall` actually reads at query time (MEM-05)** — not note frontmatter. `vault.relocate()` correctly preserves a note's OWN `embedding_b64`/`embedding_model` frontmatter (it does a `read_note`→annotate→`write_note`→`delete_note`, never stripping fields), but it does **not** touch the sidecar index. Left alone, the *next* sweep will silently re-embed every ops-bound moved note (harmless, self-healing, but costs one embed call per moved note and contradicts D-04's "no re-embed" framing for direct moves). The migration should **patch the sidecar's key** (rename old-path entry to new-path, values unchanged) in the same transaction as the `relocate()` call to make D-04's "no re-embed" claim literally true rather than "eventually true after the next sweep."

**Primary recommendation:** Build `:migrate` as three layers: (a) a rollback-ledger wrapper recording the inverse of every mutating call; (b) an ops-bound mover that calls `vault.relocate()` + a sidecar-key patch, gated by title-unchanged verify-then-trust; (c) a notes-bound enqueuer that calls `inbox.append_entry()` per legacy note then a single `pipeline_orchestrator.run(vault, mode="pipeline")` call, reusing Phase 46 verbatim. Gate the whole run on a pre/post `:graph` (`notes/`-scope) orphan diff for the Reduce track, plus a bespoke vault-wide backlink scan for the ops track, plus the standing MEM-0x/command-surface ledger and full 404+/326+ suite.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `:migrate` command dispatch (Discord) | Frontend (Discord bot) | — | Mirrors existing `:vault-sweep`/`:pipeline` admin-gated dispatch pattern in `command_router.py` |
| Migration orchestration + rollback ledger | API/Backend (sentinel-core) | — | New `app/services/migration_orchestrator.py`; same background-task shape as `pipeline_orchestrator.py`/`vault_sweeper.py` |
| Ops-bound direct move | API/Backend | Database/Storage (vault REST) | Reuses `ObsidianVault.relocate()` (`app/vault.py:631`) — no new persistence primitive |
| Notes-bound Reduce backfill | API/Backend | — | Reuses `pipeline_orchestrator.run(mode="pipeline")` (`app/services/pipeline_orchestrator.py:486`) verbatim, fed via `inbox.append_entry()` |
| Wikilink integrity gate | API/Backend | Database/Storage (links sidecar) | `graph_analysis.build_graph_report` (`app/services/graph_analysis.py:86`) + `links_sidecar_index` (`ops/graph/links-index.json`) — notes/-scoped only |
| Embedding sidecar preservation | API/Backend | Database/Storage (embedding sidecar) | `embedding_sidecar_index.py` (`ops/sweeps/embedding-index.json`), path-keyed |
| Regression ledger check | API/Backend (test suite) | Frontend (Discord command surface enumeration) | `.planning/v0.6.0-REGRESSION-LEDGER.md` (artifact) + `pytest` full-suite run |

## Standard Stack

No new external libraries are required for this phase. Every primitive this phase needs already exists in the codebase:

| Capability | Existing Module | Verified Location |
|---|---|---|
| Frontmatter-preserving relocate | `ObsidianVault.relocate()` | `sentinel-core/app/vault.py:631-690` |
| Inbox queue append (Record-equivalent) | `inbox.append_entry()` | `sentinel-core/app/services/inbox.py:183-220` |
| 6 Rs pipeline run | `pipeline_orchestrator.run()` | `sentinel-core/app/services/pipeline_orchestrator.py:486-534` |
| Wikilink graph / orphan count | `graph_analysis.build_graph_report()` | `sentinel-core/app/services/graph_analysis.py:86-128` |
| Links sidecar rebuild | `links_sidecar_index.rebuild_links_index()` | `sentinel-core/app/services/links_sidecar_index.py:99-137` |
| Embedding sidecar read/decode | `embedding_sidecar_index.decode_index_body`/`eligible_entries` | `sentinel-core/app/services/embedding_sidecar_index.py:52,209` |
| Concurrency guard (shared lock) | `acquire_sweep_lock`/`release_sweep_lock` | `sentinel-core/app/vault.py:692-720` |
| Admin gate pattern | `_is_admin_route()` | `sentinel-core/app/routes/note.py:126-138` |
| Background task scheduling | `AsyncioTaskRunner.schedule()` | `sentinel-core/app/services/task_runner.py` |

**Package Legitimacy Audit:** Not applicable — this phase introduces zero new third-party packages. `[VERIFIED: codebase]` — confirmed via direct file reads listed above.

## Architecture Patterns

### System Architecture Diagram

```
Discord :migrate [--dry-run]
    │
    ▼
command_router.handle_subcommand("migrate", ...)   [NEW — mirrors :vault-sweep admin gate]
    │  admin-gated, same shape as call_core_sweep_start/status
    ▼
POST /vault/migrate/start   (NEW route, mirrors /vault/sweep/start)
    │
    ▼
migration_orchestrator.run(vault, dry_run=bool)     [NEW — background task via AsyncioTaskRunner]
    │
    ├─ acquire_sweep_lock()  ── shared with sweeper + pipeline (D-04 precedent, Pitfall 8)
    │
    ├─ Pre-migration snapshot:
    │     graph_pre = GET /vault/graph  (notes/-scoped orphan/backlink baseline)
    │     ops_backlink_scan_pre = vault-wide search for [[old-title]] per ops-bound file
    │
    ├─ TRACK A — Ops-bound (journal/, accomplishments/) — do FIRST (lower risk)
    │     for each flat-7 file under journal/ | accomplishments/:
    │         dst = relocate(src, "ops/{journal|accomplishments}/...")   [app/vault.py:631]
    │         patch embedding-index.json: rename key old_path -> dst    [NEW helper]
    │         record_rollback_op(inverse: relocate(dst, src) + revert sidecar key)
    │
    ├─ TRACK B — Notes-bound (learning/, reference/) — Reduce backfill
    │     for each flat-7 file under learning/ | reference/:
    │         body = read_note(src)
    │         inbox_body = append_entry(inbox_body, candidate_text=body,
    │                                   result=ClassificationResult(topic=...))
    │         record_rollback_op(inverse: remove_entry(n) + restore(src, body))
    │         delete_note(src)  [after successful enqueue]
    │     write_note(INBOX_PATH, inbox_body)   # one batched write
    │     report = pipeline_orchestrator.run(vault, mode="pipeline")   [REUSED VERBATIM]
    │
    ├─ Post-migration checks:
    │     graph_post = GET /vault/graph
    │     assert graph_post.orphans - graph_pre.orphans has no NEW entries  (D-03a hard gate)
    │     ops_backlink_scan_post — re-run same scan, assert no new dangling ref
    │     IF any check fails OR any REST op raised → replay rollback ledger in reverse
    │
    ├─ Boundary hardening (D-05, MIG-03):
    │     run full pytest suite (sentinel-core + discord)
    │     verify MEM-01..09 characterization tests green
    │     verify command-surface smoke (every :command still dispatches)
    │     append check-in row to .planning/v0.6.0-REGRESSION-LEDGER.md §4
    │
    └─ release_sweep_lock()
```

### Recommended Project Structure

```
sentinel-core/
├── app/
│   ├── services/
│   │   ├── migration_orchestrator.py     # NEW — top-level :migrate orchestration
│   │   ├── migration_rollback_ledger.py  # NEW — records inverse ops, replays on failure
│   │   └── migration_status_store.py     # NEW — mirrors pipeline_status_store.py exactly
│   └── routes/
│       └── migration.py                  # NEW — POST /vault/migrate/start (dry_run flag),
│                                          #        GET /vault/migrate/status
└── tests/
    ├── test_migration_orchestrator.py    # NEW
    ├── test_migration_rollback_ledger.py # NEW
    └── test_migration_routes.py          # NEW

interfaces/discord/
├── command_router.py                     # MODIFIED: :migrate dispatch (admin-gated)
├── bot.py                                # MODIFIED: remove any stale fixed-prompt entry if present
└── core_gateway.py                       # MODIFIED: call_core_migrate_start/status
```

### Pattern 1: Reuse the pipeline orchestrator verbatim via the inbox queue, never a directory walk

**What:** Feed notes-bound legacy content through the *existing* single-queue-file mechanism (`inbox.append_entry`), then call `pipeline_orchestrator.run(vault, mode="pipeline")` unmodified.

**When to use:** Every `learning/`/`reference/` legacy file.

**Why not a direct `relocate()` into `inbox/`:** `_run_pipeline`/`_run_ralph` read exactly one file, `INBOX_PATH = "inbox/_pending-classification.md"`, via `parse_inbox()` (`app/services/inbox.py:44,133`). A file relocated to `inbox/some-note.md` is invisible to the orchestrator — it is not enumerated by any `list_under("inbox")` walk in `pipeline_orchestrator.py`. Confirmed by reading the full `_run_ralph`/`_run_pipeline` bodies (`app/services/pipeline_orchestrator.py:283-413`): both start with `inbox_body = await vault.read_note(INBOX_PATH)` then `parse_inbox(inbox_body)`.

**Example:**
```python
# migration_orchestrator.py — notes-bound track (Pattern 1)
from app.services.inbox import INBOX_PATH, append_entry
from app.services.note_classifier import ClassificationResult
from app.services import pipeline_orchestrator

async def _enqueue_notes_bound(vault, legacy_paths: list[str], rollback: "RollbackLedger") -> None:
    inbox_body = await vault.read_note(INBOX_PATH)
    for src in legacy_paths:
        body = await vault.read_note(src)
        result = ClassificationResult(
            topic="learning" if src.startswith("learning/") else "reference",
            confidence=1.0,
            title_slug="",
            reasoning="migrated from flat-7 backfill (Phase 47)",
        )
        inbox_body = append_entry(inbox_body, candidate_text=body, result=result)
        rollback.record_restore_original(src, body)  # inverse: write_note(src, body) if aborted
    await vault.write_note(INBOX_PATH, inbox_body)
    for src in legacy_paths:
        await vault.delete_note(src)  # after the batched enqueue write succeeds

    # Reuse Phase 46 verbatim — no reimplementation of Reduce/Reflect/Verify.
    report = await pipeline_orchestrator.run(vault, mode="pipeline")
    return report
```

### Pattern 2: Ops-bound moves reuse `relocate()` + an explicit sidecar-key patch (not a bare relocate)

**What:** Call the existing `ObsidianVault.relocate(src, dst)` for the frontmatter-preserving move, then immediately patch the embedding sidecar's key so semantic recall does not silently drop the note until the next sweep.

**Why the extra step is necessary:** `relocate()` (`app/vault.py:631-690`) preserves the note's own frontmatter perfectly (reads full body, adds only `original_path`/`topic_moved_at`, writes to `dst`, deletes `src`) — but `SemanticRecall` at query time reads the **sidecar** (`ops/sweeps/embedding-index.json`, path-keyed — `embedding_sidecar_index.py:44` `EMBEDDING_INDEX_PATH`), not note frontmatter (MEM-05: "no per-note HTTP read at query time"). Confirmed: `build_embedding_index` (`embedding_sidecar_index.py:126-206`) looks up `existing_index.get(path, ...)` by the CURRENT walked path; a path whose sidecar key is still the pre-move path is treated as brand-new by the next sweep — self-healing (harmless), but it means the note is re-embedded (an HTTP call), which the CONTEXT.md D-04 "no re-embed" framing for direct moves does not anticipate, and there is a window (until the next sweep runs) where the note is absent from `SemanticRecall`'s eligible set entirely under its new path.

**Example:**
```python
# migration_orchestrator.py — ops-bound track (Pattern 2)
from app.services.embedding_sidecar_index import EMBEDDING_INDEX_PATH, decode_index_body, encode_index_body

async def _move_ops_bound(vault, src: str, dst: str, rollback: "RollbackLedger") -> str:
    actual_dst = await vault.relocate(src, dst)  # app/vault.py:631
    raw = await vault.read_note(EMBEDDING_INDEX_PATH)
    index = decode_index_body(raw, EMBEDDING_INDEX_PATH) if raw.strip() else {}
    if src in index:
        index[actual_dst] = index.pop(src)          # rename key, values (embedding_b64 etc) untouched
        await vault.write_note(EMBEDDING_INDEX_PATH, encode_index_body(index, EMBEDDING_INDEX_PATH))
    rollback.record_ops_move(src, actual_dst)  # inverse: relocate(actual_dst, src) + revert sidecar key
    return actual_dst
```

### Pattern 3: The D-03a `:graph` gate only proves the Reduce-path track; ops-bound needs its own scan

**What:** `graph_analysis.build_graph_report` computes orphans/backlinks purely from an in-memory `notes: dict[str, str]` map that `links_sidecar_index.build_links_index` populates by walking **only** `NOTES_ROOT = "notes"` (`app/services/graph_analysis.py:27`, `app/services/links_sidecar_index.py:79` `walk_vault(vault, root=NOTES_ROOT)`). `ops/journal/`, `ops/accomplishments/` are never indexed by this sidecar.

**Consequence for the plan:** running `GET /vault/graph` before and after the ops-bound moves will show **zero change** regardless of whether any wikilink referencing those files actually broke — it is structurally blind to `ops/`. The migration needs its own lightweight pre/post scan for the ops-bound track: use `vault.find(query)` (keyword search — `app/vault.py` `find()`, POST `/search/simple/`) for `"[[<old-title>]]"` per moved ops-bound file, before and after the move, and assert the post-move hit count is unchanged (title-based resolution — see Pattern 4) or explicitly rewrite any hits found.

**When to use:** The ops-bound track's verify-then-trust step (D-03) and its zero-new-orphans backstop (D-03a) must be implemented as this separate scan; do not rely on `:graph`/`:check` for ops-bound verification.

### Pattern 4: Wikilink resolution is filename-stem-based, matching real Obsidian semantics — confirmed by the codebase's own resolver

**What:** `graph_analysis.resolve_wikilink` (`app/services/graph_analysis.py:56-72`) resolves a `[[Target]]` wikilink by **filename stem** (case/space/underscore-normalized), independent of directory — explicitly documented in the module docstring as pinning "research Open Question 2 (filename-stem resolution, not title- or path-based)". This mirrors real Obsidian's own documented `[[wikilink]]` resolution behavior (matches by unique note basename across the vault, not full path) — i.e., the codebase's own resolver is not a guess, it is Sentinel deliberately replicating the same semantics Obsidian itself uses.

**Implication for D-03's step 0 empirical test:** since a same-title move across directories does not change the filename stem, an ops-bound `relocate()` (title/basename unchanged, only directory changes) should NOT break any wikilink that resolves by stem — this is true both for Sentinel's own graph tooling (which only covers `notes/`, per Pattern 3) and, per Obsidian's documented behavior, for Obsidian's native link resolution/backlink pane. **This should still be empirically verified once, live, against the real Obsidian instance** (open the app, move one test note via the REST API, confirm the backlink pane still resolves) before treating it as proven — the codebase resolver's behavior is HIGH confidence, but "does the live Obsidian app's own internal cache behave identically for a REST-driven move (not a UI-driven rename)" is the one thing that must be checked empirically, not assumed, per Pitfall 7's explicit instruction ("must be tested against the real Obsidian instance, not assumed from REST semantics alone").

### Anti-Patterns to Avoid

- **Physically `relocate()`-ing learning/reference files directly into `inbox/foo.md`:** invisible to the orchestrator (Pattern 1). This is the single most likely planning mistake given CONTEXT.md's literal wording ("moved to `inbox/`").
- **Treating `GET /vault/graph`'s unchanged orphan count as proof an ops-bound move was safe:** it is structurally blind to `ops/` (Pattern 3).
- **Relying on the next scheduled sweep to "eventually" fix the embedding sidecar key after an ops-bound `relocate()`:** technically self-healing (Pitfall 3's mechanism), but it silently violates D-04's "no re-embed" framing and leaves a real (if short) window where the moved note is unrecallable via SemanticRecall under its new path (Pattern 2).
- **Re-implementing Reduce/Reflect/Verify logic inside the migration command:** Phase 46's `pipeline_orchestrator.run(mode="pipeline")` already has the exact-right behavior (including the hard-won `9b105f4` fix for Reduce→Reflect→Verify ordering) — call it, do not reimplement it.
- **Treating every `report.verify_failed`/`report.errors` entry from the reused pipeline run as a rollback trigger:** see Open Question 1 — the orchestrator's own graceful degrade (Verify-fail → dead-letter requeue to `inbox/`, per Phase 46 D-02) is a *designed*, non-corrupting outcome, not vault corruption; conflating it with "failure requiring full atomic rollback" would make D-02's rollback essentially untestable (any single bad LLM completion would abort the whole migration).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Frontmatter-preserving file move | A new copy+delete helper | `ObsidianVault.relocate()` (`app/vault.py:631`) | Already handles collision-suffix, protected-namespace guards, provenance frontmatter, delete-failure logging |
| Claim extraction + `_schema` authoring for legacy notes | A parallel "migration Reduce" prompt/parser | `pipeline_orchestrator.run(mode="pipeline")` + `six_rs/reduce.py` | Already schema-validated, already has the `9b105f4` Reduce→Reflect→Verify ordering fix and real-compliance test coverage |
| Wikilink orphan/backlink counting | A new graph walker | `graph_analysis.build_graph_report()` (notes/-scoped) | Pure computation, already tested; only needs a second, ops-bound-specific scan alongside it (Pattern 3) |
| Concurrency guard for the migration run | A new lockfile | `acquire_sweep_lock()`/`release_sweep_lock()` (`app/vault.py:692-720`) | Already shared by sweeper + pipeline (D-04 precedent); reuse as the third mutually-exclusive user of the same lock |
| Admin gating for `:migrate` | A new auth check | `_is_admin_route()` (`app/routes/note.py:126`) | Existing pattern for every destructive vault-mutation route |

**Key insight:** This phase's entire job is composition, not invention — every primitive it needs was built in Phases 44–46 specifically so Phase 47 would not have to build anything new except the rollback ledger and the two integration gaps identified above (Patterns 1 and 2).

## Common Pitfalls

### Pitfall A: Assuming "moved to inbox/" in D-01 means a literal file relocate

**What goes wrong:** A plan that calls `vault.relocate("learning/foo.md", "inbox/foo.md")` for notes-bound content will produce a file the 6 Rs orchestrator never reads, silently defeating MIG-01 (nothing gets backfilled into `notes/`) while looking successful (the file "moved").

**Why it happens:** CONTEXT.md's D-01 phrasing ("moved to `inbox/` (frontmatter preserved), then routed through the 6 Rs Reduce pipeline") reads naturally as a file move, and the general codebase pattern (`relocate()`) reinforces that reading. The orchestrator's actual queue-file contract is a Phase 46 implementation detail not restated in Phase 47's CONTEXT.md.

**How to avoid:** Use Pattern 1 (`inbox.append_entry()` + `pipeline_orchestrator.run()`), never a bare `relocate()` into `inbox/`.

**Warning signs:** A migration test asserts a file exists at `inbox/{name}.md` after migration rather than asserting `notes/{claim-slug}.md` exists and the flat-7 original is gone.

### Pitfall B: Trusting `:graph`'s unchanged count as proof for the ops-bound track

**What goes wrong:** D-03a's "hard gate: pre/post `:graph` dangling-link count diff must show zero new orphans" is read as covering both tracks; a plan ships without any ops-bound-specific check, and a genuinely broken ops-bound backlink (if any existed) ships undetected because `:graph` never looked at `ops/`.

**How to avoid:** Implement Pattern 3's separate scan (via `vault.find()`) for the ops-bound track. Document explicitly in the plan which check covers which track.

### Pitfall C (extends PITFALLS.md Pitfall 3): Embedding sidecar re-embed window on ops-bound moves

**What goes wrong:** Without Pattern 2's sidecar-key patch, every ops-bound moved note is silently re-embedded by the next scheduled sweep (self-healing, but costs N embed calls and creates a recall-blind window until that sweep runs) — contradicting the "no re-embed" framing of D-04.

**How to avoid:** Patch `ops/sweeps/embedding-index.json` (rename the key) in the same transaction as each ops-bound `relocate()` call.

### Pitfall D (from PITFALLS.md Pitfall 2 — verify closure, do not reopen): Carrier-namespace allowlist

**Status check:** Phase 44 already retired `_CARRIER_NAMESPACE_PREFIXES` entirely (D-01 in 44-CONTEXT: "Sessions-only collapse" — recency weighting is Session-summary-only going forward). `recall.py` has no carrier-prefix logic left to go stale. **Phase 47 does not need to touch this** — the D-05 accepted transient in the regression ledger (§3) is exactly about these not-yet-migrated notes losing recency weighting between Phase 44 and Phase 47, and it explicitly self-heals once this phase's migration moves them under `ops/`. The only Phase-47-relevant action is: after migration, verify (or note in the ledger) that these top-level notes are now physically under `ops/` and therefore both warm-excluded and no longer subject to the accepted-transient caveat.

### Pitfall E: Reference directory name mismatch (`reference/` vs `references/`)

**What goes wrong:** `note_classifier.py`'s closed vocabulary uses the topic slug `"reference"` (singular), but `ARCHITECTURE.md`'s documented pre-Phase-44 flat-7 routing table and `ROADMAP.md`'s Phase 47 success criteria both name the physical top-level directory `references/` (plural) — CONTEXT.md's own `<domain>` section, however, says `reference/` (singular). A migration script that assumes the wrong literal directory name will `list_under()` an empty/nonexistent prefix and silently migrate zero notes-bound content while reporting success.

**How to avoid:** At dry-run time, probe **both** `list_under("reference")` and `list_under("references")` (and similarly double-check `accomplishment/` vs `accomplishments/` — the codebase's own `TOPIC_VAULT_PATH` uses `"ops/accomplishments"`, plural) and report actual counts found under each before committing to one. `[ASSUMED]` — I could not verify the live vault's actual top-level directory name via any local tooling (Vault is REST-only, no local mount); this must be resolved empirically at dry-run time, not assumed from either doc.

## Runtime State Inventory

This phase is a rename/migration phase (flat-7 directories → PARA structure) — full inventory below.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | The embedding sidecar (`ops/sweeps/embedding-index.json`, path-keyed) and the links sidecar (`ops/graph/links-index.json`, notes/-scoped, path-keyed) both key on vault-relative path. Any note whose path changes (all ops-bound moves; all Reduce-path notes trivially, since they get a wholly new `notes/{slug}.md` path) needs its sidecar entries reconciled. | **Both:** code edit (Pattern 2 for embedding sidecar) + the links sidecar self-heals automatically on next `:graph`/`:check` call (`rebuild_links_index_if_stale` detects the `notes/` path-set diff and does a full rebuild — no manual patch needed there, only for the embedding sidecar which has no automatic path-migration awareness). |
| Live service config | None found. This project has no external live-config services (no n8n/Datadog/Tailscale-ACL-style config) that reference flat-7 paths by name. Discord command routing (`command_router.py`) references subcommand strings, not vault paths. | None — verified by reading `command_router.py`'s full dispatch list and confirming no path-literal coupling beyond `TOPIC_VAULT_PATH` (already migrated in Phase 44). |
| OS-registered state | None — this is a Docker Compose service with no OS-level task scheduler, launchd plist, or pm2 registration referencing vault paths. | None — verified by reading `docker-compose.yml`/`sentinel-core/compose.yml` structure (no path-embedded service names). |
| Secrets/env vars | `settings.sweep_skip_prefixes`, `settings.protected_namespaces` (env-overridable, `app/config.py`) reference path prefixes, not the flat-7 directories being migrated (`learning/`, `reference(s)/`, `journal/`, `accomplishments/` are not in either list — confirmed via `grep` of `vault.py:58-64` and `vault_sweeper.py:71-80`). | None — no secret/env key needs renaming. |
| Build artifacts | None — no compiled/installed artifact embeds the flat-7 directory names (this is a content migration, not a code/package rename). | None. |

**Canonical question answered:** After every flat-7 note is moved, the only runtime system still holding the OLD path is the embedding sidecar index (until patched per Pattern 2) — everything else (links sidecar, Discord routing, env/secrets, Docker/OS registration) either has no coupling to the old paths or self-heals automatically.

## Code Examples

### Reading & feeding a legacy note through Reduce (Pattern 1, full)

```python
# Source: sentinel-core/app/services/inbox.py:44,133,183-220 and
#         sentinel-core/app/services/pipeline_orchestrator.py:486-534 (verified, this session)
from app.services.inbox import INBOX_PATH, append_entry, parse_inbox
from app.services.note_classifier import ClassificationResult
from app.services.pipeline_orchestrator import run as run_pipeline

async def enqueue_and_reduce(vault, legacy_notes_bound_paths: list[str]) -> "PipelineReport":
    inbox_body = await vault.read_note(INBOX_PATH)
    for path in legacy_notes_bound_paths:
        body = await vault.read_note(path)
        topic = "learning" if path.split("/", 1)[0] == "learning" else "reference"
        result = ClassificationResult(
            topic=topic, confidence=1.0, title_slug="",
            reasoning="Phase 47 backfill migration",
        )
        inbox_body = append_entry(inbox_body, candidate_text=body, result=result)
    await vault.write_note(INBOX_PATH, inbox_body)
    for path in legacy_notes_bound_paths:
        await vault.delete_note(path)
    return await run_pipeline(vault, mode="pipeline")
```

### Ops-bound move with sidecar patch (Pattern 2, full)

```python
# Source: sentinel-core/app/vault.py:631-690, app/services/embedding_sidecar_index.py:44,52
async def move_ops_bound_with_sidecar_fix(vault, src: str, dst: str) -> str:
    actual_dst = await vault.relocate(src, dst)
    raw = await vault.read_note(EMBEDDING_INDEX_PATH)
    index = decode_index_body(raw, EMBEDDING_INDEX_PATH) if raw.strip() else {}
    if src in index:
        index[actual_dst] = index.pop(src)
        await vault.write_note(
            EMBEDDING_INDEX_PATH, encode_index_body(index, EMBEDDING_INDEX_PATH)
        )
    return actual_dst
```

### Pre/post `:graph` orphan diff (D-03a, notes-bound track only)

```python
# Source: sentinel-core/app/routes/graph.py:149-163
graph_pre = await get_vault_graph(request)   # GET /vault/graph, before migration
# ... run notes-bound migration ...
graph_post = await get_vault_graph(request)  # GET /vault/graph, after migration
new_orphans = set(graph_post.orphans) - set(graph_pre.orphans)
if new_orphans:
    raise MigrationAbort(f"D-03a gate failed: {len(new_orphans)} new orphans: {new_orphans}")
```

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The live vault's physical top-level directory for the "reference" topic is named `references/` (plural), matching `ARCHITECTURE.md`/`ROADMAP.md` wording rather than CONTEXT.md's `reference/` (singular) domain text. Could not verify directly — Vault is REST-only, no local mount. | Pitfall E | Migration dry-run silently finds zero notes-bound reference content if the wrong literal is hardcoded; low severity since dry-run report surfaces a zero-count immediately if checked. |
| A2 | Obsidian's live REST-driven move (not UI rename) preserves native backlink-pane resolution identically to Sentinel's own filename-stem resolver, for a same-title cross-directory move. Grounded in the codebase's own `resolve_wikilink` docstring + general Obsidian platform behavior (well-documented, title/basename-based resolution), but not verified this session against the live running Obsidian instance. | Pattern 4 | If wrong, ops-bound moves could silently break real Obsidian-app backlinks even though Sentinel's own tooling (which never sees `ops/` anyway) shows no change. Mitigation: run the one-note empirical test (D-03 step 0) live before trusting verify-then-trust for the full batch. |
| A3 | No local git-tracked mirror or count of the actual number of flat-7 notes exists; scale (how many files under `learning/`, `references/`, `journal/`, `accomplishments/`) is unknown pending a live dry-run `list_under()` call. | Open Questions / Environment Availability | Migration batch-size/timing decisions (single vs. chunked `:pipeline` runs) cannot be finalized until dry-run measures actual counts; plan must treat this as a runtime-measured parameter, not a fixed batch size. |

**If this table is empty:** N/A — see rows above; all three should be confirmed/resolved during dry-run before the live cutover run.

## Open Questions

1. **What exactly triggers "failure → rollback" for the notes-bound (Reduce) track?**
   - What we know: `pipeline_orchestrator.run()` has its own Phase-46-hardened graceful-degrade contract — a per-entry Verify failure is requeued to `inbox/` with a bounded retry count (`_requeue_or_flag`, `pipeline_orchestrator.py:172`) and recorded in `report.errors`/`report.verify_failed`, and the run **completes successfully** (`status="complete"`) even when some entries failed Verify. D-02/D-02a demand atomic rollback "on any failure."
   - What's unclear: whether a non-zero `report.verify_failed`/`report.errors` count from the reused pipeline run should itself trigger a full migration rollback, or whether only a **hard exception** escaping `run()` (lock conflict, unhandled crash) or a failed D-03a graph-orphan gate should trigger rollback — treating Verify-failed/dead-lettered entries as the pipeline's own designed non-corrupting outcome (a note simply stays in `inbox/`, not filed, exactly as Phase 46 intends for a bad LLM completion).
   - Recommendation: treat "failure" narrowly for atomic-rollback purposes — hard exceptions and the D-03a graph-orphan-diff gate — and treat requeued/dead-lettered entries as an accepted partial-success outcome that is reported (not silently) but does not itself unwind already-successful moves. This should be a locked decision in the phase plan (or re-confirmed with the user), since it materially changes what "rollback" tests need to assert.

2. **Exact physical top-level flat-7 directory names** (Pitfall E / Assumption A1) — resolve via a dry-run `list_under()` probe against both singular and plural spellings for `reference(s)/` and `accomplishment(s)/` before writing the migration's path-discovery logic.

3. **Live-Obsidian empirical confirmation of title-based link survival** (Assumption A2 / Pattern 4, per D-03 step 0 and PITFALLS.md Pitfall 7's explicit instruction) — must be run once against the real Obsidian instance (move one test note via REST, observe the Obsidian app's own backlink pane, not just Sentinel's `:graph`) before trusting verify-then-trust for the full ops-bound batch.

4. **Migration batch size for the Reduce track.** Given unknown scale (Assumption A3) and PITFALLS.md Pitfall 9 (local-model latency/context/exo idle-unload risk compounding across many sequential Reduce completions in one `:pipeline` run), the dry-run report should surface the actual notes-bound count so the plan can decide whether a single `:migrate` run's Reduce backfill needs chunking into multiple `:pipeline` invocations rather than one unbounded run.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Obsidian Local REST API | All vault reads/writes/relocates | Not verified live in this research session (REST-only, requires the running Obsidian app + plugin) | `settings.obsidian_api_url` default `http://host.docker.internal:27123` (`app/config.py:58`) | None — migration cannot run without it; the dry-run step itself will surface unreachability immediately (existing `check_health()`/graceful-degrade pattern) |
| pytest (sentinel-core venv) | Full-suite regression gate (MIG-03/04) | ✓ confirmed this session | `.venv/bin/python -m pytest` — 590 tests collected | — |
| pytest (discord venv) | Command-surface regression | ✓ confirmed this session | `.venv/bin/python -m pytest` — 326 tests collected | — |

**Missing dependencies with no fallback:** Obsidian REST reachability at migration run time — no fallback exists (this is the sole persistence seam); the dry-run's first action should be a `check_health()` probe with a clear abort message if unreachable, before any REST mutation is attempted.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (both `sentinel-core` and `interfaces/discord` venvs) |
| Config file | `sentinel-core/pytest.ini` / `interfaces/discord/pytest.ini` (existing) |
| Quick run command | `cd sentinel-core && .venv/bin/python -m pytest tests/test_pipeline_orchestrator.py tests/test_vault_sweeper.py tests/test_graph_analysis.py tests/test_links_sidecar_index.py -q` |
| Full suite command | `cd sentinel-core && .venv/bin/python -m pytest tests/ -q` (590 collected) AND `cd interfaces/discord && .venv/bin/python -m pytest tests/ -q` (326 collected) — per project memory, both venvs must be run; there is no single combined command |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MIG-01 | Every flat-7 note ends up under `notes/` (Reduce) or `ops/` (direct move) with `_schema` + ≥1 wikilink; none grandfathered | integration | `pytest tests/test_migration_orchestrator.py::test_full_backfill_no_grandfathering -x` | ❌ Wave 0 |
| MIG-02 | Embedding sidecar entry survives migration (frontmatter-preserving, sidecar key patched); pre/post `:graph` orphan diff shows zero new orphans (notes/-scoped) + ops-bound backlink-scan diff shows zero new dangling refs | integration | `pytest tests/test_migration_orchestrator.py::test_embedding_and_wikilink_preservation -x` | ❌ Wave 0 |
| MIG-03 | `.planning/v0.6.0-REGRESSION-LEDGER.md` MEM-01..09 rows all still green; ledger has a Phase-47 boundary check-in row appended | artifact + full suite | `grep -q 'MEM-09' .planning/v0.6.0-REGRESSION-LEDGER.md && cd sentinel-core && .venv/bin/python -m pytest tests/ -k "mem0 or recall or recency" -q` | ✅ existing MEM-0x tests; ❌ ledger check-in append is a plan task, not a test |
| MIG-04 | Full sentinel-core (590 collected) + discord (326 collected) suites stay green post-migration; no shrinking test count | automated (full suite) | `cd sentinel-core && .venv/bin/python -m pytest tests/ -q` AND `cd interfaces/discord && .venv/bin/python -m pytest tests/ -q` | ✅ existing |

### Sampling Rate

- **Per task commit:** the quick-run command above (pipeline/sweeper/graph/links-sidecar subset).
- **Per wave merge:** full-suite command (both venvs).
- **Phase gate:** full suite green (both venvs) + regression ledger check-in appended, before `/gsd-verify-work`.

### Wave 0 Gaps

- [ ] `sentinel-core/tests/test_migration_orchestrator.py` — covers MIG-01, MIG-02 (backfill correctness, embedding/wikilink preservation, rollback-on-failure)
- [ ] `sentinel-core/tests/test_migration_rollback_ledger.py` — covers D-02/D-02a (atomic rollback replays the recorded inverse of every op)
- [ ] `sentinel-core/tests/test_migration_routes.py` — covers the new `POST /vault/migrate/start` / `GET /vault/migrate/status` admin-gated route shape (mirrors `test_note_routes.py`'s sweep-route tests)
- [ ] A dedicated ops-bound backlink pre/post scan helper + its test (Pattern 3) — no existing module covers `ops/`-scoped wikilink checking; `graph_analysis`/`links_sidecar_index` are both `notes/`-scoped by design and should NOT be widened (that would violate their documented single-purpose scope) — write a small new scan function instead.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Discord-level auth unchanged; `:migrate` reuses the existing admin-user-id gate |
| V3 Session Management | No | Not applicable — no new session concept |
| V4 Access Control | Yes | `:migrate` MUST be admin-gated identically to `:vault-sweep`/`:pipeline` (`_is_admin_route()`, `app/routes/note.py:126-138`) — this is a destructive, vault-wide mutation |
| V5 Input Validation | Yes | Legacy note bodies read from the vault and fed into `six_rs.reduce.reduce_entry()`'s LLM completion must be treated as **untrusted data**, never instructions (per the project's existing untrusted-input-boundary principle, already enforced for chat messages — PITFALLS.md's Security Mistakes table explicitly extends this to every new pipeline stage) |
| V6 Cryptography | No | No new cryptographic material introduced |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via a migrated note's content (a captured note engineered to manipulate the Reduce/Reflect LLM call) | Tampering | Treat all vault content read into any `six_rs/*` prompt as untrusted data only — already the established pattern in `note_classifier.py`/`six_rs/reduce.py`; migration introduces no new call site that needs a different posture, just more volume through the same, already-hardened path |
| Partial migration leaving the vault in an inconsistent, half-moved state if the process crashes mid-run | Denial of Service / Integrity | D-02's atomic-rollback ledger (record inverse of every REST op, replay on any hard failure) is the direct mitigation — this is the phase's one genuinely new piece of code and should get the most test coverage |
| Sidecar index poisoning (a malformed/mismatched embedding-index key after a partial ops-bound move) | Tampering / Integrity | Pattern 2's sidecar-key patch must be part of the same rollback-tracked transaction as its `relocate()` call, so a rollback restores both the file path AND the sidecar key together, never one without the other |

## Sources

### Primary (HIGH confidence — verified via direct file read this session)
- `sentinel-core/app/vault.py:125-165,273-720` — `Vault` Protocol, `ObsidianVault.relocate()`/`move_to_trash()`/`write_note()`, `PROTECTED_NAMESPACES` (`:58-64`), `acquire_sweep_lock()`/`release_sweep_lock()` (`:692-720`)
- `sentinel-core/app/services/pipeline_orchestrator.py` (full file read) — `run()` entrypoint (`:486-534`), `_run_ralph`/`_run_pipeline` inbox-queue contract (`:283-413`), `start_pipeline()` background wrapper (`:540-577`)
- `sentinel-core/app/services/inbox.py` (full file read) — `INBOX_PATH`, `PendingEntry`, `append_entry()`/`parse_inbox()`/`remove_entry()` (`:44-236`)
- `sentinel-core/app/services/graph_analysis.py` (full file read) — `NOTES_ROOT`, `resolve_wikilink()` (`:56-72`), `build_graph_report()` (`:86-128`)
- `sentinel-core/app/services/links_sidecar_index.py` (full file read) — `LINKS_INDEX_PATH`, `build_links_index()` walking `root=NOTES_ROOT` (`:79`), `rebuild_links_index_if_stale()` path-set-diff staleness (`:140-184`)
- `sentinel-core/app/services/embedding_sidecar_index.py` (full file read) — `EMBEDDING_INDEX_PATH`, path-keyed `build_embedding_index()` (`:126-206`), `eligible_entries()` (`:209-307`)
- `sentinel-core/app/services/vault_sweeper.py:71-97,600-668` — `SWEEP_SKIP_PREFIXES` (`:71-80`, confirms `inbox/` intentionally removed per D-02/VAULT-04), note-frontmatter embedding write-back (`:642-650`) AND sidecar emission (`:666-668`) — confirms embeddings live in BOTH places
- `sentinel-core/app/services/note_classifier.py:36-100` — `TOPIC_VAULT_PATH` current (post-Phase-44) routing table, `topic_dir_for()`
- `sentinel-core/app/routes/graph.py` (full file read) — confirms `/vault/graph`/`/vault/stats`/`/vault/check` derive their notes map from the links sidecar only, no admin gate
- `sentinel-core/app/routes/note.py:126-138` — `_is_admin_route()` admin-gate pattern
- `sentinel-core/app/services/moc_maintenance.py` (symbol list) — `attach_to_hub`/`detach_from_hub`/`add_hub_backlink_to_member` (rollback precedent already used by Phase 46's Verify-fail path)
- `git show 9b105f4` — the Phase 46 Reduce→Reflect→Verify reorder fix; confirms no separate "rollback" primitive exists yet in the codebase (Phase 46's fix is `detach_from_hub` on Verify-fail, not a generic transaction ledger) — Phase 47's atomic-rollback ledger is genuinely new code, not a reuse of an existing rollback mechanism
- `.planning/v0.6.0-REGRESSION-LEDGER.md` (full file read) — exact MEM-0x contract text, full-suite baseline (475 collected at Phase 44 Plan 01), D-05 accepted-transient text, append-only check-in table format
- `.planning/phases/44-vault-namespace-taxonomy-foundation/44-CONTEXT.md`, `.planning/phases/46-6-rs-pipeline-orchestrator/46-CONTEXT.md` (full read) — prior-phase locked decisions this phase builds on
- `cd sentinel-core && .venv/bin/python -m pytest tests/ -q --collect-only` → 590 collected; `cd interfaces/discord && .venv/bin/python -m pytest tests/ -q --collect-only` → 326 collected (both run live this session)

### Secondary (MEDIUM confidence)
- Obsidian's documented `[[wikilink]]` resolution behavior (title/basename-based, cross-directory) — general platform knowledge cross-referenced against the codebase's own `resolve_wikilink` docstring; not independently re-verified against current Obsidian Help docs this session.

### Tertiary (LOW confidence / flagged for validation)
- Physical directory name `references/` vs `reference/` for the live vault (Assumption A1) — could not verify (REST-only, no local mount); flagged for dry-run empirical resolution.

## Metadata

**Confidence breakdown:**
- Standard stack / reuse targets: HIGH — every primitive cited to an exact file:line read this session.
- Architecture (Patterns 1-4, the three corrections in Summary): HIGH — derived directly from reading the actual entrypoint code, not from CONTEXT.md's prose description.
- Pitfalls: HIGH for A-D (grounded in code); MEDIUM for E (directory-name mismatch is inferred from cross-doc comparison, not confirmed against the live vault).

**Research date:** 2026-07-07
**Valid until:** Effectively pinned to the current commit (`9b105f4` and later) — since this phase reuses Phase 44-46 code verbatim, any further changes to `pipeline_orchestrator.py`, `vault.py`, or the sidecar modules before this phase is planned/executed should trigger a re-read of the affected sections.
