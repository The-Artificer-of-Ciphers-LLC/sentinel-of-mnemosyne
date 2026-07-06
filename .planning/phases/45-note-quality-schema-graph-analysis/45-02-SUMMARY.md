---
phase: 45-note-quality-schema-graph-analysis
plan: 02
subsystem: notes
tags: [note-schema, yaml, regex, tdd, structural-validation]

# Dependency graph
requires:
  - phase: 45-note-quality-schema-graph-analysis
    plan: "01"
    provides: Wave 0 cross-cutting invariant tests establishing the green baseline this plan builds on
provides:
  - "app.services.note_schema.parse_schema_block / split_schema_block — trailing _schema block parser (D-01), the exact seam Plan 45-05's attach_to_hub needs"
  - "app.services.note_schema.has_claim_title / has_wikilink / check_note_compliance — structural, zero-LLM compliance helpers backing :check (SC-1, SC-4)"
affects: [45-05-moc-maintenance, 45-06-graph-routes]

# Tech tracking
tech-stack:
  added: []
  patterns: ["end-anchored (terminal-block) regex parsing, mirroring markdown_frontmatter.py's start-anchored pattern but opposite direction", "non-overlapping multi-block scan + last-match-must-end-at-string-end guard (safer than a single backtracking \\Z-anchored regex)"]

key-files:
  created:
    - sentinel-core/app/services/note_schema.py
    - sentinel-core/tests/test_note_schema.py
  modified: []

key-decisions:
  - "_find_trailing_block_match scans ALL non-overlapping ```_schema blocks via finditer (self-contained, non-greedy fence-to-fence match) and requires the LAST match to end exactly at end-of-(rstripped)-body, rather than using a single \\Z-anchored regex as RESEARCH's code example showed. A naive \\Z-anchored non-greedy pattern backtracks across an earlier same-tag block's own closing fence when a stray block precedes the real one, capturing invalid combined YAML and silently degrading to None instead of returning the terminal block's dict — the multi-match-then-position-check approach avoids this failure mode entirely."
  - "check_note_compliance's has_type field is additive beyond the plan's literal behavior spec (has_schema/has_claim_title/has_wikilink + failures) — included because D-01 says the block carries 'at minimum type + hub keys', and a schema block missing its type key is itself a distinct, useful failure signal for :check."

requirements-completed: [NOTE-01]

coverage:
  - id: D1
    description: "parse_schema_block parses the well-formed terminal ```_schema block into a dict, returns None on absent/malformed/non-dict input, and never lets a stray earlier same-tag block win"
    requirement: "NOTE-01"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_note_schema.py::test_parse_schema_block_returns_dict_for_wellformed_block"
        status: pass
      - kind: unit
        ref: "sentinel-core/tests/test_note_schema.py::test_parse_schema_block_only_terminal_block_wins"
        status: pass
    human_judgment: false
  - id: D2
    description: "split_schema_block round-trips the pre-block body + raw block text, preserving pre-block content byte-for-byte, even with a stray earlier same-tag block present"
    requirement: "NOTE-01"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_note_schema.py::test_split_schema_block_roundtrips_wellformed_block"
        status: pass
      - kind: unit
        ref: "sentinel-core/tests/test_note_schema.py::test_split_schema_block_preserves_pre_block_content_with_stray_earlier_block"
        status: pass
    human_judgment: false
  - id: D3
    description: "has_claim_title/has_wikilink/check_note_compliance are structural-only, deterministic, never raise, and the module is provably free of LLM/httpx imports"
    requirement: "NOTE-01"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_note_schema.py::test_check_note_compliance_never_raises_on_malformed_input"
        status: pass
      - kind: unit
        ref: "sentinel-core/tests/test_note_schema.py::test_note_schema_module_has_no_llm_or_network_imports"
        status: pass

duration: 20min
completed: 2026-07-06
status: complete
---

# Phase 45 Plan 02: Note-Quality Schema Parser Summary

**`note_schema.py` — a pure content-parsing module that reads the trailing fenced `_schema` block from the end of a note body, splits it for safe hub-note mutation, and runs zero-LLM structural checks (claim-title, wikilink presence, per-note compliance) backing `:check`.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2
- **Files modified:** 2 created

## Accomplishments

