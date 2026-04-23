---
plan_id: 31-02
phase: 31
wave: 1
depends_on: [31-01]
files_modified:
  - modules/pathfinder/app/dialogue.py
autonomous: true
requirements: [DLG-01, DLG-02, DLG-03]
must_haves:
  truths:
    - "MOOD_ORDER constant defines exactly 5 strings: hostile, wary, neutral, friendly, allied (in that order)"
    - "MOOD_TONE_GUIDANCE dict has the 5 mood keys, each value mentions the mood name in UPPERCASE"
    - "normalize_mood(unknown_value) returns 'neutral' AND logs a WARNING"
    - "apply_mood_delta clamps at endpoints — apply_mood_delta('hostile', -1) == 'hostile'; apply_mood_delta('allied', +1) == 'allied'"
    - "apply_mood_delta('neutral', +1) == 'friendly'; apply_mood_delta('wary', -1) == 'hostile'"
    - "build_system_prompt embeds personality (first 200 chars), backstory (first 400 chars), traits, scene roster, relationship edges, mood tone guidance, JSON output contract"
    - "build_user_prompt embeds prior history transcript, this-turn other-NPC replies, and either party_line OR scene-advance framing"
    - "cap_history_turns drops oldest first, capped at 10 turns OR 2000 cl100k_base tokens"
  tests:
    - "Symbols importable: from app.dialogue import MOOD_ORDER, MOOD_TONE_GUIDANCE, normalize_mood, apply_mood_delta, build_system_prompt, build_user_prompt, cap_history_turns, HISTORY_MAX_TURNS, HISTORY_MAX_TOKENS"
    - "Plan 31-04 wires these into /npc/say; the four mood/normalize/scene-advance unit tests turn GREEN at that point"
---

<plan_objective>
Create `modules/pathfinder/app/dialogue.py` — the pure-transform helper module owning mood math and per-NPC prompt construction. This plan ships ZERO LLM calls and ZERO Obsidian I/O; it is plain string/list/dict manipulation plus tiktoken for token counting. Plan 31-03 wraps the LiteLLM call; Plan 31-04 wires both into the route handler.
</plan_objective>

<threat_model>
## STRIDE Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-31-02-T01 | Tampering | mood_poisoning via hand-edited frontmatter (T-31-SEC-02) | mitigate | `normalize_mood` rejects any value not in MOOD_ORDER; logs WARNING; returns "neutral". Test `test_npc_say_invalid_mood_normalized` proves this. |
| T-31-02-T02 | Tampering | prompt injection via stored backstory (T-31-SEC-03) | mitigate (defence in depth) | `build_system_prompt` truncates backstory to 400 chars (D-22), personality to 200 chars. Limits multi-field injection surface even if attacker controls vault. |
| T-31-02-D01 | DoS | token-budget DoS via huge history (T-31-SEC-04) | mitigate | `cap_history_turns` enforces HISTORY_MAX_TURNS=10 AND HISTORY_MAX_TOKENS=2000 via tiktoken cl100k_base. Drops oldest first. |
| T-31-02-I01 | Information Disclosure | NPC stats block contents leaking into LLM call | accept (out-of-scope) | `build_system_prompt` only consumes frontmatter fields; stats block is parsed but not passed in. |

**Block level:** none HIGH. T-31-02-T01 and T-31-02-D01 are MITIGATED (testable). T-31-02-T02 is partial defence in depth (truncation). ASVS L1 satisfied.
</threat_model>

<tasks>

