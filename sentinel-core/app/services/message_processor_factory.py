"""Factory helper for creating message processors from app state."""

from __future__ import annotations

from app.services.message_processing import MessageProcessor


def from_app_state(app_state) -> MessageProcessor:
    factory = getattr(app_state, "message_processor_factory", None)
    if callable(factory):
        return factory()
    return MessageProcessor(
        obsidian=app_state.obsidian_client,
        ai_provider=app_state.ai_provider,
        injection_filter=app_state.injection_filter,
        output_scanner=app_state.output_scanner,
    )
