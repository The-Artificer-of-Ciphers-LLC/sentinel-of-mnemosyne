# Phase 44: Vault Namespace + Taxonomy Foundation - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Restructure the vault to the three-space arscontexta layout (`self/ notes/ ops/ inbox/ templates/`) and replace the flat-7 classifier's **routing table** (not its vocabulary) with PARA destinations. In the *same* phase, fix the two silent-regression traps that a naïve taxonomy move would spring:

- `recall.py:_CARRIER_NAMESPACE_PREFIXES` (Pitfall 2 — recency-weighting allowlist goes stale when paths move)
- `vault_sweeper.py:SWEEP_SKIP_PREFIXES` (Pitfall 3 — `inbox/` becomes a first-class staging area but is never embedded)

**In scope:** namespace creation + stub auto-creation (VAULT-01), PARA reroute of the classifier (VAULT-02), recency-weighting correctness under new namespaces (VAULT-03), inbox/ sweeper/embedding fix (VAULT-04), guaranteed session-start `self/` read (VAULT-05). Full 404+ suite + MEM-01..09 stay green throughout.

**NOT in scope (later phases):** `_schema` footers / claim titles / wikilinks (Phase 45), the 6 Rs pipeline orchestration incl. the Reduce step that promotes `inbox/`→`notes/` (Phase 46), backfill/migration of existing flat-7 notes (Phase 47).

</domain>

<decisions>
## Implementation Decisions

### Carrier-allowlist / recency-weighting (VAULT-03, Pitfall 2)
- **D-01 (Sessions-only collapse):** Retire the `_CARRIER_NAMESPACE_PREFIXES` topic-content allowlist entirely. After migration every path it weighted is gone (learning/reference → `notes/` = authored knowledge with no recency decay per the locked out-of-scope rule; journal/accomplishment → `ops/` = warm-excluded). Recency weighting therefore applies **only to episodic Session summaries** — the pure MEM-09 end state. The warm-tier recency block in `recall.py` (~L795) that starts `if r.path.startswith(_CARRIER_NAMESPACE_PREFIXES)` becomes a no-op and is removed, not repointed to dead paths.
- **D-01a:** Preserve the T-41-08 principle in spirit — recency weighting must never apply to a namespace by omission/negation. With the allowlist gone, the invariant is simply "only typed Session summaries are recency-weighted," asserted by a regression test.

### inbox/ sweeper + embedding (VAULT-04, Pitfall 3)
- **D-02 (Sweeper embeds inbox/, recall keeps it out of the keyword tier):** Remove `inbox/` from `SWEEP_SKIP_PREFIXES` (and from `settings.sweep_skip_prefixes` in `config.py`) so staged captures **do** get embedded — closing the "never embedded" blind spot. Keep `inbox/` in `RecallConfig.exclude_prefixes` so raw, pre-Reduce captures stay out of the keyword warm tier until Reduce promotes them to `notes/`. This closes VAULT-04 inside Phase 44's boundary **without** pulling Phase 46's Reduce path forward. Accepted trade-off: up to one sweep-cycle of latency before a fresh capture is embedded (acceptable — captures are pre-Reduce by definition).
- **D-02a (doc-contradiction resolved):** `REQUIREMENTS.md` VAULT-04 previously read *"the vault sweeper **skips** inbox/"*, directly contradicting ROADMAP SC-4 and PITFALLS Pitfall 3. Resolved in favor of ROADMAP/Pitfalls; **VAULT-04 wording corrected in `REQUIREMENTS.md`** during this discussion so the docs no longer disagree.

### PARA reroute table (VAULT-02)
- **D-03 (Adopt ARCHITECTURE "AFTER" table verbatim):**
  - `learning`, `reference` → `inbox/` (queued; Reduce later produces `notes/{slug}.md`)
  - `journal` → `ops/journal/{YYYY-MM-DD}/`
  - `accomplishment` → `ops/accomplishments/`
  - `observation` → `ops/observations/` (unchanged location, already under ops/)
  - `noise` → `""` (never filed, unchanged)
  - `unsure` → `inbox/_pending-classification.md` (unchanged)
- **D-03a:** The classifier keeps its **closed 7-slug vocabulary** (`learning|accomplishment|journal|reference|observation|noise|unsure`). "PARA" describes the destination *structure*, not a new classifier output. Only `TOPIC_VAULT_PATH` routing changes — no reclassification of the LLM output space.
- **D-03b (single source of truth — kills the Pitfall 2 root cause):** `TOPIC_VAULT_PATH` (or a routing helper derived from it) becomes the **one** module that `recall.py`'s carrier/namespace logic imports, instead of the current duplicated hand-maintained mirror. The allowlist and the classifier can no longer drift apart.
- **D-03c (consequence, intended):** Moving `journal`/`accomplishment` under `ops/` removes them from warm recall entirely (ops/ is in `exclude_prefixes`). This is deliberate and consistent with the ops/=operational model and D-01.

### self/ stubs + session-start read (VAULT-01, VAULT-05)
- **D-04 (Lazy seeded-template stubs, D-14 pattern):** Auto-create `self/identity.md`, `self/methodology.md`, `self/goals.md`, `self/relationships.md` as **minimal guiding stubs** (short header/prompt content, not blank, not prose) on first startup read when missing. Follows the established REST-only lazy-create convention — no eager boot-time vault writes.
- **D-04a (VAULT-05 is ~90% already done):** `RecallConfig.self_paths` (`recall.py:264-269`) already reads identity/methodology/goals/relationships (+learning-areas, +ops/reminders) into **every** message today. The planner should NOT rebuild the self-read. The real delta of VAULT-05 is **guaranteeing the four canonical `self/` files exist** (via D-04 stubs) so the existing read never hits a missing file.

