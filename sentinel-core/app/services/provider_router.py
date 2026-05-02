"""
ProviderRouter — transparent primary/fallback routing for AIProvider instances.

Fallback trigger: httpx.ConnectError or httpx.TimeoutException ONLY.
HTTP errors (RateLimitError, AuthenticationError, etc.) are NOT fallback triggers —
they propagate to the caller unchanged.

Both providers fail → raises ProviderUnavailableError (caller returns HTTP 503).

Per CONTEXT.md Phase 4 decisions:
  - Fallback triggers on ConnectError/timeout only (not HTTP 4xx/5xx)
  - Both fail → HTTP 503 with detail explaining both failed, log both at ERROR level
"""
import logging

import httpx

logger = logging.getLogger(__name__)

# Errors that trigger fallback (connectivity failures only)
_FALLBACK_TRIGGERS = (httpx.ConnectError, httpx.TimeoutException)


class ProviderUnavailableError(Exception):
    """Raised when primary (and fallback, if configured) providers both fail with connectivity errors."""

    pass


class ContextLengthError(Exception):
    """Raised when a provider rejects a completion because the prompt+context exceeds model capacity."""

    pass


class ProviderRouter:
    """
    Routes complete() calls to primary provider, with optional fallback.

    Fallback is triggered ONLY on httpx.ConnectError or httpx.TimeoutException.
    All other exceptions (HTTP errors, auth failures, rate limits) propagate unchanged.
    """

    def __init__(self, primary_provider, fallback_provider=None) -> None:
        self._primary = primary_provider
        self._fallback = fallback_provider

    async def complete(
        self,
        messages: list[dict],
        stop: list[str] | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Try primary provider. On ConnectError/timeout, try fallback if configured.
        Raises ProviderUnavailableError if both fail with connectivity errors.
        Propagates non-connectivity errors from primary immediately (no fallback attempt).

        stop: optional stop sequences forwarded to the underlying LiteLLMProvider.
              Fallback provider intentionally does NOT receive stop sequences — cloud
              models (Claude) manage termination via their own chat templates.

        temperature: optional sampling temperature forwarded to the primary provider.
              Pinned by the chat path to bound reply-style variance. Fallback provider
              also receives it so cloud-model behavior matches local behavior.
        """
        try:
            return await self._primary.complete(
                messages, stop=stop, temperature=temperature
            )
        except _FALLBACK_TRIGGERS as primary_exc:
            logger.error(
                f"Primary provider failed with connectivity error: {type(primary_exc).__name__}: {primary_exc}"
            )
            if self._fallback is None:
                raise ProviderUnavailableError(
                    f"Primary provider unavailable ({type(primary_exc).__name__}) and no fallback configured."
                ) from primary_exc

            logger.warning("Attempting fallback provider...")
            try:
                # Fallback (e.g. Claude) manages its own termination — do not pass stop sequences.
                # Temperature still forwarded so reply-style variance is bounded across providers.
                result = await self._fallback.complete(messages, temperature=temperature)
                logger.info("Fallback provider succeeded.")
                return result
            except Exception as fallback_exc:
                logger.error(
                    f"Fallback provider also failed: {type(fallback_exc).__name__}: {fallback_exc}"
                )
                raise ProviderUnavailableError(
                    f"Both providers failed. "
                    f"Primary: {type(primary_exc).__name__}: {primary_exc}. "
                    f"Fallback: {type(fallback_exc).__name__}: {fallback_exc}."
                ) from fallback_exc
