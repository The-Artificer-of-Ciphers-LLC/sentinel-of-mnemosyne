from types import SimpleNamespace

from app.models import MessageEnvelope
from app.services.message_route_bridge import build_message_request


def test_build_message_request_uses_state_model_and_context_window():
    env = MessageEnvelope(content="hi", user_id="u1")
    state = SimpleNamespace(
        lmstudio_stop_sequences=["</s>"],
        settings=SimpleNamespace(model_name="m1"),
        context_window=8192,
    )
    req = build_message_request(envelope=env, app_state=state)
    assert req.model_name == "m1"
    assert req.context_window == 8192
    assert req.stop_sequences == ["</s>"]
