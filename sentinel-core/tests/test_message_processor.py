"""Behavioral tests for MessageProcessor.process().

Each test constructs a real MessageProcessor against fakes and calls
processor.process(MessageRequest(...)) directly. Assertions are strictly
behavioral: return values, raised MessageProcessingError.code, recorded calls
on fakes, caplog records. No source-grep, no tautologies, no echo-chamber
patterns (CLAUDE.md Behavioral-Test-Only Rule).
"""
from __future__ import annotations

import logging

import pytest

from app.services.message_processing import (
    MessageProcessingError,
    MessageProcessor,
    MessageRequest,
    MessageResult,
)
from app.services.provider_router import ContextLengthError, ProviderUnavailableError
from tests.conftest import build_test_active_model

#: Distinguishes "the test did not ask for a particular seam" from the test
#: deliberately wiring none — which is now its own refusal, not a bridge.
_UNSET = object()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeObsidian:
    """In-memory fake of the subset of the Vault that MessageProcessor calls."""

    def __init__(self, persona: str | None = None, self_files: dict[str, str] | None = None):
        self._persona = persona
        self._self_files = self_files or {}
        self.read_self_context_calls: list[str] = []

    async def read_self_context(self, path: str) -> str:
        self.read_self_context_calls.append(path)
        if path == "sentinel/persona.md":
            return self._persona if self._persona is not None else ""
        return self._self_files.get(path, "")

    async def get_recent_sessions(self, user_id: str, limit: int = 3) -> list[str]:
        return []

    async def find(self, query: str) -> list[dict]:
        return []


class FakeAIProvider:
    """Fake AI provider; default returns a canned response, configurable to raise."""

    def __init__(self, response: str = "Acknowledged.", raise_exc: BaseException | None = None):
        self._response = response
        self._raise = raise_exc
        self.received_messages: list[list[dict]] = []
        self.received_profile = None
        self.received_stop: list[str] | None = None
        self.received_temperature: float | None = None

    async def complete(
        self,
        messages: list[dict],
        profile=None,
        stop: list[str] | None = None,
        temperature: float | None = None,
    ) -> str:
        self.received_messages.append(list(messages))
        self.received_profile = profile
        self.received_stop = stop
        self.received_temperature = temperature
        if self._raise is not None:
            raise self._raise
        return self._response


class FakeInjectionFilter:
    """Pass-through injection filter: emits the input verbatim, marks not-blocked."""

    def filter_input(self, text: str) -> tuple[str, bool]:
        return text, False

    def wrap_context(self, text: str) -> str:
        return text


class FakeOutputScanner:
    """Configurable safety scanner."""

    def __init__(self, safe: bool = True, reason: str | None = None):
        self._safe = safe
        self._reason = reason

    async def scan(self, text: str) -> tuple[bool, str | None]:
        return self._safe, self._reason


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_processor(
    *,
    persona: str | None = "TEST PERSONA",
    self_files: dict[str, str] | None = None,
    ai_response: str = "AI says hi.",
    ai_raises: BaseException | None = None,
    output_safe: bool = True,
    active_model=_UNSET,
    context_window: int = 8192,
    stop_sequences: tuple[str, ...] = (),
) -> tuple[MessageProcessor, FakeObsidian, FakeAIProvider]:
    """A processor over a REAL ``ActiveModel`` unless the test supplies its own.

    ``context_window`` and ``stop_sequences`` moved here from ``make_request``
    when ADR-0007 step 4 removed them from ``MessageRequest``. That is not a
    cosmetic move: they are now facts about the model that will answer, so a
    test that wants a tiny window says so by describing the MODEL, which is the
    only thing the processor budgets against.

    ``active_model=None`` still means "no seam wired" — a distinct case with its
    own tests — so the default is a sentinel rather than None.
    """
    obsidian = FakeObsidian(persona=persona, self_files=self_files)
    ai = FakeAIProvider(response=ai_response, raise_exc=ai_raises)
    if active_model is _UNSET:
        active_model = build_test_active_model(
            context_window=context_window, stop_sequences=stop_sequences
        )
    proc = MessageProcessor(
        vault=obsidian,
        ai_provider=ai,
        injection_filter=FakeInjectionFilter(),
        output_scanner=FakeOutputScanner(safe=output_safe),
        active_model=active_model,
    )
    return proc, obsidian, ai


