# Phase 45: Note-Quality Schema + Graph Analysis - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-06
**Phase:** 45-Note-Quality Schema + Graph Analysis
**Mode:** advisor (research-backed comparison tables); calibration tier = standard
**Areas discussed:** `_schema` footer format, Enforcement point, Hub/MOC assignment, links-index.json freshness

---

## `_schema` footer format

| Option | Description | Selected |
|--------|-------------|----------|
| Trailing fenced block | ```_schema fenced block at note end, separate from leading provenance frontmatter; parsed by note_schema.py | ✓ |
| YAML frontmatter (merge) | Merge _schema fields into leading frontmatter — collides with provenance writer (anti-pattern) | |
| HTML comment | Invisible block; non-standard, tooling-strip risk | |

**User's choice:** Trailing fenced block (recommended)
**Notes:** Effectively pre-decided by master-spec D-05 + ARCHITECTURE.md. Confirmation, not open ground.

---

## Enforcement point

| Option | Description | Selected |
|--------|-------------|----------|
| Inspect-only via :check | Writes stay as-is; :check reports non-compliant notes; born-compliant deferred to Phase 46 Reduce | ✓ |
| Write-time auto-fill | Validate/auto-fill before persisting — pulls Phase 46 forward; no notes/ write path in P45; breaks read-mostly | |
| Hybrid (auto-fill + report) | Auto-fill mechanical, report judgment — relabels Phase 46's Reduce | |

**User's choice:** Inspect-only (recommended)
**Notes:** Backed by PITFALLS Pitfall 6 ("enforce at Verify, not file-time"). Write-time option would have been scope creep into Phase 46.

---

## Hub / MOC assignment

| Option | Description | Selected |
|--------|-------------|----------|
| Embedding + floor + min-cluster | Nearest hub over cosine floor 0.50; else hub-pending until 2nd note → materialize + back-link; concept-slug names; idempotent read-then-append | ✓ |
| Pure embedding threshold | Nearest over threshold else spawn immediately — first note = permanent one-note hub | |
| PARA/tag-keyed hubs | Hubs map to PARA areas/tags — conflicts with locked flat-notes/ Pattern 3 | |

**User's choice:** Embedding + floor + min-cluster (recommended)
**Follow-up — hub threshold:** Min cluster size = **2**; hub-pending singletons **reported as orphans** (no separate pending state). [Alternatives offered: 3-note bar; separately-tracked pending state.]

---

## links-index.json (location + freshness)

| Option | Description | Selected |
|--------|-------------|----------|
| In-vault + hybrid freshness | ops/graph/links-index.json via REST; incremental on service writes + lazy full-rebuild-if-stale on :graph; piggyback vault_sweeper | ✓ |
| In-vault + lazy-rebuild only | Same location, rebuild only on staleness — weaker signal (no per-note mtime) can serve stale graph | |
| Container-local cache | Cache outside vault — lost on redeploy; violates vault-sole-persistence | |

**User's choice:** In-vault + hybrid freshness (recommended)
**Notes:** Direct in-repo precedent — embedding_sidecar_index.py + vault_sweeper.

---

## Follow-up — :check claim-title validation

| Option | Description | Selected |
|--------|-------------|----------|
| Structural only | H1/title present and not a bare slug; deterministic, no LLM | ✓ |
| Structural + opt-in --deep LLM | Structural default; --deep flag runs LLM claim-quality pass | |
| LLM-judged | Every run uses LLM to rate title quality — cost + nondeterminism | |

**User's choice:** Structural only (recommended) — keeps :check cheap and deterministic.

---

## Claude's Discretion

- Command surface shape (`:graph` / `:stats` / `:check` as distinct commands vs facets) and terminal output formatting.
- Module naming for new graph/hub/links files (follow ARCHITECTURE.md Phase B component table).

## Deferred Ideas

- Born-compliant note writing (auto-fill standard at write) → Phase 46 (6 Rs / Reduce).
- LLM-judged claim-title quality (`:check --deep`) → future enhancement.
- Separate non-orphan "hub-pending" state → deferred in favor of honest orphan reporting.
