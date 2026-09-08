"""Factory for MessageRequest transport inputs."""

from __future__ import annotations

from app.models import MessageEnvelope
from app.services.message_processing import MessageRequest


def recorded_model_name(ctx) -> str:
    """The id of the model that will actually answer — not the configured one.

    ADR-0007, Defect B. This used to read ``ctx.settings.model_name``, i.e. the
    ``MODEL_NAME`` default, so Session summary frontmatter and the
    response-anomaly log recorded CONFIGURATION rather than the model that
    answered. That is the same failure as the ADR's opening observation: the
    container named ``google/gemma-4-31b`` for two days while LM Studio served
    ``qwen/qwen3.8-27b``, and the summaries agreed with the container.

    Reads the profile the Active model seam has already resolved for the chat
    kind. ``cached_profile`` is deliberately synchronous and never refreshes —
    this factory is on the transport path and the seam's own TTL owns when a
    refresh happens.

    Falls back to ``settings.model_name`` when no seam is present. That is not a
    test-only path: the seam is LM STUDIO's unconditionally (SC-3), so
    composition leaves it unwired on the chat path whenever ``AI_PROVIDER`` names
    a different backend, and this is what that deployment records.
    """
    active_model = getattr(ctx, "active_model", None)
    if active_model is not None:
        profile = active_model.cached_profile("chat")
        if profile is not None and profile.model_id:
            return profile.model_id
    return ctx.settings.model_name


def build_message_request(ctx, envelope: MessageEnvelope) -> MessageRequest:
    """Transport in, ``MessageRequest`` out — and no model facts along the way.

    This used to copy ``ctx.context_window`` and
    ``getattr(ctx, "lmstudio_stop_sequences", ...)`` onto the request. Both are
    gone with ADR-0007 step 4: the processor resolves a profile per request and
    reads them off it. The ``getattr`` in particular existed only because three
    hand-rolled fake route contexts might not define the attribute, and those
    fakes were replaced by a real ``RouteContext`` in step 3.
    """
    return MessageRequest(
        content=envelope.content,
        user_id=envelope.user_id,
        model_name=recorded_model_name(ctx),
    )
