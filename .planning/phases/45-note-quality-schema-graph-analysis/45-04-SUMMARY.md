---
phase: 45-note-quality-schema-graph-analysis
plan: 04
subsystem: api
tags: [vault-sidecar, wikilink-graph, obsidian-rest, self-healing-index, asyncio, pytest]

# Dependency graph
requires:
  - phase: 45-02
    provides: note_schema.parse_schema_block (trailing _schema block parser)
  - phase: 45-03
    provides: graph_analysis.NOTES_ROOT + extract_wikilinks (pure wikilink computation)
provides:
  - "links_sidecar_index.py: LINKS_INDEX_PATH, encode/decode_index_body (self-heal), build_links_index (content-hash incremental), rebuild_links_index (unconditional persist), rebuild_links_index_if_stale (D-04a hybrid freshness + lock graceful-degrade)"
  - "composition.py startup wiring: a second non-blocking, non-fatal startup task rebuilds ops/graph/links-index.json on every boot, mirroring the embedding-index startup rebuild"
affects: [45-05-moc-maintenance, 45-06-graph-stats-check-routes]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sidecar index module structurally cloned from embedding_sidecar_index.py: self-healing decode, content-hash carry-forward, non-destructive rebuild, startup wiring shape"
    - "D-04a hybrid freshness: single list_under(NOTES_ROOT) path-set diff vs. full walk+reread, gating when a full rebuild is actually needed"
    - "SweepInProgressError caught at the read-mostly call boundary (rebuild_links_index_if_stale) but propagated at the unconditional-rebuild boundary (rebuild_links_index) — same lock, two different caller contracts"

key-files:
  created:
    - sentinel-core/app/services/links_sidecar_index.py
    - sentinel-core/tests/test_links_sidecar_index.py
  modified:
    - sentinel-core/app/composition.py
    - sentinel-core/tests/test_composition.py

key-decisions:
  - "Tasks 1 and 2 landed in a single commit (9bc2e92) rather than two — rebuild_links_index_if_stale's implementation and tests depend directly on build_links_index existing, so the module was authored as one internally-consistent unit instead of split RED/GREEN per task"
  - "Links index entries store wikilinks as a sorted list (JSON-stable), not a set, since extract_wikilinks returns set[str] and JSON has no set type"
  - "rebuild_links_index_if_stale computes the notes/ path-set via a single vault.list_under(NOTES_ROOT) call (not a full walk) — matches D-04a's explicit 'cheap staleness signal' cost model; a same-path-set body edit is a documented, accepted approximation gap (RESEARCH Pitfall 5), characterized by a test, not fixed"
  - "rebuild_links_index propagates SweepInProgressError to its direct caller (mirrors rebuild_embedding_index's contract); only rebuild_links_index_if_stale catches it and degrades to the existing index (Pitfall 2) — the read-mostly :graph/:stats/:check caller never sees a hard error"

requirements-completed: [NOTE-03]

coverage:
  - id: D1
    description: "links_sidecar_index.py self-heals a corrupt/unparseable sidecar to an empty dict rather than crashing the read path"
    requirement: NOTE-03
    verification:
      - kind: unit
        ref: "tests/test_links_sidecar_index.py#test_decode_index_body_corrupt_content_self_heals_to_empty_dict"
        status: pass
      - kind: unit
        ref: "tests/test_links_sidecar_index.py#test_decode_index_body_non_dict_json_returns_empty_dict"
        status: pass
    human_judgment: false
  - id: D2
    description: "build_links_index walks notes/, indexes wikilinks + _schema per note, excludes its own sidecar path, and carries unchanged notes forward by content hash"
    requirement: NOTE-03
    verification:
      - kind: unit
        ref: "tests/test_links_sidecar_index.py#test_build_links_index_indexes_notes_with_wikilinks_and_schema"
        status: pass
      - kind: unit
        ref: "tests/test_links_sidecar_index.py#test_build_links_index_excludes_own_path"
        status: pass
      - kind: unit
        ref: "tests/test_links_sidecar_index.py#test_build_links_index_carries_forward_unchanged_note_by_hash"
        status: pass
    human_judgment: false
  - id: D3
    description: "rebuild_links_index_if_stale implements D-04a hybrid freshness (path-set diff triggers full rebuild; unchanged path-set returns existing) and degrades gracefully to the existing index when the sweep lock is held, never raising SweepInProgressError to a read-mostly caller"
    requirement: NOTE-03
    verification:
      - kind: unit
        ref: "tests/test_links_sidecar_index.py#test_rebuild_links_index_if_stale_rebuilds_on_added_path"
        status: pass
      - kind: unit
        ref: "tests/test_links_sidecar_index.py#test_rebuild_links_index_if_stale_rebuilds_on_removed_path"
        status: pass
      - kind: unit
        ref: "tests/test_links_sidecar_index.py#test_rebuild_links_index_if_stale_degrades_to_existing_index_when_lock_held"
        status: pass
      - kind: unit
        ref: "tests/test_links_sidecar_index.py#test_rebuild_links_index_if_stale_does_not_detect_body_edit_without_path_change"
        status: pass
    human_judgment: false
  - id: D4
    description: "composition.py schedules a non-blocking, non-fatal links-index startup rebuild mirroring the embedding-index startup path; full 473+ baseline and composition tests stay green"
    requirement: NOTE-03
    verification:
      - kind: unit
        ref: "tests/test_composition.py (33 tests in test_composition.py + test_links_sidecar_index.py combined)"
        status: pass
      - kind: integration
        ref: "pytest tests/ -q -W error::RuntimeWarning (524 passed, 13 skipped, zero warnings)"
        status: pass
    human_judgment: false

