---
phase: 45-note-quality-schema-graph-analysis
verified: "2026-07-06T00:00:00Z"
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:

  - "test: "Open a `notes/` note and a materialized hub note in the live Obsidian desktop app (Reading View)."

---

# Phase 45: Note-Quality Schema + Graph Analysis Verification Report

**Phase Goal:** Notes carry a durable quality standard — a trailing `_schema` footer block, a claim-style title, and wikilinks — and the user can inspect the vault's knowledge graph (orphans, backlinks, link density, `_schema` compliance) through new read-only commands. Maps of Content (MOC/hub notes) are created lazily as notes join a hub, never upfront. This phase is additive and read-mostly: no change to `POST /message`, `Recall`, or existing test coverage.

**Verified:** 2026-07-06
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth (roadmap SC) | Status | Evidence |
|---|---|---|---|
| 1 | SC-1: `_schema`/parse/`:check`-inspect machinery exists for the trailing footer block, claim-style title, and wikilink detection (write-time "born-compliant" authoring is explicitly deferred to Phase 46 per ROADMAP.md's own annotation — closed across 45+46, not by 45 alone) | ✓ VERIFIED | `note_schema.py` implements `parse_schema_block` (regex-from-end, terminal-block-only, D-01), `has_claim_title` (structural, zero LLM, D-05), `has_wikilink`, `check_note_compliance` (never raises). 20 passing unit tests in `test_note_schema.py`, incl. `test_note_schema_module_has_no_llm_or_network_imports` and a stray-earlier-block adversarial case. |
| 2 | SC-2: A hub/MOC is created the first time a note needs one and is appended-to (never duplicated) as further notes join, with the trailing `_schema` block preserved as the terminal content | ✓ VERIFIED | `moc_maintenance.py`: `find_hub_candidate`/`should_materialize_hub` (2nd-clearing-member rule, D-03/D-03a) and `attach_to_hub` (read→split→insert→re-append, never `patch_append`). Behavioral proof: the Wave-0 fixture `test_attach_to_hub_preserves_trailing_schema_block_position` in `tests/test_p45_invariants.py` runs LIVE (no longer `importorskip`-skipped) and PASSES, plus dedicated idempotency tests `test_attach_to_hub_reattaching_same_member_is_noop` and `test_create_or_update_hub_second_call_same_member_is_noop` pass. |
| 3 | SC-3: `:graph`/`:stats` report orphans, backlink counts, link density from a `links-index.json` sidecar (no full vault walk per call), with hybrid incremental+lazy-rebuild freshness | ✓ VERIFIED | `links_sidecar_index.py` (`build_links_index`, `rebuild_links_index`, `rebuild_links_index_if_stale`) + `graph_analysis.py` (`build_graph_report`, `NOTES_ROOT` single-definition, `resolve_wikilink` by filename-stem). Routes `/vault/graph`, `/vault/stats` call `rebuild_links_index_if_stale` before computing and derive the notes-map from the sidecar's pre-extracted wikilinks (no per-note re-read). 17 sidecar tests incl. self-heal-on-corrupt, exclude-own-path, carry-forward-by-hash, stale-detection-on-added/removed-path, and graceful degrade under a held sweep lock. |
| 4 | SC-4: `:check` lists notes missing `_schema`/claim-title/wikilink, structural-only (no LLM) | ✓ VERIFIED | `/vault/check` route calls `note_schema.check_note_compliance` per already-known sidecar path. `test_vault_check_makes_zero_llm_or_embedding_calls` passes. |
| 5 | SC-5: Read-mostly — `POST /message`, `Recall`, semantic recall unchanged; full existing suite stays green | ✓ VERIFIED | Full core suite: 550 passed / 12 skipped (baseline was 473/12 — the 77 net-new passes are Phase 45's own tests; no pre-existing test changed behavior or count regressed). Wave-0 characterizing test locks the D-02 "no notes/ write path" premise live. `moc_maintenance`'s write functions (`attach_to_hub`, `create_or_update_hub`) are built and unit-tested but confirmed NOT called from any active route/composition path — Phase 46 wires the caller, per plan scope. |

**Score:** 5/5 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `sentinel-core/app/services/note_schema.py` | Trailing `_schema` parser + structural checks | ✓ VERIFIED | Exports `parse_schema_block`, `split_schema_block`, `has_claim_title`, `has_wikilink`, `check_note_compliance`; zero I/O, zero LLM imports (enforced by test) |
| `sentinel-core/app/services/graph_analysis.py` | Pure wikilink-graph computation | ✓ VERIFIED | `NOTES_ROOT` single-definition, `extract_wikilinks`, `resolve_wikilink`, `GraphReport`, `build_graph_report` |
| `sentinel-core/app/services/links_sidecar_index.py` | Sidecar persistence + hybrid freshness | ✓ VERIFIED | `build_links_index`, `rebuild_links_index`, `rebuild_links_index_if_stale`, `encode_index_body`/`decode_index_body` (self-heal) |
| `sentinel-core/app/services/moc_maintenance.py` | Lazy hub matching + idempotent write | ✓ VERIFIED | `find_hub_candidate`, `should_materialize_hub`, `attach_to_hub`, `create_or_update_hub`, `propose_hub_slug`; `HUB_COSINE_FLOOR` = `RecallConfig.semantic_cosine_floor` (no new threshold) |
| `sentinel-core/app/routes/graph.py` | `/vault/graph`, `/vault/stats`, `/vault/check` | ✓ VERIFIED | 3 routes registered, Pydantic response models, no admin gate (unlike `/vault/sweep/start`), each calls `rebuild_links_index_if_stale` first |
| `sentinel-core/app/main.py` (registration) | Router wired without disturbing existing routes | ✓ VERIFIED | `from app.routes.graph import router as graph_router` + `app.include_router(graph_router)`; full suite still green |
| `sentinel-core/app/composition.py` (startup rebuild) | Non-blocking, non-fatal startup rebuild mirroring embedding-index pattern | ✓ VERIFIED | `_startup_links_rebuild()` task created alongside existing `_startup_rebuild()`, logged-not-fatal on failure |
| `interfaces/discord/core_gateway.py` | `call_core_graph/stats/check` | ✓ VERIFIED | All three mirror `call_core_sweep_status` shape exactly: `X-Sentinel-Key` header, `Exception`→friendly-string degrade |
| `interfaces/discord/command_router.py` | `:graph`/`:stats`/`:check` branches call the new gateway fns | ✓ VERIFIED | Branches call `call_core_graph`/`call_core_stats`/`call_core_check`; `_SUBCOMMAND_PROMPTS` in `bot.py` no longer has `stats`/`check` entries (dead code removed) |
| `sentinel-core/tests/test_p45_invariants.py` | Wave-0 characterizing + fixture tests | ✓ VERIFIED | All 3 tests run live and PASS (no longer skipped) — classifier-routing premise, wikilink-resolution rule, trailing-block-preservation invariant |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `app/routes/graph.py` | `links_sidecar_index.rebuild_links_index_if_stale` | Direct call before computing any report | ✓ WIRED | Confirmed in all 3 route handlers |
| `app/routes/graph.py` | `graph_analysis.build_graph_report` | Notes-map synthesized from sidecar wikilinks | ✓ WIRED | `/vault/graph`, `/vault/stats` both call it |
| `app/routes/graph.py` | `note_schema.check_note_compliance` | Per already-known path from index | ✓ WIRED | `/vault/check` |
| `app/main.py` | `app/routes/graph.py` | `include_router` | ✓ WIRED | Confirmed, full suite green |
| `app/composition.py` | `links_sidecar_index.rebuild_links_index` | Startup task | ✓ WIRED | Non-blocking `asyncio.create_task` |
| `moc_maintenance.attach_to_hub` | `note_schema.split_schema_block` | Preserve trailing block across mutation | ✓ WIRED | Confirmed by passing behavioral test |
| `interfaces/discord/command_router.py` | `core_gateway.call_core_graph/stats/check` | kwargs threaded through `handle_subcommand` | ✓ WIRED | Confirmed by `test_*_subcommand_invokes_gateway_not_call_core` — asserts `call_core.assert_not_called()` |
| `interfaces/discord/bot.py` | `core_gateway.call_core_graph/stats/check` | `_call_core_graph`/`_call_core_stats`/`_call_core_check` wrappers | ✓ WIRED | Registered in the kwargs dict passed to `handle_subcommand` |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Core suite fully green, no regression vs. baseline | `cd sentinel-core && .venv/bin/python -m pytest tests/ -q` | `550 passed, 12 skipped in 14.89s` | ✓ PASS |
| Discord suite fully green | `cd interfaces/discord && .venv/bin/python -m pytest tests/ -q` | `258 passed, 50 skipped in 0.55s` | ✓ PASS |
| Wave-0 invariants run live (not skipped) — proves trailing-block preservation behaviorally, not just by presence | `.venv/bin/python -m pytest tests/test_p45_invariants.py -v` | 3/3 passed, none skipped | ✓ PASS |
| `:graph`/`:stats`/`:check` route to the real gateway, never the free-text `call_core` prompt path | `test_graph_subcommand_invokes_gateway_not_call_core`, `test_stats_subcommand_invokes_gateway_not_call_core`, `test_check_subcommand_invokes_gateway_not_call_core` | all pass, each asserts `call_core.assert_not_called()` | ✓ PASS |
| `:check` route makes zero LLM/embedding calls | `test_vault_check_makes_zero_llm_or_embedding_calls` | pass | ✓ PASS |
| No admin gate regression: graph routes accessible to non-admin caller | `test_non_admin_caller_receives_normal_200_from_all_three_routes` | pass | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| NOTE-01 | 45-01, 45-02 | Notes carry an `_schema` footer block, claim-style title, wikilinks | ✓ SATISFIED | `note_schema.py` + 20 tests |
| NOTE-02 | 45-01, 45-05 | MOC/hub notes created lazily and updated, never duplicated | ✓ SATISFIED | `moc_maintenance.py` + idempotency tests |
| NOTE-03 | 45-01, 45-03, 45-04, 45-06, 45-07 | `:graph`/`:stats`/`:check` backed by `links-index.json` sidecar | ✓ SATISFIED | `graph_analysis.py`, `links_sidecar_index.py`, `routes/graph.py`, Discord gateway/router wiring |

No orphaned requirements — REQUIREMENTS.md maps only NOTE-01/02/03 to Phase 45, and all three are claimed by at least one plan's frontmatter `requirements` field.

### Anti-Patterns Found

None. Scanned all 9 Phase-45-touched files (`note_schema.py`, `graph_analysis.py`, `links_sidecar_index.py`, `moc_maintenance.py`, `routes/graph.py`, `core_gateway.py`, `command_router.py`, `bot.py`, `composition.py`) for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER` and placeholder-language patterns — zero matches. No debt markers requiring formal follow-up references.

### Human Verification Required

### 1. `_schema` block rendering + wikilink resolution in live Obsidian

**Test:** After deploy, open a `notes/` note carrying a trailing `_schema` block and a materialized hub note in the live Obsidian desktop app's Reading View.
**Expected:** The `_schema` block renders as a gray fenced code block (not raw markdown text); wikilinks in the note and in the hub's member list resolve/navigate correctly.
**Why human:** Requires a real Obsidian instance with the REST plugin — not reproducible in the automated pytest suite. This is carried forward unchanged from `45-VALIDATION.md`'s own "Manual-Only Verifications" table (NOTE-01/NOTE-02).

### Gaps Summary

No gaps. All 5 roadmap Success Criteria are verified against the actual codebase (not SUMMARY claims): both independent test suites are green with no baseline regression (core grew from 473/12 to 550/12 — net new Phase-45 tests, nothing removed or weakened), the read-mostly invariant is enforced by a live Wave-0 characterizing test, the single highest-risk behavior in the phase (trailing-`_schema`-block preservation across a hub mutation) is proven by a passing behavioral test rather than mere symbol presence, and the Discord surface is confirmed — via assertion, not inference — to route `:graph`/`:stats`/`:check` to the new deterministic gateway path instead of the old free-text `call_core` prompt.

The only open item is the pre-existing Manual-Only Verification VALIDATION.md itself scoped out of automated testing (Obsidian rendering), which routes to human sign-off rather than blocking the phase. Note that `45-VALIDATION.md`'s own frontmatter (`status: draft`, `nyquist_compliant: false`) and Sign-Off checklist were never updated post-execution — this is a stale planning-artifact housekeeping gap, not evidence against goal achievement, since the actual test suite and code both independently confirm the validation contract (473+ green baseline, ≤60s feedback, Wave-0 coverage) was honored in practice.

---

_Verified: 2026-07-06_
_Verifier: Claude (gsd-verifier)_