<task id="31-02-01" type="tdd" autonomous="true" tdd="true">
  <name>Task 31-02-01: Create dialogue.py with constants + mood math</name>
  <read_first>
    - modules/pathfinder/app/llm.py (lines 1-15 for module-docstring + logger pattern)
    - modules/pathfinder/app/routes/npc.py (lines 36-73 for `_validate_npc_name` + `slugify` style; line 57 for `VALID_RELATIONS = frozenset(...)` constant style)
    - .planning/phases/31-dialogue-engine/31-PATTERNS.md §1 (module shape + helper style + dependency-free constraint)
    - .planning/phases/31-dialogue-engine/31-RESEARCH.md lines 366-394 (verbatim MOOD_TONE_GUIDANCE dict)
    - .planning/phases/31-dialogue-engine/31-RESEARCH.md lines 794-817 (MOOD_ORDER, normalize_mood, apply_mood_delta reference impls)
  </read_first>
  <behavior>
    - normalize_mood("neutral") → "neutral" (no warning)
    - normalize_mood("HOSTILE") → "neutral" (case-sensitive — rejects uppercase per D-06 "exactly one of these five lowercase strings"); WARNING logged
    - normalize_mood("grumpy") → "neutral" + WARNING
    - normalize_mood("") → "neutral" + WARNING
    - normalize_mood(None) → "neutral" + WARNING
    - apply_mood_delta("neutral", 0) → "neutral"
    - apply_mood_delta("neutral", 1) → "friendly"
    - apply_mood_delta("neutral", -1) → "wary"
    - apply_mood_delta("hostile", -1) → "hostile" (clamped low)
    - apply_mood_delta("allied", 1) → "allied" (clamped high)
    - apply_mood_delta("grumpy", 1) → "friendly" (normalize→neutral, then +1)
    - apply_mood_delta("neutral", 5) → "neutral" + WARNING (out-of-range delta coerces to 0)
    - MOOD_ORDER == ["hostile", "wary", "neutral", "friendly", "allied"]
    - set(MOOD_TONE_GUIDANCE.keys()) == set(MOOD_ORDER)
  </behavior>
  <action>
CREATE `modules/pathfinder/app/dialogue.py` with this exact content (per RESEARCH.md Finding 5 and lines 794-817):

```python
"""Dialogue helpers for pathfinder module — prompt construction + mood math.

Pure-transform module: no LLM calls (those live in app.llm.generate_npc_reply),
no Obsidian I/O (those live in app.routes.npc), no FastAPI dependencies.
Only stdlib + tiktoken (already transitive via litellm) + logging.

Owns:
- MOOD_ORDER: 5-state ordered spectrum (D-06)
- MOOD_TONE_GUIDANCE: per-mood system-prompt fragments (D-08, RESEARCH Finding 5)
- normalize_mood / apply_mood_delta: state-machine math (D-07)
- build_system_prompt / build_user_prompt: per-NPC prompt assembly (D-21, D-22, RESEARCH Finding 4)
- cap_history_turns: history budget enforcement (D-14, RESEARCH Finding 3)

Per CLAUDE.md AI Deferral Ban: every helper completes its job; no TODO/pass/NotImplementedError.
"""

import logging

import tiktoken

logger = logging.getLogger(__name__)

# --- Constants (D-06, D-08, D-14) ---

MOOD_ORDER: list[str] = ["hostile", "wary", "neutral", "friendly", "allied"]

# Per RESEARCH.md Finding 5 — copy verbatim. Adjective + behavioral consequence + style direction.
MOOD_TONE_GUIDANCE: dict[str, str] = {
    "hostile": (
        "You are HOSTILE toward the party. You are curt, aggressive, and suspicious. "
        "You threaten if pushed. You do not volunteer information. You do not trust them. "
        "Respond in short, sharp sentences. Use tension and edge."
    ),
    "wary": (
        "You are WARY of the party. You are guarded and watchful. "
        "You give partial answers. You deflect probing questions. You watch for betrayal. "
        "Respond with measured caution. Keep details minimal."
    ),
    "neutral": (
        "You are NEUTRAL toward the party. You are businesslike and direct. "
        "You answer direct questions honestly but offer no warmth and no extra context. "
        "Respond matter-of-factly. No flourish, no reluctance."
    ),
    "friendly": (
        "You are FRIENDLY toward the party. You are warm and forthcoming. "
        "You volunteer useful context. You show concern for their situation. "
        "Respond with openness. Small gestures of goodwill are natural."
    ),
    "allied": (
        "You are ALLIED with the party. You trust them and share their goals. "
        "You freely offer information, warn them of danger, and act on your own initiative to help. "
        "Respond as a committed ally. Share knowledge and counsel without being asked."
    ),
}

HISTORY_MAX_TURNS: int = 10
HISTORY_MAX_TOKENS: int = 2000


# --- Mood state machine (D-06, D-07) ---

def normalize_mood(value):
    """Validate stored mood; invalid values become 'neutral' with WARNING (D-06, T-31-SEC-02)."""
    if value in MOOD_ORDER:
        return value
    logger.warning("NPC mood %r invalid; treating as 'neutral'", value)
    return "neutral"


def apply_mood_delta(current: str, delta: int) -> str:
    """Advance one step along MOOD_ORDER; clamp at endpoints (D-07)."""
    if delta not in (-1, 0, 1):
        logger.warning("apply_mood_delta: out-of-range delta=%r, coercing to 0", delta)
        delta = 0
    idx = MOOD_ORDER.index(normalize_mood(current))
    new_idx = max(0, min(len(MOOD_ORDER) - 1, idx + delta))
    return MOOD_ORDER[new_idx]
```

