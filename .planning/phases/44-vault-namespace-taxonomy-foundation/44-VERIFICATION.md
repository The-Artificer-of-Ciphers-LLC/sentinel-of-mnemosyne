---
phase: 44-vault-namespace-taxonomy-foundation
verified: 2026-07-06T14:40:33Z
status: passed
score: 5/5 must-haves verified (1 via accepted override)
behavior_unverified: 0
overrides_applied: 1
gaps: []
overrides:
  - must_have: "SC-3 / VAULT-03: Semantic recall's recency weighting still applies correctly under the new namespaces — a carrier-namespace note filed under the new taxonomy is recency-weighted the same way its flat-7 equivalent was, with no silent loss of ranking quality."
    reason: "D-01 (Sessions-only collapse), selected by the user during Phase 44 discuss (44-DISCUSSION-LOG.md § ①): carrier-namespace recency weighting is retired entirely rather than adapted, since journal/accomplishment now file under ops/ (already warm-excluded via RecallConfig.exclude_prefixes) and learning/reference route to inbox/ pending Reduce. Recency weighting is now Session-summary-only (MEM-09 end state). The D-05 transient for not-yet-migrated legacy notes is explicitly accepted and documented in v0.6.0-REGRESSION-LEDGER.md. ROADMAP.md SC-3 wording was amended to match the shipped behavior, mirroring the D-02a precedent that corrected VAULT-04's analogous contradiction during the same discuss session."
    accepted_by: "Tom Boucher"
    accepted_at: "2026-07-06T14:45:36Z"
---

# Phase 44: Vault Namespace + Taxonomy Foundation Verification Report

**Phase Goal:** The vault has the three-space arscontexta structure (`self/ notes/ ops/ inbox/ templates/`) with PARA taxonomy replacing the flat-7 classifier as the routing table. The two silent-regression traps identified in research — `recall.py`'s hardcoded `_CARRIER_NAMESPACE_PREFIXES` allowlist and `vault_sweeper.py`'s `SWEEP_SKIP_PREFIXES` never covering `inbox/` — are fixed in this same phase, not deferred. Build on top of the current post-pi modular architecture; do not revert. Recall, semantic recall, embeddings-through-Sentinel, and Pathfinder must remain fully functional throughout.

**Verified:** 2026-07-06T14:40:33Z
**Status:** passed (SC-3 accepted via override — see frontmatter)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria, verified against source)

