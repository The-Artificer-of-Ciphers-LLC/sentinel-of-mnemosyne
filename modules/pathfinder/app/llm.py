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
