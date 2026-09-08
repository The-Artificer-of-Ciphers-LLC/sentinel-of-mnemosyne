"""Single wrapper around litellm.acompletion that applies ModelProfile stop
sequences and api_base overrides, plus the single reader of the response it
returns. Subsumes the duplicate _stop_for helpers that previously lived in
llm.py and foundry.py.

The wrapper centralises the four pieces of glue every call site previously
hand-wrote:

  1. profile.stop_sequences → kwargs["stop"]
  2. api_base override → kwargs["api_base"] when truthy
  3. timeout default
  4. pass-through of all other litellm kwargs (temperature, response_format,
     tools, max_tokens, etc.)

``extract_completion_text`` is the fifth: the ``content or reasoning_content``
fallback that existed in six hand-written copies (ADR-0007 step 3). It lives
HERE, beside ``acompletion_with_profile``, because this is where the raw litellm
response five of those six copies parsed was CREATED — they call
``acompletion_with_profile`` with a ``response_format`` schema and then read the
raw response it hands back. Siting the reader anywhere else would make five of
six call sites import across a package boundary to parse a value ``shared/``
produced, inverting the dependency. Each caller now imports one module, not two.

``acompletion_with_profile``'s contract is UNCHANGED — it still returns the raw
response. The extractor is a separate exported function callers opt into, not a
changed return type.
"""

import logging
from typing import Any

import litellm

from sentinel_shared.model_profiles import ModelProfile

logger = logging.getLogger(__name__)


async def acompletion_with_profile(
    *,
    model: str,
    messages: list[dict],
    profile: ModelProfile | None = None,
    api_base: str | None = None,
    timeout: float = 60.0,
    **extra: Any,
):
    """Call litellm.acompletion with profile-derived stop sequences and api_base.

    Equivalent to:
        stop = profile.stop_sequences if profile and profile.stop_sequences else None
        kwargs = {"model": model, "messages": messages, "timeout": timeout, **extra}
        if api_base: kwargs["api_base"] = api_base
        if stop: kwargs["stop"] = stop
        return await litellm.acompletion(**kwargs)
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "timeout": timeout,
        **extra,
    }
    if api_base:
        kwargs["api_base"] = api_base
    if profile and profile.stop_sequences:
        kwargs["stop"] = profile.stop_sequences
    return await litellm.acompletion(**kwargs)


def extract_completion_text(response: Any) -> str:
    """The assistant text from a litellm-shaped completion response.

    Handles both response shapes — a plain dict and an object with attributes —
    and floors at the empty string. It NEVER returns None: callers put this value
    straight into fields declared ``str`` (``ProviderCompleteResponse.content``)
    and into ``json.loads``, and a None there is a crash one layer removed from
    the cause. It never raises either: a malformed response with no ``choices``
    yields "" rather than an IndexError inside somebody's error handler.

    **The reasoning_content fallback is load-bearing twice over, and neither
    reason is a workaround to be tidied away.** A reasoning model returns
    ``content`` empty with the real text in ``reasoning_content``; and when a
    ``json_schema`` response format is applied, LM Studio plus a Qwen3
    thinking-mode model applies the schema constraint to ``reasoning_content``
    instead of ``content``, so the JSON the caller asked for is in the thinking
    stream (bug #1773, verified 2026-04-27 in the LM Studio server log:
    ``Accumulated 31 tokens in reasoning content { "topic": "learning", ...``).

    **This is deliberately SHAPE-based and does not branch on
    ``ModelProfile.reasoning``.** ADR-0007 puts LM Studio v1's
    ``capabilities.reasoning`` on the profile, which is real corroboration — a
    model the backend itself calls a reasoning model is exactly the model that
    returns empty ``content``. It is still not worth branching on: that field is
    unset on the v0 API generation, unset on ``StaticModelSource``, and unset for
    every non-LM-Studio backend, so a helper keyed off it would stop extracting
    text on precisely the backends with the least metadata. Handle the shape,
    always, for everyone.
    """
    try:
        if isinstance(response, dict):
            msg = response["choices"][0]["message"]
            if isinstance(msg, dict):
                return msg.get("content") or msg.get("reasoning_content") or ""
        else:
            msg = response.choices[0].message
            if isinstance(msg, dict):
                return msg.get("content") or msg.get("reasoning_content") or ""
        return (
            getattr(msg, "content", None)
            or getattr(msg, "reasoning_content", None)
            or ""
        )
    except Exception as exc:  # noqa: BLE001 - any shape surprise floors at ""
        logger.warning(
            "Completion response shape unexpected (%s: %s) — extracting nothing",
            type(exc).__name__,
            exc,
        )
        return ""
