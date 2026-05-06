"""Factory for MessageRequest transport inputs."""

from __future__ import annotations

from app.models import MessageEnvelope
from app.services.message_processing import MessageRequest


def build_message_request(ctx, envelope: MessageEnvelope) -> MessageRequest:
    stop_sequences = getattr(ctx, "lmstudio_stop_sequences", None) or None
    return MessageRequest(
        content=envelope.content,
        user_id=envelope.user_id,
        model_name=ctx.settings.model_name,
        context_window=ctx.context_window,
        stop_sequences=stop_sequences,
    )
