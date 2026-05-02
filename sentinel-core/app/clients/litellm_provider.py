"""
LiteLLMProvider — wraps litellm.acompletion() behind the AIProvider Protocol.

Handles LM Studio, Claude, Ollama, and llama.cpp through LiteLLM's unified interface.
Tenacity retry: 3 attempts, exponential backoff 1s→2s→4s.
Retryable: RateLimitError, ServiceUnavailableError, httpx.ConnectError, httpx.TimeoutException
Fatal (no retry): AuthenticationError (401), BadRequestError (422), NotFoundError (404)
Hard timeout: 120 seconds per litellm.acompletion() call (PROV-03 — raised from 30s for local 14B MLX model).

Supply chain note: litellm>=1.83.0 required — versions 1.82.7-1.82.8 were malicious (March 2026).
"""
import logging

import httpx
import litellm
from litellm import BadRequestError
from tenacity import (
    retry,
    retry_if_exception_type,
)

from app.clients.retry_config import RETRY_STOP, RETRY_WAIT
from app.services.provider_router import ContextLengthError

logger = logging.getLogger(__name__)

# Transient errors worth retrying
_RETRYABLE = (
    litellm.RateLimitError,
    litellm.ServiceUnavailableError,
    httpx.ConnectError,
    httpx.TimeoutException,
)

# Substrings appearing in vendor BadRequestError messages when the prompt+context
# exceeds the model's maximum context window. Centralised here because vendor SDK
# imports must live under app/clients/ (AI-agnostic guardrail).
_CONTEXT_LENGTH_MARKERS: tuple[str, ...] = (
    "context length",
    "context_length",
    "maximum context",
    "context window",
    "too many tokens",
    "tokens. however",
    "reduce the length",
    "prompt is too long",
)


def _is_context_length_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in _CONTEXT_LENGTH_MARKERS)


class LiteLLMProvider:
    """
    AI backend client wrapping litellm.acompletion().

    LM Studio:  model_string="openai/<model_name>", api_base="http://host.docker.internal:1234/v1"
    Claude:     model_string="claude-haiku-4-5" (or sonnet), api_key=anthropic_api_key
    Ollama:     model_string="ollama/<model_name>", api_base="http://<host>:11434"
    llama.cpp:  model_string="openai/<model_name>", api_base="http://<host>:8080/v1"
    """

    def __init__(
        self,
        model_string: str,
        api_base: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._model_string = model_string
        self._api_base = api_base
        self._api_key = api_key

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=RETRY_STOP,
        wait=RETRY_WAIT,
        reraise=True,
    )
    async def complete(
        self,
        messages: list[dict],
        stop: list[str] | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Submit messages to the configured provider via LiteLLM.
        Retries 3x on transient errors. Raises immediately on 401/422/404.
        Hard 30-second timeout per call enforces PROV-03 ceiling.

        stop: optional list of stop sequences for the model family (from ModelProfile).
              Passed through to litellm.acompletion when non-empty so the LLM halts
              at the correct end-of-turn token for the loaded model architecture.

        temperature: optional sampling temperature. Pinned by callers (e.g. the
              chat path uses 0.4) to bound message-to-message reply-style variance
              when the underlying model has multiple attractor states (lecture-mode
              vs friend-mode). Pass None to use litellm's default.
        """
        kwargs: dict = {
            "model": self._model_string,
            "messages": messages,
            "timeout": 120.0,  # hard per-call ceiling (PROV-03 — raised from 30s for local 14B MLX)
        }
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if stop:
            kwargs["stop"] = stop
        if temperature is not None:
            kwargs["temperature"] = temperature

        logger.debug(f"LiteLLMProvider.complete: model={self._model_string}")
        try:
            response = await litellm.acompletion(**kwargs)
        except BadRequestError as exc:
            # Translate vendor-specific context-window rejections into a typed
            # service-layer exception so app/services/ never imports litellm.
            if _is_context_length_error(exc):
                raise ContextLengthError(
                    "Message plus context exceeds model capacity. "
                    "Try a shorter message."
                ) from exc
            raise
        return response.choices[0].message.content


async def get_context_window_from_lmstudio(
    client: httpx.AsyncClient,
    base_url: str,
    model_name: str,
) -> int:
    """
    Fetch max_context_length from LM Studio /api/v0/models/{model_name}.
    Returns 4096 (conservative default) if LM Studio unavailable at startup.
    Moved from lmstudio.py — LMStudioClient is deleted in Phase 4.
    Note: base_url is the /v1 URL; strips /v1 to reach /api/v0/.
    """
    api_base = base_url.rstrip("/").removesuffix("/v1")
    try:
        resp = await client.get(f"{api_base}/api/v0/models/{model_name}", timeout=5.0)
        resp.raise_for_status()
        return int(resp.json().get("max_context_length", 4096))
    except Exception:
        return 4096
