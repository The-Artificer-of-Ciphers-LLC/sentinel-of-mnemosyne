"""Tests for pf2e-module startup registration retry logic."""
import os
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


async def test_registration_succeeds_on_first_attempt():
    """Registration completes without retry when Core responds 200 on first attempt."""
    from app.main import _register_with_retry

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()  # does not raise

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await _register_with_retry(mock_client)

    mock_client.post.assert_called_once()
    mock_sleep.assert_not_called()


async def test_registration_retries_on_failure():
    """Registration retries when first attempts fail, succeeds on 3rd attempt."""
    from app.main import _register_with_retry

    success_resp = MagicMock()
    success_resp.raise_for_status = MagicMock()  # does not raise

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=[
            httpx.ConnectError("refused"),
            httpx.ConnectError("refused"),
            success_resp,
        ]
    )

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await _register_with_retry(mock_client)

    assert mock_client.post.call_count == 3
    assert mock_sleep.call_count == 2


async def test_registration_exits_after_all_failures():
    """SystemExit(1) raised after all 5 retry attempts fail (D-16)."""
    from app.main import _register_with_retry

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch("asyncio.sleep", new=AsyncMock()):
        with pytest.raises(SystemExit) as exc_info:
            await _register_with_retry(mock_client)

    assert exc_info.value.code == 1
    assert mock_client.post.call_count == 5


async def test_registration_payload_correct(monkeypatch):
    """Registration POST sends correct payload and X-Sentinel-Key header (D-17)."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-sentinel-key")
    from app.main import _register_with_retry, REGISTRATION_PAYLOAD

    success_resp = MagicMock()
    success_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=success_resp)

    with patch("asyncio.sleep", new=AsyncMock()):
        await _register_with_retry(mock_client)

    call_kwargs = mock_client.post.call_args
    assert call_kwargs.kwargs["json"] == REGISTRATION_PAYLOAD
    assert call_kwargs.kwargs["headers"]["X-Sentinel-Key"] == "test-sentinel-key"
    assert call_kwargs.kwargs["json"]["name"] == "pathfinder"
    assert call_kwargs.kwargs["json"]["base_url"] == "http://pf2e-module:8000"
