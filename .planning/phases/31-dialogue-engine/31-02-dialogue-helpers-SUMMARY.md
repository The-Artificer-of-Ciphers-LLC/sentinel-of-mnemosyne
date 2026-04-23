---
phase: 31
plan: 02
subsystem: pathfinder
tags: [dialogue, helpers, pure-transform, mood, prompts, tiktoken]
dependency-graph:
  requires:
    - phase-29 NPC schema (mood field exists in frontmatter)
    - tiktoken (transitive via litellm — already installed)
  provides:
    - MOOD_ORDER constant (5-state ordered spectrum)
    - MOOD_TONE_GUIDANCE dict (per-mood system-prompt fragments)
    - HISTORY_MAX_TURNS, HISTORY_MAX_TOKENS constants
    - normalize_mood / apply_mood_delta functions
    - build_system_prompt / build_user_prompt functions
    - cap_history_turns function
  affects:
    - plan 31-04 (route handler) — consumes all exported symbols
    - plan 31-03 (generate_npc_reply) — no direct consumption; parallel wave
tech-stack:
  added: [tiktoken usage (first in pathfinder module)]
  patterns: [pure-transform module, defence-in-depth truncation, token-budget guardrail]
key-files:
  created:
    - modules/pathfinder/app/dialogue.py
  modified: []
decisions:
  - Implemented plan verbatim (reference impls in 31-RESEARCH.md lines 794-906)
  - MOOD_ORDER fixed order [hostile, wary, neutral, friendly, allied] per D-06
  - normalize_mood is case-sensitive (rejects 'HOSTILE' per D-06 "exactly one of these five lowercase strings")
  - apply_mood_delta treats out-of-range delta (not in {-1, 0, 1}) as 0 with WARNING — defensive per D-07
  - Backstory capped at 400 chars, personality at 200 chars (D-22, mitigates T-31-02-T02 prompt injection)
  - Token cap uses tiktoken cl100k_base encoding (matches sentinel-core/app/services/token_guard.py)
  - cap_history_turns drops oldest first and short-circuits at turn cap before running token check
metrics:
  duration-seconds: 300
  completed: 2026-04-23
  tasks: 3
  files-created: 1
  files-modified: 0
---

# Phase 31 Plan 02: Dialogue Helpers Summary

Pure-transform helper module delivered at `modules/pathfinder/app/dialogue.py` (207 lines) owning mood math, per-NPC prompt construction, and tiktoken-based history budget enforcement. Zero LLM calls, zero Obsidian I/O, zero FastAPI dependencies — plain string/list/dict manipulation plus tiktoken cl100k_base. Ready for plan 31-04 to wire into the `/npc/say` route.

## Public Symbols Exported

**Constants (4):**
- `MOOD_ORDER: list[str]` — `["hostile", "wary", "neutral", "friendly", "allied"]`
- `MOOD_TONE_GUIDANCE: dict[str, str]` — per-mood tone-direction fragments (all 5 keys present, each value references the mood name in UPPERCASE)
- `HISTORY_MAX_TURNS: int = 10`
- `HISTORY_MAX_TOKENS: int = 2000`

**Functions (5 public, 1 private):**
- `normalize_mood(value) -> str` — invalid values coerce to `"neutral"` with WARNING
- `apply_mood_delta(current: str, delta: int) -> str` — ±1 step along MOOD_ORDER; clamps at endpoints; coerces out-of-range delta to 0
- `build_system_prompt(npc_fields, scene_roster, scene_relationships) -> str` — persona + tone + scene context + JSON output contract (reply + mood_delta)
- `build_user_prompt(history, this_turn_replies, party_line, npc_name) -> str` — thread transcript + this-turn replies + party_line OR scene-advance framing
- `cap_history_turns(turns) -> list[dict]` — cap-last-N + tiktoken token-budget guardrail; drops oldest first
- `_render_history_for_token_count` — private helper matching build_user_prompt transcript format

## Task Breakdown

| Task       | Commit   | Scope                                                   |
| ---------- | -------- | ------------------------------------------------------- |
| 31-02-01   | b822733  | dialogue.py created; constants + mood math              |
| 31-02-02   | 289b811  | build_system_prompt + build_user_prompt appended        |
| 31-02-03   | a23e639  | cap_history_turns + tiktoken import appended            |

## Verification Results

**Smoke tests (all three tasks):** `OK`

**Full symbol import:**
```
all symbols OK
```

**Pre-existing test suite:** 42/42 pass. 18 failures in `tests/test_npc.py` and `tests/test_npc_say_integration.py` are the RED stubs from plan 31-01 for the `/npc/say` route — they test `generate_npc_reply` (plan 31-03) and the route handler (plan 31-04), neither of which this plan delivers. Expected red; they go GREEN when 31-04 lands.

**AI Deferral Ban scan:** 0 matches for TODO/FIXME/NotImplementedError/raise NotImplementedError.

