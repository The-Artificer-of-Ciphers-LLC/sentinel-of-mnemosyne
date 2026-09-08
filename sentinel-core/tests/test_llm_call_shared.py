"""Tests for sentinel_shared.llm_call.

After Task 1 of 260427-vl1: ``acompletion_with_profile`` lives in
sentinel_shared so both sentinel-core and the pathfinder module can import the
same helper.

ADR-0007 step 3 adds ``extract_completion_text`` beside it — the single reader of
the raw response that wrapper returns, replacing six hand-written copies of the
``content or reasoning_content`` fallback.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from sentinel_shared.llm_call import acompletion_with_profile, extract_completion_text
from sentinel_shared.model_profiles import FamilyProfile


def _make_profile(stop: list[str] | None) -> FamilyProfile:
    """Build a minimal profile carrying just the stop_sequences we care about."""
    # ADR-0007 step 5: the wrapper's parameter is the structural
    # ``HasStopSequences`` protocol, not a named class — there are two
    # legitimate profile types and this helper only has to satisfy the one
    # attribute the wrapper reads.
    try:
        return FamilyProfile(family="test", stop_sequences=stop)  # type: ignore[call-arg]
    except TypeError:
        # Fallback: SimpleNamespace-style if the dataclass signature differs.
        from types import SimpleNamespace

        return SimpleNamespace(stop_sequences=stop)  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_stop_sequences_pass_through():
    """Test 2: profile.stop_sequences=['</end>'] is forwarded as kwargs['stop']."""
    profile = _make_profile(["</end>"])
    with patch("sentinel_shared.llm_call.litellm.acompletion", new=AsyncMock(return_value="ok")) as mock_acomp:
        await acompletion_with_profile(
            model="openai/test-model",
            messages=[{"role": "user", "content": "hi"}],
            profile=profile,
        )
    assert mock_acomp.call_count == 1
    kwargs = mock_acomp.await_args.kwargs
    assert kwargs.get("stop") == ["</end>"]


@pytest.mark.asyncio
async def test_api_base_pass_through_and_omit():
    """Test 3: api_base='http://x' forwards; api_base=None omits the key entirely."""
    with patch("sentinel_shared.llm_call.litellm.acompletion", new=AsyncMock(return_value="ok")) as mock_acomp:
        await acompletion_with_profile(
            model="openai/m",
            messages=[{"role": "user", "content": "x"}],
            api_base="http://x",
        )
        assert mock_acomp.await_args.kwargs.get("api_base") == "http://x"

        mock_acomp.reset_mock()
        await acompletion_with_profile(
            model="openai/m",
            messages=[{"role": "user", "content": "x"}],
            api_base=None,
        )
        assert "api_base" not in mock_acomp.await_args.kwargs


# ---------------------------------------------------------------------------
# extract_completion_text — ADR-0007 step 3
#
# One helper replacing six hand-written copies, so it is tested once against
# every shape those six covered between them.
# ---------------------------------------------------------------------------


def _dict_response(**message_fields):
    return {"choices": [{"message": dict(message_fields)}]}


def _object_response(**message_fields):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(**message_fields))]
    )


def test_extract_returns_content_from_a_dict_message():
    assert extract_completion_text(_dict_response(content="hello")) == "hello"


def test_extract_returns_content_from_an_object_message():
    assert extract_completion_text(_object_response(content="hello")) == "hello"


def test_extract_falls_back_to_reasoning_content_on_a_dict_message():
    """Bug #1773: with a json_schema response format, LM Studio plus a Qwen3
    thinking-mode model applies the schema constraint to reasoning_content and
    leaves content empty. The JSON the caller asked for is in the thinking
    stream — this fallback is why five structured call sites work at all."""
    response = _dict_response(content="", reasoning_content='{"topic": "learning"}')
    assert extract_completion_text(response) == '{"topic": "learning"}'


def test_extract_falls_back_to_reasoning_content_on_an_object_message():
    """A reasoning model returns content None with the real text in
    reasoning_content — the same behaviour on the other response shape."""
    response = _object_response(content=None, reasoning_content="thought text")
    assert extract_completion_text(response) == "thought text"


def test_extract_floors_at_empty_string_never_none():
    """`ProviderCompleteResponse.content` is declared `str`, and callers feed
    this straight into json.loads. None here is a crash one layer removed from
    its cause."""
    assert extract_completion_text(_dict_response(content="", reasoning_content="")) == ""
    assert extract_completion_text(_object_response(content=None, reasoning_content=None)) == ""
    assert extract_completion_text(_dict_response()) == ""


def test_extract_returns_empty_string_on_a_malformed_response():
    """No choices at all — "" rather than an IndexError raised inside somebody
    else's error handler."""
    assert extract_completion_text({"choices": []}) == ""
    assert extract_completion_text({}) == ""
    assert extract_completion_text(None) == ""


