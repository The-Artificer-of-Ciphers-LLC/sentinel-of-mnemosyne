"""Tests for OutputScanner service (SEC-02)."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.output_scanner import OutputScanner


@pytest.fixture
def mock_anthropic():
    """Mock Anthropic client with async messages.create."""
    client = MagicMock()
    client.messages.create = AsyncMock(
        return_value=MagicMock(content=[MagicMock(text="SAFE")])
    )
    return client


@pytest.fixture
def scanner(mock_anthropic):
    return OutputScanner(mock_anthropic)


# --- clean pass tests ---


async def test_clean_response_passes(scanner, mock_anthropic):
    is_safe, reason = await scanner.scan("The model replied with a helpful answer.")
    assert is_safe is True
    assert reason is None
    mock_anthropic.messages.create.assert_not_called()


async def test_empty_response_passes(scanner, mock_anthropic):
    is_safe, reason = await scanner.scan("")
    assert is_safe is True
    mock_anthropic.messages.create.assert_not_called()


# --- regex trigger tests ---


async def test_api_key_triggers_haiku_returns_leak(mock_anthropic):
    mock_anthropic.messages.create = AsyncMock(
        return_value=MagicMock(content=[MagicMock(text="LEAK")])
    )
    scanner = OutputScanner(mock_anthropic)
    is_safe, reason = await scanner.scan("Your key is sk-ant-abc123def456ghi789jkl012mno345")
    assert is_safe is False
    assert reason is not None
    mock_anthropic.messages.create.assert_called_once()


async def test_api_key_triggers_haiku_returns_safe(mock_anthropic):
    # mock returns SAFE (default fixture)
    scanner = OutputScanner(mock_anthropic)
    is_safe, reason = await scanner.scan("Your key is sk-ant-abc123def456ghi789jkl012mno345")
    assert is_safe is True
    mock_anthropic.messages.create.assert_called_once()


async def test_openai_style_key_fires(scanner, mock_anthropic):
    await scanner.scan("sk-abcdefghijklmnopqrstuvwxyz1234567890")
    mock_anthropic.messages.create.assert_called()


async def test_aws_key_fires(scanner, mock_anthropic):
    await scanner.scan("AKIAIOSFODNN7EXAMPLE")
    mock_anthropic.messages.create.assert_called()


async def test_sentinel_key_name_fires(scanner, mock_anthropic):
    await scanner.scan("SENTINEL_API_KEY=supersecretvalue123")
    mock_anthropic.messages.create.assert_called()


# --- fail-open tests ---


async def test_timeout_fails_open(mock_anthropic):
    mock_anthropic.messages.create = AsyncMock(side_effect=asyncio.TimeoutError())
    scanner = OutputScanner(mock_anthropic)
    is_safe, reason = await scanner.scan("sk-ant-abc123def456ghi789jkl012mno345")
    assert is_safe is True


async def test_exception_fails_open(mock_anthropic):
    mock_anthropic.messages.create = AsyncMock(side_effect=Exception("API error"))
    scanner = OutputScanner(mock_anthropic)
    is_safe, reason = await scanner.scan("sk-ant-abc123def456ghi789jkl012mno345")
    assert is_safe is True


async def test_anthropic_key_not_set_degrades_gracefully():
    """OutputScanner with None client fails open instead of crashing."""
    scanner = OutputScanner(None)
    is_safe, reason = await scanner.scan("sk-ant-abc123def456ghi789jkl012")
    assert is_safe is True


# --- precision tests ---


async def test_private_ip_does_not_fire_on_plain_ip(scanner, mock_anthropic):
    """
    Private IP addresses alone do not trigger the scanner.
    Per Research Pitfall 5: naive IP patterns fire too broadly on normal vault notes.
    Private IP pattern excluded from initial blocklist.
    """
    await scanner.scan("The server is at 192.168.1.1")
    mock_anthropic.messages.create.assert_not_called()