# Metrics
duration: 15min
completed: 2026-07-06
status: complete
---

# Phase 45 Plan 04: Links Sidecar Index Summary

**links_sidecar_index.py — a structural clone of embedding_sidecar_index.py persisting ops/graph/links-index.json, with D-04a hybrid freshness (path-set diff, not full walk) and graceful degrade under a held sweep lock, wired into a non-fatal composition.py startup rebuild alongside the existing embedding-index rebuild**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-06T12:43:35-04:00 (after 45-03 completion)
- **Completed:** 2026-07-06T12:58:03-04:00
- **Tasks:** 3
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `links_sidecar_index.py` builds/decodes the wikilink-graph sidecar at `ops/graph/links-index.json`, self-healing to `{}` on any corrupt/unparseable content, mirroring `embedding_sidecar_index.decode_index_body` exactly
- `build_links_index` walks `NOTES_ROOT` ("notes"), defensively excludes its own sidecar path, records each note's content hash + wikilinks (via `graph_analysis.extract_wikilinks`) + parsed `_schema` block (via `note_schema.parse_schema_block`), and carries unchanged notes forward by content-hash comparison without recomputation
- `rebuild_links_index` unconditionally rebuilds and persists the sidecar via `write_note`, piggybacking the existing sweep lock so it never interleaves writes with an in-progress `:vault-sweep`
- `rebuild_links_index_if_stale` implements the D-04a hybrid freshness model: a single `list_under(NOTES_ROOT)` path-set diff against the stored index keys triggers a full rebuild only when notes were added/removed/renamed; a held sweep lock degrades to serving the existing (possibly stale) index instead of raising `SweepInProgressError` to a read-mostly `:graph`/`:stats`/`:check` caller (Pitfall 2)
- `composition.py`'s `initialize_startup` now schedules a second non-blocking startup task that rebuilds the links index on every boot, mirroring the embedding-index startup rebuild's try/except-log-non-fatal + `create_task` + done-callback shape exactly — additive only, embedding-index startup behavior is unchanged

## Task Commits

Tasks 1 and 2 landed together in one commit (see Deviations below for why); Task 3 is separate.

1. **Task 1 + Task 2: encode/decode self-heal, build_links_index, rebuild_links_index, rebuild_links_index_if_stale** - `9bc2e92` (feat)
2. **Task 3: composition.py startup rebuild wiring (+ test-fixture fix for a surfaced RuntimeWarning)** - `d422764` (feat)

**Plan metadata:** (this commit, see below)

## Files Created/Modified
- `sentinel-core/app/services/links_sidecar_index.py` - LINKS_INDEX_PATH, encode/decode_index_body, build_links_index, rebuild_links_index, rebuild_links_index_if_stale
- `sentinel-core/tests/test_links_sidecar_index.py` - 18 tests covering self-heal, own-path exclusion, content-hash carry-forward, path-set staleness, lock graceful-degrade, non-destructiveness
- `sentinel-core/app/composition.py` - added `_startup_links_rebuild` background task alongside the existing `_startup_rebuild` (embedding-index) task in `initialize_startup`
- `sentinel-core/tests/test_composition.py` - configured `read_note` on two `AsyncMock()` vault fixtures and stubbed the new links-index rebuild in two others (see Deviations)

