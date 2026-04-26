"""Regression tests for pf2e-garbled-llm-response debug session (2026-04-26).

Three bugs fixed:
  Bug 1: LLM topic classifier returning 'misc' for well-known PF2e terms
          (e.g. 'off guard', 'flanking') -> keyword fast-path pre-classifier added.
  Bug 2: Salvage path in generate_ruling_fallback/generate_ruling_from_passages
          accepted garbled/injected LLM output as a valid ruling answer.
  Bug 3: No content sanity gate before the Obsidian cache write, causing a
          single bad LLM response to poison all future similar queries.

Production incident: query 'when does off guard apply between two party members
and a monster' returned hallucinated text containing embedded JSON timestamps,
'[Develer's Manual entry point]' injection markers, and nonsense phrases. The
garbled answer was cached and served to all subsequent similar queries.
"""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Bug 1: Keyword-based topic pre-classifier
# ---------------------------------------------------------------------------


def test_keyword_classify_off_guard_exact():
    """Production query must classify to 'off-guard' via keyword fast-path."""
    from app.rules import keyword_classify_topic

    q = "when does off guard apply between two party members and a monster"
    result = keyword_classify_topic(q)
    assert result == "off-guard", f"Expected 'off-guard', got {result!r}"


def test_keyword_classify_flanking_routes_to_off_guard():
    """Flanking queries route to 'off-guard' (flanking is the mechanism that grants off-guard)."""
    from app.rules import keyword_classify_topic

    assert keyword_classify_topic("how does flanking work") == "off-guard"
    assert keyword_classify_topic("what is the flanking bonus") == "off-guard"
    assert keyword_classify_topic("Flanking a target in PF2e") == "off-guard"


def test_keyword_classify_grapple():
    from app.rules import keyword_classify_topic

    assert keyword_classify_topic("how do I grapple an enemy") == "grapple"
    assert keyword_classify_topic("what happens when I am grabbed") == "grapple"


def test_keyword_classify_no_match_returns_none():
    """Queries with no keyword match return None — fall through to LLM classifier."""
    from app.rules import keyword_classify_topic

    # Treasure, encumbrance, subsystems, downtime have no keyword entries — fall through to LLM.
    assert keyword_classify_topic("how does treasure identification work") is None
    assert keyword_classify_topic("what is the encumbrance limit for a fighter") is None
    assert keyword_classify_topic("how does downtime work in PF2e") is None


def test_keyword_classify_empty_and_none_return_none():
    from app.rules import keyword_classify_topic

    assert keyword_classify_topic("") is None
    assert keyword_classify_topic(None) is None  # type: ignore[arg-type]


def test_keyword_classify_case_insensitive():
    """Keyword matching must be case-insensitive."""
    from app.rules import keyword_classify_topic

    assert keyword_classify_topic("OFF GUARD condition in PF2e") == "off-guard"
    assert keyword_classify_topic("FLANKING rules") == "off-guard"


# ---------------------------------------------------------------------------
# Bug 2+3: Content sanity gate (check_ruling_answer_sanity)
# ---------------------------------------------------------------------------


def test_sanity_rejects_embedded_json_timestamp():
    """Answer containing embedded JSON timestamp field must raise ValueError."""
    from app.rules import check_ruling_answer_sanity

    garbled = (
        'Some preamble text.\n\n'
        '{\n    "timestamp": 156075248,\n    "comment_likelihood": {"likeliness": -1}\n}'
    )
    with pytest.raises(ValueError, match="injection/garble"):
        check_ruling_answer_sanity(garbled)


def test_sanity_rejects_develer_manual_marker():
    """Injection marker '[Develer' must be caught."""
    from app.rules import check_ruling_answer_sanity

    with pytest.raises(ValueError, match="injection/garble"):
        check_ruling_answer_sanity(
            "Off-Guard applies when [Develer's Manual entry point] the creature is flanked."
        )


def test_sanity_rejects_entry_point_marker():
    """Generic 'entry point' injection phrase must be caught."""
    from app.rules import check_ruling_answer_sanity

    with pytest.raises(ValueError, match="injection/garble"):
        check_ruling_answer_sanity(
            "Some answer text. entry point injection payload here."
        )


def test_sanity_rejects_big_smooch_nonsense():
    """Specific hallucinated phrase from production incident must be caught."""
    from app.rules import check_ruling_answer_sanity

    with pytest.raises(ValueError, match="injection/garble"):
        check_ruling_answer_sanity(
            "Yielding to the big-big smooch, I'll be the one who makes the rules."
        )


