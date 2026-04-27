"""Cartosia NPC field extractor (260427-czb Task 2).

Calls ``acompletion_with_profile`` from sentinel_shared.llm_call ONCE per NPC
with strict ``json_schema`` mode. Per vl1 hotfix #4: LM Studio rejects
``response_format={"type": "json_object"}`` — we MUST use json_schema.

Per CLAUDE.md AI Deferral Ban + project memory `feedback_no_deferral`:
the schema enforces enum on mood, integer 1–20 on level, all required
Phase 29 fields. Defaults (level=1, ancestry=Human, mood=neutral, traits=[])
are taught to the model via the system prompt — defense-in-depth runtime
validation rejects out-of-schema responses (defensive, since strict mode
should already catch them at the LM Studio layer).

Returns a dict ready for inclusion in the NPC frontmatter. The caller
(``cartosia_import.write_npc``) appends ``relationships=[]``,
``imported_from='cartosia-archive'``, ``imported_at=<iso>``, and
``token_image=<set later or None>``.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Literal

from sentinel_shared.llm_call import acompletion_with_profile

logger = logging.getLogger(__name__)


class NpcExtractionError(Exception):
    """Raised when the LLM response cannot be parsed into a valid NpcFields dict.

    The error message embeds the raw LLM response (truncated) so the
    cartosia_import dry-run report can surface it to the operator.
    """


# ---------------------------------------------------------------------------
# JSON schema — sent to LM Studio under {"type": "json_schema", "strict": True}
# ---------------------------------------------------------------------------

NPC_EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "ancestry": {"type": "string"},
        "class": {"type": "string"},
        "level": {"type": "integer", "minimum": 1, "maximum": 20},
        "mood": {
            "type": "string",
            "enum": ["neutral", "friendly", "hostile", "wary", "curious"],
        },
        "personality": {"type": "string", "maxLength": 400},
        "backstory": {"type": "string", "maxLength": 600},
        "traits": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "name",
        "ancestry",
        "class",
        "level",
        "personality",
        "backstory",
        "traits",
        "mood",
    ],
    "additionalProperties": False,
}


_SYSTEM_PROMPT = """You extract Pathfinder 2e NPC fields from raw markdown.
Return ONLY the JSON matching the schema. Do not invent stats — if the source
omits a field, use the most defensible default:
- level: 1 if no creature-level cue (Format B characters are usually level 1-3 commoners)
- ancestry: "Human" if not stated
- class: a PF2e class name OR a 1-2 word role descriptor (e.g. "Trapper", "Beggar")
- mood: "neutral"
- traits: [] (only fill if the source explicitly lists PF2e traits)
- personality: <=2 sentences, in third person, present tense
- backstory: <=3 sentences, in third person, past tense

Preserve the NPC's name verbatim — including punctuation, ampersands, and
"and"/"&" conjunctions for two-NPC files (e.g. "Veela and Tarek")."""


_USER_PROMPT_TEMPLATE = """Source file: {filepath}
Format: {format}

---
{raw_markdown}
---

Extract NPC fields per schema."""


_VALID_MOODS = frozenset(NPC_EXTRACTION_SCHEMA["properties"]["mood"]["enum"])
_REQUIRED_FIELDS = frozenset(NPC_EXTRACTION_SCHEMA["required"])


# ---------------------------------------------------------------------------
# Model resolver — uses LM Studio's loaded models if available, else falls
# back to MODEL_PREFERRED env var (the canonical path used by every other
# pathfinder LLM call site; we don't write a 4th prefix-handling site).
# ---------------------------------------------------------------------------


def _resolve_structured_model() -> tuple[str, str | None]:
    """Return (model_id, api_base) for the 'structured' profile.

    Honours MODEL_PREFERRED (operator override) and falls back to the
    sentinel-core default. Adds the litellm 'openai/' prefix if missing.
    """
    api_base = os.environ.get("LMSTUDIO_BASE_URL") or "http://host.docker.internal:1234"
    api_base_v1 = api_base.rstrip("/")
    if not api_base_v1.endswith("/v1"):
        api_base_v1 = f"{api_base_v1}/v1"
    preferred = (
        os.environ.get("MODEL_PREFERRED")
        or os.environ.get("MODEL_NAME")
        or "qwen3.6-35b-a3b"
    )
    if "/" not in preferred and not preferred.startswith("openai/"):
        preferred = f"openai/{preferred}"
    return preferred, api_base_v1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def extract_npc(
    content: str,
    source_path: str,
    *,
    format: Literal["A", "B"],
) -> dict:
    """Extract Phase 29-compliant NPC frontmatter fields from raw markdown.

    Args:
      content: the raw markdown body of the source file.
      source_path: the relative archive path, included verbatim in the user
        prompt so the LLM can use filename hints when the body is sparse.
      format: "A" (PF2e stat block) or "B" (Biography + Appearance).

    Returns:
      A dict with all 8 required schema keys. The caller adds
      relationships, imported_from, imported_at, and token_image.

    Raises:
      NpcExtractionError: response is not valid JSON, fails schema
        validation, or is missing required fields.
    """
    model, api_base = _resolve_structured_model()
    user_prompt = _USER_PROMPT_TEMPLATE.format(
        filepath=source_path, format=format, raw_markdown=content
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    response = await acompletion_with_profile(
        model=model,
        messages=messages,
        api_base=api_base,
        api_key="lmstudio",  # litellm requires a non-empty key; LM Studio ignores it
        timeout=60.0,
        temperature=0.0,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "npc",
                "strict": True,
                "schema": NPC_EXTRACTION_SCHEMA,
            },
        },
    )

    raw = _extract_content(response)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NpcExtractionError(
            f"NPC extraction returned invalid JSON: {exc}; raw response: {raw[:500]}"
        ) from exc

    _validate_payload(payload, raw=raw)
    return payload


def _extract_content(response) -> str:
    """Pull the message content from a litellm response (dict or pydantic).

    Handles the qwen3 thinking-mode quirk where strict json_schema can land
    in reasoning_content rather than content (note_classifier comment).
    """
    try:
        if isinstance(response, dict):
            msg = response["choices"][0]["message"]
            return (msg.get("content") or msg.get("reasoning_content") or "").strip()
        msg = response.choices[0].message  # type: ignore[attr-defined]
        return (
            getattr(msg, "content", None)
            or getattr(msg, "reasoning_content", None)
            or ""
        ).strip()
    except (KeyError, IndexError, AttributeError) as exc:
        raise NpcExtractionError(f"unexpected LLM response shape: {exc}") from exc


def _validate_payload(payload: dict, *, raw: str) -> None:
    if not isinstance(payload, dict):
        raise NpcExtractionError(
            f"expected JSON object, got {type(payload).__name__}; raw: {raw[:500]}"
        )
    missing = _REQUIRED_FIELDS - set(payload.keys())
    if missing:
        raise NpcExtractionError(
            f"missing required fields: {sorted(missing)}; raw: {raw[:500]}"
        )
    if payload["mood"] not in _VALID_MOODS:
        raise NpcExtractionError(
            f"invalid mood '{payload['mood']}' (not in {sorted(_VALID_MOODS)}); raw: {raw[:500]}"
        )
    level = payload["level"]
    if not isinstance(level, int) or not (1 <= level <= 20):
        raise NpcExtractionError(
            f"invalid level {level!r} (must be int 1-20); raw: {raw[:500]}"
        )
    if not isinstance(payload["traits"], list):
        raise NpcExtractionError(
            f"traits must be a list, got {type(payload['traits']).__name__}; raw: {raw[:500]}"
        )