- `parse_schema_block(body)` parses the terminal ` ```_schema ` fenced block into a dict via `yaml.safe_load` only, returning `None` on absent/malformed/non-dict input and never raising — verified against a stray earlier same-tag block (a prose "example of the format") never winning over the real terminal block.
- `split_schema_block(body)` returns `(pre_block_body, raw_block_text_or_None)`, preserving all pre-block content byte-for-byte so a caller (Plan 45-05's `attach_to_hub`) can mutate the body and re-append the block unchanged — round-trips modulo trailing whitespace.
- `has_claim_title(body, filename_slug)` implements D-05's structural-only claim-title test: H1 exists, normalized text differs from the normalized filename slug, more than one word — zero LLM calls.
- `has_wikilink(body)` and `check_note_compliance(body, filename_slug)` round out the per-note compliance report (`has_schema`/`has_type`/`has_claim_title`/`has_wikilink` + a `failures` list), aggregating all four checks deterministically and catching any internal error as a FAIL entry rather than raising.
- A dedicated test (`test_note_schema_module_has_no_llm_or_network_imports`) walks the module's AST and asserts no `httpx`/`openai`/`litellm`/`aiohttp`/`requests` import exists anywhere in `note_schema.py` — the enforced determinism gate for SC-4/D-05/T-45-DET.

## Task Commits

Each task followed RED → GREEN TDD gates with atomic commits:

1. **Task 1: Trailing `_schema` block parse + split (D-01)**
   - `49e7450` (test) — RED: failing tests against `NotImplementedError` stubs
   - `e9508d4` (feat) — GREEN: `parse_schema_block` + `split_schema_block` implemented
2. **Task 2: Structural claim-title + wikilink + compliance (D-05)**
   - `8f01e59` (test) — RED: failing tests against `NotImplementedError` stubs (no-LLM-import gate passed immediately since the module already imported nothing forbidden)
   - `856626d` (feat) — GREEN: `has_claim_title` + `has_wikilink` + `check_note_compliance` implemented

## TDD Gate Compliance

Both tasks show a clean RED-then-GREEN commit pair in git log order (`test(45-02): ...` immediately followed by `feat(45-02): ...`), confirmed by running each task's `<verify>` command against the RED stub (all failed with `NotImplementedError`) before implementing.

## Files Created/Modified

- `sentinel-core/app/services/note_schema.py` — `parse_schema_block`, `split_schema_block`, `has_claim_title`, `has_wikilink`, `check_note_compliance` + the module-private `_find_trailing_block_match` helper and three compiled regexes (`_SCHEMA_BLOCK_RE`, `_H1_RE`, `_WIKILINK_RE`).
- `sentinel-core/tests/test_note_schema.py` — 20 tests covering both tasks' behaviors, acceptance criteria, and the no-LLM-import determinism gate.

## Decisions Made

- **`_find_trailing_block_match` uses a multi-match-then-position-check strategy, not RESEARCH's literal `\Z`-anchored single-regex code example.** RESEARCH's own Trade-offs paragraph flagged that a naive `\Z`-anchored non-greedy pattern is "slightly more permissive" than needed; tracing through the backtracking behavior confirmed a stray earlier same-tag block would make the `\Z`-anchored pattern's leftmost-match-first semantics span from the FIRST block's opening fence all the way to the LAST block's closing fence, capturing invalid combined content as the "inner YAML" and silently returning `None` instead of the correct terminal-block dict. The implemented approach (`finditer` over a non-\Z-anchored self-contained fence pattern, then require the last match's end index to equal the stripped body's length) finds each block as a separate, non-overlapping match and cannot be fooled this way. This decision is a Rule 1 (auto-fix bug) deviation from the RESEARCH code example, applied before any test was written against it.
- **`check_note_compliance` includes a `has_type` field** beyond the plan's literal `<behavior>` list, because D-01 defines the `_schema` block as carrying "at minimum `type` + hub keys" — a schema block present but missing its `type` key is a distinct, useful failure signal that doesn't change the shape of the aggregate result other functions depend on.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] RESEARCH's literal `\Z`-anchored regex code example would misparse a note containing a stray earlier same-tag fenced block**
- **Found during:** Task 1, before writing the RED tests (anticipated while re-reading Pattern 1's Trade-offs discussion)
- **Issue:** A single `` ```_schema\s*\n(.*?)\n```\s*\Z `` pattern with `re.search` backtracks past an earlier block's own closing fence when a stray same-tag block precedes the real terminal block, capturing everything between the FIRST opening fence and the LAST closing fence as "inner YAML" — which fails to parse as a dict and silently returns `None` instead of the correct terminal block.
- **Fix:** Implemented `_find_trailing_block_match` using `re.finditer` over a non-anchored self-contained fence pattern, then required the last match to end exactly at the end of the (rstripped) body — this finds each fenced block as a separate, non-overlapping match and can never conflate two blocks.
- **Files modified:** `sentinel-core/app/services/note_schema.py`
- **Commit:** `e9508d4`

Or otherwise: no other auto-fixed issues.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Plan 45-05 (`moc_maintenance.py`) can now import `split_schema_block` directly: `pre_body, raw_block = note_schema.split_schema_block(hub_body)` gives the exact seam needed to insert a new member wikilink before the trailing block and re-append it unchanged.
- Plan 45-06 (routes) can call `check_note_compliance(body, filename_slug)` per note to back `:check`'s per-note FAIL/WARN reporting with zero additional LLM/network cost.
- No blockers. Full suite green at 494 passed / 14 skipped (474 baseline from Plan 45-01 + 20 new tests, zero regressions).

---
*Phase: 45-note-quality-schema-graph-analysis*
*Completed: 2026-07-06*

## Self-Check: PASSED

- FOUND: sentinel-core/app/services/note_schema.py
- FOUND: sentinel-core/tests/test_note_schema.py
- FOUND: 49e7450 (Task 1 RED commit)
- FOUND: e9508d4 (Task 1 GREEN commit)
- FOUND: 8f01e59 (Task 2 RED commit)
- FOUND: 856626d (Task 2 GREEN commit)
