"""Tests for ProviderRouter fallback logic (PROV-05)."""
import pytest
import httpx
import litellm
from unittest.mock import AsyncMock

from app.services.provider_router import ProviderRouter, ProviderUnavailableError


@pytest.fixture
def primary():
    m = AsyncMock()
    m.complete = AsyncMock(return_value="primary response")
    return m


@pytest.fixture
def fallback():
    m = AsyncMock()
    m.complete = AsyncMock(return_value="fallback response")
    return m


async def test_returns_primary_response_on_success(primary, fallback):
    router = ProviderRouter(primary, fallback)
    result = await router.complete([{"role": "user", "content": "hi"}])
    assert result == "primary response"
    primary.complete.assert_called_once()
    fallback.complete.assert_not_called()


async def test_falls_back_on_connect_error(primary, fallback):
    primary.complete.side_effect = httpx.ConnectError("refused")
    router = ProviderRouter(primary, fallback)
    result = await router.complete([{"role": "user", "content": "hi"}])
    assert result == "fallback response"
    fallback.complete.assert_called_once()


async def test_falls_back_on_timeout(primary, fallback):
    primary.complete.side_effect = httpx.TimeoutException("timeout")
    router = ProviderRouter(primary, fallback)
    result = await router.complete([{"role": "user", "content": "hi"}])
    assert result == "fallback response"
    fallback.complete.assert_called_once()


async def test_no_fallback_on_rate_limit_error(primary, fallback):
    primary.complete.side_effect = litellm.RateLimitError(
        "rate limited", llm_provider="test", model="test"
    )
    router = ProviderRouter(primary, fallback)
    with pytest.raises(litellm.RateLimitError):
        await router.complete([{"role": "user", "content": "hi"}])
    fallback.complete.assert_not_called()


async def test_raises_unavailable_when_both_fail(primary, fallback):
    primary.complete.side_effect = httpx.ConnectError("refused")
    fallback.complete.side_effect = httpx.ConnectError("refused")
    router = ProviderRouter(primary, fallback)
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await router.complete([{"role": "user", "content": "hi"}])
    assert "both providers failed" in str(exc_info.value).lower()


async def test_raises_unavailable_with_no_fallback(primary):
    router = ProviderRouter(primary, fallback_provider=None)
    primary.complete.side_effect = httpx.ConnectError("refused")
    with pytest.raises(ProviderUnavailableError):
        await router.complete([{"role": "user", "content": "hi"}])


async def test_unavailable_error_message_mentions_both(primary, fallback):
    primary.complete.side_effect = httpx.ConnectError("refused")
    fallback.complete.side_effect = httpx.TimeoutException("timeout")
    router = ProviderRouter(primary, fallback)
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await router.complete([{"role": "user", "content": "hi"}])
    assert "both providers failed" in str(exc_info.value).lower()
