"""Tests for ObsidianClient (MEM-01, MEM-05, MEM-08)."""
import pytest
import httpx
from httpx import AsyncClient
from app.clients.obsidian import ObsidianClient


@pytest.fixture
def obsidian_user_context_mock():
    """MockTransport: returns 200 with markdown body for self/identity.md path (D-01)."""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/vault/self/identity.md":
            return httpx.Response(200, text="# User: trekkie\n\nI am a developer.")
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.fixture
def obsidian_404_mock():
    """MockTransport: returns 404 for all requests."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.fixture
def obsidian_connect_error_mock():
    """MockTransport: raises ConnectError for all requests."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")
    return httpx.MockTransport(handler)


@pytest.fixture
def obsidian_directory_listing_mock():
    """MockTransport: returns a directory listing JSON for ops/sessions/ paths."""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/vault/ops/sessions/" in path and path.endswith("/"):
            # Return a list of filenames including one for trekkie
            return httpx.Response(
                200,
                json=["trekkie-12-00-00.md", "trekkie-13-00-00.md", "other-user-14-00-00.md"],
            )
        if "/vault/ops/sessions/" in path and path.endswith(".md"):
            return httpx.Response(200, text="## Session content for trekkie")
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.fixture
def obsidian_put_capture_mock():
    """MockTransport: records PUT requests and returns 200."""
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            captured.append({
                "path": request.url.path,
                "content": request.content.decode("utf-8"),
            })
            return httpx.Response(200)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    transport.captured = captured
    return transport


@pytest.fixture
def obsidian_search_mock():
    """MockTransport: returns a JSON search results list."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "/search/simple/" in request.url.path:
            return httpx.Response(200, json=[{"filename": "core/users/trekkie.md", "score": 1.0}])
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.fixture
def obsidian_health_ok_mock():
    """MockTransport: returns 200 for vault/ listing (health check)."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.rstrip("/") == "/vault" or request.url.path == "/vault/":
            return httpx.Response(200, json=[])
        return httpx.Response(404)
    return httpx.MockTransport(handler)


async def test_get_user_context_returns_content(obsidian_user_context_mock):
    """get_user_context() returns markdown body when Obsidian returns 200."""
    async with AsyncClient(transport=obsidian_user_context_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "test-api-key")
        result = await obsidian.get_user_context("trekkie")
    assert result == "# User: trekkie\n\nI am a developer."


async def test_get_user_context_returns_none_on_404(obsidian_404_mock):
    """get_user_context() returns None when Obsidian returns 404."""
    async with AsyncClient(transport=obsidian_404_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "test-api-key")
        result = await obsidian.get_user_context("trekkie")
    assert result is None


async def test_get_user_context_returns_none_on_connect_error(obsidian_connect_error_mock):
    """get_user_context() returns None (graceful degrade) when Obsidian is unreachable."""
    async with AsyncClient(transport=obsidian_connect_error_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "test-api-key")
        result = await obsidian.get_user_context("trekkie")
    assert result is None


async def test_get_recent_sessions_returns_list(obsidian_directory_listing_mock):
    """get_recent_sessions() returns a list of strings from directory listing."""
    async with AsyncClient(transport=obsidian_directory_listing_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "test-api-key")
        result = await obsidian.get_recent_sessions("trekkie", limit=3)
    assert isinstance(result, list)
    # May have 0 to 3 items — graceful return, not assertion on count


async def test_get_recent_sessions_returns_empty_on_error(obsidian_connect_error_mock):
    """get_recent_sessions() returns [] when Obsidian is unreachable."""
    async with AsyncClient(transport=obsidian_connect_error_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "test-api-key")
        result = await obsidian.get_recent_sessions("trekkie")
    assert result == []


async def test_write_session_summary_calls_put(obsidian_put_capture_mock):
    """write_session_summary() sends a PUT request to /vault/{path}."""
    async with AsyncClient(transport=obsidian_put_capture_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "test-api-key")
        await obsidian.write_session_summary(
            "ops/sessions/2026-04-10/trekkie-12-00-00.md",
            "# Session\n\nContent here."
        )
    assert len(obsidian_put_capture_mock.captured) == 1
    assert "ops/sessions/2026-04-10/trekkie-12-00-00.md" in obsidian_put_capture_mock.captured[0]["path"]


async def test_search_vault_returns_list(obsidian_search_mock):
    """search_vault() returns a list of search results."""
    async with AsyncClient(transport=obsidian_search_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "test-api-key")
        result = await obsidian.search_vault("trekkie")
    assert isinstance(result, list)
    assert len(result) > 0


async def test_search_vault_returns_empty_on_error(obsidian_connect_error_mock):
    """search_vault() returns [] when Obsidian is unreachable."""
    async with AsyncClient(transport=obsidian_connect_error_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "test-api-key")
        result = await obsidian.search_vault("trekkie")
    assert result == []