DO NOT add prompt builders or `cap_history_turns` in this task — they land in 31-02-02 / 31-02-03.

Smoke test:
```bash
cd modules/pathfinder && python -c "from app.dialogue import MOOD_ORDER, MOOD_TONE_GUIDANCE, normalize_mood, apply_mood_delta; assert MOOD_ORDER == ['hostile', 'wary', 'neutral', 'friendly', 'allied']; assert set(MOOD_TONE_GUIDANCE.keys()) == set(MOOD_ORDER); assert normalize_mood('grumpy') == 'neutral'; assert apply_mood_delta('neutral', 1) == 'friendly'; assert apply_mood_delta('hostile', -1) == 'hostile'; assert apply_mood_delta('allied', 1) == 'allied'; print('OK')"
```
  </action>
  <acceptance_criteria>
    - test -f modules/pathfinder/app/dialogue.py
    - grep -F '"hostile", "wary", "neutral", "friendly", "allied"' modules/pathfinder/app/dialogue.py matches
    - grep -F 'HISTORY_MAX_TURNS: int = 10' modules/pathfinder/app/dialogue.py matches
    - grep -F 'HISTORY_MAX_TOKENS: int = 2000' modules/pathfinder/app/dialogue.py matches
    - All 5 mood keys present in MOOD_TONE_GUIDANCE (grep for `"hostile":`, `"wary":`, `"neutral":`, `"friendly":`, `"allied":`)
    - Smoke test command exits 0 with output `OK`
    - grep -vE '^\s*#' modules/pathfinder/app/dialogue.py | grep -E '(TODO|FIXME|NotImplementedError|^\s*pass\s*$|raise NotImplementedError)' returns 0 matches (AI Deferral Ban; comment lines stripped first)
  </acceptance_criteria>
  <automated>cd modules/pathfinder && python -c "from app.dialogue import MOOD_ORDER, MOOD_TONE_GUIDANCE, normalize_mood, apply_mood_delta; assert MOOD_ORDER == ['hostile', 'wary', 'neutral', 'friendly', 'allied']; assert set(MOOD_TONE_GUIDANCE.keys()) == set(MOOD_ORDER); assert normalize_mood('grumpy') == 'neutral'; assert apply_mood_delta('neutral', 1) == 'friendly'; assert apply_mood_delta('hostile', -1) == 'hostile'; assert apply_mood_delta('allied', 1) == 'allied'; print('OK')"</automated>
</task>

