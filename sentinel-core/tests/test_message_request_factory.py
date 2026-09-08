from types import SimpleNamespace

from app.model import ActiveModel, ModelProfile, StaticModelSource
from app.models import MessageEnvelope
from app.services.message_request_factory import build_message_request


def _seam_with_resolved_chat_model(model_id: str) -> ActiveModel:
    """An ActiveModel that has already resolved ``model_id`` for the chat kind."""
    source = StaticModelSource(
        [
            ModelProfile(
                model_id=model_id,
                litellm_model=f"openai/{model_id}",
                api_base="http://lmstudio.test/v1",
                context_window=119552,
            )
        ]
    )
    return ActiveModel([source], SimpleNamespace())


def test_build_message_request_from_context_and_envelope():
    """The request carries transport facts and a recorded name — nothing else.

    ADR-0007 step 4 removed ``context_window`` and ``stop_sequences`` from
    ``MessageRequest``; the context no longer supplies them and the processor
    reads both off the profile it resolves. Asserting their ABSENCE is the point:
    a request that could still carry a window is a request that could carry a
    stale one.
    """
    ctx = SimpleNamespace(settings=SimpleNamespace(model_name="test-model"))
    envelope = MessageEnvelope(content="hello", user_id="user-1")

    req = build_message_request(ctx, envelope)

    assert req.content == "hello"
    assert req.user_id == "user-1"
    assert req.model_name == "test-model"
    assert not hasattr(req, "context_window")
    assert not hasattr(req, "stop_sequences")


async def test_build_message_request_records_the_resolved_model_not_model_name():
    """ADR-0007 Defect B.

    MODEL_NAME is set to something the backend is deliberately NOT serving, so
    a regression cannot pass by coincidence: the two strings differ, and only
    the resolved one is correct.
    """
    seam = _seam_with_resolved_chat_model("qwen/qwen3.8-27b")
    resolved = await seam.for_task("chat")
    assert resolved.model_id == "qwen/qwen3.8-27b"

    ctx = SimpleNamespace(
        settings=SimpleNamespace(model_name="google/gemma-4-31b"),
        active_model=seam,
    )

    req = build_message_request(ctx, MessageEnvelope(content="hi", user_id="user-1"))

    assert req.model_name == "qwen/qwen3.8-27b"
    assert req.model_name != ctx.settings.model_name


async def test_build_message_request_falls_back_to_model_name_without_a_seam():
    """A context with no seam still records a name.

    Composition wires one for every provider as of ADR-0007 step 4 (LM Studio's
    own when it is primary, a config-derived seam for that backend otherwise),
    so this is now a defensive path rather than an ordinary deployment. It is
    kept because ``recorded_model_name`` is on the transport path and must
    never blank the recorded model just because the seam is absent — a blank
    name in session frontmatter is worse than a stale one.
    """
    ctx = SimpleNamespace(
        settings=SimpleNamespace(model_name="configured-model"),
    )

    req = build_message_request(ctx, MessageEnvelope(content="hi", user_id="u"))

    assert req.model_name == "configured-model"


async def test_build_message_request_falls_back_when_the_seam_has_not_resolved_yet():
    """A seam with a cold cache must not blank the recorded name."""
    seam = _seam_with_resolved_chat_model("qwen/qwen3.8-27b")  # never awaited
    ctx = SimpleNamespace(
        settings=SimpleNamespace(model_name="configured-model"),
        active_model=seam,
    )

    req = build_message_request(ctx, MessageEnvelope(content="hi", user_id="u"))

    assert req.model_name == "configured-model"