### Migration-window behavior (44→47)
- **D-05 (Accept the transient, document it):** Between Phase 44 and Phase 47, existing top-level `journal/`, `accomplishments/`, `learning/`, `references/` notes are not yet physically migrated. With D-01 removing the allowlist, existing top-level `journal/`/`accomplishments/` notes remain warm-recallable but lose recency weighting immediately. This is **accepted and documented** (it aligns with MEM-09 and self-heals when Phase 47 moves them under `ops/`). It is recorded in the MIG-03 regression ledger as a **known, accepted behavior change — not a silent regression**. No throwaway compat shim is written in Phase 44.

### Claude's Discretion
- Exact home/name of the shared taxonomy module for D-03b (`note_classifier.py` is the natural home; `recall.py` imports from it) — planner's call.
- Exact stub content wording for D-04 — keep it token-bounded since these files are read every message.
- `PROTECTED_NAMESPACES += "templates/"` (ARCHITECTURE Phase A candidate) — include if it doesn't destabilize the suite; low-risk additive guard.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Design / research (the source of truth for this phase)
- `.planning/research/ARCHITECTURE.md` — Phase A build order; the before/after `TOPIC_VAULT_PATH` reroute table; target three-space namespace layout; `PROTECTED_NAMESPACES += templates/` candidate.
- `.planning/research/PITFALLS.md` §Pitfalls 1, 2, 3, 7 — the regression traps this phase must fix (Pitfall 2 = carrier allowlist, Pitfall 3 = inbox/ blind spot, Pitfall 1 = regression-ledger discipline).
- `docs/2nd-brain-original-design/10-CONTEXT-master-spec.md` — D-01 vault structure, D-03 flat-7 taxonomy definitions, D-05 note-quality standard (D-05 is Phase 45 material, read for context only).

### Code to modify (verified locations)
- `sentinel-core/app/services/recall.py` — `_CARRIER_NAMESPACE_PREFIXES` (L67), warm-tier recency block (~L795), `RecallConfig.exclude_prefixes` (L247), `RecallConfig.self_paths` (L264-269).
- `sentinel-core/app/services/vault_sweeper.py` — `SWEEP_SKIP_PREFIXES` (L69), `_active_skip_prefixes()` (L83), `EMBEDDING_INDEX_PATH` sidecar.
- `sentinel-core/app/services/note_classifier.py` — `TOPIC_VAULT_PATH` (L57), `topic_dir_for()` (L68), closed-vocab `TopicSlug` (L41).
- `sentinel-core/app/config.py` — `sweep_skip_prefixes` settings override (L137-152).
- `sentinel-core/app/vault.py` — `PROTECTED_NAMESPACES` (L56).

### Milestone tracking
- `.planning/REQUIREMENTS.md` — VAULT-01..05 (VAULT-04 corrected during this discussion); MIG-03 regression ledger requirement.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `RecallConfig.self_paths` — already performs the VAULT-05 every-message self/ read; reuse, don't rebuild.
- `note_classifier.topic_dir_for()` — single choke point for "where does topic X file"; changing `TOPIC_VAULT_PATH` reroutes both the `:note` filer and the sweeper's relocation logic at once.
- `vault_sweeper._active_skip_prefixes()` — settings-driven denylist with a module-level backstop; both must drop `inbox/` for D-02.
- D-14 lazy-create pattern (REST-only vault) — the established convention for stub creation (D-04).

### Established Patterns
- **Positive-allowlist / no-weight-by-omission** (T-41-08): the invariant to preserve even as D-01 deletes the allowlist — assert "only Session summaries are recency-weighted."
- **ops/ = operational, warm-excluded**: the model that makes D-03c (journal/accompl leaving warm recall) coherent rather than a regression.
- **Dual-maintenance is the Pitfall 2 root cause**: the fix is structural (D-03b single source of truth), not just "update both lists."

### Integration Points
- `recall.py` carrier logic ← imports routing from `note_classifier.py` (new coupling per D-03b).
- Sweeper embedding sidecar (`ops/sweeps/embedding-index.json`) now also indexes `inbox/` content (D-02).
- MIG-03 regression ledger records the D-05 accepted transient.

</code_context>

<specifics>
## Specific Ideas

- The whole phase is a "fix the trap in the same commit that creates the hazard" exercise — the ROADMAP goal explicitly forbids deferring the two trap fixes. Plans must land the namespace/reroute change and its matching allowlist/sweeper fix together, verified by regression tests, never as separate waves that leave a red window.
- Success gate (SC-5): full existing 404+ suite **plus** MEM-01..MEM-09 stay green throughout — treat MEM regression tests as a hard gate at every plan boundary (Pitfall 1 discipline).

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (Reduce-step on-demand embedding, `_schema`/wikilinks, and flat-7 backfill were all considered and correctly routed to Phases 46/45/47 respectively.)

</deferred>

---

*Phase: 44-vault-namespace-taxonomy-foundation*
*Context gathered: 2026-07-06*
