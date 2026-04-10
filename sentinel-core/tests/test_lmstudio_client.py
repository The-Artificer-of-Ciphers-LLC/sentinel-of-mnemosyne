"""
Tests for LM Studio HTTP client (CORE-04).
Stubs — implementations filled in Plan 03 (Wave 2).
"""
import pytest


@pytest.mark.skip(reason="Implementation pending — Plan 03 Wave 2")
async def test_lmstudio_client_returns_completion():
    """LM Studio client returns assistant message content from mocked /v1/chat/completions response."""
    pass


@pytest.mark.skip(reason="Implementation pending — Plan 03 Wave 2")
async def test_lmstudio_client_fetches_context_window():
    """get_context_window() returns max_context_length from mocked /api/v0/models/{model} response."""
    pass


@pytest.mark.skip(reason="Implementation pending — Plan 03 Wave 2")
async def test_lmstudio_client_returns_4096_default_on_unavailable():
    """get_context_window() returns 4096 when LM Studio is unreachable (graceful degradation)."""
    pass