def make_request(content: str = "hello") -> MessageRequest:
    return MessageRequest(content=content, user_id="trekkie", model_name="test-model")


# ---------------------------------------------------------------------------
# Tests — one per scenario in PLAN.md task 7
# ---------------------------------------------------------------------------


async def test_context_overflow_raises_with_correct_code():
    """Token guard fires when messages plus a tiny context_window exceed capacity.

    Behavioral assertion: MessageProcessingError raised with code='context_overflow'."""
    # A model with a 10-token window — the system fallback persona alone exceeds
    # it comfortably. The window is the MODEL's, not the request's (step 4).
    proc, _, _ = make_processor(context_window=10)
    req = make_request(content="some content here")

    with pytest.raises(MessageProcessingError) as excinfo:
        await proc.process(req)

    assert excinfo.value.code == "context_overflow"


async def test_provider_unavailable_raises_with_correct_code():
    """ProviderUnavailableError from ai_provider.complete maps to provider_unavailable."""
    proc, _, _ = make_processor(ai_raises=ProviderUnavailableError("primary down, no fallback"))
    req = make_request()

    with pytest.raises(MessageProcessingError) as excinfo:
        await proc.process(req)

    assert excinfo.value.code == "provider_unavailable"


async def test_security_block_raises_with_correct_code():
    """OutputScanner returning (False, reason) maps to security_blocked."""
    proc, _, _ = make_processor(output_safe=False)
    req = make_request()

    with pytest.raises(MessageProcessingError) as excinfo:
        await proc.process(req)

    assert excinfo.value.code == "security_blocked"


async def test_summary_path_and_content_shape_on_happy_path():
    """A successful process() returns a MessageResult with a vault-shaped summary path
    that contains both the user message and the AI response in its content."""
    proc, _, ai = make_processor(ai_response="Got it. The new car sounds great.")
    req = make_request(content="I bought a new car today.")

    result = await proc.process(req)

    assert isinstance(result, MessageResult)
    assert result.content == "Got it. The new car sounds great."
    assert result.model == "test-model"
    # Path shape: ops/sessions/<date>/<user_id>-<time>.md
    assert result.summary_path.startswith("ops/sessions/")
    assert "/trekkie-" in result.summary_path
    assert result.summary_path.endswith(".md")
    # Content carries both halves of the exchange under their headers.
    assert "## User" in result.summary_content
    assert "I bought a new car today." in result.summary_content
    assert "## Sentinel" in result.summary_content
    assert "Got it. The new car sounds great." in result.summary_content
    # AI provider received exactly one completion call.
    assert len(ai.received_messages) == 1


async def test_persona_vault_read_used_in_system_message():
    """When sentinel/persona.md returns non-empty text, that text replaces the
    fallback persona in messages[0] sent to ai_provider.complete()."""
    proc, obsidian, ai = make_processor(persona="You are TEST PERSONA, the operator's assistant.")
    req = make_request()

    await proc.process(req)

    # The vault was consulted for persona.md (real call, real path).
    assert "sentinel/persona.md" in obsidian.read_self_context_calls
    # ai_provider received messages[0] sourced from the vault, not the fallback.
    assert len(ai.received_messages) == 1
    sent = ai.received_messages[0]
    assert sent[0]["role"] == "system"
    assert sent[0]["content"] == "You are TEST PERSONA, the operator's assistant."
    # And specifically NOT the hardcoded fallback.
    assert sent[0]["content"] != MessageProcessor._FALLBACK_PERSONA


async def test_persona_fallback_when_vault_returns_empty(caplog):
    """When sentinel/persona.md returns empty, messages[0] is _FALLBACK_PERSONA
    and a WARN log is emitted."""
    proc, _, ai = make_processor(persona="")  # vault returns empty string
    req = make_request()

    with caplog.at_level(logging.WARNING, logger="app.services.message_processing"):
        await proc.process(req)

    assert len(ai.received_messages) == 1
    sent = ai.received_messages[0]
    assert sent[0]["role"] == "system"
    assert sent[0]["content"] == MessageProcessor._FALLBACK_PERSONA
    # WARN log surfaced the fallback.
    assert any(
        "persona" in rec.getMessage().lower() and "fallback" in rec.getMessage().lower()
        for rec in caplog.records
    ), f"Expected persona-fallback WARN log; got: {[r.getMessage() for r in caplog.records]}"


