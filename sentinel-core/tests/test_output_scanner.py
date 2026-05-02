"""Tests for OutputScanner service (SEC-02)."""
import pytest
from unittest.mock import AsyncMock

from app.services.output_scanner import OutputScanner


@pytest.fixture
def mock_classifier():
    """Mock secondary classifier callable — returns 'SAFE' by default."""
    return AsyncMock(return_value="SAFE")


@pytest.fixture
def scanner(mock_classifier):
    return OutputScanner(mock_classifier)


# --- clean pass tests ---


async def test_clean_response_passes(scanner, mock_classifier):
    is_safe, reason = await scanner.scan("The model replied with a helpful answer.")
    assert is_safe is True
    assert reason is None
    mock_classifier.assert_not_called()


async def test_empty_response_passes(scanner, mock_classifier):
    is_safe, reason = await scanner.scan("")
    assert is_safe is True
    mock_classifier.assert_not_called()


# --- regex trigger tests ---


async def test_api_key_triggers_classifier_returns_leak():
    classifier = AsyncMock(return_value="LEAK")
    scanner = OutputScanner(classifier)
    is_safe, reason = await scanner.scan("Your key is sk-ant-abc123def456ghi789jkl012mno345")
    assert is_safe is False
    assert reason is not None
    classifier.assert_called_once()


async def test_api_key_triggers_classifier_returns_safe():
    classifier = AsyncMock(return_value="SAFE")
    scanner = OutputScanner(classifier)
    is_safe, reason = await scanner.scan("Your key is sk-ant-abc123def456ghi789jkl012mno345")
    assert is_safe is True
    classifier.assert_called_once()


async def test_openai_style_key_fires(scanner, mock_classifier):
    await scanner.scan("sk-abcdefghijklmnopqrstuvwxyz1234567890")
    mock_classifier.assert_called()


async def test_aws_key_fires(scanner, mock_classifier):
    await scanner.scan("AKIAIOSFODNN7EXAMPLE")
    mock_classifier.assert_called()


async def test_sentinel_key_name_fires(scanner, mock_classifier):
    await scanner.scan("SENTINEL_API_KEY=supersecretvalue123")
    mock_classifier.assert_called()


# --- fail-open tests ---


async def test_timeout_fails_open(monkeypatch):
    """Real asyncio.wait_for timeout — scanner must fail open, not crash."""
    import asyncio as _asyncio

    from app.services import output_scanner as scanner_module

    monkeypatch.setattr(scanner_module, "SECONDARY_TIMEOUT_S", 0.01)

    async def _slow_classifier(excerpt: str, fired_patterns: list[str]) -> str:
        await _asyncio.sleep(1.0)
        return "SAFE"

    scanner = OutputScanner(_slow_classifier)
    is_safe, reason = await scanner.scan("sk-ant-abc123def456ghi789jkl012mno345")
    assert is_safe is True
    assert reason is None


async def test_exception_fails_open():
    classifier = AsyncMock(side_effect=Exception("provider error"))
    scanner = OutputScanner(classifier)
    is_safe, reason = await scanner.scan("sk-ant-abc123def456ghi789jkl012mno345")
    assert is_safe is True


async def test_no_classifier_degrades_gracefully():
    """OutputScanner with None classifier fails open instead of crashing."""
    scanner = OutputScanner(None)
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
    classifier = AsyncMock(return_value="LEAK")
    scanner = OutputScanner(classifier)

    # Build a response where the secret lives well past character 2000
    padding = "x" * 3000
    secret = "sk-ant-abc123def456ghi789jkl012mno345"
    response = padding + secret

    is_safe, reason = await scanner.scan(response)

    # The secret must have been found by the regex and the classifier must have
    # been called with an excerpt that contains it.
    classifier.assert_called_once()
    call_args = classifier.call_args
    excerpt = call_args.args[0]
    assert secret in excerpt, (
        "Excerpt sent to classifier did not contain the secret — window was not centered on match"
    )
    assert is_safe is False


async def test_extract_excerpt_centers_on_match():
    """Unit test for _extract_excerpt: window must contain the match regardless of position."""
    scanner = OutputScanner(None)
    padding = "a" * 4000
    secret = "AKIAIOSFODNN7EXAMPLE"
    response = padding + secret

    excerpt = scanner._extract_excerpt(response, ["aws_access_key"])
    assert secret in excerpt


# --- precision tests ---


async def test_private_ip_does_not_fire_on_plain_ip(scanner, mock_classifier):
    """
    Private IP addresses alone do not trigger the scanner.
    Per Research Pitfall 5: naive IP patterns fire too broadly on normal vault notes.
    Private IP pattern excluded from initial blocklist.
    """
    await scanner.scan("The server is at 192.168.1.1")
    mock_classifier.assert_not_called()