<task id="31-02-02" type="tdd" autonomous="true" tdd="true">
  <name>Task 31-02-02: Add build_system_prompt + build_user_prompt to dialogue.py</name>
  <read_first>
    - modules/pathfinder/app/dialogue.py (output of Task 31-02-01)
    - .planning/phases/31-dialogue-engine/31-RESEARCH.md lines 820-906 (build_system_prompt + build_user_prompt reference implementations)
    - .planning/phases/31-dialogue-engine/31-CONTEXT.md decisions D-21, D-22 (truncation values)
  </read_first>
  <behavior>
    - build_system_prompt(fields={name:Varek, level:1, ancestry:Gnome, class:Rogue, personality:Nervous, backstory:Fled., traits:[sneaky], mood:neutral}, [Varek], []) → contains "Varek", "Nervous", "Fled.", "sneaky", "NEUTRAL", "JSON object", "mood_delta", "reply"
    - build_system_prompt with backstory of 500 chars truncates to 400 in output
    - build_system_prompt with personality of 300 chars truncates to 200 in output
    - build_system_prompt with mood:wary includes "WARY" in output
    - build_system_prompt with scene_roster=[Varek, Baron Aldric] for npc Varek includes "Others present in this scene: Baron Aldric"
    - build_system_prompt with scene_relationships=[{target:Baron Aldric, relation:fears}] includes "You fears Baron Aldric."
    - build_user_prompt([], [], "hello", "Varek") contains 'The party has just said: "hello"' and "Respond as Varek"
    - build_user_prompt([], [], "", "Varek") contains "silent" and "Continue the scene" (scene-advance D-20)
    - build_user_prompt(history=[{party_line:Q, replies:[{npc:Varek, reply:A}]}], ...) contains "--- Earlier in the conversation ---", "Q", "A"
    - build_user_prompt(this_turn_replies=[{npc:Baron, reply:Bline}], party_line:hi, npc_name:Varek) contains "--- This turn so far ---" and "Bline"
  </behavior>
  <action>
APPEND to `modules/pathfinder/app/dialogue.py` the two prompt-builder functions per RESEARCH.md lines 820-906:

```python
def build_system_prompt(
    npc_fields: dict,
    scene_roster: list[str],
    scene_relationships: list[dict],
) -> str:
    """Per-NPC system prompt: persona + tone + scene context + JSON output contract.

    Truncates backstory to 400 chars, personality to 200 chars (D-22, defence in depth).
    """
    name = npc_fields.get("name", "?")
    level = npc_fields.get("level", "?")
    ancestry = npc_fields.get("ancestry", "")
    npc_class = npc_fields.get("class", "")
    personality = (npc_fields.get("personality") or "")[:200].replace("\n", " ")
    backstory = (npc_fields.get("backstory") or "")[:400].replace("\n", " ")
    traits = ", ".join(npc_fields.get("traits") or [])
    mood = normalize_mood(npc_fields.get("mood") or "neutral")
    tone = MOOD_TONE_GUIDANCE[mood]

    other_npcs = [n for n in scene_roster if n != name]
    rel_lines = []
    for rel in scene_relationships:
        if isinstance(rel, dict) and rel.get("target") and rel.get("relation"):
            rel_lines.append(f"You {rel['relation']} {rel['target']}.")
    rel_block = (
        "\n".join(rel_lines)
        if rel_lines
        else "(no known relationships with others in this scene)"
    )

    scene_block = (
        f"Others present in this scene: {', '.join(other_npcs)}."
        if other_npcs
        else "You are alone with the party."
    )

    return (
        f"You are {name}, a level-{level} {ancestry} {npc_class}.\n"
        f"Personality: {personality}\n"
        f"Backstory: {backstory}\n"
        f"Traits: {traits}\n"
        f"\n{scene_block}\n"
        f"Relationships with others in this scene:\n{rel_block}\n"
        f"\nTone guidance for your current mood ({mood}):\n{tone}\n"
        f"\nOutput format: Return ONLY a JSON object — no markdown, no code fences, no prose outside JSON — "
        f"with these exact keys:\n"
        f'  "reply": string. Your in-character response, 1-4 sentences. '
        f'Format: *{{brief action or expression}}.* "{{spoken line}}"\n'
        f'  "mood_delta": integer, exactly one of -1, 0, +1. '
        f"Use -1 if the party just threatened, insulted, or betrayed you. "
        f"Use +1 if they were genuinely persuasive, kind, or helpful. "
        f"Use 0 for normal chatter or ambiguous turns (this is the default)."
    )


def build_user_prompt(
    history: list[dict],
    this_turn_replies: list[dict],
    party_line: str,
    npc_name: str,
) -> str:
    """Per-NPC user message: thread history + this-turn replies + current party line OR scene-advance framing."""
    sections: list[str] = []

    if history:
        lines = ["--- Earlier in the conversation ---"]
        for turn in history:
            lines.append(f"Party: {turn.get('party_line', '')!r}")
            for r in turn.get("replies", []) or []:
                lines.append(f"{r.get('npc', '?')}: {r.get('reply', '')}")
        sections.append("\n".join(lines))

    if this_turn_replies:
        lines = ["--- This turn so far ---"]
        if party_line:
            lines.append(f"Party: {party_line!r}")
        else:
            lines.append("Party: (silent)")
        for r in this_turn_replies:
            lines.append(f"{r.get('npc', '?')}: {r.get('reply', '')}")
        sections.append("\n".join(lines))

    if party_line:
        sections.append(
            f'The party has just said: "{party_line}". Respond as {npc_name}.'
        )
    else:
        sections.append(
            "The party is silent. Continue the scene naturally — react to what was just "
            f"said, or advance the situation based on your character and the conversation "
            f"so far. Respond as {npc_name}."
        )

    return "\n\n".join(sections)
```