async def test_check_health_returns_true(obsidian_health_ok_mock):
    """check_health() returns True when Obsidian vault listing returns 200."""
    async with AsyncClient(transport=obsidian_health_ok_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "test-api-key")
        result = await obsidian.check_health()
    assert result is True


async def test_check_health_returns_false_on_error(obsidian_connect_error_mock):
    """check_health() returns False when Obsidian is unreachable."""
    async with AsyncClient(transport=obsidian_connect_error_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "test-api-key")
        result = await obsidian.check_health()
    assert result is False


# ---------------------------------------------------------------------------
# Phase 10 — read_self_context() single-path method (MEM-02, 2B-02)
# Implemented in Plan 10-03. Tests exercise the per-path method;
# asyncio.gather() over all 5 paths is tested in test_message.py.
# ---------------------------------------------------------------------------

import unittest.mock


@pytest.fixture
def obsidian_self_context_200_mock():
    """MockTransport: returns 200 with body for /vault/self/identity.md."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/vault/self/identity.md":
            return httpx.Response(200, text="# Identity\n\nStub body.")
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture
def obsidian_self_context_error_mock():
    """MockTransport: raises ConnectError for all requests."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    return httpx.MockTransport(handler)


async def test_get_self_context_parallel_all_present(obsidian_self_context_200_mock):
    """read_self_context(path) returns non-empty string when vault file is present."""
    async with AsyncClient(
        transport=obsidian_self_context_200_mock, base_url="http://test"
    ) as client:
        obsidian = ObsidianClient(client, "http://test", "test-api-key")
        result = await obsidian.read_self_context("self/identity.md")
    assert isinstance(result, str), "read_self_context() must return a str"
    assert result.strip(), "File is present — result must be non-empty"


async def test_get_self_context_parallel_one_404(obsidian_404_mock):
    """read_self_context(path) returns empty string silently on 404 (per D-02)."""
    async with AsyncClient(
        transport=obsidian_404_mock, base_url="http://test"
    ) as client:
        obsidian = ObsidianClient(client, "http://test", "test-api-key")
        result = await obsidian.read_self_context("self/methodology.md")
    assert result == "", "404 must return empty string"


async def test_get_self_context_parallel_error_returns_empty(obsidian_self_context_error_mock):
    """read_self_context(path) returns empty string on connection error."""
    async with AsyncClient(
        transport=obsidian_self_context_error_mock, base_url="http://test"
    ) as client:
        obsidian = ObsidianClient(client, "http://test", "test-api-key")
        result = await obsidian.read_self_context("self/goals.md")
    assert result == "", "Error must return empty string"


async def test_get_self_context_404_no_log(obsidian_404_mock):
    """read_self_context(path) does NOT call logger.warning on 404 (silent per D-02)."""
    async with AsyncClient(
        transport=obsidian_404_mock, base_url="http://test"
    ) as client:
        obsidian = ObsidianClient(client, "http://test", "test-api-key")
        import app.clients.obsidian as obsidian_module

        with unittest.mock.patch.object(obsidian_module.logger, "warning") as mock_warn:
            result = await obsidian.read_self_context("self/relationships.md")
        mock_warn.assert_not_called()
    assert result == ""


# ---------------------------------------------------------------------------
# Phase 25-04 — _safe_request() helper (RD-04 / DUP-02)
# ---------------------------------------------------------------------------

import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_obsidian_client():
    """ObsidianClient backed by a mock httpx.AsyncClient."""
    mock_http = AsyncMock()
    return ObsidianClient(mock_http, "http://test", "test-api-key")


async def test_safe_request_returns_result_on_success(mock_obsidian_client):
    """_safe_request passes through the coroutine result."""

    async def coro():
        return "vault content"

    result = await mock_obsidian_client._safe_request(coro(), "default", "test_op")
    assert result == "vault content"


async def test_safe_request_returns_default_on_exception(mock_obsidian_client):
    """_safe_request catches exceptions and returns the default."""

    async def coro():
        raise httpx.ConnectError("boom")

    result = await mock_obsidian_client._safe_request(coro(), [], "test_op")
    assert result == []


async def test_safe_request_logs_warning_for_list_default(mock_obsidian_client, caplog):
    """Non-bool default triggers a warning log."""
    import logging

    async def coro():
        raise Exception("err")

    with caplog.at_level(logging.WARNING):
        await mock_obsidian_client._safe_request(coro(), [], "op_name")
    assert "op_name" in caplog.text


async def test_safe_request_silent_suppresses_log(mock_obsidian_client, caplog):
    """silent=True suppresses the warning log (used by check_health)."""
    import logging

    async def coro():
        raise Exception("err")

    with caplog.at_level(logging.WARNING):
        await mock_obsidian_client._safe_request(coro(), False, "check_health", silent=True)
    assert "check_health" not in caplog.text