| # | Truth (ROADMAP SC) | Status | Evidence |
|---|---|---|---|
| 1 | The vault has `self/`, `notes/`, `ops/`, `inbox/`, `templates/` namespaces, with stub files auto-created wherever they don't already exist | ✓ VERIFIED (with documented caveat) | `self/identity.md`, `self/methodology.md`, `self/goals.md`, `self/relationships.md` are lazily stub-created via `build_self_stub()` + `Recall._ensure_self_stub()` (recall.py:87-142, 718-742), confirmed by passing tests `test_self_stub_creation_on_miss`, `test_self_stub_no_overwrite_when_present`, `test_self_stub_canonical_paths_only`, plus the message-path integration tests `test_first_message_self_heals_missing_self_files` / `test_second_message_does_not_rewrite_existing_self_files` (all re-run individually, all PASS). `templates/` is added to `PROTECTED_NAMESPACES` (vault.py:58-64) and `config.protected_namespaces` (config.py:177-183) — a protection guard, not a content stub, but the namespace is recognized. `ops/` and `inbox/` self-materialize on first `write_note` (Obsidian REST create-if-missing) — no explicit stub needed. **Caveat:** `notes/` is NOT stubbed or created in this phase — 44-CONTEXT.md explicitly places "the Reduce step that promotes `inbox/`→`notes/`" out of scope for Phase 44 ("NOT in scope (later phases)"), a decision recorded during phase-discuss before planning began. Since no writer targets `notes/` until Phase 46 exists, this is a structural sequencing dependency, not an oversight — flagged here for visibility, not scored as a failure. |
| 2 | PARA taxonomy supersedes the flat-7 classifier: `learning`/`reference` route to `inbox/`; `journal`/`accomplishment`/`observation` file under `ops/` subdirectories | ✓ VERIFIED | `note_classifier.py` `TOPIC_VAULT_PATH` confirmed rerouted exactly to the D-03 AFTER table (learning→inbox, reference→inbox, journal→ops/journal, accomplishment→ops/accomplishments, observation→ops/observations, noise→"", unsure→inbox). Both hardcoded `journal/` literal sites (`note_classifier.topic_dir_for`, `note_intake._topic_target_path`) confirmed deriving from the dict's `base` value, not a hardcoded literal (Pitfall 1 closed at both sites — read directly from source). `vault_sweep_plan.is_in_topic_dir` confirmed taxonomy-aware (nested-date `ops/journal/` family special-cased; every other topic dir matches on full path) — Pitfall 2 closed. Individually re-ran `test_topic_dir_for_journal_derives_from_dict`-equivalent coverage and `test_is_in_topic_dir_does_not_conflate_ops_subdirs` — PASS. Closed 7-slug `TopicSlug`/`CLOSED_VOCAB` vocabulary unchanged (routing-only change, D-03a) confirmed in source. |
| 3 | Semantic recall's recency weighting still applies correctly under the new namespaces — a carrier-namespace note filed under the new taxonomy is recency-weighted the same way its flat-7 equivalent was, with no silent loss of ranking quality | ✓ VERIFIED (via accepted override) | ROADMAP SC-3 wording reconciled to the shipped D-01 decision and the deviation accepted via override (accepted_by Tom Boucher, 2026-07-06). See Gaps section below. The implementation deliberately retires carrier-namespace recency weighting entirely (D-01) rather than adapting it to the new taxonomy. This was a reasoned, user-approved decision made during phase-discuss (44-DISCUSSION-LOG.md § ①, "User's choice: A. Sessions-only collapse") and is honestly documented as an accepted, non-silent transient (v0.6.0-REGRESSION-LEDGER.md § 3, D-05) — but it is the literal opposite of what ROADMAP.md's SC-3 text promises, and ROADMAP.md's own SC-3 wording was never reconciled with this decision the way REQUIREMENTS.md's VAULT-04 wording was explicitly corrected (D-02a) for a very similar ROADMAP-vs-implementation contradiction. This is a real, code-verified divergence from the phase's own documented success criterion, not a SUMMARY-claim discrepancy. |
| 4 | Content staged in `inbox/` is no longer wholesale excluded from the vault sweeper — it stops being an unconditional recall blind spot (while remaining excluded from the keyword warm tier until Reduce promotes it) | ✓ VERIFIED | `inbox/` confirmed absent from both `vault_sweeper.SWEEP_SKIP_PREFIXES` (vault_sweeper.py:71-80) and `config.sweep_skip_prefixes` (config.py:137-152) — sweeper walks/embeds it. `inbox/` confirmed present in `RecallConfig.exclude_prefixes` (recall.py:249) — both `KeywordRecall`'s filename filter (recall.py:395) and `SemanticRecall`'s `eligible_entries` (recall.py:565-568) apply `exclude_prefixes`, so embedded `inbox/` vectors stay out of both warm tiers. `test_inbox_gap_not_recalled` and `test_sweep_never_relocates_pending_classification_file` (D-07 control-file guard against corrupting `inbox/_pending-classification.md`) re-run individually — both PASS. |
| 5 | Every message reads the three-space `self/` files (identity, methodology, goals, relationships) at session start, and the full existing test suite plus MEM-01..MEM-09 stay green throughout this phase | ✓ VERIFIED | `Recall._hot_self()` (recall.py:744-765) confirmed reading all 4 canonical `self/` paths via `_ensure_self_stub` on every message (existing `RecallConfig.self_paths` every-message read reused per D-04a, not rebuilt). Full suite independently re-run: **473 passed, 12 skipped, 0 failed** — matches the orchestrator-reported and SUMMARY-claimed count. MEM-01..09 characterization test names confirmed present in `tests/` and passing as part of the full run. |

