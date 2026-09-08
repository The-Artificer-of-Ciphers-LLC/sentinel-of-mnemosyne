"""Tests for LiteLLMProvider retry logic and error handling (PROV-02, PROV-03)."""
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
import litellm

from app.clients.litellm_provider import LiteLLMProvider


@pytest.fixture
def lmstudio_provider():
    return LiteLLMProvider(
        model_string="openai/test-model",
        api_base="http://test-lmstudio/v1",
        api_key="lmstudio",
    )


async def test_complete_returns_text_on_success(lmstudio_provider):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hello from provider"
    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
        result = await lmstudio_provider.complete([{"role": "user", "content": "hi"}])
    assert result == "Hello from provider"


async def test_retries_on_rate_limit_error(lmstudio_provider):
    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=litellm.RateLimitError("rate limited", llm_provider="test", model="test")) as mock_call:
        with pytest.raises(litellm.RateLimitError):
            await lmstudio_provider.complete([{"role": "user", "content": "hi"}])
    assert mock_call.call_count == 3


async def test_retries_on_service_unavailable(lmstudio_provider):
    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=litellm.ServiceUnavailableError("unavailable", llm_provider="test", model="test")) as mock_call:
        with pytest.raises(litellm.ServiceUnavailableError):
            await lmstudio_provider.complete([{"role": "user", "content": "hi"}])
    assert mock_call.call_count == 3


async def test_retries_on_connect_error(lmstudio_provider):
    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=httpx.ConnectError("refused")) as mock_call:
        with pytest.raises(httpx.ConnectError):
            await lmstudio_provider.complete([{"role": "user", "content": "hi"}])
    assert mock_call.call_count == 3


async def test_no_retry_on_authentication_error(lmstudio_provider):
    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=litellm.AuthenticationError("bad key", llm_provider="test", model="test")) as mock_call:
        with pytest.raises(litellm.AuthenticationError):
            await lmstudio_provider.complete([{"role": "user", "content": "hi"}])
    assert mock_call.call_count == 1


async def test_no_retry_on_bad_request_error(lmstudio_provider):
    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=litellm.BadRequestError("bad request", llm_provider="test", model="test")) as mock_call:
        with pytest.raises(litellm.BadRequestError):
            await lmstudio_provider.complete([{"role": "user", "content": "hi"}])
    assert mock_call.call_count == 1


async def test_retries_on_timeout_exception(lmstudio_provider):
    """PROV-03: TimeoutException is in the retryable set and triggers retry (up to 3 attempts)."""
    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=httpx.TimeoutException("timed out")) as mock_call:
        with pytest.raises(httpx.TimeoutException):
            await lmstudio_provider.complete([{"role": "user", "content": "hi"}])
    assert mock_call.call_count == 3


async def test_complete_falls_back_to_reasoning_content_when_content_is_none(lmstudio_provider):
    """Reasoning models (e.g. google/gemma-4-31b) can return `content` empty/None
    with the actual text in `reasoning_content` (bug #1773 precedent — qwen3
    thinking-mode). complete() must return the reasoning text, not None, since
    POST /provider/complete's response model declares `content: str`."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = None
    mock_response.choices[0].message.reasoning_content = "thought text"
    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
        result = await lmstudio_provider.complete([{"role": "user", "content": "hi"}])
    assert result == "thought text"


async def test_complete_returns_empty_string_when_both_content_and_reasoning_empty(lmstudio_provider):
    """Never return None even when both fields are empty — "" is the floor."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = None
    mock_response.choices[0].message.reasoning_content = None
    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
        result = await lmstudio_provider.complete([{"role": "user", "content": "hi"}])
    assert result == ""


# ---------------------------------------------------------------------------
# ADR-0007 step 3 — the profile is the argument
# ---------------------------------------------------------------------------


def _ok_response(text: str = "ok"):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = text
    return mock_response


