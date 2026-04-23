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