**Score:** 5/5 truths verified (1 present-and-functioning-but-behaviorally-different-from-spec, tracked as a gap, not as behavior-unverified) (SC-3 satisfied via accepted override + ROADMAP reconciliation)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `sentinel-core/app/services/note_classifier.py` | `TOPIC_VAULT_PATH` rerouted to D-03 AFTER table; `topic_dir_for` journal-derive | ✓ VERIFIED | Confirmed in source (lines 56-95) |
| `sentinel-core/app/services/note_intake.py` | `_topic_target_path` journal-derive; searchable_only redirect retired (D-06) | ✓ VERIFIED | Confirmed in source (lines 36-88, 141-150); `searchable_only` kwarg kept for interface stability but dead — grepped repo-wide, no other consumer branches on it |
| `sentinel-core/app/services/vault_sweep_plan.py` | `is_in_topic_dir` taxonomy-aware family-root fix | ✓ VERIFIED | Confirmed in source (lines 27-49) |
| `sentinel-core/app/services/recall.py` | `_CARRIER_NAMESPACE_PREFIXES` + `_path_date` removed; `_WARM_TIER_EXCLUDE_PREFIXES` removed; `build_self_stub` + stub-ensure wiring | ✓ VERIFIED | All confirmed absent/present as claimed via direct source read and repo-wide grep |
| `sentinel-core/app/services/vault_sweeper.py` | `SWEEP_SKIP_PREFIXES` drops `inbox/`; `_is_inbox_control_file` relocation guard | ✓ VERIFIED | Confirmed in source (lines 71-80, 163-177, 538-541) |
| `sentinel-core/app/config.py` | `sweep_skip_prefixes` drops `inbox/`; `protected_namespaces` gains `templates/` | ✓ VERIFIED | Confirmed in source (lines 137-152, 177-183) |
| `sentinel-core/app/vault.py` | `PROTECTED_NAMESPACES` gains `templates/` | ✓ VERIFIED | Confirmed in source (lines 58-64) |
| `sentinel-core/app/routes/message.py` | `_safe_file_chat_note` "guaranteed searchable" redirect retired | ✓ VERIFIED | Confirmed in source (lines 80-98) — docstring explicitly documents D-06 retirement; no `searchable_only=True` argument passed |
| `.planning/v0.6.0-REGRESSION-LEDGER.md` | MEM-01..09 contract + D-05 accepted transient | ✓ VERIFIED (with minor completeness note) | File exists, names MEM-01..09 and D-05 as required. **Note:** the "Phase Boundary Check-ins" table (§4) has only one row (Phase 44/Plan 01, 2026-07-06); plans 02/03/04 did not append their own check-in rows despite the ledger's stated append-only-per-boundary contract. This is a documentation-completeness gap, not a functional one — the actual full-suite state was independently re-verified green regardless. Low severity; noted for Phase 45+ discipline. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `recall.py` warm-tier exclusion | `RecallConfig.exclude_prefixes` | single-sourced, `inbox/` included | ✓ WIRED | `_WARM_TIER_EXCLUDE_PREFIXES` fully deleted from `recall.py` and its re-export from `message_processing.py`; `test_no_stale_warm_tier_exclude_prefixes_duplicate` re-run — PASS |
| `note_intake.classify_and_apply` | classified destination (no redirect) | direct write, no journal-redirect branch | ✓ WIRED | Confirmed — the redirect branch is physically absent from source, replaced by a comment explaining D-06 |
| `vault_sweeper.run_sweep` | topic-move proposal | `_is_inbox_control_file` guard suppresses relocation of `inbox/_*` control files only | ✓ WIRED | Confirmed at vault_sweeper.py:538-541; `test_sweep_never_relocates_pending_classification_file` re-run — PASS |
| `Recall._hot_self` | `Recall._ensure_self_stub` | four-path allowlist (`_CANONICAL_SELF_STUB_PATHS`), not all of `self_paths` | ✓ WIRED | Confirmed at recall.py:744-765 — `ops/reminders.md` and `self/learning-areas.md` explicitly excluded from the stub-ensure branch |
| `KeywordRecall` / `SemanticRecall.eligible_entries` | `RecallConfig.exclude_prefixes` | both tiers apply the same exclusion set | ✓ WIRED | Confirmed at recall.py:395 and recall.py:565-568 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full suite green | `cd sentinel-core && .venv/bin/python -m pytest tests/ -q --tb=short` | 473 passed, 12 skipped, 0 failed | ✓ PASS |
| PARA reroute + Pitfall 1/2 fixes | `pytest tests/test_note_classifier.py tests/test_vault_sweep_plan.py -k "is_in_topic_dir_does_not_conflate"` | PASS | ✓ PASS |
| Carrier-allowlist removal invariant | `pytest tests/test_recall.py -k test_recency_applies_only_to_session_summaries` | PASS | ✓ PASS |
| Warm-tier exclusion single-source | `pytest tests/test_recall.py -k test_no_stale_warm_tier_exclude_prefixes_duplicate` | PASS | ✓ PASS |
| D-07 control-file relocation guard | `pytest tests/test_vault_sweeper.py -k test_sweep_never_relocates_pending_classification_file` | PASS | ✓ PASS |
| D-06 redirect retirement | `pytest tests/test_message.py -k "test_chat_note_path_passes_warm_tier_exclusion_filter or test_observation_topic_chat_note_redirected_to_searchable_path"` | PASS | ✓ PASS |
| Self-stub creation/idempotency (VAULT-01/05) | `pytest tests/test_message.py -k "test_first_message_self_heals_missing_self_files or test_second_message_does_not_rewrite_existing_self_files"` | PASS | ✓ PASS |
| templates/ protected-namespace guard | `pytest tests/test_obsidian_vault.py -k test_is_protected_path_templates_namespace` | PASS | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| VAULT-01 | 44-02, 44-04 | Three-space structure + stub auto-creation | ✓ SATISFIED (with `notes/` caveat, see SC-1) | self/ stubs + templates/ protection confirmed in source |
| VAULT-02 | 44-01, 44-03 | PARA taxonomy supersedes flat-7 routing | ✓ SATISFIED | TOPIC_VAULT_PATH reroute + D-06 retirement confirmed |
| VAULT-03 | 44-01 | Recency weighting correctness under new namespaces | ✓ SATISFIED (via accepted override) | ROADMAP SC-3 amended to match shipped D-01 behavior; deviation accepted via override. |
| VAULT-04 | 44-02, 44-03 | inbox/ no longer wholesale-skipped by sweeper | ✓ SATISFIED | Confirmed in source + tests |
| VAULT-05 | 44-04 | Every message reads self/ at session start | ✓ SATISFIED | Confirmed in source + tests |

