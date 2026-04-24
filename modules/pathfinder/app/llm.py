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

# Cap per-NPC reply length so multi-NPC scenes rendered as stacked "> " quote
# markdown stay under Discord's 2000-char message limit (IN-03).
_MAX_REPLY_CHARS = 1500  # leaves headroom under Discord's 2000-char limit once wrapped in "> " quote markdown across multi-NPC scenes


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
        reply = str(parsed.get("reply", stripped)).strip()[:_MAX_REPLY_CHARS]
        delta = parsed.get("mood_delta", 0)
        if not isinstance(delta, int) or delta not in (-1, 0, 1):
            delta = 0
        return {"reply": reply, "mood_delta": delta}
    except json.JSONDecodeError:
        logger.warning(
            "generate_npc_reply: JSON parse failed, salvaging reply text. raw_head=%r",
            raw[:200],
        )
        salvaged = (stripped or "...")[:_MAX_REPLY_CHARS]
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


async def generate_harvest_fallback(
    monster_name: str,
    model: str,
    api_base: str | None = None,
) -> dict:
    """Generate a harvest table for an unseeded monster (D-02 LLM fallback).

    Grounds the LLM in the canonical DC-by-level table (GM Core pg. 52, levels 0-25)
    embedded verbatim in the system prompt, plus a sampled equipment-price reference
    so DCs and vendor values land in plausible ranges.

    Returns a dict stamped with source='llm-generated' AND verified=False (SC-4).
    Post-parse DC sanity clamp overwrites any component medicine_dc that doesn't
    match DC_BY_LEVEL for the stated monster level (Pitfall 4 mitigation).

    Raises on malformed JSON — the route layer (Plan 32-04) catches and returns 500.
    Do NOT salvage a partial result; a half-result cached would poison the DM's data.
    """
    # Function-scope import breaks the app.llm -> app.harvest -> app.routes.npc -> app.llm
    # cycle (app.routes.npc imports build_mj_prompt / extract_npc_fields / etc. from this
    # module at module load). A module-scope `from app.harvest import DC_BY_LEVEL` would
    # deadlock the import machinery. Rule 3 blocking-issue fix — documented in SUMMARY.
    from app.harvest import DC_BY_LEVEL

    system_prompt = (
        "You are a Pathfinder 2e Remaster DM assistant. "
        "Given a monster name, return a JSON object describing harvestable components "
        "and craftable items. Ground your DCs in the PF2e DC-by-level table (GM Core pg. 52):\n"
        "Level 0: DC 14, Level 1: DC 15, Level 2: DC 16, Level 3: DC 18, "
        "Level 4: DC 19, Level 5: DC 20, Level 6: DC 22, Level 7: DC 23, "
        "Level 8: DC 24, Level 9: DC 26, Level 10: DC 27, Level 11: DC 28, "
        "Level 12: DC 30, Level 13: DC 31, Level 14: DC 32, Level 15: DC 34, "
        "Level 16: DC 35, Level 17: DC 36, Level 18: DC 38, Level 19: DC 39, "
        "Level 20: DC 40, Level 21: DC 42, Level 22: DC 44, Level 23: DC 46, "
        "Level 24: DC 48, Level 25: DC 50. "
        "Hard components add +2; unusual materials add +5.\n\n"
        "Sample craftable vendor values (from Paizo equipment): "
        "Leather armor 2 gp, Dagger 2 sp, Torch 1 cp, Healing potion (lesser) 12 gp, "
        "Antidote (lesser) 10 gp, Poison (lesser arsenic) 12 gp.\n\n"
        "Return ONLY a JSON object — no markdown, no code fences — with these exact keys:\n"
        '  "monster": string (the input name),\n'
        '  "level": integer (your best estimate; default 1 if ambiguous),\n'
        '  "components": list of objects, each with:\n'
        '    "type": string (e.g., "Hide", "Claws", "Venom gland"),\n'
        '    "medicine_dc": integer (use the DC table above),\n'
        '    "craftable": list of objects, each with:\n'
        '      "name": string (item name),\n'
        '      "crafting_dc": integer (use item level against the DC table),\n'
        '      "value": string (e.g., "2 gp" or "5 sp" or "3 cp").\n'
        "Return nothing except the JSON object."
    )
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Monster: {monster_name}"},
        ],
        "timeout": 60.0,
    }
    if api_base:
        kwargs["api_base"] = api_base

    response = await litellm.acompletion(**kwargs)
    content = response.choices[0].message.content
    parsed = json.loads(_strip_code_fences(content))

    # Stamp source + verified per SC-4 / T-32-LLM-01.
    parsed["source"] = "llm-generated"
    parsed["verified"] = False

    # DC sanity clamp (Pitfall 4) — trust the table, not the LLM.
    level = parsed.get("level")
    if isinstance(level, int) and level in DC_BY_LEVEL:
        expected_dc = DC_BY_LEVEL[level]
        for comp in parsed.get("components", []) or []:
            if isinstance(comp, dict):
                observed = comp.get("medicine_dc")
                if isinstance(observed, int) and observed != expected_dc:
                    logger.warning(
                        "LLM harvest DC mismatch for %s: level=%d observed_dc=%d expected=%d (overwriting)",
                        monster_name, level, observed, expected_dc,
                    )
                    comp["medicine_dc"] = expected_dc
    return parsed
