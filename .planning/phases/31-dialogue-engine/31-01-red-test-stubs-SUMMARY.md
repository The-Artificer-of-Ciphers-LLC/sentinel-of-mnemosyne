---
phase: 31-dialogue-engine
plan: 01
subsystem: testing
tags: [pytest, pytest-asyncio, httpx, asgi-transport, unittest-mock, red-scaffolding, tdd]

# Dependency graph
requires:
  - phase: 29-npc-crud-obsidian-persistence
    provides: NPC Obsidian schema (mood/relationships frontmatter), _validate_npc_name sanitizer, ObsidianClient patterns
  - phase: 30-npc-outputs
    provides: LLM helper pattern (extract_npc_fields), test module layout
provides:
  - 26 RED test stubs (16 module unit + 2 integration + 8 bot unit) that define the contract Waves 1-3 must implement against
  - 6 module-scope NOTE constants for Varek/Baron fixtures across 5 mood states + 1 relationship variant
  - StatefulMockVault helper for full round-trip integration tests
  - 8 canonical bot-layer assertions (payload shape, scene rendering, warning preamble, thread-history pairing + filtering)
affects: [31-02, 31-03, 31-04, 31-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Wave 0 RED scaffolding — stubs reference not-yet-existing symbols; AttributeError/AssertionError at runtime is the honest RED signal, collection succeeds"
    - "StatefulMockVault — in-memory vault that replays put_note writes through get_note for multi-turn integration tests"
    - "Tone-guidance keyword discipline — system_prompt MUST contain the UPPERCASE mood name (NEUTRAL/WARY/HOSTILE/FRIENDLY/ALLIED) so prompt construction is observable in tests"

key-files:
  created:
    - modules/pathfinder/tests/test_npc_say_integration.py
  modified:
    - modules/pathfinder/tests/test_npc.py
    - interfaces/discord/tests/test_subcommands.py

key-decisions:
  - "Copy-not-import the NOTE fixtures into the new integration test file for test isolation (PATTERNS.md §2 guidance)"
  - "Use AttributeError on missing patch target as the RED signal for tests that depend on Wave 1 symbols — avoids try/except-skip and keeps the RED→GREEN transition honest"
  - "StatefulMockVault allows a single test to POST twice and observe mood persistence across calls — matches RESEARCH.md SC-1..SC-3 scenario shape"

patterns-established:
  - "Wave-0 RED test file: header docstring explicitly states which Wave-1 symbol is missing so future readers know why the tests currently fail"
  - "Bot thread-history FakeThread pattern: a local class exposing .history(*, limit, oldest_first) that returns an async generator — unit-testable without discord.py installed"
  - "Tone-guidance keyword assertion: uppercase mood name in system_prompt (e.g. 'WARY', 'HOSTILE') is the observable that the Wave-1 prompt builder must honor"

requirements-completed: []  # Plan 31-01 is RED scaffolding; requirements DLG-01..03 are satisfied by Waves 1-3 once tests turn GREEN.

# Metrics
duration: 6min
completed: 2026-04-23
---

# Phase 31 Plan 01: Wave 0 RED Test Stubs Summary

**26 failing test stubs (16 module unit + 2 integration + 8 bot unit) define the contract for /npc/say, mood persistence, scene orchestration, and thread history — Waves 1-3 will turn these GREEN without further test work.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-23T20:00:38Z
- **Completed:** 2026-04-23T20:06:25Z
- **Tasks:** 3 / 3
- **Files modified:** 3 (1 created, 2 appended)

## Accomplishments

- **Module unit coverage (16 stubs)** in `modules/pathfinder/tests/test_npc.py` spanning DLG-01..03: solo happy path, unknown NPC 404, personality-in-system-prompt, mood deltas +1/-1/0, clamp at hostile/allied, invalid-mood normalization (T-31-SEC-02), scene order, in-turn scene context awareness, scene-advance framing, 5-NPC soft-cap warning, fail-fast on missing NPC (D-29), JSON-parse-salvage (T-31-SEC-03), and 2000-char party_line cap (T-31-SEC-04).
- **Integration coverage (2 stubs)** in new file `modules/pathfinder/tests/test_npc_say_integration.py`: full two-turn mood round-trip via `StatefulMockVault` (SC-1..3) and two-NPC distinct-voices-plus-awareness scene (SC-4).
- **Bot/Discord coverage (8 stubs)** in `interfaces/discord/tests/test_subcommands.py`: solo/scene/scene-advance dispatch payload shape, unknown-verb help lists `say`, quote-block render, warning preamble render, thread-history pairing + scene-membership filter (D-11..D-13) via duck-typed `_FakeThread`.
- **All 26 stubs collect cleanly** (no ImportError) and **FAIL on run** with the expected RED signals: 16 + 8 = 24 via `AttributeError` on patching `app.routes.npc.generate_npc_reply` or `bot._extract_thread_history`, and 4 via `AssertionError` (route 404 where 200/422 expected, help text missing `say`). Collection failures: zero.
- **No regression** — the 40 pre-existing tests in the two modified files (21 in test_npc.py, 19 in test_subcommands.py) still pass.

## Task Commits

Each task was committed atomically with `--no-verify` (worktree parallel executor):

1. **Task 31-01-01: 16 test_npc_say_* stubs + 6 NOTE fixtures** — `28c7d62` (test)
2. **Task 31-01-02: 2 integration stubs + StatefulMockVault** — `1c90a2e` (test)
3. **Task 31-01-03: 8 bot-side stubs (say dispatch + thread history)** — `b9c5b15` (test)

## Files Created/Modified

- **Created** `modules/pathfinder/tests/test_npc_say_integration.py` (169 lines) — 2 integration stubs, `StatefulMockVault` helper, env-bootstrap stanza, copy-not-import NOTE fixtures.
- **Modified** `modules/pathfinder/tests/test_npc.py` (+443 lines) — 6 new module-scope NOTE constants (VAREK_NEUTRAL/HOSTILE/WARY/ALLIED/INVALID_MOOD, BARON_HOSTILE, VAREK_FEARS_BARON) + 16 append-only `test_npc_say_*` stubs. Existing 21 tests untouched.
- **Modified** `interfaces/discord/tests/test_subcommands.py` (+216 lines) — 8 append-only stubs for `:pf npc say` dispatch, rendering, and thread-history extraction. Existing 19 tests untouched.

## Verification Commands Run

Collect-only (all must show "N tests collected" with zero collection errors):

```
cd modules/pathfinder && pytest tests/test_npc.py -k npc_say --collect-only -q
# → 16/37 tests collected (21 deselected) in 0.05s

cd modules/pathfinder && pytest tests/test_npc_say_integration.py --collect-only -q
# → 2 tests collected in 0.03s

cd interfaces/discord && pytest tests/test_subcommands.py -k 'say or thread_history or unknown_verb_help_includes_say' --collect-only -q
# → 8/27 tests collected (19 deselected) in 0.01s
```

RED proof (all tests fail; zero collection errors):

```
pytest tests/test_npc.py -k npc_say -q
# → 16 failed, 21 deselected in 1.67s (14× AttributeError on generate_npc_reply, 2× assertion)

pytest tests/test_npc_say_integration.py -q
# → 2 failed in 1.04s (2× AttributeError on generate_npc_reply)

pytest tests/test_subcommands.py -k 'say or thread_history or unknown_verb_help_includes_say' -q
# → 8 failed, 19 deselected in 0.12s (2× AttributeError on _extract_thread_history, 6× assertion)
```

No-regression proof:

```
pytest tests/test_npc.py -k "not npc_say" -q          # → 21 passed, 16 deselected
pytest tests/test_subcommands.py -k "not say and not thread_history" -q  # → 19 passed, 8 deselected
```

## RED Signal Summary

All 26 tests fail for the correct reason (missing Wave 1-3 symbol or behavior):

| Test file | AttributeError | AssertionError | Total |
|-----------|---------------:|---------------:|------:|
| test_npc.py (16 say tests) | 14 | 2 | 16 |
| test_npc_say_integration.py | 2 | 0 | 2 |
| test_subcommands.py (8 tests) | 2 | 6 | 8 |
| **Total** | **18** | **8** | **26** |

The 8 `AssertionError` failures are route-dispatch expectations that cannot be blocked by a missing symbol (e.g., `_pf_dispatch` currently returns an "Unknown npc command" string for `say`, so assertions on payload shape fail naturally).

## Decisions Made

- **Copied (not imported) NOTE fixtures** into the integration test file. `from .test_npc import NOTE_VAREK_NEUTRAL` would couple the two test files and obscure which fixture lives where. The cost (two copies of a 7-line string constant) is negligible; the benefit (each test file is self-contained) is real.
- **`AttributeError` is the deliberate RED signal**, not `try/except ImportError` with skip. Skipping hides the RED→GREEN transition; runtime AttributeError makes Wave 1's job visible: add the symbol → the patch attaches → the real assertions run.
- **Tone-guidance uppercase keyword** (`WARY`, `HOSTILE`, `NEUTRAL`) chosen as the observable for mood-tone system prompts. PATTERNS.md §2 guidance says prompt builders use uppercase mood names; enforcing this in tests pins the Wave 1 prompt shape.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. All three tasks completed on first attempt; verification passed on first run; no flaky behavior; no hook interference beyond a benign formatter pass on the newly-created integration test file.

## Threat Flags

No new security-relevant surface introduced — this plan ships test scaffolding only. The 16 module tests explicitly cover the anticipated threats listed in the plan's `<threat_model>`:

- **T-31-SEC-02** (mood poisoning) → `test_npc_say_invalid_mood_normalized`
- **T-31-SEC-03** (prompt injection via party_line) → `test_npc_say_json_parse_salvage` (graceful degrade shape)
- **T-31-SEC-04** (token-budget DoS) → `test_npc_say_party_line_too_long`

The plan's `<threat_model>` also references `T-31-SEC-01` (path traversal via name). That control is enforced by the reused `_validate_npc_name` sanitizer and is already covered by Phase 29 CR-02 mitigation tests; Wave 1 will wire it via the `NPCSayRequest` validator.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Plan 31-02 (dialogue-helpers)** is ready. It will add `app/dialogue.py` with `normalize_mood`, `apply_mood_delta`, `cap_history_turns`, `build_system_prompt`, `build_user_prompt`. Five of the 16 module tests (`test_npc_say_mood_*`, `test_npc_say_invalid_mood_normalized`) depend on this plan.
- **Plan 31-03 (llm-generate-reply)** adds `app.llm.generate_npc_reply`. Sixteen of the 26 tests unblock once this symbol is importable (the `patch("app.routes.npc.generate_npc_reply", ...)` lines begin resolving).
- **Plan 31-04 (route-and-registration)** wires `POST /npc/say`, `NPCSayRequest`, `NPCSayResponse`. This turns the 2 integration tests and 12 of the 16 module tests GREEN.
- **Plan 31-05 (bot-wiring)** adds the `say` verb branch in `_pf_dispatch`, the `_extract_thread_history` helper, and updates the Available-verbs help text. This turns the 8 bot tests GREEN.

No blockers. The RED contract is committed; Waves 1-3 have an unambiguous target.

## Self-Check: PASSED

Files verified to exist:
- FOUND: modules/pathfinder/tests/test_npc.py (modified)
- FOUND: modules/pathfinder/tests/test_npc_say_integration.py (new)
- FOUND: interfaces/discord/tests/test_subcommands.py (modified)

Commits verified in log:
- FOUND: 28c7d62 (Task 31-01-01)
- FOUND: 1c90a2e (Task 31-01-02)
- FOUND: b9c5b15 (Task 31-01-03)

---
*Phase: 31-dialogue-engine*
*Completed: 2026-04-23*
