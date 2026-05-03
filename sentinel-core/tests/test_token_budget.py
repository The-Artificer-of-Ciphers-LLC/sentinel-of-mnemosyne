"""Tests for token budget service (CORE-05)."""
import pytest
from app.services.token_budget import TokenBudget, TokenLimitError


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