No orphaned requirements — REQUIREMENTS.md maps VAULT-01..05 to Phase 44 exclusively, and every ID is claimed by at least one plan's frontmatter.

### Anti-Patterns Found

None. Grepped all 9 modified/created production files for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER` — zero matches.

### D-06 Retirement Check (explicit ask)

Confirmed **retired, not merely bypassed**: the `searchable_only` redirect branch that used to redirect a warm-tier-excluded destination to a `journal` path is physically removed from `note_intake.classify_and_apply` (source read directly, lines 36-88) and replaced with an explanatory comment. The `searchable_only` parameter remains in the function signature (accepted for interface stability per the plan's own stated intent) but is never referenced in the function body — grepped repo-wide, no caller or downstream logic branches on it. `routes/message.py`'s `_safe_file_chat_note` docstring explicitly documents the retirement rationale and no longer passes `searchable_only=True`. Both `test_message.py` tests that used to assert the old redirect guarantee now assert the real, current classified-destination behavior (individually re-run, both PASS).

### Human Verification Required

None identified — all findings above are code-verifiable and were verified against source, not inferred from SUMMARY claims.

### Gaps Summary

**RESOLVED (accepted override, 2026-07-06):** The gap below was accepted by the user via verification override, and ROADMAP.md SC-3 was amended to match the shipped D-01 behavior. Retained here for the audit trail.

One genuine gap: **SC-3 (VAULT-03)** as literally worded in ROADMAP.md is not satisfied by the implementation. The phase's own locked design decision (D-01, "Sessions-only collapse," selected by the user during phase-discuss per 44-DISCUSSION-LOG.md § ①) deliberately retires carrier-namespace recency weighting entirely rather than adapting it to survive under the new taxonomy. This is a well-reasoned, transparently documented, and consistently executed decision — it is not corner-cutting or an executor's silent deviation — but ROADMAP.md's SC-3 text was never reconciled with it (unlike REQUIREMENTS.md's VAULT-04 wording, which received an explicit correction, D-02a, during the same discuss session for an analogous contradiction). Two closable paths forward:

1. **Accept via override** — add an `overrides:` entry to this VERIFICATION.md's frontmatter (see suggestion below) citing D-01/D-03c and re-run verification, since the deviation is deliberate and already fully documented.
2. **Amend ROADMAP.md** — update Phase 44's SC-3 text to match the actual, shipped behavior ("recency weighting is now Session-summary-only; carrier-namespace notes under the new taxonomy are warm-excluded via `ops/` rather than recency-ranked") so the roadmap contract stops disagreeing with the codebase.

**This looks intentional.** To accept this deviation, add to VERIFICATION.md frontmatter:

```yaml
overrides:
  - must_have: "Semantic recall's recency weighting still applies correctly under the new namespaces — a carrier-namespace note filed under the new taxonomy is recency-weighted the same way its flat-7 equivalent was"
    reason: "D-01 (Sessions-only collapse), selected by the user during Phase 44 discuss (44-DISCUSSION-LOG.md § ①): carrier-namespace recency weighting is retired entirely rather than adapted, since journal/accomplishment now file under ops/ (already warm-excluded) and learning/reference route to inbox/ pending Reduce. Recency weighting is now Session-summary-only (MEM-09 end state). The D-05 transient for not-yet-migrated legacy notes is explicitly accepted and documented in v0.6.0-REGRESSION-LEDGER.md."
    accepted_by: "{your name}"
    accepted_at: "{current ISO timestamp}"
```

All other success criteria, artifacts, key links, and requirements are verified true in the codebase (not merely claimed in SUMMARY.md), and the full test suite is independently confirmed green at 473 passed / 12 skipped / 0 failed.

---

*Verified: 2026-07-06T14:40:33Z*
*Verifier: Claude (gsd-verifier)*
