"""Tests for SentinelCoreClient — shared HTTP client used by all interfaces."""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from shared.sentinel_client import SentinelCoreClient


@pytest.fixture
def client():
    return SentinelCoreClient(
        base_url="http://sentinel-core:8000",
        api_key="test-secret-key",
        timeout=10.0,
    )


async def test_send_message_success(client):
    """200 response with {"content": "AI reply"} returns "AI reply"."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"content": "AI reply"}
    mock_resp.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_resp)

    result = await client.send_message("user1", "hello", mock_http)
    assert result == "AI reply"
    mock_http.post.assert_called_once()


async def test_send_message_timeout(client):
    """httpx.TimeoutException returns a user-facing timeout string (contains "too long")."""
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    result = await client.send_message("user1", "hello", mock_http)
    assert "too long" in result.lower()


async def test_send_message_401(client):
    """HTTPStatusError with status 401 returns auth error string (contains "Authentication")."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(
        side_effect=httpx.HTTPStatusError("401", request=MagicMock(), response=mock_resp)
    )

    result = await client.send_message("user1", "hello", mock_http)
    assert "Authentication" in result


async def test_send_message_422(client):
    """HTTPStatusError with status 422 returns context-too-long string (contains "too long")."""
    mock_resp = MagicMock()
    mock_resp.status_code = 422

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(
        side_effect=httpx.HTTPStatusError("422", request=MagicMock(), response=mock_resp)
    )

    result = await client.send_message("user1", "hello", mock_http)
    assert "too long" in result.lower()


async def test_send_message_connect_error(client):
    """httpx.ConnectError returns unreachable string (contains "Cannot reach")."""
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    result = await client.send_message("user1", "hello", mock_http)
    assert "Cannot reach" in result


async def test_send_message_never_leaks_url(client):
    """ConnectError error string returned to caller does NOT contain the base_url value."""
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    result = await client.send_message("user1", "hello", mock_http)
    # The base_url "http://sentinel-core:8000" must not appear in the returned string
    assert "sentinel-core:8000" not in result
    assert "http://sentinel-core" not in result


async def test_send_message_never_leaks_api_key(client):
    """Error strings returned to caller do NOT contain the api_key value."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(
        side_effect=httpx.HTTPStatusError("401", request=MagicMock(), response=mock_resp)
    )

    result = await client.send_message("user1", "hello", mock_http)
    # The api_key "test-secret-key" must not appear in the returned string
    assert "test-secret-key" not in result


# ---------------------------------------------------------------------------
# post_to_module() tests — RED phase (Task 1, 29-03)
# ---------------------------------------------------------------------------


async def test_post_to_module_success(client):
    """200 response returns parsed JSON dict."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"name": "Varek", "slug": "varek", "path": "mnemosyne/pf2e/npcs/varek.md"}
    mock_resp.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_resp)

    result = await client.post_to_module("modules/pathfinder/npc/create", {"name": "Varek"}, mock_http)
    assert result == {"name": "Varek", "slug": "varek", "path": "mnemosyne/pf2e/npcs/varek.md"}
    mock_http.post.assert_called_once()
    call_url = mock_http.post.call_args[0][0]
    assert call_url.endswith("modules/pathfinder/npc/create")


async def test_post_to_module_strips_leading_slash(client):
    """Leading slash in path is stripped so URL is not doubled."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": True}
    mock_resp.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_resp)

    await client.post_to_module("/modules/pathfinder/npc/show", {"name": "Varek"}, mock_http)
    call_url = mock_http.post.call_args[0][0]
    assert "//" not in call_url.replace("http://", "")


async def test_post_to_module_raises_http_status_error(client):
    """4xx/5xx HTTPStatusError propagates to caller (not swallowed)."""
    mock_resp = MagicMock()
    mock_resp.status_code = 409

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(
        side_effect=httpx.HTTPStatusError("409", request=MagicMock(), response=mock_resp)
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.post_to_module("modules/pathfinder/npc/create", {"name": "Varek"}, mock_http)


async def test_post_to_module_raises_connect_error(client):
    """ConnectError propagates to caller (not swallowed)."""
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(httpx.ConnectError):
        await client.post_to_module("modules/pathfinder/npc/create", {"name": "Varek"}, mock_http)


async def test_post_to_module_sends_sentinel_key_header(client):
    """X-Sentinel-Key header is sent with correct value on every call."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    mock_resp.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_resp)

    await client.post_to_module("modules/pathfinder/npc/show", {"name": "Varek"}, mock_http)
    call_kwargs = mock_http.post.call_args[1]
    assert call_kwargs["headers"]["X-Sentinel-Key"] == "test-secret-key"
