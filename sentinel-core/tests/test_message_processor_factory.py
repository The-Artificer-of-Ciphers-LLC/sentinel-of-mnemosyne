from types import SimpleNamespace

from app.services.message_processing import MessageProcessor
from app.services.message_processor_factory import from_app_state


def test_from_app_state_uses_factory_when_callable():
    sentinel = object()
    state = SimpleNamespace(message_processor_factory=lambda: sentinel)
    assert from_app_state(state) is sentinel


def test_from_app_state_builds_default_processor():
    state = SimpleNamespace(
        message_processor_factory=None,
        obsidian_client=object(),
        ai_provider=object(),
        injection_filter=object(),
        output_scanner=object(),
    )
    out = from_app_state(state)
    assert isinstance(out, MessageProcessor)