Smoke test (run after implementing):
```bash
cd modules/pathfinder && python -c "
from app.dialogue import build_system_prompt, build_user_prompt
sp = build_system_prompt(
    {'name': 'Varek', 'level': 1, 'ancestry': 'Gnome', 'class': 'Rogue',
     'personality': 'Nervous', 'backstory': 'Fled.', 'traits': ['sneaky'], 'mood': 'wary'},
    scene_roster=['Varek', 'Baron'],
    scene_relationships=[{'target': 'Baron', 'relation': 'fears'}],
)
assert 'Varek' in sp
assert 'WARY' in sp
assert 'You fears Baron.' in sp
assert 'Others present in this scene: Baron.' in sp
assert 'JSON object' in sp
sp2 = build_system_prompt({'name': 'X', 'backstory': 'a' * 500, 'personality': 'b' * 300, 'mood': 'neutral'}, [], [])
assert 'a' * 400 in sp2 and 'a' * 401 not in sp2
assert 'b' * 200 in sp2 and 'b' * 201 not in sp2
up = build_user_prompt([], [], '', 'Varek')
assert 'silent' in up and 'Continue the scene' in up and 'Respond as Varek' in up
up2 = build_user_prompt([], [], 'hello', 'Varek')
assert 'The party has just said: \"hello\"' in up2
print('OK')
"
```
  </action>
  <acceptance_criteria>
    - grep -E '^def build_system_prompt\(' modules/pathfinder/app/dialogue.py matches
    - grep -E '^def build_user_prompt\(' modules/pathfinder/app/dialogue.py matches
    - grep -F '[:200]' modules/pathfinder/app/dialogue.py matches
    - grep -F '[:400]' modules/pathfinder/app/dialogue.py matches
    - grep -F 'The party is silent. Continue the scene naturally' modules/pathfinder/app/dialogue.py matches (D-20 framing verbatim)
    - grep -F '--- Earlier in the conversation ---' modules/pathfinder/app/dialogue.py matches
    - grep -F '--- This turn so far ---' modules/pathfinder/app/dialogue.py matches
    - grep -F 'Return ONLY a JSON object' modules/pathfinder/app/dialogue.py matches
    - Smoke test exits 0 with output OK
    - grep -vE '^\s*#' modules/pathfinder/app/dialogue.py | grep -E '(TODO|FIXME|NotImplementedError|raise NotImplementedError)' returns 0 matches
  </acceptance_criteria>
  <automated>cd modules/pathfinder && python -c "from app.dialogue import build_system_prompt, build_user_prompt; sp = build_system_prompt({'name': 'Varek', 'level': 1, 'ancestry': 'Gnome', 'class': 'Rogue', 'personality': 'Nervous', 'backstory': 'Fled.', 'traits': ['sneaky'], 'mood': 'wary'}, scene_roster=['Varek', 'Baron'], scene_relationships=[{'target': 'Baron', 'relation': 'fears'}]); assert 'WARY' in sp and 'You fears Baron.' in sp and 'Others present in this scene: Baron.' in sp and 'JSON object' in sp; up = build_user_prompt([], [], '', 'Varek'); assert 'silent' in up and 'Continue the scene' in up; print('OK')"</automated>
