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
from typing import TYPE_CHECKING

import httpx
import litellm
from litellm import BadRequestError
from tenacity import (
    retry,
    retry_if_exception_type,
)

from app.clients.retry_config import RETRY_STOP, RETRY_WAIT
from app.services.provider_router import ContextLengthError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.model import ModelProfile

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

    ADR-0007 step 3: the constructor arguments survive, but their JOB narrowed.
    ``api_key`` is still construction-time state (it is a credential, not a model
    fact) and ``model_string`` / ``api_base`` are now only the STATIC fallback —
    what to use when a call supplies no ``ModelProfile``, i.e. the cloud provider
    whose model never changes underneath us. When a profile IS supplied it is
    authoritative for the model id, the api base and the stop sequences.

    This adapter deliberately holds NO ``ActiveModel`` reference. ADR-0007
    rejected the "adapter resolves the model internally" option because it
    inverts ADR-0002's layering: a single-purpose HTTP adapter under
    ``app/clients/`` would depend on a service module, and the three scalars on
    ``MessageRequest`` would survive because nothing above would need to carry
    them. ``ProviderRouter`` — a service — holds the seam instead.
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
        profile: "ModelProfile | None" = None,
        stop: list[str] | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Submit messages to the configured provider via LiteLLM.
        Retries 3x on transient errors. Raises immediately on 401/422/404.
        Hard 120-second timeout per call enforces PROV-03 ceiling.

        profile: the model facts as ONE value (ADR-0007). When supplied it is
              authoritative and fully determines the call: ``litellm_model`` is
              the model string, ``api_base`` is the base URL, and
              ``stop_sequences`` are the stop sequences. It is deliberately NOT
              merged with the constructor's ``model_string``/``api_base`` — a
              half-profile call that inherited the constructor's base URL is
              exactly how a Claude profile would end up pointed at LM Studio.
              ``None`` restores the pre-ADR-0007 behaviour (construction-time
              model and base), which is what the static cloud provider uses.

        stop: an explicit override of ``profile.stop_sequences``, present because
              ``POST /provider/complete`` carries a ``stop`` field. When it is
              empty/None the profile answers. With neither, no ``stop`` kwarg is
              sent at all.

        temperature: optional sampling temperature. Forwarded to litellm.acompletion
              when not None. No caller currently pins a temperature for the chat
              path. Pass None to use litellm's default.
        """
        if profile is not None:
            model_string = profile.litellm_model
            api_base = profile.api_base
            profile_stop = list(profile.stop_sequences)
        else:
            model_string = self._model_string
            api_base = self._api_base
            profile_stop = []

        stop_sequences = list(stop) if stop else profile_stop

        kwargs: dict = {
            "model": model_string,
            "messages": messages,
            "timeout": 120.0,  # hard per-call ceiling (PROV-03 — raised from 30s for local 14B MLX)
        }
        if api_base:
            kwargs["api_base"] = api_base
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if stop_sequences:
            kwargs["stop"] = stop_sequences
        if temperature is not None:
            kwargs["temperature"] = temperature

        logger.debug(f"LiteLLMProvider.complete: model={model_string}")
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
        # Reasoning models (e.g. google/gemma-4-31b) can return `content`
        # empty/None with the actual text in `reasoning_content` — mirrors
        # the LM Studio + Qwen3 thinking-mode fallback used in
        # app/services/six_rs/reduce.py::_extract_completion_content and
        # pipeline_orchestrator.py::_extract_completion_content (bug #1773).
        # POST /provider/complete's response model declares `content: str`,
        # so this must never return None — "" is the floor.
        msg = response.choices[0].message
        if isinstance(msg, dict):
            return msg.get("content") or msg.get("reasoning_content") or ""
        return (
            getattr(msg, "content", None)
            or getattr(msg, "reasoning_content", None)
            or ""
        )


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


async def get_model_capabilities_from_lmstudio(
    client: httpx.AsyncClient,
    base_url: str,
    model_name: str,
) -> dict | None:
    """
    Fetch live capability data for ``model_name`` from LM Studio's
    ``/api/v0/models/{model_name}`` endpoint (same endpoint/pattern as
    ``get_context_window_from_lmstudio`` above and
    ``sentinel_shared.model_profiles.get_profile`` — the confirmed live seam
    for LM Studio model metadata; this reuses it rather than adding a new
    HTTP client).

    Returns a dict normalized to look like ``litellm.get_model_info()``'s
    shape so callers (``app.services.model_selector._score``) can treat live
    and litellm-sourced data uniformly:

      - ``"max_tokens"``: int — LM Studio's ``max_context_length``
      - ``"supports_function_calling"``: bool — whether LM Studio's
        ``capabilities`` list contains ``"tool_use"`` (the local equivalent of
        litellm's ``supports_function_calling``)
      - ``"state"``: str — LM Studio's own ``state`` field, preserved for
        callers that want it

    Returns ``None`` — never a permissive default — on any HTTP/JSON failure,
    a missing model (404), a non-dict response body, or when the model is not
    reported ``state: "loaded"``. Callers MUST treat ``None`` as "no live
    data available for this model" and fail closed accordingly (never assume
    capability).

    fix-score-local-model-capabilities: litellm's ``get_model_info()`` /
    ``supports_function_calling()`` only know about a static cloud registry —
    they have no entry for LM Studio-style local model ids (e.g.
    "google/gemma-4-31b"), so every local model previously scored 0 for every
    task_kind in ``model_selector._score``. This function is the live-data
    source that fixes that.
    """
    api_base = base_url.rstrip("/").removesuffix("/v1")
    try:
        resp = await client.get(f"{api_base}/api/v0/models/{model_name}", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    if not isinstance(data, dict):
        return None
    if data.get("state") != "loaded":
        # Not genuinely loaded — fail closed, no permissive default.
        return None

    capabilities = data.get("capabilities") or []
    max_tokens = data.get("max_context_length") or data.get("loaded_context_length") or 0
    return {
        "max_tokens": int(max_tokens),
        "supports_function_calling": "tool_use" in capabilities,
        "state": data.get("state"),
    }
