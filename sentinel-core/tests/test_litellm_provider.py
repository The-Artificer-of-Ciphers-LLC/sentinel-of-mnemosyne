"""Tests for LiteLLMProvider retry logic and error handling (PROV-02, PROV-03)."""
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
import litellm

from app.clients.litellm_provider import LiteLLMProvider, get_context_window_from_lmstudio


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


async def test_get_context_window_from_lmstudio_returns_value():
    import httpx
    def handler(request):
        return httpx.Response(200, json={"max_context_length": 32768, "id": "test-model"})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await get_context_window_from_lmstudio(client, "http://test/v1", "test-model")
    assert result == 32768


async def test_get_context_window_from_lmstudio_returns_4096_on_error():
    import httpx
    transport = httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await get_context_window_from_lmstudio(client, "http://test/v1", "test-model")
    assert result == 4096
