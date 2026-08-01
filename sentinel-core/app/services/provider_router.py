"""
ProviderRouter — transparent primary/fallback routing for AIProvider instances.

Fallback trigger: httpx.ConnectError, httpx.TimeoutException, or litellm.NotFoundError.
Other HTTP errors (RateLimitError, AuthenticationError, etc.) are NOT fallback triggers —
they propagate to the caller unchanged.

Both providers fail → raises ProviderUnavailableError (caller returns HTTP 503).

Per CONTEXT.md Phase 4 decisions:
  - Fallback triggers on ConnectError/timeout (not HTTP 4xx/5xx in general)
  - Both fail → HTTP 503 with detail explaining both failed, log both at ERROR level

Per Phase 42 decision D-06: litellm.NotFoundError (HTTP 404) is ALSO a fallback
trigger — a model-not-served backend can fail with a plain 404 rather than a
connectivity error, so a ConnectError-only fallback would never fire for it.
Formerly justified by the (now-retired) exo backend's 404-on-no-instance
behavior; kept as a general safety net for any openai_compatible backend with
the same failure shape. NotFoundError is a fallback trigger ONLY — it is
deliberately NOT added to app/clients/litellm_provider.py's retryable set (a
404 is not a transient error).
"""
import logging

import httpx
import litellm

from app.errors import ContextLengthError, ProviderUnavailableError

# Errors that trigger fallback (connectivity failures + model-not-served)
_FALLBACK_TRIGGERS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    litellm.NotFoundError,  # D-06: model-not-served backends can fail with a 404
)

logger = logging.getLogger(__name__)





class ProviderRouter:
    """
    Routes complete() calls to primary provider, with optional fallback.

    Fallback is triggered on httpx.ConnectError, httpx.TimeoutException, or
    litellm.NotFoundError (D-06 — model-not-served backends can 404). All other
    exceptions (other HTTP errors, auth failures, rate limits) propagate unchanged.
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