async def test_stop_sequences_reach_the_provider():
    """The resolved model's stop sequences must be forwarded as stop=.

    Regression guard for 93df616, where the chat path silently DROPPED stop
    sequences because the provider Protocol did not declare the parameter. The
    source moved from ``req.stop_sequences`` to the resolved profile in
    ADR-0007 step 4; the assertion — that they arrive — is unchanged, and that
    is the part that was ever load-bearing.
    """
    proc, _, ai = make_processor(stop_sequences=("<end_of_turn>",))
    req = make_request()

    await proc.process(req)

    assert ai.received_stop == ["<end_of_turn>"]


async def test_no_stop_sequences_passes_none():
    """When the resolved model has no stop sequences, the provider receives
    stop=None rather than a missing/omitted argument."""
    proc, _, ai = make_processor()
    req = make_request()

    await proc.process(req)

    assert ai.received_stop is None


async def test_litellm_context_length_string_mapped_to_context_overflow():
    """A ContextLengthError raised by the provider layer must map to
    context_overflow, NOT provider_misconfigured. The vendor-specific
    BadRequestError → ContextLengthError translation now lives in
    app/clients/litellm_provider.py; this test enforces the service-layer
    half of the contract."""
    err = ContextLengthError(
        "Message plus context exceeds model capacity. Try a shorter message."
    )
    proc, _, _ = make_processor(ai_raises=err)
    req = make_request()

    with pytest.raises(MessageProcessingError) as excinfo:
        await proc.process(req)

    assert excinfo.value.code == "context_overflow"


async def test_empty_body_session_does_not_introduce_stray_separator():
    """CR-03: a SessionSummary with empty body must not add a stray '---' separator.

    Seeds a FakeVault with one real-body session and one empty-body session.
    Verifies that the injected context block contains the real body and does NOT
    contain a stray '\\n---\\n' left by the empty session.
    """
    from app.services.recall import Recall, RecallConfig, RetentionPolicy
    from tests.fakes.vault import FakeVault
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    notes = {
        # Session with real body
        f"ops/sessions/{today}/trekkie-10-00-00.md": (
            f"---\ndate: {today}\nuser_id: trekkie\ntime: 10-00-00\n---\n"
            "## User\nReal message\n## Sentinel\nReal reply\n"
        ),
        # Session with empty body — should be silently skipped, not add separator
        f"ops/sessions/{today}/trekkie-09-00-00.md": "",
    }
    policy = RetentionPolicy(hot_limit=10, hot_window_days=30)
    vault = FakeVault(notes=notes)
    recall = Recall(vault=vault, config=RecallConfig(), policy=policy)

    # FakeAIProvider captures the messages it receives
    ai = FakeAIProvider(response="OK")
    proc = MessageProcessor(
        vault=vault,
        ai_provider=ai,
        injection_filter=FakeInjectionFilter(),
        output_scanner=FakeOutputScanner(safe=True),
        recall=recall,
        active_model=build_test_active_model(),
    )
    req = make_request(content="test")
    await proc.process(req)

    # Extract the injected context message(s) — they appear before the user prompt
    all_messages = ai.received_messages[-1]
    context_messages = [m["content"] for m in all_messages if m.get("role") == "user"]

    # There should be no "stray" separator: a leading "\n---\n" without preceding content
    # or two consecutive separators, which is what an empty body produces.
    context_text = "\n".join(context_messages)
    # An empty-body session contributes "\n---\n" before actual content.
    # After the fix, the empty session is simply skipped.
    assert "\n---\n\n---\n" not in context_text, (
        "Double separator detected — empty-body session was not skipped: "
        f"{context_text!r}"
    )
    # The real session's content must still appear
    assert "Real message" in context_text or "Real reply" in context_text, (
        "Real session body must be present in context; "
        f"context was: {context_text!r}"
    )


async def test_degenerate_response_logs_response_anomaly_warning_and_is_returned_unchanged(caplog):
    """A degenerate provider response (repeated 'la-system' garbage) trips
    the anomaly detector: exactly one WARNING starting with
    'response-anomaly:' is logged, and the response is still returned
    UNCHANGED to the caller (detection only, never a gate)."""
    degenerate = (
        "This covers la-system methodology, la-system principles, and "
        "la-system markers for managing active requests."
    )
    proc, _, ai = make_processor(ai_response=degenerate)
    req = make_request(content="what is in my second brain?")

    with caplog.at_level(logging.WARNING, logger="app.services.message_processing"):
        result = await proc.process(req)

    assert result.content == degenerate
    anomaly_warnings = [
        r for r in caplog.records
        if r.getMessage().startswith("response-anomaly:")
    ]
    assert len(anomaly_warnings) == 1, (
        f"Expected exactly one response-anomaly warning; got: "
        f"{[r.getMessage() for r in caplog.records]}"
    )


