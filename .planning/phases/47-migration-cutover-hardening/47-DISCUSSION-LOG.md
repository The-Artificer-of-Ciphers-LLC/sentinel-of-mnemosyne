# Phase 47: Migration Cutover + Hardening - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-06
**Phase:** 47-Migration Cutover + Hardening
**Areas discussed:** Migration path, Safety model, Wikilink integrity, Embedding policy, Reduce-path backlinks

---

## Migration path (how notes-bound content reaches PARA)

| Option | Description | Selected |
|--------|-------------|----------|
| Route through Reduce | Move to inbox/, run 6 Rs Reduce → born-compliant `notes/{claim-slug}.md`. Rewrites content + re-embeds. | ✓ |
| Direct move + staple | Move straight to notes/ preserving frontmatter, staple `_schema` + ensure ≥1 wikilink. Cheap, keeps embeddings, titles unchanged. | |
| Hybrid | Direct-move compliant/ops-bound; Reduce only non-compliant learning/reference. | |

**User's choice:** Route through Reduce (for notes-bound `learning`/`reference`).
**Notes:** Accepts content-rewrite + re-embed cost for born-compliance and consistency with the go-forward pipeline. Ops-bound (journal/accomplishments) is handled by direct in-place move — established in CONTEXT D-01 as the natural other track.

---

## Safety model (the cutover run)

| Option | Description | Selected |
|--------|-------------|----------|
| Dry-run + atomic rollback | Preview pass, then transactional run; on any failure revert all moves. | ✓ |
| Resumable per-note ledger | Per-note idempotent moves recorded in a ledger; re-run resumes. No global rollback. | |
| Dry-run + resumable ledger | Preview + per-note atomic + re-runnable, no transactional rollback. | |

**User's choice:** Dry-run + atomic rollback.
**Notes:** Vault must never be left half-migrated. Accepts that rollback of REST moves is more work to build. Mirrors Phase 46 rollback-on-fail lesson.

---

## Wikilink integrity

| Option | Description | Selected |
|--------|-------------|----------|
| Verify title-based, then trust | Empirically confirm Obsidian resolves `[[links]]` by title; if so and title unchanged, links survive the move. Gate on pre/post `:graph` diff. | ✓ |
| Actively rewrite backlinks | Rewrite every `[[ref]]` to moved notes. Robust to title changes / path-based resolution. | |
| Redirect stubs | Leave stub at old path pointing to new location. | |

**User's choice:** Verify title-based, then trust.
**Notes:** Cleanly covers the ops-bound direct-move track. Surfaced tension: it does NOT cover Reduce-path notes whose titles change → resolved in the follow-up below.

---

## Embedding policy

| Option | Description | Selected |
|--------|-------------|----------|
| Preserve in-place, no re-embed | Frontmatter-preserving move carries `embedding_b64`; nothing re-embeds. | ✓ |
| Embed-on-Reduce | Notes routed through Reduce embed immediately (inbox/ is sweep-skipped). | |
| Preserve + embed-on-Reduce | Direct moves preserve; Reduce-path embeds immediately. | |

**User's choice:** Preserve in-place, no re-embed.
**Notes:** Holds for direct-move (ops) track. Since Reduce rewrites content, those notes inherently re-embed at Reduce time — CONTEXT D-04 records the combined "preserve in-place + embed-on-Reduce" behavior so both tracks are correct.

---

## Reduce-path backlinks (follow-up — tension resolution)

Surfaced tension: routing notes-bound content through Reduce renames the note (new claim title + new path), so "verify title-based, then trust" cannot save inbound `[[old-title]]` links to those notes.

| Option | Description | Selected |
|--------|-------------|----------|
| Rewrite backlinks for Reduce'd notes | Scan vault, rewrite `[[old]]`→`[[new claim title]]` for Reduce-path notes; ops-bound still verify-then-trust. Guarantees zero new orphans. | ✓ |
| Measure first, rewrite only if needed | Count inbound links (may be ~0 since old notes predate wikilinks); rewrite only if nonzero. | |
| Gate-only, abort on orphans | No rewrite code; rely on pre/post `:graph` diff to abort+rollback on new orphans. | |

**User's choice:** Rewrite backlinks for Reduce'd notes.
**Notes:** Correct regardless of how many inbound links exist. Two-track wikilink handling: ops-bound = verify-then-trust; notes-bound (Reduce) = active backlink rewrite. Pre/post `:graph` zero-new-orphans diff remains the hard backstop gate (aborts + rolls back).

## Claude's Discretion

- Migration command name/flags (`:migrate` assumed) and dry-run output format.
- Batch ordering (ops-bound-first suggested to simplify rollback bookkeeping).

## Deferred Ideas

None — final phase of the milestone; discussion stayed within scope.
