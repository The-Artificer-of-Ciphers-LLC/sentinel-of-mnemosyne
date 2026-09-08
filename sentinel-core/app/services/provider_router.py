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

ADR-0007 step 3: a NotFoundError with an Active model seam wired now buys ONE
invalidate-and-retry against a freshly resolved model before the fallback path
is entered (ADR decision 1). The 404 is the backend saying "I do not serve that
model", which is precisely the signal a metadata refresh answers — and it is the
signal the live 2026-09-07 incident produced when the container kept naming a
model LM Studio had stopped serving.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

import httpx
import litellm

from app.errors import ContextLengthError, ProviderUnavailableError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.model import ActiveModel, ModelProfile

# Errors that trigger fallback (connectivity failures + model-not-served)
_FALLBACK_TRIGGERS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    litellm.NotFoundError,  # D-06: model-not-served backends can fail with a 404
)

logger = logging.getLogger(__name__)





#: The task kind used when a call supplies no profile to name one (e.g. the
#: output scanner's own classifier call, which is chat-shaped).
_DEFAULT_TASK_KIND = "chat"


class ProviderRouter:
    """
    Routes complete() calls to primary provider, with optional fallback.

    Fallback is triggered on httpx.ConnectError, httpx.TimeoutException, or
    litellm.NotFoundError (D-06 — model-not-served backends can 404). All other
    exceptions (other HTTP errors, auth failures, rate limits) propagate unchanged.

    ADR-0007 step 3 adds two seams and one behaviour:

    * ``active_model`` — the PRIMARY provider's Active model seam. The router is
      the only thing that re-resolves, which is why the reference lives here and
      not on ``LiteLLMProvider``: the router is a service, so holding it does not
      inherit the ADR-0002 layering objection that killed the adapter-side
      variant. It is wired only when the primary provider is the one the seam
      describes; a seam for a different backend would answer a 404 by handing the
      primary a model id from someone else's catalogue.
    * ``fallback_model`` — the FALLBACK provider's own seam, over
      ``StaticModelSource``. ADR decision 8 puts ``api_base`` on the profile, so
      forwarding the primary's profile to the cloud fallback would hand Anthropic
      LM Studio's base URL and LM Studio's model id — a fallback that cannot
      succeed, arriving exactly when the primary is already down. The local
      profile is an argument to the primary call ONLY and never crosses.
    * invalidate-and-retry-once (ADR decision 1). ``litellm.NotFoundError`` is the
      backend saying "I do not serve that model", which is the one signal worth
      spending a metadata refresh on. Bounded at exactly one retry: an unbounded
      retry against a backend that keeps 404ing is the failure mode.
    """

    def __init__(
        self,
        primary_provider,
        fallback_provider=None,
        *,
        active_model: "ActiveModel | None" = None,
        fallback_model: "ActiveModel | None" = None,
    ) -> None:
        self._primary = primary_provider
        self._fallback = fallback_provider
        self._active_model = active_model
        self._fallback_model = fallback_model

    async def complete(
        self,
        messages: list[dict],
        profile: "ModelProfile | None" = None,
        stop: list[str] | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Try primary provider. On ConnectError/timeout, try fallback if configured.
        Raises ProviderUnavailableError if both fail with connectivity errors.
        Propagates non-connectivity errors from primary immediately (no fallback attempt).

        profile: the model facts for the PRIMARY leg (ADR-0007). Forwarded
              verbatim. The fallback leg resolves its own — see the class
              docstring.

        stop: an explicit override of the profile's stop sequences, forwarded to
              the underlying LiteLLMProvider. Fallback provider intentionally does
              NOT receive stop sequences — cloud models (Claude) manage
              termination via their own chat templates — and its resolved profile
              is stripped of them for the same reason.

        temperature: optional sampling temperature forwarded to the primary provider
              when not None. No caller currently pins a chat temperature. Fallback
              provider also receives it so cloud-model behavior matches local behavior.
        """
        try:
            return await self._primary.complete(
                messages, profile, stop=stop, temperature=temperature
            )
        except _FALLBACK_TRIGGERS as primary_exc:
            logger.error(
                f"Primary provider failed with connectivity error: {type(primary_exc).__name__}: {primary_exc}"
            )

            # ADR decision 1: a not-served 404 (and ONLY that) buys exactly one
            # invalidate-and-retry against a freshly resolved model. Connectivity
            # errors are deliberately excluded — a backend that cannot be reached
            # has told us nothing new about which model it serves, so re-resolving
            # would spend a request to learn the same thing twice.
            if isinstance(primary_exc, litellm.NotFoundError) and self._active_model is not None:
                fresh = await self._reresolve(profile)
                if fresh is not None:
                    logger.warning(
                        "Primary reported the model is not served — re-resolved %r "
                        "and retrying the primary ONCE before falling back",
                        fresh.model_id,
                    )
                    try:
                        return await self._primary.complete(
                            messages, fresh, stop=stop, temperature=temperature
                        )
                    except _FALLBACK_TRIGGERS as retry_exc:
                        logger.error(
                            "Primary failed again after re-resolution "
                            f"({type(retry_exc).__name__}: {retry_exc}) — no second retry"
                        )
                        primary_exc = retry_exc

            if self._fallback is None:
                raise ProviderUnavailableError(
                    f"Primary provider unavailable ({type(primary_exc).__name__}) and no fallback configured."
                ) from primary_exc

            logger.warning("Attempting fallback provider...")
            try:
                fallback_profile = await self._resolve_fallback_profile(profile)
                # Fallback (e.g. Claude) manages its own termination — do not pass stop sequences.
                # Temperature still forwarded so reply-style variance is bounded across providers.
                result = await self._fallback.complete(
                    messages, fallback_profile, temperature=temperature
                )
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

    # ---- ADR decision 1 / decision 8 helpers ------------------------------

    @staticmethod
    def _task_kind(profile: "ModelProfile | None") -> str:
        if profile is not None and profile.task_kind:
            return profile.task_kind
        return _DEFAULT_TASK_KIND

    async def _reresolve(self, profile: "ModelProfile | None") -> "ModelProfile | None":
        """Invalidate the seam and resolve the SAME task kind again.

        Returns ``None`` when re-resolution is impossible, in which case the
        caller continues into the ordinary fallback path. A resolution failure is
        not itself a fallback trigger (see ``MessageProcessor``), but here we are
        already handling a primary failure that IS one — refusing to fall back
        because the re-resolve also failed would turn one outage into two.
        """
        assert self._active_model is not None  # guarded by the caller
        self._active_model.invalidate()
        try:
            return await self._active_model.for_task(self._task_kind(profile))
        except Exception as exc:  # noqa: BLE001 - any resolution failure is equal here
            logger.warning(
                "Re-resolution after a not-served 404 failed (%s: %s) — skipping the "
                "retry and continuing to the fallback path",
                type(exc).__name__,
                exc,
            )
            return None

    async def _resolve_fallback_profile(
        self, primary_profile: "ModelProfile | None"
    ) -> "ModelProfile | None":
        """The fallback's OWN profile — never the primary's.

        Resolved from the fallback's ``StaticModelSource`` leg, then stripped of
        stop sequences to preserve the pre-existing deliberate behaviour that the
        cloud provider manages its own termination. ``None`` (no fallback seam
        wired) means the fallback provider uses its construction-time cloud
        configuration, which is exactly what it did before ADR-0007.
        """
        if self._fallback_model is None:
            return None
        try:
            resolved = await self._fallback_model.for_task(
                self._task_kind(primary_profile)
            )
        except Exception as exc:  # noqa: BLE001 - degrade to construction-time config
            logger.warning(
                "Fallback model resolution failed (%s: %s) — the fallback provider "
                "will use its construction-time configuration",
                type(exc).__name__,
                exc,
            )
            return None
        return replace(resolved, stop_sequences=())
