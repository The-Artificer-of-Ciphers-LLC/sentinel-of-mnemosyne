"""Tests for ProviderRouter fallback logic (PROV-05).

ADR-0007 step 3 additions: the profile is the argument, a not-served 404 buys
exactly ONE invalidate-and-retry, and the cloud fallback is called with a profile
it resolved itself rather than the local one.
"""
import pytest
import httpx
import litellm
from unittest.mock import AsyncMock

from app.model import ActiveModel, ModelProfile, StaticModelSource
from app.services.provider_router import ProviderRouter, ProviderUnavailableError

# The two profiles the fallback test contrasts. LOCAL is deliberately shaped
# like the live LM Studio box on 2026-09-07 (mlx qwen, 119552 loaded window,
# ChatML stops); CLOUD is what StaticModelSource serves for the Claude leg.
LOCAL_PROFILE = ModelProfile(
    model_id="qwen/qwen3.8-27b",
    litellm_model="openai/qwen/qwen3.8-27b",
    api_base="http://lmstudio.test/v1",
    context_window=119552,
    stop_sequences=("<|im_end|>",),
    task_kind="chat",
)
CLOUD_PROFILE = ModelProfile(
    model_id="claude-haiku-4-5",
    litellm_model="claude-haiku-4-5",
    api_base=None,
    context_window=200_000,
    stop_sequences=("\n\nHuman:",),  # present so the stripping is observable
    task_kind="chat",
)
FRESH_LOCAL_PROFILE = ModelProfile(
    model_id="qwen/qwen3.8-8b",
    litellm_model="openai/qwen/qwen3.8-8b",
    api_base="http://lmstudio.test/v1",
    context_window=32768,
    task_kind="chat",
)


class CountingModelSource:
    """A real ModelSource that records how many times it was asked.

    Wraps a real StaticModelSource rather than faking the protocol, so "was the
    seam consulted?" is answered by the same code path production uses.
    """

    def __init__(self, profiles):
        self._inner = StaticModelSource(profiles)
        self.refreshes = 0

    async def candidates(self):
        self.refreshes += 1
        return await self._inner.candidates()


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
    messages = [{"role": "user", "content": "hi"}]
    result = await router.complete(messages, stop=["END"], temperature=0.2)
    assert result == "primary response"
    primary.complete.assert_awaited_once_with(
        messages, None, stop=["END"], temperature=0.2
    )
    fallback.complete.assert_not_called()


async def test_falls_back_on_connect_error(primary, fallback):
    primary.complete.side_effect = httpx.ConnectError("refused")
    router = ProviderRouter(primary, fallback)
    messages = [{"role": "user", "content": "hi"}]
    result = await router.complete(messages, stop=["END"], temperature=0.4)
    assert result == "fallback response"
    primary.complete.assert_awaited_once_with(
        messages, None, stop=["END"], temperature=0.4
    )
    fallback.complete.assert_awaited_once_with(messages, None, temperature=0.4)


async def test_falls_back_on_timeout(primary, fallback):
    primary.complete.side_effect = httpx.TimeoutException("timeout")
    router = ProviderRouter(primary, fallback)
    messages = [{"role": "user", "content": "hi"}]
    result = await router.complete(messages, stop=["END"], temperature=0.7)
    assert result == "fallback response"
    primary.complete.assert_awaited_once_with(
        messages, None, stop=["END"], temperature=0.7
    )
    fallback.complete.assert_awaited_once_with(messages, None, temperature=0.7)


async def test_no_fallback_on_rate_limit_error(primary, fallback):
    primary.complete.side_effect = litellm.RateLimitError(
        "rate limited", llm_provider="test", model="test"
    )
    router = ProviderRouter(primary, fallback)
    with pytest.raises(litellm.RateLimitError):
        await router.complete([{"role": "user", "content": "hi"}], stop=["END"])
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


async def test_falls_back_on_not_found_error(primary, fallback):
    """D-06: litellm.NotFoundError (a model-not-served backend's 404 failure mode)
    triggers fallback, mirroring the existing ConnectError/TimeoutException
    behavior."""
    primary.complete.side_effect = litellm.NotFoundError(
        "no instance found", llm_provider="openai", model="mlx-community/x"
    )
    router = ProviderRouter(primary, fallback)
    messages = [{"role": "user", "content": "hi"}]
    result = await router.complete(messages, stop=["END"], temperature=0.4)
    assert result == "fallback response"
    primary.complete.assert_awaited_once_with(
        messages, None, stop=["END"], temperature=0.4
    )
    fallback.complete.assert_awaited_once_with(messages, None, temperature=0.4)


async def test_raises_unavailable_on_not_found_error_with_no_fallback(primary):
    """D-06: NotFoundError with no fallback configured raises ProviderUnavailableError,
    mirroring test_raises_unavailable_with_no_fallback."""
    router = ProviderRouter(primary, fallback_provider=None)
    primary.complete.side_effect = litellm.NotFoundError(
        "no instance found", llm_provider="openai", model="mlx-community/x"
    )
    with pytest.raises(ProviderUnavailableError):
        await router.complete([{"role": "user", "content": "hi"}])


async def test_unavailable_error_message_mentions_both(primary, fallback):
    primary.complete.side_effect = httpx.ConnectError("refused")
    fallback.complete.side_effect = httpx.TimeoutException("timeout")
    router = ProviderRouter(primary, fallback)
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await router.complete([{"role": "user", "content": "hi"}])
    assert "both providers failed" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# ADR-0007 decision 1 — invalidate and retry ONCE on a not-served 404
