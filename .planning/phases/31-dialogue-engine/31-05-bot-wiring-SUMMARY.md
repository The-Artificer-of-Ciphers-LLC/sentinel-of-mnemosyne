---
phase: 31-dialogue-engine
plan: 05
subsystem: discord-interface
tags: [discord, dialogue, npc, regex, thread-history]

requires:
  - phase: 31-dialogue-engine
    provides: [31-01 RED test stubs, 31-04 POST /npc/say route]

provides:
  - ":pf npc say <Name>[,<Name>...] | <party_line>` dispatch branch"
  - "Pipe-separator parsing with empty-payload scene-advance support (D-01, D-02)"
  - "Stacked markdown quote-block rendering with warning preamble (D-03, D-18)"
  - "_extract_thread_history: user-bot pair-matching with scene-membership filter (D-13)"
  - "Unknown-verb help and top-level usage line include `say`"

affects: [future dialogue phases, v0.5 Foundry VTT ingest (Phase 35), session notes (Phase 34)]

tech-stack:
  added: []
  patterns:
    - "regex-based thread-history walker with duck-typed thread interface"
    - "consistent pipe-delimited verb grammar across :pf npc verbs"

key-files:
  created: []
  modified:
    - "interfaces/discord/bot.py"

key-decisions:
  - "Filter on explicit bot_user_id (not generic .author.bot) to avoid cross-bot pollution"
  - "History payload defaults to empty list in _pf_dispatch — thread walking is an on_message concern, not dispatch"

patterns-established:
  - "Module-level helpers (_render_say_response, _extract_thread_history) instead of nested closures — testable in isolation"
  - "Pre-LLM validation short-circuit: missing pipe OR empty names list returns usage string without calling post_to_module"

requirements-completed: [DLG-01, DLG-02, DLG-03]

duration: 8min
completed: 2026-04-23
---

# Plan 31-05: Bot Wiring Summary

**`:pf npc say` Discord dispatch with stacked quote-block render and thread-history pair-matching, closing the 26-test Dialogue Engine RED→GREEN loop**

## Performance

- **Duration:** ~8 min (including orchestrator finish-in-place after partial executor handoff)
- **Completed:** 2026-04-23
- **Tasks:** 2 (+1 SUMMARY)
- **Files modified:** 1

## Accomplishments

- `say` branch in `_pf_dispatch` posts to `modules/pathfinder/npc/say` with names/party_line/user_id/history payload
- Pipe-separator parse with comma-split and trim; scene-advance empty-payload branch preserved (D-02)
- Missing pipe OR empty names short-circuits to usage string — `post_to_module` never invoked (fail-fast)
- `_render_say_response` renders each reply as a `> ` markdown quote block, with optional warning preamble + blank-line separator
- `_extract_thread_history` walks `thread.history(limit=50, oldest_first=True)`, pair-matches user `:pf npc say` messages with the next bot quote-block reply, filters turns by current-scene NPC overlap (D-13)
- Unknown-verb help and top-level usage string both include `say`
- All 8 bot-layer RED stubs (test_pf_say_*, test_thread_history_*, test_pf_unknown_verb_help_includes_say) → GREEN
- 23 pre-existing discord tests still pass (50 skipped unchanged) — no regressions

## Task Commits

1. **Task 31-05-01: helpers** — `25b9d43` (feat)
2. **Task 31-05-02: dispatch + usage + help** — `e4fc11e` (feat)

## Files Created/Modified

- `interfaces/discord/bot.py` — added `import re`, `_SAY_PATTERN`, `_QUOTE_PATTERN`, `_render_say_response`, `_extract_thread_history`, `say` branch in `_pf_dispatch`, updated top-level usage + Available list

## Decisions Made

- Filter thread-history turns by `bot_user_id` match (not generic `.author.bot`) — prevents picking up replies from co-existing bots in shared channels (Pitfall 3 from 31-PATTERNS.md).
- Kept `history=[]` in dispatch payload. Thread walking belongs to `on_message` (future wiring) and would otherwise require plumbing a channel reference through every verb. Tests validate `_extract_thread_history` directly.

## Deviations from Plan

**Orchestrator resumed executor work mid-plan.** The initial `gsd-executor` agent returned after only 22 tool uses with no commits — it had written the helper functions to `bot.py` in its worktree but never staged/committed or added the dispatch branch. Rather than spawn a second executor (which would have re-read all context files), the orchestrator finished the plan inline on main using the partial work as a reference.

**Ruff formatter quirk (Rule 3 — auto-adapted).** Ruff's PostToolUse hook strips unused imports between atomic Edits. The first Edit added `import re`, but the formatter removed it before the second Edit (which introduced the first `re.compile` usage). Re-added `import re` after test failures revealed the strip, and it persisted once the compile calls existed in the same file-state as the import. This matches the pattern 31-02's SUMMARY flagged. No functional impact.

**Total deviations:** 1 executor-handoff (benign — same final code, merged on main rather than via worktree), 1 formatter quirk (auto-fixed).

## Issues Encountered

- Partial executor handoff (described above). Clean recovery.
- `uv sync` in `interfaces/discord` fails on `setuptools.backends` during fresh builds — pre-existing environment issue, unrelated to this plan. Test runs use `uv run --no-sync` to bypass.

## Next Phase Readiness

- DLG-01, DLG-02, DLG-03 fully implemented across module + interface layers. All 26 Wave 0 RED stubs are now GREEN.
- Phase 31 verification gate next. No blockers.
- Future: `on_message` integration can now call `_extract_thread_history` to populate the `history` payload on multi-turn dialogue — a pure extension, no API changes needed.

---
*Phase: 31-dialogue-engine*
*Completed: 2026-04-23*
