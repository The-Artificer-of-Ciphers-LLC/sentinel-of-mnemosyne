"""
Tests for token guard service (CORE-05).
Stubs — implementations filled in Plan 03 (Wave 2).
"""
import pytest


@pytest.mark.skip(reason="Implementation pending — Plan 03 Wave 2")
def test_rejects_oversized():
    """count_tokens() returns value > context window for a 10,000-word message."""
    pass


@pytest.mark.skip(reason="Implementation pending — Plan 03 Wave 2")
def test_permits_normal():
    """count_tokens() returns value within 8192-token window for a short message."""
    pass


@pytest.mark.skip(reason="Implementation pending — Plan 03 Wave 2")
def test_token_count_includes_message_overhead():
    """count_tokens() adds 3 tokens per message for role/separator overhead plus 3 priming tokens."""
    pass