async def test_clean_response_logs_no_response_anomaly_warning(caplog):
    """A well-formed response must not trip the anomaly detector."""
    proc, _, ai = make_processor(ai_response="Got it. That sounds like a great milestone!")
    req = make_request()

    with caplog.at_level(logging.WARNING, logger="app.services.message_processing"):
        result = await proc.process(req)

    assert result.content == "Got it. That sounds like a great milestone!"
    anomaly_warnings = [
        r for r in caplog.records
        if r.getMessage().startswith("response-anomaly:")
    ]
    assert anomaly_warnings == []


async def test_anomaly_detector_raising_does_not_break_message_processing(monkeypatch):
    """If detect_anomalies() itself raises, message processing must still
    succeed and return the content unchanged — observability must never be
    able to take down the message path."""
    import app.services.message_processing as mp_module

    def _boom(*args, **kwargs):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(mp_module, "detect_anomalies", _boom)

    proc, _, ai = make_processor(ai_response="Perfectly normal reply.")
    req = make_request()

    result = await proc.process(req)

    assert result.content == "Perfectly normal reply."


# ---------------------------------------------------------------------------
# ADR-0007 Defect B — end to end
#
# The recorded model name used to be settings.MODEL_NAME, so Session summary
# frontmatter and the response-anomaly log recorded CONFIGURATION rather than
# the model that answered. This is the same failure as the ADR's opening
# observation: the container named google/gemma-4-31b for two days while LM
# Studio served qwen/qwen3.8-27b, and the summaries agreed with the container.
#
# These go through the real build_message_request rather than make_request, so
# the assertion covers the whole path from the seam to the written frontmatter.
# ---------------------------------------------------------------------------


def _ctx_with_resolved_model(resolved_id: str, configured_id: str):
    from types import SimpleNamespace

    from app.model import ActiveModel, ModelProfile, StaticModelSource

    source = StaticModelSource(
        [
            ModelProfile(
                model_id=resolved_id,
                litellm_model=f"openai/{resolved_id}",
                api_base="http://lmstudio.test/v1",
                context_window=8192,
            )
        ]
    )
    seam = ActiveModel([source], SimpleNamespace())
    return seam, SimpleNamespace(
        settings=SimpleNamespace(model_name=configured_id),
        active_model=seam,
    )


async def test_session_summary_frontmatter_records_the_model_that_answered():
    from app.models import MessageEnvelope
    from app.services.message_request_factory import build_message_request

    seam, ctx = _ctx_with_resolved_model("qwen/qwen3.8-27b", "google/gemma-4-31b")
    await seam.for_task("chat")

    req = build_message_request(
        ctx, MessageEnvelope(content="hello", user_id="trekkie")
    )
    # The SAME seam the factory read, which is how composition wires it: one
    # object answers "which model" for the recorded name and for the completion.
    proc, _, _ = make_processor(ai_response="Noted.", active_model=seam)

    result = await proc.process(req)

    assert result.model == "qwen/qwen3.8-27b"
    assert "model: qwen/qwen3.8-27b" in result.summary_content
    assert "google/gemma-4-31b" not in result.summary_content, (
        "the frontmatter must record the model that answered, not MODEL_NAME"
    )


async def test_response_anomaly_warning_records_the_model_that_answered(caplog):
    from app.models import MessageEnvelope
    from app.services.message_request_factory import build_message_request

    seam, ctx = _ctx_with_resolved_model("qwen/qwen3.8-27b", "google/gemma-4-31b")
    await seam.for_task("chat")

    req = build_message_request(
        ctx,
        MessageEnvelope(content="what is in my second brain?", user_id="trekkie"),
    )
    degenerate = (
        "This covers la-system methodology, la-system principles, and "
        "la-system markers for managing active requests."
    )
    proc, _, _ = make_processor(ai_response=degenerate, active_model=seam)

    with caplog.at_level(logging.WARNING, logger="app.services.message_processing"):
        await proc.process(req)

    anomalies = [
        r.getMessage()
        for r in caplog.records
        if r.getMessage().startswith("response-anomaly:")
    ]
    assert len(anomalies) == 1
    assert "model=qwen/qwen3.8-27b" in anomalies[0]
    assert "gemma" not in anomalies[0]


