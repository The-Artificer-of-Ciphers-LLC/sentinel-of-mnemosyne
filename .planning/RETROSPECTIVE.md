# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v0.6.0 — Restore the Second-Brain Core

**Shipped:** 2026-07-07
**Phases:** 4 | **Plans:** 25 | **Commits:** 141 (+23,881/−536)

### What Was Built
- Three-space arscontexta vault (`self/ notes/ ops/ inbox/ templates/`) with PARA taxonomy superseding the flat-7 classifier, plus fixes for the recall carrier-allowlist and sweeper inbox-skip silent-regression traps (Phase 44)
- Note-quality standard — trailing `_schema` footer blocks, claim-style titles, wikilinks, lazy MOC/hub notes — plus `/vault/graph|stats|check` routes backed by a `links-index.json` sidecar (Phase 45)
- The 6 Rs pipeline (Record → Reduce → Reflect → Reweave → Verify → Rethink) as real background orchestration, cloned from the vault sweeper's shape, wired end-to-end for `:capture`/`:seed`/`:ralph`/`:pipeline`/`:reweave`/`:rethink` with a concurrency guard and explicit outcome reporting (Phase 46)
- Live vault migration cutover — existing flat-7 notes physically backfilled into `ops/` and `notes/` with wikilinks intact, zero grandfathering, zero new orphans, plus admin-gated `/vault/migrate/*` routes and a Discord `:migrate` surface (Phase 47)
- sentinel-core grew to ≈11,576 LOC (Python); both suites finished green (593 passed/12 skipped core, 286 passed/50 skipped discord)

### What Worked
- RED-first Nyquist test scaffolding at the start of every phase (Wave 0 characterizing/fixture-invariant tests) caught classifier-routing and wikilink-resolution regressions before implementation began
- Reusing `pipeline_orchestrator` verbatim for the Phase 47 Track B notes-bound backfill instead of writing a parallel migration-specific orchestrator — the concurrency guard, outcome reporting, and Verify gating from Phase 46 transferred directly
- The dry-run + zero-orphan `:graph` gate caught the live-vault journal date-subdir gap before the Phase 47 live write executed — a destructive migration was proven safe empirically, not just by test-fixture coverage
- Two-track migration split (ops direct-move vs. notes-Reduce-backfill) matched the actual shape of the content: relocation-only for journal/accomplishment/observation, real `_schema`/wikilink authoring for learning/reference

### What Was Inefficient
- The gsd-tools digit-leading-slug directory resolver bug (open-gsd/gsd-core #2043) mis-resolved Phase 46's `46-6-rs-...` directory, forcing manual reconciliation and `--force` flags through the phase
- STATE.md narrative-body label drift ("Current Phase Name" / "Last Activity Description not found") needed hand-reconciliation at each phase-complete boundary; frontmatter progress stayed authoritative but the prose lagged behind
- SC-3 in Phase 44 needed a wording reconciliation against the shipped D-01 "Sessions-only collapse" decision after the fact, rather than being written correctly the first time

### Patterns Established
- Two-track migration: `ops/`-bound content direct-moved with sidecar-key preservation; `notes/`-bound content backfilled via the Reduce stage of the existing pipeline, never a bespoke writer
- Migration rollback ledger + backlink scan as a standing pre/post safety gate for any destructive vault-structure change
- Born-compliant notes via Reduce: `_schema` quality enforcement happens only at Verify, so Reduce always files a note (as draft if imperfect) and never stalls capture
- Sidecar-key preservation on relocate: embedding-index entries survive a move as a frontmatter-preserving relocation, never a delete+recreate

### Key Lessons
1. Inspect the real vault before a destructive cutover — the live journal was date-subdir'd, unlike every test fixture, and only the dry-run + `:graph` gate surfaced that gap in time
2. Never mock the gate in orchestrator tests — the Phase 46 pipeline shipped green in tests but filed zero notes in production because the Verify gate's precondition (a member `[[wikilink]]`) was never exercised end-to-end; live UAT caught what the mocked test suite could not
3. Digit-leading phase-directory slugs (e.g. `46-6-rs-...`) break tooling that assumes alphabetic-first segments — treat this as a standing constraint on phase-slug naming, not a one-off workaround
4. Reusing an existing orchestrator's shape (sweeper → pipeline → migration) compounds — each reuse inherited concurrency guards and outcome reporting for free instead of re-deriving them

---

## Cross-Milestone Trends

Baseline milestone for this retrospective — cross-milestone trend tracking begins with the next milestone.