</task>

<task id="31-02-03" type="tdd" autonomous="true" tdd="true">
  <name>Task 31-02-03: Add cap_history_turns to dialogue.py (tiktoken guardrail)</name>
  <read_first>
    - modules/pathfinder/app/dialogue.py (output of Task 31-02-02)
    - sentinel-core/app/services/token_guard.py lines 20-40 (existing tiktoken cl100k_base usage pattern)
    - .planning/phases/31-dialogue-engine/31-RESEARCH.md lines 252-273 (cap_history reference impl + reasoning)
    - .planning/phases/31-dialogue-engine/31-PATTERNS.md "No-Analog Findings" (tiktoken availability via litellm transitive)
  </read_first>
  <behavior>
    - cap_history_turns([]) → [] (empty input)
    - cap_history_turns(15 small turns) → returns last 10 (HISTORY_MAX_TURNS cap by default)
    - cap_history_turns(5 small turns) → returns all 5 (under both caps)
    - cap_history_turns([1 huge turn with 3000-token party_line]) → returns [] (token cap kicks in even for 1 turn)
    - Output preserves original order (newest at end); when truncating, oldest dropped first
    - Idempotent: cap_history_turns(cap_history_turns(x)) == cap_history_turns(x)
  </behavior>
  <action>
APPEND to `modules/pathfinder/app/dialogue.py`:

```python
# --- History budget (D-14, RESEARCH Finding 3) ---

def _render_history_for_token_count(turns: list[dict]) -> str:
    """Render turns as a single string for tiktoken counting (matches build_user_prompt format)."""
    out = []
    for turn in turns:
        out.append(f"Party: {turn.get('party_line', '')!r}")
        for r in turn.get("replies", []) or []:
            out.append(f"{r.get('npc', '?')}: {r.get('reply', '')}")
    return "\n".join(out)


def cap_history_turns(turns: list[dict]) -> list[dict]:
    """Drop oldest turns first until under HISTORY_MAX_TURNS AND HISTORY_MAX_TOKENS (D-14).

    Token count uses tiktoken cl100k_base — same encoding as
    sentinel-core/app/services/token_guard.py for consistency.
    """
    if not turns:
        return []
    # Primary cap: keep last N turns
    capped = list(turns[-HISTORY_MAX_TURNS:])
    # Guardrail: token cap drops oldest until under budget
    enc = tiktoken.get_encoding("cl100k_base")
    while capped:
        rendered = _render_history_for_token_count(capped)
        if len(enc.encode(rendered)) <= HISTORY_MAX_TOKENS:
            break
        capped = capped[1:]  # drop oldest first
    return capped
```

