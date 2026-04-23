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

Per CLAUDE.md AI Deferral Ban: every helper completes its job; no deferral markers.
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

# Module-scope tiktoken encoder (IN-01): get_encoding is internally cached by
# tiktoken but hoisting matches the idiomatic pattern used in
# sentinel-core/app/services/token_guard.py and avoids a lookup on every call.
_ENC = tiktoken.get_encoding("cl100k_base")


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


# --- Prompt builders (D-21, D-22, RESEARCH Finding 4) ---

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
            lines.append(f'Party: "{turn.get("party_line", "")}"')
            for r in turn.get("replies", []) or []:
                lines.append(f"{r.get('npc', '?')}: {r.get('reply', '')}")
        sections.append("\n".join(lines))

    if this_turn_replies:
        lines = ["--- This turn so far ---"]
        if party_line:
            lines.append(f'Party: "{party_line}"')
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


# --- History budget (D-14, RESEARCH Finding 3) ---

def _render_history_for_token_count(turns: list[dict]) -> str:
    """Render turns as a single string for tiktoken counting (matches build_user_prompt format)."""
    out = []
    for turn in turns:
        out.append(f'Party: "{turn.get("party_line", "")}"')
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
    # Guardrail: token cap drops oldest until under budget (uses module-scope _ENC).
    while capped:
        rendered = _render_history_for_token_count(capped)
        if len(_ENC.encode(rendered)) <= HISTORY_MAX_TOKENS:
            break
        capped = capped[1:]  # drop oldest first
    return capped
