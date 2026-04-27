"""Tests for the cartosia NPC field extractor (260427-czb Task 2).

Mocks the LLM call. Asserts on:
  * The actual structure of the request sent to acompletion_with_profile
    (response_format must be json_schema strict, not json_object).
  * The system prompt content (preserve names verbatim, do not invent stats).
  * The returned NpcFields dict shape and values.
  * Defensive errors on truncated / out-of-schema responses.

No real network calls. Per Behavioral-Test-Only Rule, every test calls
extract_npc() directly and asserts on its observable output.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.cartosia_npc_extract import (
    NPC_EXTRACTION_SCHEMA,
    NpcExtractionError,
    extract_npc,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_llm_response(payload: dict) -> dict:
    """Shape a fake litellm response around the given JSON payload."""
    return {
        "choices": [
            {"message": {"content": json.dumps(payload), "reasoning_content": ""}}
        ]
    }


# ---------------------------------------------------------------------------
# Format A — Fenn the Beggar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_format_a_extraction_returns_expected_fields():
    fixture = (
        "# Fenn the Beggar — Level 4 NPC (Scout / Informant)\n\n"
        "**Creature 4** | XP: 200\n\n**AC** 18\n**HP** 42\n"
    )
    fake = _mock_llm_response({
        "name": "Fenn the Beggar",
        "ancestry": "Human",
        "class": "Scout",
        "level": 4,
        "mood": "neutral",
        "personality": "Acts like a beggar; sharp underneath.",
        "backstory": "Operates from North House as an informant.",
        "traits": [],
    })
    with patch(
        "app.cartosia_npc_extract.acompletion_with_profile",
        new=AsyncMock(return_value=fake),
    ) as mock:
        fields = await extract_npc(fixture, "The NPCs/Fenn the Beggar.md", format="A")

    assert fields["name"] == "Fenn the Beggar"
    assert fields["level"] == 4
    assert fields["class"] == "Scout"
    assert fields["mood"] == "neutral"
    assert fields["traits"] == []

    # Verify the LLM call shape — Behavioral-Test-Only: assert on actual
    # request contents, not just call count.
    assert mock.await_count == 1
    kwargs = mock.await_args.kwargs
    rf = kwargs["response_format"]
    assert rf["type"] == "json_schema", "must use json_schema strict, not json_object (LM Studio rejects json_object)"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"] == NPC_EXTRACTION_SCHEMA

    # System prompt must explicitly tell the model not to invent stats and
    # to preserve names verbatim.
    messages = kwargs["messages"]
    sys_msg = next(m for m in messages if m["role"] == "system")
    assert "do not invent" in sys_msg["content"].lower() or "not invent" in sys_msg["content"].lower()
    user_msg = next(m for m in messages if m["role"] == "user")
    assert "Format: A" in user_msg["content"]
    assert "The NPCs/Fenn the Beggar.md" in user_msg["content"]


# ---------------------------------------------------------------------------
# Format B — Alice Twoorb
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_format_b_extraction_preserves_default_level():
    fixture = (
        "### Biography\n\nTrapper.\n\n### Appearance\n\nLong gray hair.\n\n"
        "**Age: 32**\n\n**Location**: Otari\n"
    )
    fake = _mock_llm_response({
        "name": "Alice Twoorb",
        "ancestry": "Human",
        "class": "Trapper",
        "level": 1,
        "mood": "neutral",
        "personality": "Bores easily; whispers when she speaks.",
        "backstory": "Has lived in Otari her whole life.",
        "traits": [],
    })
    with patch(
        "app.cartosia_npc_extract.acompletion_with_profile",
        new=AsyncMock(return_value=fake),
    ):
        fields = await extract_npc(
            fixture, "Cartosia/Ostenwald/Otari/Alice Twoorb.md", format="B"
        )

    assert fields["name"] == "Alice Twoorb"
    assert fields["level"] == 1  # default for Format B per system prompt
    assert fields["class"] == "Trapper"


# ---------------------------------------------------------------------------
# Defensive: out-of-schema mood
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_out_of_schema_mood_raises_extraction_error():
    """Strict json_schema should make this impossible at the LM Studio layer,
    but the extractor must defend against it (vl1 hotfix #4 lesson)."""
    fake = _mock_llm_response({
        "name": "X",
        "ancestry": "Human",
        "class": "Y",
        "level": 1,
        "mood": "grumpy",  # not in enum
        "personality": "p",
        "backstory": "b",
        "traits": [],
    })
    with patch(
        "app.cartosia_npc_extract.acompletion_with_profile",
        new=AsyncMock(return_value=fake),
    ):
        with pytest.raises(NpcExtractionError) as exc_info:
            await extract_npc("body", "p.md", format="A")
    assert "mood" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Defensive: truncated JSON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_truncated_json_raises_extraction_error_with_raw_response():
    fake = {"choices": [{"message": {"content": '{"name": "X", "ance', "reasoning_content": ""}}]}
    with patch(
        "app.cartosia_npc_extract.acompletion_with_profile",
        new=AsyncMock(return_value=fake),
    ):
        with pytest.raises(NpcExtractionError) as exc_info:
            await extract_npc("body", "p.md", format="A")
    # Raw response must be captured for the dry-run/error report.
    assert '{"name": "X"' in str(exc_info.value)


# ---------------------------------------------------------------------------
# Defensive: missing required field
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_required_field_raises_extraction_error():
    fake = _mock_llm_response({
        # missing 'name'
        "ancestry": "Human",
        "class": "Y",
        "level": 1,
        "mood": "neutral",
        "personality": "p",
        "backstory": "b",
        "traits": [],
    })
    with patch(
        "app.cartosia_npc_extract.acompletion_with_profile",
        new=AsyncMock(return_value=fake),
    ):
        with pytest.raises(NpcExtractionError):
            await extract_npc("body", "p.md", format="A")


# ---------------------------------------------------------------------------
# Schema sanity — required fields and constraints
# ---------------------------------------------------------------------------


def test_schema_requires_phase29_fields_and_enforces_level_range():
    required = set(NPC_EXTRACTION_SCHEMA["required"])
    for field in {"name", "ancestry", "class", "level", "mood", "personality", "backstory", "traits"}:
        assert field in required
    assert NPC_EXTRACTION_SCHEMA["additionalProperties"] is False
    level_spec = NPC_EXTRACTION_SCHEMA["properties"]["level"]
    assert level_spec["minimum"] == 1
    assert level_spec["maximum"] == 20
    mood_enum = NPC_EXTRACTION_SCHEMA["properties"]["mood"]["enum"]
    assert "neutral" in mood_enum
