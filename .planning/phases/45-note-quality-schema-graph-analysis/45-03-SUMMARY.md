---
phase: 45-note-quality-schema-graph-analysis
plan: 03
subsystem: graph-analysis
tags: [wikilink-graph, orphans, backlinks, link-density, NOTE-03]
dependency-graph:
  requires: [45-01]
  provides: [graph_analysis.NOTES_ROOT, graph_analysis.extract_wikilinks, graph_analysis.resolve_wikilink, graph_analysis.GraphReport, graph_analysis.build_graph_report]
  affects: [45-04-links-sidecar-index, 45-06-graph-routes]
tech-stack:
  added: []
  patterns: [regex-based wikilink extraction (stdlib re, no markdown AST), filename-stem slug matching, dataclass-based report object, module-constant SPOT for shared path prefix]
key-files:
  created:
    - sentinel-core/app/services/graph_analysis.py
    - sentinel-core/tests/test_graph_analysis.py
  modified: []
decisions:
  - "NOTES_ROOT defined exactly once in graph_analysis.py (Pitfall 3 SPOT); no second string literal for the notes prefix anywhere in this module"
  - "resolve_wikilink matches by slugified filename stem (lowercase, spaces/underscores folded to hyphens), not raw string equality — a display-text wikilink target like [[Member One]] must resolve to notes/member-one.md"
  - "build_graph_report excludes self-links from outlinks/backlinks (a note wikilinking itself doesn't count as an external connection) — not explicitly specified in the plan, applied as the natural reading of 'no inbound AND no outbound links'"
metrics:
  duration: ~10 min
  completed: 2026-07-06
status: complete
---

# Phase 45 Plan 03: Wikilink Graph Analysis (graph_analysis.py) Summary

Built `graph_analysis.py`: pure, I/O-free wikilink-graph computation backing `:graph`/`:stats` (NOTE-03, SC-3) — wikilink extraction with alias/heading-anchor stripping, filename-stem link resolution (research Open Question 2), and orphan/backlink/hub-count/link-density computation over an in-memory notes map, honoring D-03b (hub-pending singletons reported as orphans).

## What Was Built

- **`NOTES_ROOT = "notes"`** — the single canonical definition of the flat notes/ prefix (Pitfall 3 SPOT / T-45-DRIFT mitigation). Verified single-definition via both a live pytest regression guard (`test_notes_root_single_definition`) and the plan's grep acceptance criterion.
- **`extract_wikilinks(body) -> set[str]`** — regex-based (`\[\[([^\]|#]+)`) extraction of wikilink targets, stripping the alias segment of `[[Target|Alias]]` and the heading-anchor segment of `[[Target#Heading]]`.
- **`resolve_wikilink(target, note_paths) -> str | None`** — resolves a raw wikilink target to the flat-notes path whose filename stem matches, via a normalizing `_slugify` helper (lowercase, spaces/underscores → hyphens) so a display-text target like `Member One` resolves to `notes/member-one.md`. This is the exact contract the Wave-0 wikilink fixture (`tests/test_p45_invariants.py::test_wikilink_resolves_to_flat_notes_path_by_filename_stem`) imports and pins — it now runs (no longer skipped) and passes.
- **`GraphReport` dataclass** — `note_count`, `orphans`, `backlinks`, `hub_count`, `link_density`.
- **`build_graph_report(notes, hub_paths) -> GraphReport`** — computes resolved outlinks per note, builds the backlinks map, marks a note orphan when it has neither resolved inbound nor outbound edges (D-03b: hub-pending singletons land here, no separate pending state), sets `hub_count` from the passed `hub_paths`, and computes `link_density` as total resolved edges over `note_count` (0.0 guarded for an empty vault). Pure computation — takes an in-memory notes map, performs no vault reads of its own.

## Approach

Followed the plan's two-task TDD structure exactly:

1. **Task 1 (RED → GREEN):** Wrote the full test file (`tests/test_graph_analysis.py`, both tasks' tests) and confirmed RED via `ImportError` (module didn't exist). Committed the failing tests, then implemented `NOTES_ROOT` + `extract_wikilinks` + `resolve_wikilink` only, re-ran the task-scoped verify command (`-k "wikilink or resolve"`, 7/7 passed) and the Wave-0 fixture (now green), then committed.
2. **Task 2 (GREEN):** Added `GraphReport` + `build_graph_report` to the same module, ran the full test file (11/11 passed), then committed.

Both `feat` commits land after the single `test` commit, satisfying the RED→GREEN gate sequence.

## Verification

- `pytest tests/test_graph_analysis.py -q -k "wikilink or resolve"` → 7 passed (Task 1 scope)
- `pytest tests/test_graph_analysis.py -q` → 11 passed (full module)
- `pytest tests/test_graph_analysis.py tests/test_p45_invariants.py -q` → 13 passed, 1 skipped (wikilink fixture now green; moc_maintenance fixture correctly still skips — Plan 45-05 not yet landed)
- `pytest tests/ -q` → **506 passed, 13 skipped** (baseline was 473 passed/12 skipped before this plan; net +33 passed/+1 skipped across 45-01/45-02/45-03, zero regressions, zero new failures)
- `grep -rn 'NOTES_ROOT' app/services/graph_analysis.py | grep -c 'NOTES_ROOT ='` → `1`

## TDD Gate Compliance

Gate sequence confirmed in git log:
1. `test(45-03): add failing tests for graph_analysis wikilink extraction + resolver + GraphReport` (RED)
2. `feat(45-03): add NOTES_ROOT + wikilink extraction + filename-stem resolver` (GREEN, Task 1)
3. `feat(45-03): add GraphReport dataclass + build_graph_report computation` (GREEN, Task 2)

## Deviations from Plan

None — plan executed exactly as written. Both tasks' behavior, acceptance criteria, and verification commands are satisfied without any auto-fix, architectural change, or scope adjustment.

## Threat Flags

None — this plan's only new surface is the pure-computation `graph_analysis.py` module already covered by the plan's own threat model (T-45-DRIFT mitigated via the single-definition guard above; T-45-REGEX accepted as-is, no catastrophic-backtracking pattern introduced).

## Self-Check: PASSED

- FOUND: sentinel-core/app/services/graph_analysis.py
- FOUND: sentinel-core/tests/test_graph_analysis.py
- FOUND commit af6ad7e (test)
- FOUND commit 53192c6 (feat Task 1)
- FOUND commit 99f0890 (feat Task 2)
