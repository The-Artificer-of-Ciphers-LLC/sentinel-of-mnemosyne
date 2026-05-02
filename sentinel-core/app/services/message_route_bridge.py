"""Bridge helpers for message route adapter."""

from __future__ import annotations

from app.services.message_processing import MessageRequest


def build_message_request(*, envelope, app_state) -> MessageRequest:
    stop_sequences = getattr(app_state, "lmstudio_stop_sequences", None) or None
    return MessageRequest(
        content=envelope.content,
        user_id=envelope.user_id,
        model_name=app_state.settings.model_name,
        context_window=app_state.context_window,
        stop_sequences=stop_sequences,
    )
