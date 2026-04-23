"""LLM helpers for pathfinder module — NPC field extraction via LiteLLM.

Calls litellm.acompletion() directly (no wrapper class).
Uses the project's configured LITELLM_MODEL + LITELLM_API_BASE from settings.
"""
import json
import logging

import litellm

logger = logging.getLogger(__name__)

# Suppress litellm's verbose startup logs
litellm.suppress_debug_info = True


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences that LLMs wrap JSON responses in."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


async def extract_npc_fields(
    name: str,
    description: str,
    model: str,
    api_base: str | None = None,
) -> dict:
    """Call LLM to extract NPC frontmatter fields from a freeform description.

    Returns a dict with keys: name, level (int), ancestry, class, traits (list),
    personality, backstory, mood. Raises json.JSONDecodeError on LLM parse failure.

    Per D-06 and D-07: unspecified fields are randomly filled from PF2e Remaster options.
    Valid ancestries: Human, Elf, Dwarf, Gnome, Halfling, Goblin, Leshy, Ratfolk, Tengu.
    """
    system_prompt = (
        "You are a Pathfinder 2e Remaster NPC generator. "
        "Extract or infer NPC fields from the user description. "
        "Return ONLY a JSON object — no markdown, no explanation — with these exact keys: "
        "name (string), level (integer, default 1 if unspecified), "
        "ancestry (string, randomly choose from: Human, Elf, Dwarf, Gnome, Halfling, Goblin, Leshy, Ratfolk, Tengu if unspecified), "
        "class (string, randomly choose a valid PF2e Remaster class if unspecified), "
        "traits (list of strings, may be empty), "
        "personality (string, 1-2 sentences), "
        "backstory (string, 2-4 sentences), "
        "mood (string, always 'neutral' for new NPCs). "
        "Return nothing except the JSON object."
    )
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Name: {name}\nDescription: {description}"},
        ],
        "timeout": 60.0,
    }
    if api_base:
        kwargs["api_base"] = api_base

    response = await litellm.acompletion(**kwargs)
    content = response.choices[0].message.content
    return json.loads(_strip_code_fences(content))


async def generate_npc_reply(
    system_prompt: str,
    user_prompt: str,
    model: str,
    api_base: str | None = None,
) -> dict:
    """LLM dialogue call — returns {reply: str, mood_delta: int} for one NPC turn (DLG-01, DLG-02).

    Single chat call extracts both the in-character reply and the mood shift signal.
    Graceful degradation on JSON parse failure (T-31-SEC-03):
    - Returns {reply: <salvaged prose>, mood_delta: 0}; does NOT raise.
    - Logs WARNING with raw[:200] for diagnosis.

    Caller is responsible for selecting the model (D-27 — chat tier from resolve_model("chat")).
    """
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "timeout": 60.0,
    }
    if api_base:
        kwargs["api_base"] = api_base

    response = await litellm.acompletion(**kwargs)
    raw = response.choices[0].message.content or ""
    stripped = _strip_code_fences(raw).strip()

    try:
        parsed = json.loads(stripped)
        reply = str(parsed.get("reply", stripped)).strip()[:1500]
        delta = parsed.get("mood_delta", 0)
        if not isinstance(delta, int) or delta not in (-1, 0, 1):
            delta = 0
        return {"reply": reply, "mood_delta": delta}
    except json.JSONDecodeError:
        logger.warning(
            "generate_npc_reply: JSON parse failed, salvaging reply text. raw_head=%r",
            raw[:200],
        )
        salvaged = (stripped or "...")[:1500]
        return {"reply": salvaged, "mood_delta": 0}


async def generate_mj_description(
    fields: dict,
    model: str,
    api_base: str | None = None,
) -> str:
    """Generate a comma-separated visual description for a Midjourney token prompt (OUT-02).

    Constrained LLM call: max_tokens=40 limits output to 15-30 tokens (D-10).
    Inputs sanitized (D-11): personality and backstory truncated to 200 chars and
    newlines replaced with spaces before LLM interpolation, blocking prompt injection.
    Returns plain string — NOT JSON-parsed.
    """
    personality = (fields.get("personality") or "")[:200].replace("\n", " ")
    backstory = (fields.get("backstory") or "")[:200].replace("\n", " ")
    traits = ", ".join(fields.get("traits") or [])
    system_prompt = (
        "You are a visual description generator for tabletop RPG character tokens. "
        "Output ONLY a comma-separated list of visual description phrases, 15-30 tokens total. "
        "Describe physical appearance only: features, clothing, expression, posture. "
        "No Midjourney parameters. No prose. No punctuation except commas. "
        "Example output: nervous eyes, disheveled dark clothing, scarred knuckles, hunched posture"
    )
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Ancestry: {fields.get('ancestry', '')}\n"
                    f"Class: {fields.get('class', '')}\n"
                    f"Traits: {traits}\n"
                    f"Personality: {personality}\n"
                    f"Backstory: {backstory}"
                ),
            },
        ],
        "max_tokens": 40,
        "timeout": 30.0,
    }
    if api_base:
        kwargs["api_base"] = api_base

    response = await litellm.acompletion(**kwargs)
    return response.choices[0].message.content.strip()


def build_mj_prompt(fields: dict, description: str) -> str:
    """Assemble the full Midjourney /imagine prompt from description + fixed template (D-09).

    Fixed suffix enforces --ar 1:1 (token aspect) and --no text (no captions).
    """
    ancestry = fields.get("ancestry", "")
    npc_class = fields.get("class", "")
    return (
        f"{description}, {ancestry} {npc_class}, "
        "tabletop RPG portrait token, circular frame, "
        "parchment border, oil painting style, dramatic lighting "
        "--ar 1:1 --q 2 --s 180 --no text"
    )


async def update_npc_fields(
    current_note: str,
    correction: str,
    model: str,
    api_base: str | None = None,
) -> dict:
    """Call LLM to extract changed fields from a freeform correction string.

    Returns a dict of ONLY the fields that changed (e.g., {"level": 7}).
    The caller merges this into the parsed frontmatter and PUTs the full note.

    Per D-10: identity/roleplay fields are returned here. If stats are mentioned,
    caller must handle stats block separately (full stats block replacement).
    """
    system_prompt = (
        "You are a Pathfinder 2e NPC editor. "
        "Given the current NPC note and a freeform correction, "
        "return ONLY a JSON object of the fields that changed. "
        "Keys must be valid NPC frontmatter fields: "
        "name, level, ancestry, class, traits, personality, backstory, mood. "
        "Do not include fields that did not change. "
        "Return nothing except the JSON object."
    )
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Current note:\n{current_note}\n\nCorrection: {correction}"},
        ],
        "timeout": 60.0,
    }
    if api_base:
        kwargs["api_base"] = api_base

    response = await litellm.acompletion(**kwargs)
    content = response.choices[0].message.content
    return json.loads(_strip_code_fences(content))
