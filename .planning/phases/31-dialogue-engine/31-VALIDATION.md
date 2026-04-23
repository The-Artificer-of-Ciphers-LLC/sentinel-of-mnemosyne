---
phase: 31
slug: dialogue-engine
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-23
---

# Phase 31 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from §"Validation Architecture (Nyquist Dimension 8)" in 31-RESEARCH.md.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`asyncio_mode = "auto"`) |
| **Config file** | `modules/pathfinder/pyproject.toml`, `interfaces/discord/pyproject.toml` |
| **Quick run command** | `cd modules/pathfinder && python -m pytest tests/test_npc.py -x -q` |
| **Full suite command** | `cd modules/pathfinder && python -m pytest tests/ -q && cd ../../interfaces/discord && python -m pytest tests/ -q` |
| **Integration test command** | `cd modules/pathfinder && python -m pytest tests/test_npc_say_integration.py -x -q` |
| **Estimated runtime** | ~45 seconds (full) / ~5 seconds (quick) |

---

## Sampling Rate

- **After every task commit:** Run `cd modules/pathfinder && python -m pytest tests/test_npc.py -x -q`
- **After every plan wave:** Run `cd modules/pathfinder && python -m pytest tests/ -q && cd ../../interfaces/discord && python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite green + `tests/test_npc_say_integration.py` green
- **Max feedback latency:** 45 seconds

---

## Per-Task Verification Map

> Task IDs are assigned during planning. Rows below enumerate every test the plans must produce, mapped to requirement and expected test type. Planner fills `Task ID`, `Plan`, and `Wave` columns based on PLAN.md frontmatter.

### Module-layer tests (`modules/pathfinder/tests/test_npc.py` extensions)

| Test Name | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command |
|-----------|-------------|------------|-----------------|-----------|-------------------|
| `test_npc_say_solo_happy` | DLG-01 | — | N/A | unit | `cd modules/pathfinder && python -m pytest tests/test_npc.py::test_npc_say_solo_happy -x` |
| `test_npc_say_unknown` | DLG-01 | T-31-SEC-01 (path traversal via name) | `_validate_npc_name` rejects control chars; 404 on missing slug | unit | `pytest modules/pathfinder/tests/test_npc.py::test_npc_say_unknown -x` |
| `test_npc_say_system_prompt_has_personality` | DLG-01 | — | Personality substring present in system prompt arg | unit (spy) | `pytest modules/pathfinder/tests/test_npc.py::test_npc_say_system_prompt_has_personality -x` |
| `test_npc_say_mood_increment` | DLG-02 | — | `put_note` called with YAML `mood: friendly` when delta=+1 from neutral | unit | `pytest modules/pathfinder/tests/test_npc.py::test_npc_say_mood_increment -x` |
| `test_npc_say_mood_decrement` | DLG-02 | — | `mood: hostile` when delta=-1 from wary | unit | `pytest modules/pathfinder/tests/test_npc.py::test_npc_say_mood_decrement -x` |
| `test_npc_say_mood_zero_no_write` | DLG-02 | — | `put_note` NOT called when delta=0 | unit | `pytest modules/pathfinder/tests/test_npc.py::test_npc_say_mood_zero_no_write -x` |
| `test_npc_say_mood_clamp_hostile` | DLG-02 | — | delta=-1 from hostile ⇒ no vault write (no-op) | unit | `pytest modules/pathfinder/tests/test_npc.py::test_npc_say_mood_clamp_hostile -x` |
| `test_npc_say_mood_clamp_allied` | DLG-02 | — | delta=+1 from allied ⇒ no vault write | unit | `pytest modules/pathfinder/tests/test_npc.py::test_npc_say_mood_clamp_allied -x` |
| `test_npc_say_invalid_mood_normalized` | DLG-02 | T-31-SEC-02 (mood poisoning) | Invalid stored mood treated as neutral; warning emitted | unit | `pytest modules/pathfinder/tests/test_npc.py::test_npc_say_invalid_mood_normalized -x` |
| `test_npc_say_scene_order` | DLG-03 | — | Response order matches request order | unit | `pytest modules/pathfinder/tests/test_npc.py::test_npc_say_scene_order -x` |
| `test_npc_say_scene_context_awareness` | DLG-03 | — | Second NPC's user_prompt contains first NPC's reply text | unit (spy) | `pytest modules/pathfinder/tests/test_npc.py::test_npc_say_scene_context_awareness -x` |
| `test_npc_say_scene_advance` | DLG-03 | — | Empty party_line ⇒ "party is silent" framing in user prompt | unit (spy) | `pytest modules/pathfinder/tests/test_npc.py::test_npc_say_scene_advance -x` |
| `test_npc_say_five_npc_warning` | DLG-03 | — | `warning` field set when ≥5 NPCs | unit | `pytest modules/pathfinder/tests/test_npc.py::test_npc_say_five_npc_warning -x` |
| `test_npc_say_scene_missing_fails_fast` | DLG-03 | — | First missing NPC ⇒ 404; no LLM calls made | unit | `pytest modules/pathfinder/tests/test_npc.py::test_npc_say_scene_missing_fails_fast -x` |
| `test_npc_say_json_parse_salvage` | DLG-01/02 | T-31-SEC-03 (prompt injection via party_line) | Malformed JSON ⇒ reply salvaged, mood_delta=0, logged | unit | `pytest modules/pathfinder/tests/test_npc.py::test_npc_say_json_parse_salvage -x` |
| `test_npc_say_party_line_too_long` | DLG-01 | T-31-SEC-04 (token-budget DoS) | party_line >2000 chars ⇒ 422 | unit | `pytest modules/pathfinder/tests/test_npc.py::test_npc_say_party_line_too_long -x` |

### Bot-layer tests (`interfaces/discord/tests/test_subcommands.py` extensions)

| Test Name | Requirement | Secure Behavior | Test Type | Automated Command |
|-----------|-------------|-----------------|-----------|-------------------|
| `test_pf_say_solo_dispatch` | DLG-01 | Correct payload to sentinel-core | unit | `pytest interfaces/discord/tests/test_subcommands.py::test_pf_say_solo_dispatch -x` |
| `test_pf_say_scene_dispatch` | DLG-03 | `names == [a, b]` after comma split | unit | `pytest interfaces/discord/tests/test_subcommands.py::test_pf_say_scene_dispatch -x` |
| `test_pf_say_scene_advance_dispatch` | DLG-03 | Empty payload ⇒ `party_line == ""` | unit | `pytest interfaces/discord/tests/test_subcommands.py::test_pf_say_scene_advance_dispatch -x` |
| `test_pf_unknown_verb_help_includes_say` | DLG-01 (D-04) | Help text contains `say` | unit | `pytest interfaces/discord/tests/test_subcommands.py::test_pf_unknown_verb_help_includes_say -x` |
| `test_pf_say_render_two_quote_blocks` | DLG-03 | 2 replies ⇒ 2 `> `-prefixed lines | unit | `pytest interfaces/discord/tests/test_subcommands.py::test_pf_say_render_two_quote_blocks -x` |
| `test_pf_say_render_warning_preamble` | DLG-03 | `warning` field prepended to output | unit | `pytest interfaces/discord/tests/test_subcommands.py::test_pf_say_render_warning_preamble -x` |
| `test_thread_history_pairing` | DLG-01/03 | Pair-matching user-say → bot-reply across thread | unit | `pytest interfaces/discord/tests/test_subcommands.py::test_thread_history_pairing -x` |
| `test_thread_history_filter_scene` | DLG-03 (D-13) | Turns filtered to any currently-named NPC | unit | `pytest interfaces/discord/tests/test_subcommands.py::test_thread_history_filter_scene -x` |

### Integration tests (`modules/pathfinder/tests/test_npc_say_integration.py` — new file)

| Test Name | Requirement | Proves | Automated Command |
|-----------|-------------|--------|-------------------|
| `test_solo_mood_roundtrip_through_vault` | DLG-01, DLG-02, SC-1, SC-2, SC-3 | Call 1 shifts mood neutral→wary in mock vault; call 2 reads wary from vault and system_prompt reflects wary tone | `pytest modules/pathfinder/tests/test_npc_say_integration.py::test_solo_mood_roundtrip_through_vault -x` |
| `test_scene_distinct_voices_and_awareness` | DLG-03, SC-4 | Two NPCs with different moods produce distinct system prompts; second NPC sees first's reply in user prompt | `pytest modules/pathfinder/tests/test_npc_say_integration.py::test_scene_distinct_voices_and_awareness -x` |

*Status codes for the Task ID assignment column (planner fills): ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Wave 0 establishes the test scaffolding before implementation lands. RED is expected; GREEN after Wave 1 implementation.

- [ ] `modules/pathfinder/tests/test_npc.py` — append 16 `test_npc_say_*` test stubs (import-protected by `try: from app.dialogue import ...` stanzas so collection does not fail)
- [ ] `modules/pathfinder/tests/test_npc_say_integration.py` — new file, 2 scenario tests with canned-LLM fixture and in-memory vault mock
- [ ] `interfaces/discord/tests/test_subcommands.py` — append 8 `test_pf_say_*` test stubs
- [ ] No new framework install — pytest-asyncio + ASGITransport already configured
- [ ] No new production dependencies — `tiktoken` already transitively installed in pathfinder via `litellm` lock

Wave 0 is complete when: `pytest modules/pathfinder/tests/test_npc.py -k "npc_say" --collect-only -q` shows 16 collected test functions AND `pytest interfaces/discord/tests/test_subcommands.py -k "say or unknown_verb_help or thread_history" --collect-only -q` shows 8 collected.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| In-character reply quality (personality reflected) | DLG-01, SC-1 | Quality is subjective; unit tests can only check personality substring appears in system prompt, not that the LLM actually used it | In Discord, run `:pf npc say <known NPC> \| <question matching their backstory>` and confirm the reply references traits from their profile |
| Mood shift feels right for the fictional situation | DLG-02, SC-3 | LLM judgement of salience is subjective | Hostile party statement ⇒ confirm `:pf npc show <name>` reports shifted mood afterward |
| Multi-NPC scene sounds like two distinct voices (not two copies of one voice) | DLG-03, SC-4 | Voice distinctness is subjective | In Discord, run `:pf npc say <A>,<B> \| <prompt>` with two personality-distinct NPCs; compare tones |
| Scene advance flows conversationally | DLG-03 | Narrative cohesion cannot be unit-tested | Send `:pf npc say <A>,<B> \|` (empty payload) after prior scene; confirm continuation reads as a scene beat, not a non-sequitur |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (16 module + 8 bot + 2 integration)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every DLG-* requirement is covered by ≥2 unit tests + 1 integration assertion)
- [x] Wave 0 covers all MISSING references (test stubs before implementation)
- [x] No watch-mode flags
- [x] Feedback latency < 45s (full suite)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending (planner assigns Task IDs and fills Plan/Wave columns during step 8)
