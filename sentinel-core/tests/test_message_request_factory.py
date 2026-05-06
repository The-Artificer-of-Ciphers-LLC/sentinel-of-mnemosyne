from types import SimpleNamespace

from app.models import MessageEnvelope
from app.services.message_request_factory import build_message_request


def test_build_message_request_from_context_and_envelope():
    ctx = SimpleNamespace(
        settings=SimpleNamespace(model_name="test-model"),
        context_window=8192,
        lmstudio_stop_sequences=["</s>"],
    )
    envelope = MessageEnvelope(content="hello", user_id="user-1")

    req = build_message_request(ctx, envelope)

    assert req.content == "hello"
    assert req.user_id == "user-1"
    assert req.model_name == "test-model"
    assert req.context_window == 8192
    assert req.stop_sequences == ["</s>"]
