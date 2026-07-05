"""Tests for the pf2e -> sentinel-core chat handoff (Phase 42-04, D-09, SC-6).

llm.py's chat/completion call sites now reach the LLM exclusively through
`app.llm._core_client.complete()` (POST /provider/complete on sentinel-core)
instead of `sentinel_shared.llm_call.acompletion_with_profile` /
`litellm.acompletion` directly. These tests patch the module-level
`_core_client` singleton's `complete()` method and assert:

  1. The migrated functions call core_client.complete() with no model/api_base
     forwarded (core resolves provider + model — SC-6, D-09).
  2. They correctly consume `result["content"]` from complete()'s
     {content, model} return.
  3. Their pre-existing JSON-parse/salvage/citation-framing logic is preserved
     byte-for-byte around the new invocation line.
  4. complete() raising (not swallowing) still surfaces as a real exception
     to callers that don't wrap it (T-42-09) — no new swallow-to-string
     behavior was introduced at the migration boundary.

Task 1 covers the free-text/simple sites: generate_npc_reply,
generate_ruling_from_passages, generate_ruling_fallback,
generate_session_recap, generate_mj_description.

Task 2 extends this file with the structured (JSON-contract) sites:
extract_npc_fields, update_npc_fields, generate_harvest_fallback,
classify_rule_topic, generate_story_so_far.
"""
import json
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.llm import (
    generate_mj_description,
    generate_npc_reply,
    generate_ruling_fallback,
    generate_ruling_from_passages,
    generate_session_recap,
)
from app.rules import RuleChunk


def _core_result(content: str, model: str = "test-model") -> dict:
    """Build a minimal core_client.complete()-shaped result: {content, model}."""
    return {"content": content, "model": model}


# ---------------------------------------------------------------------------
# generate_npc_reply — free-text dialogue call site (DLG-01/02)
# ---------------------------------------------------------------------------


async def test_generate_npc_reply_consumes_core_client_content():
    with patch(
        "app.llm._core_client.complete",
        new=AsyncMock(return_value=_core_result('{"reply": "Hello there.", "mood_delta": 1}')),
    ) as mock_complete:
        result = await generate_npc_reply(
            system_prompt="You are Varek.",
            user_prompt="Hello!",
            model="unused-because-core-resolves-it",
            api_base="unused-because-core-resolves-it",
        )

    assert result == {"reply": "Hello there.", "mood_delta": 1}
    mock_complete.assert_awaited_once()
    kwargs = mock_complete.await_args.kwargs
    assert "messages" in kwargs
    assert "client" in kwargs
    # SC-6/D-09: no model/api_base forwarded to core — core resolves both.
    assert "model" not in kwargs
    assert "api_base" not in kwargs


async def test_generate_npc_reply_json_parse_failure_still_salvages():
    """Pre-existing salvage path (T-31-SEC-03) still fires with the new content source."""
    with patch(
        "app.llm._core_client.complete",
        new=AsyncMock(return_value=_core_result("this is plain prose, no JSON at all")),
    ):
        result = await generate_npc_reply(
            system_prompt="sys", user_prompt="user", model="m",
        )
    assert result["reply"] == "this is plain prose, no JSON at all"
    assert result["mood_delta"] == 0


async def test_generate_npc_reply_core_raise_propagates_unswallowed():
    """complete() raises (T-42-09 mitigation posture) — generate_npc_reply does
    not wrap the invocation, so the exception surfaces to the caller unswallowed,
    same as acompletion_with_profile's transport errors did pre-migration."""
    with patch(
        "app.llm._core_client.complete",
        new=AsyncMock(side_effect=httpx.ConnectError("core unreachable")),
    ):
        with pytest.raises(httpx.ConnectError):
            await generate_npc_reply(system_prompt="sys", user_prompt="user", model="m")


# ---------------------------------------------------------------------------
# generate_ruling_from_passages — corpus-hit composer (D-08, marker='source')
# ---------------------------------------------------------------------------


async def test_generate_ruling_from_passages_uses_core_client_and_preserves_citations():
    chunk = RuleChunk(
        id="test", book="Player Core", page="1", section="Off-Guard",
        text="Off-Guard imposes a -2 penalty to AC.", topics=["off-guard"],
    )
    passages = [(chunk, 0.9)]
    with patch(
        "app.llm._core_client.complete",
        new=AsyncMock(return_value=_core_result(
            json.dumps({"question": "q", "answer": "a", "why": "w", "marker": "source"})
        )),
    ) as mock_complete:
        result = await generate_ruling_from_passages(
            query="does off-guard apply",
            passages=passages,
            topic="off-guard",
            model="m",
        )

    assert result["marker"] == "source"
    # Citations are caller-derived from passage metadata — never from the LLM.
    assert result["citations"][0]["book"] == "Player Core"
    assert result["source"]  # non-empty citation label, derived from the chunk
    mock_complete.assert_awaited_once()
    assert "model" not in mock_complete.await_args.kwargs
    assert "api_base" not in mock_complete.await_args.kwargs


# ---------------------------------------------------------------------------
# generate_ruling_fallback — corpus-miss composer (D-08, marker='generated')
# ---------------------------------------------------------------------------


async def test_generate_ruling_fallback_uses_core_client_generated_marker():
    with patch(
        "app.llm._core_client.complete",
        new=AsyncMock(return_value=_core_result(
            json.dumps({"question": "q", "answer": "a", "why": "w"})
        )),
    ) as mock_complete:
        result = await generate_ruling_fallback(query="q", topic="misc", model="m")

    assert result["marker"] == "generated"
    assert result["source"] is None
    assert result["citations"] == []
    mock_complete.assert_awaited_once()


# ---------------------------------------------------------------------------
# generate_session_recap — structured session recap composer (SES-01..03)
# ---------------------------------------------------------------------------


async def test_generate_session_recap_uses_core_client_and_parses_required_keys():
    payload = {
        "recap": "It happened.",
        "npcs": ["varek"],
        "locations": ["Westcrown"],
        "npc_notes_per_character": {"varek": "note"},
    }
    with patch(
        "app.llm._core_client.complete",
        new=AsyncMock(return_value=_core_result(json.dumps(payload))),
    ) as mock_complete:
        result = await generate_session_recap(
            events_log="stuff happened", npc_frontmatter_block="", model="m",
        )

    assert result == payload
    mock_complete.assert_awaited_once()


# ---------------------------------------------------------------------------
# generate_mj_description — plain-string MJ token prompt helper (OUT-02)
# ---------------------------------------------------------------------------


async def test_generate_mj_description_uses_core_client_returns_plain_string():
    with patch(
        "app.llm._core_client.complete",
        new=AsyncMock(return_value=_core_result("nervous eyes, disheveled clothing")),
    ) as mock_complete:
        result = await generate_mj_description(
            fields={
                "ancestry": "Gnome", "class": "Rogue", "traits": [],
                "personality": "p", "backstory": "b",
            },
            model="m",
        )

    assert result == "nervous eyes, disheveled clothing"
    mock_complete.assert_awaited_once()