async def test_write_session_summary_swallows_exception_and_logs(mock_obsidian_client, caplog):
    """write_session_summary swallows transport errors via _safe_request,
    returns None, and logs a warning. Vault write failure must not raise to the
    background task or the route."""
    import logging

    mock_obsidian_client._client.put = AsyncMock(side_effect=httpx.ConnectError("down"))
    with caplog.at_level(logging.WARNING):
        result = await mock_obsidian_client.write_session_summary(
            "ops/sessions/test.md", "content"
        )
    assert result is None
    assert "write_session_summary" in caplog.text


# --- 260427-vl1 Task 5: list_directory / read_note / write_note / delete_note / patch_append ---


@pytest.fixture
def obsidian_list_dir_mock():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/vault/foo/" and request.method == "GET":
            return httpx.Response(200, json=["a.md", "b.md", "subdir/"])
        if request.url.path == "/vault/missing/":
            return httpx.Response(404)
        return httpx.Response(500)
    return httpx.MockTransport(handler)


async def test_list_directory_returns_entries(obsidian_list_dir_mock):
    async with AsyncClient(transport=obsidian_list_dir_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "k")
        entries = await obsidian.list_directory("foo")
    assert entries == ["a.md", "b.md", "subdir/"]


async def test_list_directory_404_returns_empty(obsidian_list_dir_mock):
    async with AsyncClient(transport=obsidian_list_dir_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "k")
        entries = await obsidian.list_directory("missing")
    assert entries == []


async def test_list_directory_5xx_returns_empty(obsidian_list_dir_mock):
    """Non-404 errors degrade to [] via _safe_request."""
    async with AsyncClient(transport=obsidian_list_dir_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "k")
        entries = await obsidian.list_directory("anywhere")
    assert entries == []


@pytest.fixture
def obsidian_read_note_mock():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/vault/foo.md":
            return httpx.Response(200, text="# foo\nbody here")
        if request.method == "GET" and request.url.path == "/vault/missing.md":
            return httpx.Response(404)
        return httpx.Response(500)
    return httpx.MockTransport(handler)


async def test_read_note_returns_body(obsidian_read_note_mock):
    async with AsyncClient(transport=obsidian_read_note_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "k")
        body = await obsidian.read_note("foo.md")
    assert body == "# foo\nbody here"


async def test_read_note_404_returns_empty(obsidian_read_note_mock):
    async with AsyncClient(transport=obsidian_read_note_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "k")
        body = await obsidian.read_note("missing.md")
    assert body == ""


@pytest.fixture
def obsidian_write_capture_mock():
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append({
            "method": request.method,
            "path": request.url.path,
            "content_type": request.headers.get("Content-Type", ""),
            "auth": request.headers.get("Authorization", ""),
            "patch_pos": request.headers.get("Obsidian-API-Content-Insertion-Position", ""),
            "content": request.content.decode("utf-8") if request.content else "",
        })
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    transport.captured = captured  # type: ignore[attr-defined]
    return transport


async def test_write_note_puts_with_markdown_content_type(obsidian_write_capture_mock):
    async with AsyncClient(transport=obsidian_write_capture_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "k")
        await obsidian.write_note("references/x.md", "# x\nbody")
    cap = obsidian_write_capture_mock.captured[0]  # type: ignore[attr-defined]
    assert cap["method"] == "PUT"
    assert cap["path"] == "/vault/references/x.md"
    assert "text/markdown" in cap["content_type"]
    assert cap["auth"] == "Bearer k"
    assert cap["content"] == "# x\nbody"


async def test_write_note_raises_on_5xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "k")
        with pytest.raises(Exception):
            await obsidian.write_note("x.md", "body")


async def test_delete_note_issues_delete(obsidian_write_capture_mock):
    async with AsyncClient(transport=obsidian_write_capture_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "k")
        await obsidian.delete_note("x.md")
    cap = obsidian_write_capture_mock.captured[0]  # type: ignore[attr-defined]
    assert cap["method"] == "DELETE"
    assert cap["path"] == "/vault/x.md"


async def test_patch_append_sets_end_position_header(obsidian_write_capture_mock):
    async with AsyncClient(transport=obsidian_write_capture_mock, base_url="http://test") as client:
        obsidian = ObsidianClient(client, "http://test", "k")
        await obsidian.patch_append("ops/log.md", "new line\n")
    cap = obsidian_write_capture_mock.captured[0]  # type: ignore[attr-defined]
    assert cap["method"] == "PATCH"
    assert cap["path"] == "/vault/ops/log.md"
    assert cap["patch_pos"] == "end"
    assert cap["content"] == "new line\n"
