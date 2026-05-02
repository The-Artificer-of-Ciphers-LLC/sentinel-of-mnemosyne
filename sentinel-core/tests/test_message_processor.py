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


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeObsidian:
    """In-memory fake of the subset of ObsidianClient that MessageProcessor calls."""

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

    async def search_vault(self, query: str) -> list[dict]:
        return []


class FakeAIProvider:
    """Fake AI provider; default returns a canned response, configurable to raise."""

    def __init__(self, response: str = "Acknowledged.", raise_exc: BaseException | None = None):
        self._response = response
        self._raise = raise_exc
        self.received_messages: list[list[dict]] = []

    async def complete(self, messages: list[dict]) -> str:
        self.received_messages.append(list(messages))
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
) -> tuple[MessageProcessor, FakeObsidian, FakeAIProvider]:
    obsidian = FakeObsidian(persona=persona, self_files=self_files)
    ai = FakeAIProvider(response=ai_response, raise_exc=ai_raises)
    proc = MessageProcessor(
        obsidian=obsidian,
        ai_provider=ai,
        injection_filter=FakeInjectionFilter(),
        output_scanner=FakeOutputScanner(safe=output_safe),
    )
    return proc, obsidian, ai


def make_request(content: str = "hello", context_window: int = 8192) -> MessageRequest:
    return MessageRequest(
        content=content,
        user_id="trekkie",
        model_name="test-model",
        context_window=context_window,
        stop_sequences=None,
    )


# ---------------------------------------------------------------------------
# Tests — one per scenario in PLAN.md task 7
# ---------------------------------------------------------------------------


async def test_context_overflow_raises_with_correct_code():
    """Token guard fires when messages plus a tiny context_window exceed capacity.

    Behavioral assertion: MessageProcessingError raised with code='context_overflow'."""
    proc, _, _ = make_processor()
    # context_window=10 — system fallback persona alone exceeds this comfortably.
    req = make_request(content="some content here", context_window=10)

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


# Mark all tests in this module as async — pytest-asyncio is in auto mode per
# pyproject.toml (asyncio_mode="auto"), but make the dependency explicit.
pytestmark = pytest.mark.asyncio
