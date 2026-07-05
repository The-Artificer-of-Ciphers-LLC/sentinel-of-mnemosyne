"""Tests for the cartosia NPC field extractor (260427-czb Task 2).

Phase 42-05 (D-09, SC-6): extract_npc() now reaches the LLM through
`app.pf_npc_extract._core_client.complete()` (POST /provider/complete on
sentinel-core) instead of `acompletion_with_profile`/litellm directly, and no
longer forwards a strict `json_schema` response_format (core's passthrough
has no such parameter — see module docstring). These tests patch the
module-level `_core_client` singleton's `complete()` method and assert:

  * The migrated call site reaches core_client.complete() with no
    model/api_base/response_format forwarded (core resolves provider+model
    — SC-6, D-09).
  * The system prompt content (preserve names verbatim, do not invent stats).
  * The returned NpcFields dict shape and values.
  * Defensive errors on truncated / out-of-schema responses.
  * complete() raising propagates unswallowed (extract_npc does not wrap the
    invocation in its own try/except).

No real network calls. Per Behavioral-Test-Only Rule, every test calls
extract_npc() directly and asserts on its observable output.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.pf_npc_extract import (
    NPC_EXTRACTION_SCHEMA,
    NpcExtractionError,
    extract_npc,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _core_result(payload: dict, model: str = "test-model") -> dict:
    """Build a core_client.complete()-shaped result: {content, model}."""
    return {"content": json.dumps(payload), "model": model}


# ---------------------------------------------------------------------------
# Format A — Fenn the Beggar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_format_a_extraction_returns_expected_fields():
    fixture = (
        "# Fenn the Beggar — Level 4 NPC (Scout / Informant)\n\n"
        "**Creature 4** | XP: 200\n\n**AC** 18\n**HP** 42\n"
    )
    fake = _core_result({
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
        "app.pf_npc_extract._core_client.complete",
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
    assert "messages" in kwargs
    assert "client" in kwargs
    # SC-6/D-09: no model/api_base/response_format forwarded to core — core
    # resolves provider+model itself, and the passthrough has no schema param.
    assert "model" not in kwargs
    assert "api_base" not in kwargs
    assert "response_format" not in kwargs

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
    fake = _core_result({
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
        "app.pf_npc_extract._core_client.complete",
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
    """No server-side strict-schema enforcement backs this call anymore
    (Phase 42-05 dropped response_format) — _validate_payload is now the
    PRIMARY, not merely defensive, gate (vl1 hotfix #4 lesson)."""
    fake = _core_result({
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
        "app.pf_npc_extract._core_client.complete",
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
    fake = {"content": '{"name": "X", "ance', "model": "test-model"}
    with patch(
        "app.pf_npc_extract._core_client.complete",
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
    fake = _core_result({
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
        "app.pf_npc_extract._core_client.complete",
        new=AsyncMock(return_value=fake),
    ):
        with pytest.raises(NpcExtractionError):
            await extract_npc("body", "p.md", format="A")


# ---------------------------------------------------------------------------
# complete() raises — propagates unswallowed (T-42-12 posture)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_core_client_raise_propagates_unswallowed():
    """extract_npc does not wrap the core_client.complete() invocation in its
    own try/except, so a transport error surfaces to the caller unswallowed —
    same posture as acompletion_with_profile's transport errors pre-migration."""
    with patch(
        "app.pf_npc_extract._core_client.complete",
        new=AsyncMock(side_effect=httpx.ConnectError("core unreachable")),
    ):
        with pytest.raises(httpx.ConnectError):
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