def test_sanity_rejects_comment_likelihood_json():
    """JSON key 'comment_likelihood' from production garble must be caught."""
    from app.rules import check_ruling_answer_sanity

    with pytest.raises(ValueError, match="injection/garble"):
        check_ruling_answer_sanity('Answer: {"comment_likelihood": {"likeliness": -1}}')


def test_sanity_rejects_too_short():
    """Salvaged answers with fewer than 8 words are rejected (not a real ruling)."""
    from app.rules import check_ruling_answer_sanity

    with pytest.raises(ValueError, match="too short"):
        check_ruling_answer_sanity("Off-guard.")

    with pytest.raises(ValueError, match="too short"):
        check_ruling_answer_sanity("Yes. No.")


def test_sanity_rejects_empty_by_default():
    from app.rules import check_ruling_answer_sanity

    with pytest.raises(ValueError):
        check_ruling_answer_sanity("")


def test_sanity_accepts_empty_when_allow_empty_true():
    """allow_empty=True bypasses the empty/short checks (for declined rulings)."""
    from app.rules import check_ruling_answer_sanity

    check_ruling_answer_sanity("", allow_empty=True)  # must not raise


def test_sanity_accepts_legitimate_pf2e_ruling():
    """A proper PF2e ruling passes all sanity checks."""
    from app.rules import check_ruling_answer_sanity

    check_ruling_answer_sanity(
        "Off-Guard applies when a creature cannot fully defend itself. "
        "When two allies are flanking an enemy (one on each side of the enemy), "
        "that enemy gains the off-guard condition against both attackers, "
        "taking a -2 circumstance penalty to its AC."
    )


def test_sanity_accepts_short_but_legitimate_ruling():
    """A ruling with exactly 8+ words and no garble markers passes."""
    from app.rules import check_ruling_answer_sanity

    # 9 words — above the minimum threshold
    check_ruling_answer_sanity(
        "Off-guard imposes a minus two penalty to armor class."
    )


# ---------------------------------------------------------------------------
# Bug 2: Salvage path raises instead of caching garbled output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_ruling_fallback_garbled_prose_raises():
    """When the LLM returns non-JSON garbled prose, the salvage path must raise
    ValueError (not return the garble as a valid answer). This prevents caching poison."""
    garbled_prose = (
        '"I\'ll be the one who makes the rules" is a fun way.\n\n'
        '{\n    "timestamp": 156075248\n}\n\n'
        '[Develer\'s Manual entry point]\nHere be a big smooch.'
    )
    mock_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=garbled_prose))]
    )
    with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        from app.llm import generate_ruling_fallback

        with pytest.raises(ValueError, match="injection/garble"):
            await generate_ruling_fallback(
                query="when does off guard apply",
                topic="off-guard",
                model="openai/x",
                api_base=None,
            )


@pytest.mark.asyncio
async def test_generate_ruling_from_passages_garbled_prose_raises():
    """Salvage path in generate_ruling_from_passages also rejects garbled output."""
    from app.rules import RuleChunk

    garbled_prose = (
        "Here be a big smooch. entry point injection.\n"
        '{"timestamp": 999, "comment_likelihood": {"likeliness": -1}}'
    )
    mock_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=garbled_prose))]
    )
    chunk = RuleChunk(
        id="test", book="Player Core", page="1", section="Off-Guard",
        text="Off-Guard imposes a -2 penalty to AC.", topics=["off-guard"],
    )
    passages = [(chunk, 0.85)]

    with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        from app.llm import generate_ruling_from_passages

        with pytest.raises(ValueError, match="injection/garble"):
            await generate_ruling_from_passages(
                query="when does off guard apply",
                passages=passages,
                topic="off-guard",
                model="openai/x",
                api_base=None,
            )


@pytest.mark.asyncio
async def test_generate_ruling_fallback_valid_salvage_passes():
    """Valid prose (non-JSON but clean text) that passes the sanity gate is accepted."""
    valid_prose = (
        "Off-Guard applies when a creature is flanked by two allies on opposite sides. "
        "The creature takes a -2 circumstance penalty to its AC while off-guard. "
        "Flanking requires two allies to be on opposite sides and threatening the target. "
        "See Player Core for the complete flanking rules."
    )
    mock_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=valid_prose))]
    )
    with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        from app.llm import generate_ruling_fallback

        result = await generate_ruling_fallback(
            query="when does off guard apply",
            topic="off-guard",
            model="openai/x",
            api_base=None,
        )
    assert result["answer"] == valid_prose[:2000]
    assert result["marker"] == "generated"
    assert result["topic"] == "off-guard"
