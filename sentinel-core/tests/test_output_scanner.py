"""Tests for OutputScanner service (SEC-02)."""
import pytest
from unittest.mock import AsyncMock

from app.services.output_scanner import OutputScanner


def _ai_provider_returning(verdict: str) -> AsyncMock:
    """Build a mock ProviderRouter whose .complete returns the given verdict."""
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=verdict)
    return provider


@pytest.fixture
def mock_ai_provider():
    """Mock ProviderRouter — `complete` returns 'SAFE' by default."""
    return _ai_provider_returning("SAFE")


@pytest.fixture
def scanner(mock_ai_provider):
    return OutputScanner(ai_provider=mock_ai_provider)


# --- clean pass tests ---


async def test_clean_response_passes(scanner, mock_ai_provider):
    is_safe, reason = await scanner.scan("The model replied with a helpful answer.")
    assert is_safe is True
    assert reason is None
    mock_ai_provider.complete.assert_not_called()


async def test_empty_response_passes(scanner, mock_ai_provider):
    is_safe, reason = await scanner.scan("")
    assert is_safe is True
    mock_ai_provider.complete.assert_not_called()


# --- regex trigger tests ---


async def test_api_key_triggers_classifier_returns_leak():
    ai_provider = _ai_provider_returning("LEAK")
    scanner = OutputScanner(ai_provider=ai_provider)
    is_safe, reason = await scanner.scan("Your key is sk-ant-abc123def456ghi789jkl012mno345")
    assert is_safe is False
    assert reason is not None
    ai_provider.complete.assert_called_once()


async def test_api_key_triggers_classifier_returns_safe():
    ai_provider = _ai_provider_returning("SAFE")
    scanner = OutputScanner(ai_provider=ai_provider)
    is_safe, reason = await scanner.scan("Your key is sk-ant-abc123def456ghi789jkl012mno345")
    assert is_safe is True
    ai_provider.complete.assert_called_once()


async def test_openai_style_key_fires(scanner, mock_ai_provider):
    await scanner.scan("sk-abcdefghijklmnopqrstuvwxyz1234567890")
    mock_ai_provider.complete.assert_called()


async def test_aws_key_fires(scanner, mock_ai_provider):
    await scanner.scan("AKIAIOSFODNN7EXAMPLE")
    mock_ai_provider.complete.assert_called()


async def test_sentinel_key_name_fires(scanner, mock_ai_provider):
    await scanner.scan("SENTINEL_API_KEY=supersecretvalue123")
    mock_ai_provider.complete.assert_called()


# --- fail-open tests ---


async def test_timeout_fails_open(monkeypatch):
    """Real asyncio.wait_for timeout — scanner must fail open, not crash."""
    import asyncio as _asyncio

    from app.services import output_scanner as scanner_module

    monkeypatch.setattr(scanner_module, "SECONDARY_TIMEOUT_S", 0.01)

    async def _slow_complete(messages):
        await _asyncio.sleep(1.0)
        return "SAFE"

    slow_ai_provider = AsyncMock()
    slow_ai_provider.complete = _slow_complete

    scanner = OutputScanner(ai_provider=slow_ai_provider)
    is_safe, reason = await scanner.scan("sk-ant-abc123def456ghi789jkl012mno345")
    assert is_safe is True
    assert reason is None


async def test_exception_fails_open():
    ai_provider = AsyncMock()
    ai_provider.complete = AsyncMock(side_effect=Exception("provider error"))
    scanner = OutputScanner(ai_provider=ai_provider)
    is_safe, reason = await scanner.scan("sk-ant-abc123def456ghi789jkl012mno345")
    assert is_safe is True


async def test_no_classifier_degrades_gracefully():
    """OutputScanner with no ai_provider fails open instead of crashing."""
    scanner = OutputScanner(ai_provider=None)
    is_safe, reason = await scanner.scan("sk-ant-abc123def456ghi789jkl012")
    assert is_safe is True


# --- excerpt window tests (HR-02) ---


async def test_secret_at_position_beyond_2000_is_caught():
    """
    Regression test for HR-02: a secret that appears after position 2000 in the
    response must still be visible to the secondary classifier.  The old code used
    response[:2000] which would miss the secret entirely; _extract_excerpt now
    centers the window on the match position.
    """
    ai_provider = _ai_provider_returning("LEAK")
    scanner = OutputScanner(ai_provider=ai_provider)

    # Build a response where the secret lives well past character 2000
    padding = "x" * 3000
    secret = "sk-ant-abc123def456ghi789jkl012mno345"
    response = padding + secret

    is_safe, reason = await scanner.scan(response)

    # The secret must have been found by the regex and the classifier must have
    # been called with an excerpt that contains it.
    ai_provider.complete.assert_called_once()
    call_args = ai_provider.complete.call_args
    messages = call_args.args[0]
    # The excerpt is embedded in the user-message content; the system message is index 0.
    user_content = messages[1]["content"]
    assert secret in user_content, (
        "Excerpt sent to classifier did not contain the secret — window was not centered on match"
    )
    assert is_safe is False


async def test_extract_excerpt_centers_on_match():
    """Unit test for _extract_excerpt: window must contain the match regardless of position."""
    scanner = OutputScanner(ai_provider=None)
    padding = "a" * 4000
    secret = "AKIAIOSFODNN7EXAMPLE"
    response = padding + secret

    excerpt = scanner._extract_excerpt(response, ["aws_access_key"])
    assert secret in excerpt


# --- precision tests ---


async def test_private_ip_does_not_fire_on_plain_ip(scanner, mock_ai_provider):
    """
    Private IP addresses alone do not trigger the scanner.
    Per Research Pitfall 5: naive IP patterns fire too broadly on normal vault notes.
    Private IP pattern excluded from initial blocklist.
    """
    await scanner.scan("The server is at 192.168.1.1")
    mock_ai_provider.complete.assert_not_called()
