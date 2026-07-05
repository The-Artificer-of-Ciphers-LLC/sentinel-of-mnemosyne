"""Cartosia NPC field extractor (260427-czb Task 2).

Phase 42 (D-09, SC-6): the archive-import NPC-extraction chat call site
reaches the LLM through sentinel-core's POST /provider/complete via
``SentinelCoreClient.complete()`` (core resolves provider/model — exo/LM
Studio selection + fallback are centralized on the core side). This module
no longer calls litellm directly, and no longer forwards a strict
``json_schema`` ``response_format`` — ``SentinelCoreClient.complete()``'s
contract is ``{messages, client, stop, temperature}`` only (per 42-03/42-04),
so schema conformance is enforced by the system prompt below plus
``_validate_payload()`` rather than by LM Studio's ``json_schema`` strict
mode this module relied on pre-42-05 (vl1 hotfix #4: LM Studio rejects
``response_format={"type": "json_object"}``, so a prior version of this
module used ``json_schema`` strict mode instead).

Per CLAUDE.md AI Deferral Ban + project memory `feedback_no_deferral`:
the schema enforces enum on mood, integer 1-20 on level, all required
Phase 29 fields. Defaults (level=1, ancestry=Human, mood=neutral, traits=[])
are taught to the model via the system prompt — ``_validate_payload`` is now
the PRIMARY (not merely defensive) gate on schema conformance, since no
server-side strict-schema enforcement backs it anymore.

Returns a dict ready for inclusion in the NPC frontmatter. The caller
(``cartosia_import.write_npc``) appends ``relationships=[]``,
``imported_from='cartosia-archive'``, ``imported_at=<iso>``, and
``token_image=<set later or None>``.
"""
from __future__ import annotations

import json
import logging
from typing import Literal

import httpx

from app.config import settings
from sentinel_client import SentinelCoreClient

logger = logging.getLogger(__name__)

# pf2e -> sentinel-core chat handoff (D-09, SC-6). Single client instance built
# from existing settings (no new URL literal) — mirrors the module-level
# SentinelCoreClient singleton convention established in app/llm.py (42-04).
_core_client = SentinelCoreClient(
    base_url=settings.sentinel_core_url,
    api_key=settings.sentinel_api_key,
)


class NpcExtractionError(Exception):
    """Raised when the LLM response cannot be parsed into a valid NpcFields dict.

    The error message embeds the raw LLM response (truncated) so the
    cartosia_import dry-run report can surface it to the operator.
    """


# ---------------------------------------------------------------------------
# JSON schema — documents the required NPC-field shape and backs
# ``_validate_payload``'s enum/range/required-field checks below. Phase 42
# (D-09): no longer forwarded to the LLM as a ``response_format`` constraint
# (core's ``/provider/complete`` passthrough has no such parameter) — it is
# now purely a local validation reference.
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
    user_prompt = _USER_PROMPT_TEMPLATE.format(
        filepath=source_path, format=format, raw_markdown=content
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    async with httpx.AsyncClient() as client:
        result = await _core_client.complete(
            messages=messages,
            client=client,
            temperature=0.0,
        )
    raw = (result["content"] or "").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NpcExtractionError(
            f"NPC extraction returned invalid JSON: {exc}; raw response: {raw[:500]}"
        ) from exc

    _validate_payload(payload, raw=raw)
    return payload


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