async def test_profile_supplies_model_api_base_and_stop_sequences(lmstudio_provider):
    """The profile is authoritative for all three model facts.

    The fixture provider was constructed naming `openai/test-model` at
    `http://test-lmstudio/v1`; a call carrying a profile must use the PROFILE's
    model and base instead. That is the whole point of ADR-0007: a model string
    pinned at construction time is the staleness this design removes.
    """
    from app.model import ModelProfile

    profile = ModelProfile(
        model_id="qwen/qwen3.8-27b",
        litellm_model="openai/qwen/qwen3.8-27b",
        api_base="http://swapped-lmstudio/v1",
        context_window=119552,
        stop_sequences=("<|im_end|>",),
    )
    with patch(
        "litellm.acompletion", new_callable=AsyncMock, return_value=_ok_response()
    ) as mock_call:
        await lmstudio_provider.complete([{"role": "user", "content": "hi"}], profile)

    kwargs = mock_call.await_args.kwargs
    assert kwargs["model"] == "openai/qwen/qwen3.8-27b"
    assert kwargs["api_base"] == "http://swapped-lmstudio/v1"
    assert kwargs["stop"] == ["<|im_end|>"]
    # The credential is construction-time state, not a model fact — it survives.
    assert kwargs["api_key"] == "lmstudio"


async def test_profile_without_stop_sequences_sends_no_stop_kwarg(lmstudio_provider):
    """No stop sequences means no `stop` kwarg at all — not an empty list.

    litellm treats an explicit empty `stop` differently from an absent one on
    some backends, and a cloud model receiving `stop: []` is not the same request
    as one receiving none.
    """
    from app.model import ModelProfile

    profile = ModelProfile(
        model_id="claude-haiku-4-5", litellm_model="claude-haiku-4-5"
    )
    with patch(
        "litellm.acompletion", new_callable=AsyncMock, return_value=_ok_response()
    ) as mock_call:
        await lmstudio_provider.complete([{"role": "user", "content": "hi"}], profile)

    assert "stop" not in mock_call.await_args.kwargs


async def test_explicit_stop_overrides_the_profile(lmstudio_provider):
    """POST /provider/complete carries a `stop` field a module may set for its
    own prompt shape; when present it wins over the profile's."""
    from app.model import ModelProfile

    profile = ModelProfile(
        model_id="qwen/qwen3.8-27b",
        litellm_model="openai/qwen/qwen3.8-27b",
        stop_sequences=("<|im_end|>",),
    )
    with patch(
        "litellm.acompletion", new_callable=AsyncMock, return_value=_ok_response()
    ) as mock_call:
        await lmstudio_provider.complete(
            [{"role": "user", "content": "hi"}], profile, stop=["###"]
        )

    assert mock_call.await_args.kwargs["stop"] == ["###"]


async def test_no_profile_falls_back_to_construction_time_configuration(
    lmstudio_provider,
):
    """The static cloud case, and the pre-ADR-0007 posture, both still work."""
    with patch(
        "litellm.acompletion", new_callable=AsyncMock, return_value=_ok_response()
    ) as mock_call:
        await lmstudio_provider.complete([{"role": "user", "content": "hi"}])

    kwargs = mock_call.await_args.kwargs
    assert kwargs["model"] == "openai/test-model"
    assert kwargs["api_base"] == "http://test-lmstudio/v1"


# ``test_get_context_window_from_lmstudio_returns_value`` and
# ``..._returns_4096_on_error`` were deleted with their subject in ADR-0007 step
# 4. ``get_context_window_from_lmstudio`` issued a per-model
# ``GET /api/v0/models/{id}`` to answer "how big is this model's window" — the
# question ``app/model.py`` now answers off a single model-LIST call, and once
# the registry's live path went it had no caller left. Both guarantees have
# successors in tests/test_model.py: the value case is
# ``test_context_window_falls_back_to_max_context_length`` (same
# ``max_context_length`` field, same backend, read through the seam) and the
# error case is ``test_context_window_falls_back_to_declared_4096`` plus the
# cold last-known-good case, which assert the same conservative 4096 floor
# without pretending a failed fetch produced a real number.
