"""
Tests for PiAdapterClient retry logic (PROV-03).
"""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from app.clients.pi_adapter import PiAdapterClient


def make_mock_response(content="ok"):
    """httpx Response methods (raise_for_status, json) are sync — use MagicMock."""
    resp = MagicMock()
    resp.json.return_value = {"content": content}
    resp.raise_for_status.return_value = None
    return resp


@pytest.fixture
def http_client():
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def pi_client(http_client):
    return PiAdapterClient(http_client=http_client, harness_url="http://pi:8765")


@pytest.mark.asyncio
async def test_send_messages_success(pi_client, http_client):
    """Happy path — single call succeeds."""
    http_client.post.return_value = make_mock_response("hello")

    result = await pi_client.send_messages([{"role": "user", "content": "hi"}])
    assert result == "hello"
    assert http_client.post.call_count == 1


@pytest.mark.asyncio
async def test_send_messages_retries_on_connect_error(pi_client, http_client):
    """ConnectError triggers 3 retry attempts before reraising (PROV-03)."""
    http_client.post.side_effect = httpx.ConnectError("refused")

    with pytest.raises(httpx.ConnectError):
        await pi_client.send_messages([{"role": "user", "content": "hi"}])

    assert http_client.post.call_count == 3


@pytest.mark.asyncio
async def test_send_messages_retries_on_timeout(pi_client, http_client):
    """TimeoutException triggers 3 retry attempts before reraising (PROV-03)."""
    http_client.post.side_effect = httpx.TimeoutException("timeout")

    with pytest.raises(httpx.TimeoutException):
        await pi_client.send_messages([{"role": "user", "content": "hi"}])

    assert http_client.post.call_count == 3


@pytest.mark.asyncio
async def test_send_messages_succeeds_on_retry(pi_client, http_client):
    """Transient failure followed by success — retries until OK."""
    http_client.post.side_effect = [
        httpx.ConnectError("refused"),
        make_mock_response("recovered"),
    ]

    result = await pi_client.send_messages([{"role": "user", "content": "hi"}])
    assert result == "recovered"
    assert http_client.post.call_count == 2


@pytest.mark.asyncio
async def test_send_messages_hard_timeout_set(pi_client, http_client):
    """send_messages uses 90s hard timeout per call (PROV-03)."""
    http_client.post.return_value = make_mock_response("ok")

    await pi_client.send_messages([{"role": "user", "content": "hi"}])

    call_kwargs = http_client.post.call_args[1]
    assert call_kwargs["timeout"] == 90.0


@pytest.mark.asyncio
async def test_send_messages_no_retry_on_http_error(pi_client, http_client):
    """HTTP errors (4xx/5xx) are NOT retried — only connection failures are."""
    mock_request = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "503", request=mock_request, response=mock_response
    )
    http_client.post.return_value = mock_response

    with pytest.raises(httpx.HTTPStatusError):
        await pi_client.send_messages([{"role": "user", "content": "hi"}])

    assert http_client.post.call_count == 1
