"""Single wrapper around litellm.acompletion that applies ModelProfile stop
sequences and api_base overrides. Subsumes the duplicate _stop_for helpers
that previously lived in llm.py and foundry.py.

The wrapper centralises the four pieces of glue every call site previously
hand-wrote:

  1. profile.stop_sequences → kwargs["stop"]
  2. api_base override → kwargs["api_base"] when truthy
  3. timeout default
  4. pass-through of all other litellm kwargs (temperature, response_format,
     tools, max_tokens, etc.)
"""

from typing import Any

import litellm

from sentinel_shared.model_profiles import ModelProfile


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