# ---------------------------------------------------------------------------
# ADR-0007 decision 4 (as amended 2026-09-08) — an unresolvable model is a
# refusal, not a fallback.
#
# `for_task` RAISES when a live backend's candidates cannot be disambiguated,
# where an earlier draft returned a config-named phantom. That gives the chat
# path a failure mode it did not have before, and the rule is: surface it, do
# not route it to the paid cloud provider. Routing it there would convert an
# operator error into a bill AND hide the condition the raise exists to announce.
# ---------------------------------------------------------------------------


class _RaisingModelSource:
    """A real ModelSource whose backend answers with nothing usable.

    Not a stub that raises: it returns an EMPTY candidate set, which is what a
    reachable-but-undisambiguatable backend actually produces, and lets
    ActiveModel's own refusal rung do the raising.
    """

    async def candidates(self):
        from app.model import ModelCandidates

        return ModelCandidates()


async def test_unresolvable_model_surfaces_as_a_clean_error():
    """A resolution failure is a MessageProcessingError, not an unhandled 500."""
    from app.model import ActiveModel

    proc, _, _ = make_processor(active_model=ActiveModel([_RaisingModelSource()]))

    with pytest.raises(MessageProcessingError) as excinfo:
        await proc.process(make_request())

    assert excinfo.value.code == "model_unresolved"
    # The detail must not name what WAS loaded, however tempting it is to help:
    # same leak rule the HTTP path follows (T-42-08).
    assert "lmstudio" not in str(excinfo.value).lower()


async def test_unresolvable_model_never_reaches_the_provider():
    """The other half: the provider — and therefore the paid cloud fallback
    behind it — is never called at all."""
    from app.model import ActiveModel

    proc, _, ai = make_processor(active_model=ActiveModel([_RaisingModelSource()]))

    with pytest.raises(MessageProcessingError):
        await proc.process(make_request())

    assert ai.received_messages == [], "no completion may be attempted"


async def test_resolved_profile_is_passed_to_the_provider():
    """The profile is the argument: what the seam resolved is what the provider
    receives, and the chat path budgets against ITS context window rather than
    the request's."""
    from types import SimpleNamespace

    from app.model import ActiveModel, ModelProfile, StaticModelSource

    resolved = ModelProfile(
        model_id="qwen/qwen3.8-27b",
        litellm_model="openai/qwen/qwen3.8-27b",
        api_base="http://lmstudio.test/v1",
        context_window=119552,
        stop_sequences=("<|im_end|>",),
    )
    seam = ActiveModel([StaticModelSource([resolved])], SimpleNamespace())
    proc, _, ai = make_processor(active_model=seam)

    # The request names a DIFFERENT model (``test-model``) and carries no window
    # of its own at all any more — the profile is the single source of both.
    await proc.process(make_request())

    assert ai.received_profile is not None
    assert ai.received_profile.model_id == "qwen/qwen3.8-27b"
    assert ai.received_profile.context_window == 119552
    assert ai.received_stop == ["<|im_end|>"]


async def test_a_processor_with_no_seam_refuses_rather_than_guessing_a_window():
    """No ActiveModel is a refusal, not a fallback.

    Until ADR-0007 step 4 this bridged from ``MessageRequest``'s own
    ``context_window`` / ``stop_sequences``. Those are gone, and the tempting
    replacement — a declared 4096-token profile — would silently truncate
    context on a real deployment while every test stayed green. Composition
    always wires a seam, so reaching here at all is a wiring bug and must say so.
    """
    proc, _, ai = make_processor(active_model=None)

    with pytest.raises(MessageProcessingError) as excinfo:
        await proc.process(make_request())

    assert excinfo.value.code == "model_unresolved"
    assert ai.received_messages == [], "no completion may be attempted"


# Mark all tests in this module as async — pytest-asyncio is in auto mode per
# pyproject.toml (asyncio_mode="auto"), but make the dependency explicit.
pytestmark = pytest.mark.asyncio
