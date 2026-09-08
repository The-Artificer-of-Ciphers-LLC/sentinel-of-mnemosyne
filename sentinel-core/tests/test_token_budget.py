"""Tests for token budget service (CORE-05)."""
import logging

import pytest

from app.model import ModelProfile
from app.services.token_budget import DEFAULT_ENCODING, TokenBudget, TokenLimitError


@pytest.fixture()
def budget():
    return TokenBudget()


def test_rejects_oversized(budget):
    """count() returns value > 8192 for a very long message."""
    long_content = "word " * 10_000
    messages = [{"role": "user", "content": long_content}]
    assert budget.count(messages) > 8192


def test_permits_normal(budget):
    """count() returns value well within 8192 for a short message."""
    messages = [{"role": "user", "content": "hello"}]
    assert budget.count(messages) < 100


def test_token_count_includes_message_overhead(budget):
    """count() adds 3 tokens per message overhead + 3 priming tokens."""
    # Empty message values: 3 overhead per message + 3 priming = 6 minimum
    messages = [{"role": "", "content": ""}]
    count = budget.count(messages)
    assert count >= 6  # 3 per-message + 3 priming


def test_check_raises_on_exceeded(budget):
    """check() raises TokenLimitError when over context window."""
    long_content = "word " * 10_000
    messages = [{"role": "user", "content": long_content}]
    with pytest.raises(TokenLimitError) as exc_info:
        budget.check(messages, context_window=8192)
    assert exc_info.value.limit == 8192
    assert exc_info.value.count > 8192


def test_check_passes_for_normal(budget):
    """check() does not raise for a short message."""
    messages = [{"role": "user", "content": "hello"}]
    budget.check(messages, context_window=8192)  # must not raise


def test_multi_message_count(budget):
    """count() sums tokens across all messages in a 3-message array."""
    messages = [
        {"role": "user", "content": "Here is context about me:\nI am a developer."},
        {"role": "assistant", "content": "Understood."},
        {"role": "user", "content": "What should I build?"},
    ]
    single = [{"role": "user", "content": "What should I build?"}]
    assert budget.count(messages) > budget.count(single)


def test_truncate_short_text_unchanged(budget):
    """truncate() returns text unchanged when it fits within max_tokens."""
    short = "This is a short message."
    assert budget.truncate(short, 100) == short


def test_truncate_long_text(budget):
    """truncate() truncates text and appends marker when over max_tokens."""
    long_content = "word " * 10_000
    result = budget.truncate(long_content, 500)
    assert "[...context truncated to fit token budget]" in result
    # The encoded tokens before the marker should be <= max_tokens.
    # count() adds 6-token overhead (3 per-message + 3 priming),
    # so the counted value will be ~max_tokens + 6.
    marker = "\n\n[...context truncated to fit token budget]"
    text_before_marker = result.replace(marker, "")
    count = budget.count([{"role": "user", "content": text_before_marker}])
    assert count <= 507  # max_tokens (500) + overhead (6) + possible boundary token
    assert count > 500  # must exceed max_tokens for truncation to have occurred


def test_truncate_empty_text(budget):
    """truncate() returns empty string for empty input."""
    assert budget.truncate("", 100) == ""


def test_truncate_zero_max_tokens(budget):
    """truncate() with max_tokens=0 returns only the truncation marker."""
    result = budget.truncate("some content", 0)
    assert result == "\n\n[...context truncated to fit token budget]"


def test_encoding_name_property(budget):
    """encoding_name returns the encoding used."""
    assert budget.encoding_name == "cl100k_base"


def test_custom_encoding():
    """TokenBudget accepts a custom encoding name."""
    custom = TokenBudget(encoding="p50k_base")
    assert custom.encoding_name == "p50k_base"


# ---------------------------------------------------------------------------
# ADR-0007 step 5 — the encoding is NAMED on the profile, and an unknown name
# degrades instead of raising. The approximation itself is accepted (cl100k_base
# is not Qwen's tokenizer); what these pin is that it is stated, and that a
# tokenizer name can never take down the chat path.
# ---------------------------------------------------------------------------


def test_profile_encoding_is_used_and_reported():
    """A profile naming an encoding tiktoken knows gets that encoding."""
    profile = ModelProfile(
        model_id="m", litellm_model="openai/m", tokenizer_encoding="p50k_base"
    )
    budget = TokenBudget.for_profile(profile)

    assert budget.encoding_name == "p50k_base"
    # Really that encoding, not merely a label: p50k_base and cl100k_base
    # tokenise this string to different lengths.
    assert budget.count([{"role": "user", "content": "  indented\tand\ttabbed"}]) != (
        TokenBudget(encoding=DEFAULT_ENCODING).count(
            [{"role": "user", "content": "  indented\tand\ttabbed"}]
        )
    )


def test_unknown_profile_encoding_degrades_with_a_warning(caplog):
    """An unrecognised name warns and falls back — it must never raise.

    ``tiktoken.get_encoding`` raises ValueError on an unknown name, and this
    runs inside message processing. A raise here would turn a cosmetic
    misconfiguration into a failed conversation.
    """
    profile = ModelProfile(
        model_id="m", litellm_model="openai/m", tokenizer_encoding="qwen-bpe-does-not-exist"
    )

    with caplog.at_level(logging.WARNING, logger="app.services.token_budget"):
        budget = TokenBudget.for_profile(profile)

    assert budget.encoding_name == DEFAULT_ENCODING, (
        "encoding_name must report what is IN USE, not what was asked for"
    )
    assert "qwen-bpe-does-not-exist" in caplog.text
    assert budget.count([{"role": "user", "content": "hello"}]) > 0


def test_profile_naming_no_encoding_is_the_default_and_silent(caplog):
    """No encoding named → cl100k_base, and no warning: this is the normal case."""
    profile = ModelProfile(
        model_id="m", litellm_model="openai/m", tokenizer_encoding=""
    )

    with caplog.at_level(logging.WARNING, logger="app.services.token_budget"):
        budget = TokenBudget.for_profile(profile)

    assert budget.encoding_name == DEFAULT_ENCODING
    assert caplog.text == "", f"unexpected warning: {caplog.text}"