## Decisions Made
- Tasks 1 and 2 authored and committed together (not split into separate RED/GREEN-per-task commits) since `rebuild_links_index_if_stale` and its tests depend directly on `build_links_index` existing — splitting would have produced an artificial intermediate commit with no independent test value
- Wikilinks stored as a sorted list (not the `set[str]` `extract_wikilinks` returns) for JSON round-trip stability
- The notes/ path-set staleness check uses a single `list_under(NOTES_ROOT)` call, not a full walk — matches D-04a's explicit "cheap staleness signal" cost model (RESEARCH Pitfall 5); a body-only edit to an existing note with no path-set change is an accepted, documented approximation gap, characterized by `test_rebuild_links_index_if_stale_does_not_detect_body_edit_without_path_change`
- `rebuild_links_index` propagates `SweepInProgressError` to its direct caller (same contract as `rebuild_embedding_index`); only the `_if_stale` wrapper catches it and degrades — keeping the unconditional-rebuild function's contract honest for any future direct caller

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a latent RuntimeWarning surfaced by adding the second startup background task**
- **Found during:** Task 3 verification (`pytest tests/test_composition.py tests/test_links_sidecar_index.py -q`)
- **Issue:** Adding `links_sidecar_index.rebuild_links_index` as a second concurrent `initialize_startup` background task caused 4 existing `test_composition.py` fixtures (which use a bare, unconfigured `AsyncMock()` as the vault double) to emit `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited`. Root cause, confirmed via isolated repro: an unconfigured `AsyncMock().read_note(...)` returns another `AsyncMock` (not a `str`) by default; the shared `raw and raw.strip()` existing-index-read guard (present in both `_emit_embedding_index`/`rebuild_embedding_index` in `vault_sweeper.py` and this plan's `rebuild_links_index`) then calls `.strip()` on that mock, which — since `AsyncMock.__call__` always returns a coroutine — silently creates and discards a coroutine object. Production `Vault` implementations (`ObsidianVault`/`FakeVault`) always return a real `str` from `read_note`, so this never manifests outside a loosely-typed test double; it was previously latent because no test exercised two concurrent unmonkeypatched background tasks against the same bare mock at once.
- **Fix:** Configured `fake_vault.read_note = AsyncMock(return_value="")` on the two fixtures that exercise the real rebuild path end-to-end (`test_initialize_startup_pins_route_context_and_minimal_state`, `test_initialize_startup_returns_warning_when_vault_unreachable`); stubbed `app.services.links_sidecar_index.rebuild_links_index` with a no-op `AsyncMock(return_value={})` in the two fixtures that already scope themselves to embedding-index-only behavior (`test_initialize_startup_calls_rebuild_embedding_index_not_run_sweep`, `test_initialize_startup_passes_embedding_model_loaded_from_graph`), keeping those tests' assertions unrelated to the new task.
- **Files modified:** `sentinel-core/tests/test_composition.py`
- **Verification:** `pytest tests/test_composition.py tests/test_links_sidecar_index.py -q -W error::RuntimeWarning` → 33 passed, zero warnings-as-errors. Full suite: `pytest tests/ -q -W error::RuntimeWarning` → 524 passed, 13 skipped, zero warnings.
- **Committed in:** `d422764` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - latent test-double bug surfaced by this plan's own change)
**Impact on plan:** Necessary for a genuinely clean test run per project policy (no waived warnings); no scope creep — the fix is confined to test fixtures, not production code, since production Vault implementations were never affected.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `links_sidecar_index.py` exposes the full seam Plan 45-06's routes need: `rebuild_links_index_if_stale(ctx.vault)` is ready to be called from `/vault/graph`/`/vault/stats`/`/vault/check`
- `rebuild_links_index`/`build_links_index` are also directly available for Plan 45-05's `moc_maintenance.attach_to_hub` if it later wants a single-entry incremental patch (not implemented in this plan — out of scope per D-04a's "service-side writer patches directly" clause, which belongs to the writer, not this sidecar module)
- Startup now produces a fresh `ops/graph/links-index.json` on every boot with zero operator action, matching the embedding-index precedent
- No blockers for Plan 45-05 or 45-06

---
*Phase: 45-note-quality-schema-graph-analysis*
*Completed: 2026-07-06*

## Self-Check: PASSED

All created files verified present on disk; all referenced commit hashes (`9bc2e92`, `d422764`, `1e1a700`) verified present in git log.