Smoke test:
```bash
cd modules/pathfinder && python -c "
from app.dialogue import cap_history_turns, HISTORY_MAX_TURNS, HISTORY_MAX_TOKENS
# Empty
assert cap_history_turns([]) == []
# Under caps
small = [{'party_line': f'q{i}', 'replies': [{'npc': 'V', 'reply': f'a{i}'}]} for i in range(5)]
assert len(cap_history_turns(small)) == 5
# Over turn cap
many = [{'party_line': f'q{i}', 'replies': [{'npc': 'V', 'reply': f'a{i}'}]} for i in range(15)]
out = cap_history_turns(many)
assert len(out) == HISTORY_MAX_TURNS, f'expected {HISTORY_MAX_TURNS}, got {len(out)}'
assert out[-1]['party_line'] == 'q14'  # newest preserved
assert out[0]['party_line'] == 'q5'    # oldest dropped first
# Token cap
huge = [{'party_line': 'x' * 12000, 'replies': []}]  # ~3000 tokens — over 2000 cap
assert cap_history_turns(huge) == []
# Idempotent
assert cap_history_turns(cap_history_turns(many)) == cap_history_turns(many)
print('OK')
"
```
  </action>
  <acceptance_criteria>
    - grep -E '^def cap_history_turns\(' modules/pathfinder/app/dialogue.py matches
    - grep -F 'tiktoken.get_encoding("cl100k_base")' modules/pathfinder/app/dialogue.py matches
    - grep -F 'HISTORY_MAX_TURNS' modules/pathfinder/app/dialogue.py occurs at least 2 times (constant + cap usage)
    - grep -F 'HISTORY_MAX_TOKENS' modules/pathfinder/app/dialogue.py occurs at least 2 times
    - Smoke test exits 0 with output OK
    - All eight Plan 31-02 truths verifiable: from app.dialogue import everything succeeds; constants correct; mood functions correct; prompt builders correct; cap_history_turns enforces both caps
    - grep -vE '^\s*#' modules/pathfinder/app/dialogue.py | grep -E '(TODO|FIXME|NotImplementedError|raise NotImplementedError)' returns 0 matches
  </acceptance_criteria>
  <automated>cd modules/pathfinder && python -c "from app.dialogue import cap_history_turns, HISTORY_MAX_TURNS, HISTORY_MAX_TOKENS; assert cap_history_turns([]) == []; small = [{'party_line': f'q{i}', 'replies': [{'npc': 'V', 'reply': f'a{i}'}]} for i in range(5)]; assert len(cap_history_turns(small)) == 5; many = [{'party_line': f'q{i}', 'replies': [{'npc': 'V', 'reply': f'a{i}'}]} for i in range(15)]; out = cap_history_turns(many); assert len(out) == HISTORY_MAX_TURNS; assert out[-1]['party_line'] == 'q14'; assert out[0]['party_line'] == 'q5'; huge = [{'party_line': 'x' * 12000, 'replies': []}]; assert cap_history_turns(huge) == []; print('OK')"</automated>
</task>

</tasks>

<verification>
After all 3 tasks complete:

```bash
# 1. All symbols importable
cd modules/pathfinder && python -c "from app.dialogue import (
    MOOD_ORDER, MOOD_TONE_GUIDANCE, HISTORY_MAX_TURNS, HISTORY_MAX_TOKENS,
    normalize_mood, apply_mood_delta,
    build_system_prompt, build_user_prompt, cap_history_turns,
); print('all symbols OK')"

# 2. Wave 0 stubs that depend ONLY on dialogue.py constants/helpers should now go GREEN once Plan 31-04 wires the route. Verify import surface here.

# 3. AI Deferral Ban check
grep -vE '^\s*#' modules/pathfinder/app/dialogue.py | grep -E '(TODO|FIXME|NotImplementedError|raise NotImplementedError)' && echo "FAIL — deferral markers found" || echo "PASS — no deferrals"

# 4. Test that doesn't depend on route still passes
cd modules/pathfinder && python -m pytest tests/ -q  # existing tests unchanged
```
</verification>

<success_criteria>
- modules/pathfinder/app/dialogue.py exists with: 9 exported symbols (3 constants, 5 functions, 1 _render_history_for_token_count helper considered private).
- All smoke tests in the three tasks exit 0 with `OK`.
- No production code in routes/ or llm.py modified — this plan is single-file.
- The five symbols MOOD_ORDER, MOOD_TONE_GUIDANCE, normalize_mood, apply_mood_delta, build_system_prompt, build_user_prompt, cap_history_turns are ready for Plan 31-03 (uses none) and Plan 31-04 (consumes all).
- AI Deferral Ban: zero TODO/FIXME/NotImplementedError/raise NotImplementedError outside comments.
</success_criteria>

<output>
Create `.planning/phases/31-dialogue-engine/31-31-02-SUMMARY.md` documenting:
- File created: modules/pathfinder/app/dialogue.py with N lines
- Public symbols exported (list)
- Smoke test outputs (3× OK)
- Confirmation that AI Deferral Ban scan returns 0 matches
- Note: prompt builder + mood math + history cap all live; LiteLLM call lands in Plan 31-03; route handler lands in Plan 31-04.
</output>