# ---------------------------------------------------------------------------


async def test_not_found_retries_primary_exactly_once_then_falls_back(primary, fallback):
    """A not-served 404 with a seam wired buys ONE retry against a freshly
    resolved model, and only then the fallback.

    The count is the assertion. An unbounded retry against a backend that keeps
    404ing is the failure mode this bound exists to prevent — it would turn one
    bad request into an infinite loop against a backend that is already telling
    us, correctly, that it does not serve the model.
    """
    primary.complete.side_effect = litellm.NotFoundError(
        "no instance found", llm_provider="openai", model="qwen/qwen3.8-27b"
    )
    source = CountingModelSource([FRESH_LOCAL_PROFILE])
    router = ProviderRouter(primary, fallback, active_model=ActiveModel([source]))

    messages = [{"role": "user", "content": "hi"}]
    result = await router.complete(messages, LOCAL_PROFILE)

    assert result == "fallback response"
    assert primary.complete.await_count == 2, "exactly one retry, no more"
    assert source.refreshes == 1
    # The retry used the RE-RESOLVED profile, not the stale one it just 404'd on.
    retry_profile = primary.complete.await_args_list[1].args[1]
    assert retry_profile.model_id == "qwen/qwen3.8-8b"
    fallback.complete.assert_awaited_once()


async def test_not_found_without_active_model_goes_straight_to_fallback(primary, fallback):
    """No seam wired → behaviour is exactly what it was before ADR-0007: one
    primary attempt, then the fallback. Nothing to invalidate, nothing to retry."""
    primary.complete.side_effect = litellm.NotFoundError(
        "no instance found", llm_provider="openai", model="qwen/qwen3.8-27b"
    )
    router = ProviderRouter(primary, fallback)

    result = await router.complete([{"role": "user", "content": "hi"}], LOCAL_PROFILE)

    assert result == "fallback response"
    assert primary.complete.await_count == 1
    fallback.complete.assert_awaited_once()


async def test_connect_error_does_not_re_resolve(primary, fallback):
    """Only the not-served signal justifies spending a metadata refresh.

    A backend that cannot be reached has told us NOTHING new about which model it
    serves, so re-resolving would spend a request to learn the same thing twice —
    and would do it at exactly the moment the backend is already struggling.
    """
    primary.complete.side_effect = httpx.ConnectError("refused")
    source = CountingModelSource([FRESH_LOCAL_PROFILE])
    router = ProviderRouter(primary, fallback, active_model=ActiveModel([source]))

    result = await router.complete([{"role": "user", "content": "hi"}], LOCAL_PROFILE)

    assert result == "fallback response"
    assert primary.complete.await_count == 1
    assert source.refreshes == 0, "connectivity failure must not re-resolve"


async def test_retry_that_fails_again_falls_back_without_a_second_retry(primary, fallback):
    """The bound holds when the retry ALSO 404s: fallback, not a third attempt."""
    primary.complete.side_effect = litellm.NotFoundError(
        "no instance found", llm_provider="openai", model="qwen/qwen3.8-27b"
    )
    router = ProviderRouter(
        primary,
        fallback,
        active_model=ActiveModel([StaticModelSource([FRESH_LOCAL_PROFILE])]),
    )

    result = await router.complete([{"role": "user", "content": "hi"}], LOCAL_PROFILE)

    assert result == "fallback response"
    assert primary.complete.await_count == 2
    fallback.complete.assert_awaited_once()


# ---------------------------------------------------------------------------
# ADR-0007 decision 8 — the cloud fallback resolves its OWN profile
# ---------------------------------------------------------------------------


async def test_fallback_receives_its_own_profile_never_the_local_one(primary, fallback):
    """The local profile is an argument to the PRIMARY call only.

    ADR decision 8 puts ``api_base`` on the profile, so forwarding the local
    profile to Claude would hand Anthropic LM Studio's base URL and LM Studio's
    model id — a fallback that cannot possibly succeed, arriving exactly when the
    primary is already down. This is the test that fails loudly if someone
    "simplifies" the router by forwarding one profile to both legs.
    """
    primary.complete.side_effect = httpx.ConnectError("refused")
    router = ProviderRouter(
        primary,
        fallback,
        fallback_model=ActiveModel([StaticModelSource([CLOUD_PROFILE])]),
    )

    result = await router.complete([{"role": "user", "content": "hi"}], LOCAL_PROFILE)
    assert result == "fallback response"

    called_profile = fallback.complete.await_args.args[1]
    assert called_profile is not None
    # Neither of the local model's facts crossed.
    assert called_profile.model_id != LOCAL_PROFILE.model_id
    assert called_profile.api_base != LOCAL_PROFILE.api_base
    # It carries the cloud model's own identity, from StaticModelSource.
    assert called_profile.model_id == "claude-haiku-4-5"
    assert called_profile.api_base is None
    # And still no stop sequences — cloud models manage their own termination.
    assert called_profile.stop_sequences == ()


async def test_fallback_profile_is_none_when_no_fallback_seam_is_wired(primary, fallback):
    """Without a fallback seam the cloud provider uses its construction-time
    configuration — the pre-ADR-0007 behaviour — and still never sees the local
    profile."""
    primary.complete.side_effect = httpx.ConnectError("refused")
    router = ProviderRouter(primary, fallback)

    await router.complete([{"role": "user", "content": "hi"}], LOCAL_PROFILE)

    assert fallback.complete.await_args.args[1] is None
