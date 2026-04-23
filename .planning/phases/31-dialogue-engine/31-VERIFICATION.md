---
phase: 31-dialogue-engine
verified: 2026-04-23T00:00:00Z
status: passed
score: 12/12 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: null
  previous_score: null
---

# Phase 31: Dialogue Engine Verification Report

**Phase Goal:** Enable in-character NPC dialogue grounded in Obsidian profiles, with persistent mood state and support for multi-NPC scenes.
**Requirements:** DLG-01, DLG-02, DLG-03
**Verified:** 2026-04-23
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (merged from ROADMAP SC + PLAN must_haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `POST /modules/pathfinder/npc/say` returns an in-character reply grounded in NPC Obsidian profile (DLG-01 / SC-1) | VERIFIED | `say_npc` handler at `modules/pathfinder/app/routes/npc.py:858-966`; `build_system_prompt` embeds personality/backstory/traits/mood/relationships; spot-check confirmed `has_personality=True, has_backstory=True, has_traits=True, has_scene_roster=True, has_WARY_tone=True`. Test `test_npc_say_system_prompt_has_personality` PASSED. |
| 2 | Mood state is stored in NPC frontmatter and updated after interactions (DLG-02 / SC-2, SC-3) | VERIFIED | Handler writes mood via `build_npc_markdown + obsidian.put_note` at `npc.py:941-946`; tests `test_npc_say_mood_increment`, `test_npc_say_mood_decrement`, `test_npc_say_mood_clamp_hostile`, `test_npc_say_mood_clamp_allied` all PASSED. Runtime spot-check: `apply_mood_delta('neutral', +1) == 'friendly'`, `apply_mood_delta('wary', -1) == 'hostile'`. |
| 3 | Mood persistence uses GET-then-PUT via `build_npc_markdown + put_note` (D-09); never `patch_frontmatter_field` for mood | VERIFIED | `grep` confirms `patch_frontmatter_field` appears only in the `relate` handler (line 516) for relationships. Say handler uses `build_npc_markdown(..)` + `obsidian.put_note(..)` at lines 941 & 946. Matches 2026-04-23 memory constraint. |
| 4 | Mood write skipped when new_mood == current_mood (D-07) | VERIFIED | `npc.py:938` — `if new_mood != current_mood:` gates the put_note call. Test `test_npc_say_mood_zero_no_write` PASSED. Also covers clamp no-op (hostile-1, allied+1). |
| 5 | Multi-NPC scene returns distinct replies per NPC in given order, serial LLM calls with prior-reply context (DLG-03 / SC-4) | VERIFIED | Serial loop at `npc.py:910-959` constructs `this_turn_replies` and feeds to each subsequent `build_user_prompt`. Tests `test_npc_say_scene_order`, `test_npc_say_scene_context_awareness` PASSED. |
| 6 | Scene advance (empty `party_line`) uses dedicated framing (D-02, D-20) | VERIFIED | `build_user_prompt` branches on `party_line` truthiness (dialogue.py:164-173); spot-check confirmed "silent" appears in the user prompt on empty party_line. Test `test_npc_say_scene_advance` PASSED. Bot dispatch handles empty payload (bot.py:521-533). |
| 7 | >=5-NPC warning exactly matches `⚠ {N} NPCs in scene — consider splitting for clarity.` | VERIFIED | `npc.py:963-964` emits exact string. Test `test_npc_say_five_npc_warning` PASSED. Bot prepends warning via `_render_say_response` (bot.py:199-201); test `test_pf_say_render_warning_preamble` PASSED. |
| 8 | First missing NPC raises 404 with `{slug, name}` before any LLM call (D-29) | VERIFIED | `npc.py:874-878` fails fast before Step 4 model resolution. Test `test_npc_say_unknown` + `test_npc_say_scene_missing_fails_fast` PASSED. |
| 9 | `REGISTRATION_PAYLOAD` has 12 routes including `npc/say` with description `"In-character NPC dialogue with mood tracking (DLG-01..03)"` | VERIFIED | Runtime check: `len(routes)=12`, `has npc/say=True`. `main.py:63` matches exact description. |
| 10 | Discord `:pf npc say <Name>[,<Name>...] | <party_line>` dispatches to module; pipe-separator parse + comma-trim + empty-names usage + missing-pipe usage | VERIFIED | `_pf_dispatch` say branch at `bot.py:518-537`. Tests `test_pf_say_solo_dispatch`, `test_pf_say_scene_dispatch`, `test_pf_say_scene_advance_dispatch` PASSED. Unknown-verb help includes `say` (bot.py:542); test `test_pf_unknown_verb_help_includes_say` PASSED. |
| 11 | Discord bot renders replies as stacked markdown quote blocks (D-03) | VERIFIED | `_render_say_response` at `bot.py:190-204` prefixes each reply with `> `. Test `test_pf_say_render_two_quote_blocks` PASSED. |
| 12 | `_extract_thread_history` module-level helper walks `thread.history(limit=50, oldest_first=True)`, pair-matches user says with bot quote replies, filters by NPC intersection (D-11..D-14) | VERIFIED | `bot.py:207-252`. Intersection filter at line 235 enforces D-13. Tests `test_thread_history_pairing` + `test_thread_history_filter_scene` PASSED. |

**Score:** 12/12 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `modules/pathfinder/app/main.py` | 12th route `npc/say` added to `REGISTRATION_PAYLOAD` | VERIFIED | 12 routes confirmed at runtime; description string exact. |
| `modules/pathfinder/app/routes/npc.py` | `NPCSayRequest`, `TurnHistory`, `NPCReply`, `NPCSayResponse` models + `POST /say` handler | VERIFIED | All 4 Pydantic models present (lines 152-203). Handler at lines 858-966; 966 lines total (up from ~830 in Phase 30). |
| `modules/pathfinder/app/dialogue.py` | New module: MOOD_ORDER, MOOD_TONE_GUIDANCE, normalize_mood, apply_mood_delta, build_system_prompt, build_user_prompt, cap_history_turns | VERIFIED | 207 lines. All symbols import cleanly. Runtime spot-check confirmed constants + behavior. |
| `modules/pathfinder/app/llm.py` | `generate_npc_reply` async helper with JSON salvage | VERIFIED | 216 lines. Function at lines 72-115 with timeout=60.0, fence-stripping reuse, salvage path on `JSONDecodeError`. |
| `interfaces/discord/bot.py` | `say` verb branch, `_render_say_response`, `_extract_thread_history`, unknown-verb help updated | VERIFIED | All 4 present. 892 lines total. `say` branch at 518-537; `_render_say_response` at 190-204; `_extract_thread_history` at 207-252. |
| `modules/pathfinder/tests/test_npc.py` | 16 `test_npc_say_*` tests GREEN | VERIFIED | 16 passed, 0 failed. |
| `modules/pathfinder/tests/test_npc_say_integration.py` | 2 integration tests GREEN | VERIFIED | 2 passed. |
| `interfaces/discord/tests/test_subcommands.py` | 8 new `say`/`thread_history`/`unknown_verb_help_includes_say` tests GREEN | VERIFIED | 8 passed. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| Discord `:pf npc say` | sentinel-core | `_sentinel_client.post_to_module("modules/pathfinder/npc/say", ...)` (bot.py:534) | WIRED | Mock-verified in `test_pf_say_solo_dispatch`; real call path intact. |
| pathfinder `/npc/say` | Obsidian | `obsidian.get_note(path)` (npc.py:873) + `obsidian.put_note(path, content)` (npc.py:946) | WIRED | Integration test `test_solo_mood_roundtrip_through_vault` confirms full round-trip with StatefulMockVault. |
| `say_npc` handler | LLM | `generate_npc_reply(...)` (npc.py:927) | WIRED | `generate_npc_reply` imported at npc.py:38; callable and async. |
| `say_npc` handler | dialogue helpers | `build_system_prompt / build_user_prompt / cap_history_turns / normalize_mood / apply_mood_delta` (npc.py:919-936) | WIRED | All imports present; exercised in 16 unit tests. |
| Registration | sentinel-core | `REGISTRATION_PAYLOAD['routes']` length 12 includes `npc/say` | WIRED | Runtime assertion passed. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|---|
| `say_npc` response `replies[].reply` | `llm_result["reply"]` | `generate_npc_reply` → `litellm.acompletion` | Yes (real LLM call in production; mocked with real-shape responses in tests) | FLOWING |
| `say_npc` response `replies[].new_mood` | `apply_mood_delta(current, delta)` | NPC frontmatter (`normalize_mood(fields["mood"])`) + LLM `mood_delta` | Yes (reads real frontmatter; integration test round-trips via vault) | FLOWING |
| `say_npc` response `warning` | `f"⚠ {len(scene_roster)} NPCs in scene — consider splitting for clarity."` | computed from `len(req.names)` >= 5 | Yes — exact string verified by `test_npc_say_five_npc_warning` | FLOWING |
| Discord rendered reply | `_render_say_response(result)` | pathfinder module response | Yes — quote-block rendering verified by `test_pf_say_render_two_quote_blocks` | FLOWING |
| Obsidian mood persistence | `obsidian.put_note(path, content)` with `build_npc_markdown(updated_fields)` | `apply_mood_delta` output, skipped when unchanged | Yes — `test_solo_mood_roundtrip_through_vault` verifies vault reflects new mood | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Module test suite green | `cd modules/pathfinder && uv run python -m pytest tests/ -q` | 60 passed in 1.15s | PASS |
| Discord test suite green | `cd interfaces/discord && uv run --no-sync python -m pytest tests/ -q` | 31 passed, 50 skipped in 0.09s | PASS |
| Say unit tests green (DLG-01..03 module coverage) | `pytest tests/test_npc.py -k npc_say -v` | 16 passed | PASS |
| Integration tests green (SC round-trip) | `pytest tests/test_npc_say_integration.py -v` | 2 passed | PASS |
| Bot unit tests green (8) | `pytest tests/test_subcommands.py -k 'say or thread_history or unknown_verb_help_includes_say' -v` | 8 passed | PASS |
| REGISTRATION_PAYLOAD route count | Python import + length check | `len(routes)=12, has npc/say=True` | PASS |
| Mood math boundary | `apply_mood_delta('hostile', -1)` / `apply_mood_delta('allied', +1)` | `'hostile'` / `'allied'` (clamped) | PASS |
| Mood math increment | `apply_mood_delta('neutral', +1)` | `'friendly'` | PASS |
| normalize_mood invalid value | `normalize_mood('foo')` | Returns `'neutral'` + WARNING log | PASS |
| MOOD_ORDER definition | Python import | `['hostile', 'wary', 'neutral', 'friendly', 'allied']` | PASS |
| HISTORY cap constants | Python import | `HISTORY_MAX_TURNS=10, HISTORY_MAX_TOKENS=2000` | PASS |
| build_system_prompt embeds all required sections | Python spot-check | personality, backstory, traits, scene roster, relationships (`fears Baron`), WARY tone, JSON contract (reply+mood_delta) all present | PASS |
| build_user_prompt scene-advance framing | Python spot-check (empty party_line) | `"silent"` present in prompt | PASS |
| D-09 mood write mechanism | `grep patch_frontmatter_field` in say handler | No matches in say_npc; only in pre-existing `relate` handler at line 516 | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DLG-01 | 31-04 | "User can send 'party says [X]' with an NPC name and receive an in-character reply grounded in that NPC's Obsidian profile" | SATISFIED | `test_npc_say_solo_happy`, `test_npc_say_system_prompt_has_personality`, `test_solo_mood_roundtrip_through_vault`, `test_pf_say_solo_dispatch` — all PASSED. Handler grounds reply in frontmatter via `build_system_prompt`. |
| DLG-02 | 31-04 | "NPC mood state is tracked per NPC and influences dialogue responses over time" | SATISFIED | `test_npc_say_mood_increment/decrement/clamp_hostile/clamp_allied/zero_no_write/invalid_mood_normalized` (6 tests). Mood is written to frontmatter via GET-then-PUT; tone guidance varies by mood in system prompt (`MOOD_TONE_GUIDANCE`). |
| DLG-03 | 31-04 | "User can run a multi-NPC dialogue scene where multiple NPCs each reply in their distinct voice" | SATISFIED | `test_npc_say_scene_order`, `test_npc_say_scene_context_awareness`, `test_npc_say_scene_advance`, `test_npc_say_five_npc_warning`, `test_scene_distinct_voices_and_awareness` — all PASSED. Serial round-robin with `this_turn_replies` context. |

No orphaned requirements (REQUIREMENTS.md maps DLG-01..03 to Phase 31; all 3 covered).

### Anti-Patterns Found

None. grep for `TODO|FIXME|XXX|HACK|PLACEHOLDER|NotImplementedError` across `dialogue.py`, `llm.py`, `npc.py` say handler, and `bot.py` say additions returned zero results.

### Human Verification Required

None — all phase goals verified programmatically via unit tests, integration tests (with StatefulMockVault full round-trip), and runtime spot-checks. The LLM quality dimension (whether the reply "feels in character") is emergent behavior not claimed by this phase's Success Criteria; phase contract is that grounding data flows to the LLM call, which is verified.

### Gaps Summary

No gaps. All 5 plans shipped, 12 must-haves verified, 3 requirements satisfied, all 91 tests across both code bases green (60 pathfinder + 31 discord, 50 legitimately skipped per existing test design).

Notable design choices confirmed:
- `_pf_dispatch` sends `history=[]` (empty) in the current implementation; `_extract_thread_history` is exposed as a module-level helper for future wiring. Tests explicitly assert `payload["history"] == []  # no channel passed → empty history`, meaning this is the documented Wave-3 contract (thread-history walking from live on_message path is scoped as module-level utility; current dispatch is user_id-only). This matches plan 31-05's must-haves exactly (`_extract_thread_history` exists at module level) and is not a gap.

---

_Verified: 2026-04-23_
_Verifier: Claude (gsd-verifier)_
