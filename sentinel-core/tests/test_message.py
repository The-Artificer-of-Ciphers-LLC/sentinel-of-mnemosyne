"""
Tests for POST /message endpoint (CORE-03).
Stubs — implementations filled in Plan 03 (Wave 2).
"""
import pytest


@pytest.mark.skip(reason="Implementation pending — Plan 03 Wave 2")
async def test_post_message_returns_response_envelope():
    """POST /message with valid content returns ResponseEnvelope with content and model fields."""
    pass


@pytest.mark.skip(reason="Implementation pending — Plan 03 Wave 2")
async def test_post_message_503_when_lmstudio_unavailable():
    """POST /message returns 503 with error field when LM Studio is unreachable."""
    pass


@pytest.mark.skip(reason="Implementation pending — Plan 03 Wave 2")
async def test_post_message_422_when_message_too_long():
    """POST /message returns 422 when token count exceeds context window."""
    pass
