---
phase: 34
plan: 05
subsystem: interfaces/discord
tags: [session-notes, discord, bot, recap-view, pf2e]
requirements: [SES-01, SES-02, SES-03]
dependency_graph:
  requires:
    - 34-04: session route registered in sentinel-core (POST /modules/pathfinder/session)
  provides:
    - Discord command surface for :pf session {start,log,end,show,undo}
    - RecapView discord.ui.View with 180s timeout
    - build_session_embed for all session response types
  affects:
    - interfaces/discord/bot.py
    - interfaces/discord/tests/conftest.py
tech_stack:
  added: []
  patterns:
    - RecapView(discord.ui.View) with timeout=180.0, message wiring after send()
    - placeholder->edit slow-query UX for show/end verbs (reuse of Phase 33 pattern)
    - flag token stripping before forwarding to route (T-34-W4-01 threat mitigation)
key_files:
  modified:
    - interfaces/discord/bot.py
    - interfaces/discord/tests/conftest.py
decisions:
  - "D-02: _PF_NOUNS extended to {npc, harvest, rule, session}"
  - "D-04: elif noun == 'session': branch in _pf_dispatch dispatches to modules/pathfinder/session"
  - "D-08: RecapView presents 'Recap last session' button on start when recap_text is present"
  - "D-11: RecapView timeout=180.0 (never None; persistent views require bot-restart re-registration)"
  - "D-20: show and end verbs post placeholder then edit with final embed"
  - "T-34-W4-01: flag tokens stripped from event_text before forwarding; route reads flags from flags: dict"
metrics:
  duration: "~8 minutes"
  completed_date: "2026-04-25"
  tasks_completed: 2
  files_modified: 2
---

# Phase 34 Plan 05: Session Discord Dispatch Summary

**One-liner:** Discord session command surface wired — RecapView + build_session_embed + `_pf_dispatch` session branch; 50/50 bot tests GREEN.

## What Was Built

Plan 34-05 (Wave 4) completes the Phase 34 Discord integration. After this plan the DM can type `:pf session start`, `:pf session log <event>`, `:pf session show`, `:pf session end`, and `:pf session undo` in Discord. All five verbs dispatch through the existing `_pf_dispatch` architecture to `POST /modules/pathfinder/session`.

### Files Modified

**`interfaces/discord/bot.py`**

1. `_PF_NOUNS` extended to `frozenset({"npc", "harvest", "rule", "session"})` (D-02)

2. `RecapView(discord.ui.View)` class added:
   - `timeout=180.0` (never `timeout=None` — persistent views require bot-restart re-registration, PATTERNS.md anti-pattern)
   - `message = None` set to `None` at construction; caller MUST set `view.message = msg` AFTER `await channel.send(..., view=view)` returns (D-11)
   - `recap_button` sends an ephemeral embed with the prior session recap text and clears the button from the message
   - `on_timeout` edits the message to plain text inviting `:pf session start --recap` for deferred recap

3. `build_session_embed(data: dict)` function added before `build_ruling_embed`:
   - Dispatches on `data["type"]`: `start`, `log`, `undo`, `show`, `end`, `end_skeleton`
   - Generic fallback for unknown types
   - Color mapping: `green` (start), `blue` (log/show), `orange` (undo), `dark_green` (end), `red` (end_skeleton/fallback)

4. `elif noun == "session":` branch in `_pf_dispatch`:
   - Parses `--force`, `--recap`, `--retry-recap` flags from `rest`
   - Strips flag tokens from `event_text` before forwarding to route (T-34-W4-01)
   - Sends flag dict separately in `payload["flags"]`
   - Slow-query placeholder for `show` and `end` verbs (D-20)
   - `start` verb with `recap_text` in result: constructs RecapView, sends embed+view, sets `view.message = msg` after send
   - All other verbs: embed-dict return using `build_session_embed`

**`interfaces/discord/tests/conftest.py`**

Extended `_ColorStub` with `Color.green()` and `Color.orange()` classmethods (required by `build_session_embed`; L-5 prevention — added centrally, never per-file).

## Test Results

| Suite | Before | After |
|-------|--------|-------|
| Discord bot tests | 48 passed | 50 passed |
| Session-specific stubs | 2 RED (missing implementation) | 2 GREEN |

Both `test_session_noun_registered` and `test_pf_session_unknown_verb_returns_usage` flipped GREEN.

## Commits

| Hash | Description |
|------|-------------|
| 59bc13c | feat(34-05): session Discord dispatch — _PF_NOUNS, session branch, RecapView, build_session_embed |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing functionality] Color stubs for build_session_embed**
- **Found during:** Task 34-05-01 (implementing build_session_embed)
- **Issue:** `build_session_embed` uses `discord.Color.green()` and `discord.Color.orange()` which were not in conftest.py's `_ColorStub`. Tests would have failed at collection time with AttributeError.
- **Fix:** Added `green()` and `orange()` classmethods to `_ColorStub` in `conftest.py`, following the L-5 prevention pattern established in Phase 33 (centralized, never per-file).
- **Files modified:** `interfaces/discord/tests/conftest.py`
- **Commit:** 59bc13c (included in the same commit)

None other — plan executed as written.

## Phase 34 Status

All 5 plans complete:
- 34-01: Wave 0 RED TDD scaffolding (pytest stubs)
- 34-02: Session route skeleton + Obsidian persistence helpers
- 34-03: LLM recap + generate_story_so_far
- 34-04: FastAPI session router wired to sentinel-core
- 34-05: Discord command surface (this plan)

Full `:pf session` command surface is live. Discord tests 50/50 GREEN.

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns introduced beyond what the plan's `<threat_model>` covered. T-34-W4-01 (flag injection) mitigation is present: flag tokens stripped from `event_text` before forwarding to route; flags forwarded separately in `payload["flags"]`.

## Known Stubs

None — `build_session_embed` renders all response types from real route data. RecapView is fully wired. No hardcoded empty values in the rendering path.

## Self-Check: PASSED

- interfaces/discord/bot.py: FOUND
- .planning/phases/34-session-notes/34-05-SUMMARY.md: FOUND
- commit 59bc13c: FOUND
- RecapView class in bot.py: FOUND
- build_session_embed in bot.py: FOUND
- "session" in _PF_NOUNS: FOUND