**Behavioral truths verified inline (all 8 from plan must_haves):**
- `MOOD_ORDER == ['hostile', 'wary', 'neutral', 'friendly', 'allied']` ✓
- All 5 mood keys in MOOD_TONE_GUIDANCE, each with UPPERCASE mood name in value ✓
- `normalize_mood('grumpy')` → `'neutral'` + WARNING ✓
- `apply_mood_delta('hostile', -1)` → `'hostile'` (clamped low) ✓
- `apply_mood_delta('allied', +1)` → `'allied'` (clamped high) ✓
- `apply_mood_delta('neutral', +1)` → `'friendly'` ✓
- `apply_mood_delta('wary', -1)` → `'hostile'` ✓
- `build_system_prompt` truncates backstory to 400 / personality to 200 ✓
- `build_system_prompt` embeds traits, scene roster, relationship edges, mood tone, JSON contract ✓
- `build_user_prompt` generates scene-advance framing when `party_line == ''` ✓
- `cap_history_turns` drops oldest first; idempotent; 15 small turns → 10; huge varied-text turn → 0 ✓

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Doc] Rephrased module docstring to avoid AI-Deferral-Ban false positive**
- **Found during:** Task 31-02-01 acceptance check
- **Issue:** Plan-provided docstring read `"no TODO/pass/NotImplementedError"` — the grep-based deferral scan in acceptance criteria matched this phrase and returned 1 hit, tripping the gate even though the line was a declarative affirmation (not actual deferred work).
- **Fix:** Replaced the listing of forbidden tokens with `"no deferral markers"` — preserves intent, clears the scan.
- **Files modified:** `modules/pathfinder/app/dialogue.py` (docstring line 14)
- **Commit:** b822733

**2. [Rule 3 — Tooling] Ruff formatter strips unused imports — appended import + first-use in same Write**
- **Found during:** Task 31-02-03 setup
- **Issue:** The project's PostToolUse formatter (ruff, likely with F401 fix) auto-strips unused imports. When task 31-02-01 created the module with `import tiktoken` but no tiktoken usage (those would appear in task 31-02-03), ruff removed the import after each Edit. Repeated Edit attempts to re-add the import alone all failed — the formatter ran and stripped it every time.
- **Fix:** Used a single `Write` operation in task 31-02-03 that added both `import tiktoken` AND the `cap_history_turns` function body that calls `tiktoken.get_encoding("cl100k_base")`. With a real usage present, ruff retained the import.
- **Files modified:** `modules/pathfinder/app/dialogue.py`
- **Commit:** a23e639
- **Note:** The plan's per-task incremental structure assumed imports could be staged ahead of first use; the project formatter enforces the opposite. Final file contains both as intended by the plan.

### Observations (not deviations)

**Plan smoke test for token cap had tokenizer-density assumption error.** The plan's task-03 smoke test used `'x' * 12000` expecting ~3000 tokens to exceed the 2000 cap. Under cl100k_base, `'x' * 12000` encodes to only ~1500 tokens (repeat-char run-length compression). The test assertion `cap_history_turns(huge) == []` would fail not because `cap_history_turns` is broken but because the input wasn't large enough. The implementation is correct and verified against the plan's reference code (RESEARCH.md lines 252-273). Corrected verification used varied ASCII text (`random.choice(string.ascii_letters + ' ')`) which tokenizes densely and does trigger the token cap, producing the expected empty-list output. This is a plan-smoke-test accuracy note — no production-code change required.

## Smoke Test Outputs

**Task 31-02-01:**
```
NPC mood 'grumpy' invalid; treating as 'neutral'
OK
```

**Task 31-02-02:**
```
OK
```

**Task 31-02-03 (corrected for cl100k_base compression):**
```
OK
```

## Hand-Off Notes for Downstream Plans

- **Plan 31-03** (`generate_npc_reply`): does NOT import any symbol from this module — it's the LiteLLM wrapper. Prompt-string construction is the caller's job (plan 31-04).
- **Plan 31-04** (`/npc/say` route handler): MUST import `MOOD_ORDER, normalize_mood, apply_mood_delta, build_system_prompt, build_user_prompt, cap_history_turns` from `app.dialogue`. The four mood/normalize/scene-advance unit tests in `tests/test_npc.py` go GREEN at that point (they test the end-to-end route behaviour that depends on these helpers being wired).
- **`MOOD_TONE_GUIDANCE`** is not typically imported by consumers — it's embedded via `build_system_prompt` internally.

## Threat Flags

No new security-relevant surface beyond what the plan's threat model covers. Module has no I/O, no network, no file access. Truncation bounds (400/200) are fixed constants; no runtime user-controlled sizing. `cap_history_turns` protects against T-31-02-D01 (token-budget DoS). `normalize_mood` enforces T-31-02-T01 (mood poisoning rejection).

## Self-Check: PASSED

- FOUND: modules/pathfinder/app/dialogue.py
- FOUND: b822733 (task 31-02-01)
- FOUND: 289b811 (task 31-02-02)
- FOUND: a23e639 (task 31-02-03)
