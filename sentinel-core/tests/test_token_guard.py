"""Tests for token guard service (CORE-05)."""
import pytest
from app.services.token_guard import count_tokens, check_token_limit, TokenLimitError


def test_rejects_oversized():
    """count_tokens() returns value > 8192 for a very long message."""
    long_content = "word " * 10_000
    messages = [{"role": "user", "content": long_content}]
    assert count_tokens(messages) > 8192


def test_permits_normal():
    """count_tokens() returns value well within 8192 for a short message."""
    messages = [{"role": "user", "content": "hello"}]
    assert count_tokens(messages) < 100


def test_token_count_includes_message_overhead():
    """count_tokens() adds 3 tokens per message overhead + 3 priming tokens."""
    # Empty message values: 3 overhead per message + 3 priming = 6 minimum
    messages = [{"role": "", "content": ""}]
    count = count_tokens(messages)
    assert count >= 6  # 3 per-message + 3 priming


def test_check_token_limit_raises_on_exceeded():
    """check_token_limit() raises TokenLimitError when over context window."""
    long_content = "word " * 10_000
    messages = [{"role": "user", "content": long_content}]
    with pytest.raises(TokenLimitError) as exc_info:
        check_token_limit(messages, context_window=8192)
    assert exc_info.value.limit == 8192
    assert exc_info.value.count > 8192


def test_check_token_limit_passes_for_normal():
    """check_token_limit() does not raise for a short message."""
    messages = [{"role": "user", "content": "hello"}]
    check_token_limit(messages, context_window=8192)  # must not raise


def test_multi_message_token_guard():
    """count_tokens() sums tokens across all messages in a 3-message array."""
    messages = [
        {"role": "user", "content": "Here is context about me:\nI am a developer."},
        {"role": "assistant", "content": "Understood."},
        {"role": "user", "content": "What should I build?"},
    ]
    single = [{"role": "user", "content": "What should I build?"}]
    assert count_tokens(messages) > count_tokens(single)
