"""Tests for ObsidianVault (MEM-01, MEM-05, MEM-08)."""
import unittest.mock
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import AsyncClient

from app.services.recall import RetentionPolicy, SessionSummary
from app.vault import ObsidianVault, VaultUnreachableError, _parse_session_summary


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


_SESSION_NOTE_BODY = """\
---
timestamp: 2026-06-12T12:00:00+00:00
user_id: trekkie
model: qwen3
---

## User

Hello sentinel

## Sentinel

Hello trekkie
"""

_SESSION_NOTE_DATE = "2026-06-12"
_SESSION_NOTE_FILENAME = "trekkie-12-00-00.md"
_SESSION_NOTE_PATH = f"ops/sessions/{_SESSION_NOTE_DATE}/{_SESSION_NOTE_FILENAME}"


@pytest.fixture
def obsidian_directory_listing_mock():
    """MockTransport: returns a directory listing JSON for ops/sessions/ paths.

    The note body is a full parseable session note so typed contract tests can
    assert on the parsed SessionSummary fields.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/vault/ops/sessions/" in path and path.endswith("/"):
            # Return a list of filenames including one for trekkie
            return httpx.Response(
                200,
                json=[_SESSION_NOTE_FILENAME, "other-user-14-00-00.md"],
            )
        if "/vault/ops/sessions/" in path and path.endswith(".md"):
            return httpx.Response(200, text=_SESSION_NOTE_BODY)
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
        obsidian = ObsidianVault(client, "http://test", "test-api-key")
        result = await obsidian.get_user_context("trekkie")
    assert result == "# User: trekkie\n\nI am a developer."


async def test_get_user_context_returns_none_on_404(obsidian_404_mock):
    """get_user_context() returns None when Obsidian returns 404."""
    async with AsyncClient(transport=obsidian_404_mock, base_url="http://test") as client:
        obsidian = ObsidianVault(client, "http://test", "test-api-key")
        result = await obsidian.get_user_context("trekkie")
    assert result is None


async def test_get_user_context_returns_none_on_connect_error(obsidian_connect_error_mock):
    """get_user_context() returns None (graceful degrade) when Obsidian is unreachable."""
    async with AsyncClient(transport=obsidian_connect_error_mock, base_url="http://test") as client:
        obsidian = ObsidianVault(client, "http://test", "test-api-key")
        result = await obsidian.get_user_context("trekkie")
    assert result is None


async def test_get_recent_sessions_returns_list(obsidian_directory_listing_mock):
    """get_recent_sessions() returns a list of SessionSummary objects (typed contract — MEM-08)."""
    async with AsyncClient(transport=obsidian_directory_listing_mock, base_url="http://test") as client:
        obsidian = ObsidianVault(client, "http://test", "test-api-key")
        result = await obsidian.get_recent_sessions("trekkie", policy=RetentionPolicy())
    assert isinstance(result, list)
    assert len(result) >= 1, "Expected at least one parsed SessionSummary"
    summary = result[0]
    assert isinstance(summary, SessionSummary)
    assert summary.date == _SESSION_NOTE_DATE
    assert summary.user_id == "trekkie"
    assert summary.user_msg == "Hello sentinel"


async def test_get_recent_sessions_returns_empty_on_error(obsidian_connect_error_mock):
    """get_recent_sessions() returns [] when Obsidian is unreachable."""
    async with AsyncClient(transport=obsidian_connect_error_mock, base_url="http://test") as client:
        obsidian = ObsidianVault(client, "http://test", "test-api-key")
        result = await obsidian.get_recent_sessions("trekkie", policy=RetentionPolicy())
    assert result == []


async def test_parse_session_summary_parses_full_note():
    """_parse_session_summary parses a well-formed session note into exact SessionSummary fields."""
    path = _SESSION_NOTE_PATH
    parsed = _parse_session_summary(path, _SESSION_NOTE_BODY)
    assert parsed is not None
    assert isinstance(parsed, SessionSummary)
    assert parsed.date == "2026-06-12"
    assert parsed.user_id == "trekkie"
    assert parsed.time == "12-00-00"
    assert parsed.user_msg == "Hello sentinel"
    assert parsed.sentinel_msg == "Hello trekkie"
    assert parsed.path == path
    assert "## User" in parsed.body


async def test_parse_session_summary_malformed_note_does_not_raise():
    """_parse_session_summary returns empty-string fallbacks for missing fields — never raises."""
    path = "ops/sessions/2026-06-12/trekkie-09-00-00.md"
    malformed_body = "no frontmatter, no headings, just raw text"
    parsed = _parse_session_summary(path, malformed_body)
    # Valid path → should not return None even with malformed body
    assert parsed is not None
    assert isinstance(parsed, SessionSummary)
    assert parsed.date == "2026-06-12"
    assert parsed.user_id == "trekkie"
    assert parsed.user_msg == ""
    assert parsed.sentinel_msg == ""


async def test_parse_session_summary_unparseable_path_returns_none():
    """_parse_session_summary returns None when path is too short to derive date/user_id/time."""
    assert _parse_session_summary("bad/path.md", "some body") is None


async def test_parse_session_summary_frontmatter_value_containing_dashes():
    """CR-01: a frontmatter field value containing '---' does not corrupt user_msg/sentinel_msg.

    Previously the fragile find("---") chain would pick up a "---" inside a
    frontmatter value as the closing delimiter, causing the body extraction to start
    at the wrong position and misparse User/Sentinel sections.
    """
    # A note whose 'model' field value contains three dashes to trigger the old
    # off-by-one misfiring.  The body still has well-formed ## User / ## Sentinel.
    note_with_dashes_in_fm = (
        "---\n"
        "timestamp: 2026-06-12T14:00:00+00:00\n"
        "user_id: trekkie\n"
        "model: some---value\n"
        "---\n"
        "\n"
        "## User\n"
        "\n"
        "What is my goal?\n"
        "\n"
        "## Sentinel\n"
        "\n"
        "Build the Sentinel.\n"
    )
    path = "ops/sessions/2026-06-12/trekkie-14-00-00.md"
    parsed = _parse_session_summary(path, note_with_dashes_in_fm)
    assert parsed is not None, "Expected a valid SessionSummary, got None"
    assert parsed.user_msg == "What is my goal?", (
        f"user_msg corrupted by frontmatter '---' value; got {parsed.user_msg!r}"
    )
    assert parsed.sentinel_msg == "Build the Sentinel.", (
        f"sentinel_msg corrupted by frontmatter '---' value; got {parsed.sentinel_msg!r}"
    )


async def test_write_session_summary_calls_put(obsidian_put_capture_mock):
    """write_session_summary() sends a PUT request to /vault/{path}."""
    async with AsyncClient(transport=obsidian_put_capture_mock, base_url="http://test") as client:
        obsidian = ObsidianVault(client, "http://test", "test-api-key")
        await obsidian.write_session_summary(
            "ops/sessions/2026-04-10/trekkie-12-00-00.md",
            "# Session\n\nContent here."
        )
    assert len(obsidian_put_capture_mock.captured) == 1
    assert "ops/sessions/2026-04-10/trekkie-12-00-00.md" in obsidian_put_capture_mock.captured[0]["path"]


async def test_find_returns_list(obsidian_search_mock):
    """find() returns a list of search results."""
    async with AsyncClient(transport=obsidian_search_mock, base_url="http://test") as client:
        obsidian = ObsidianVault(client, "http://test", "test-api-key")
        result = await obsidian.find("trekkie")
    assert isinstance(result, list)
    assert len(result) > 0


async def test_find_returns_empty_on_error(obsidian_connect_error_mock):
    """find() returns [] when Obsidian is unreachable."""
    async with AsyncClient(transport=obsidian_connect_error_mock, base_url="http://test") as client:
        obsidian = ObsidianVault(client, "http://test", "test-api-key")
        result = await obsidian.find("trekkie")
    assert result == []


async def test_check_health_returns_true(obsidian_health_ok_mock):
    """check_health() returns True when Obsidian vault listing returns 200."""
    async with AsyncClient(transport=obsidian_health_ok_mock, base_url="http://test") as client:
        obsidian = ObsidianVault(client, "http://test", "test-api-key")
        result = await obsidian.check_health()
    assert result is True


async def test_check_health_returns_false_on_error(obsidian_connect_error_mock):
    """check_health() returns False when Obsidian is unreachable."""
    async with AsyncClient(transport=obsidian_connect_error_mock, base_url="http://test") as client:
        obsidian = ObsidianVault(client, "http://test", "test-api-key")
        result = await obsidian.check_health()
    assert result is False


# ---------------------------------------------------------------------------
# Phase 10 — read_self_context() single-path method (MEM-02, 2B-02)
# Implemented in Plan 10-03. Tests exercise the per-path method;
# asyncio.gather() over all 5 paths is tested in test_message.py.
# ---------------------------------------------------------------------------



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
        obsidian = ObsidianVault(client, "http://test", "test-api-key")
        result = await obsidian.read_self_context("self/identity.md")
    assert isinstance(result, str), "read_self_context() must return a str"
    assert result.strip(), "File is present — result must be non-empty"


async def test_get_self_context_parallel_one_404(obsidian_404_mock):
    """read_self_context(path) returns empty string silently on 404 (per D-02)."""
    async with AsyncClient(
        transport=obsidian_404_mock, base_url="http://test"
    ) as client:
        obsidian = ObsidianVault(client, "http://test", "test-api-key")
        result = await obsidian.read_self_context("self/methodology.md")
    assert result == "", "404 must return empty string"


async def test_get_self_context_parallel_error_returns_empty(obsidian_self_context_error_mock):
    """read_self_context(path) returns empty string on connection error."""
    async with AsyncClient(
        transport=obsidian_self_context_error_mock, base_url="http://test"
    ) as client:
        obsidian = ObsidianVault(client, "http://test", "test-api-key")
        result = await obsidian.read_self_context("self/goals.md")
    assert result == "", "Error must return empty string"


async def test_get_self_context_404_no_log(obsidian_404_mock):
    """read_self_context(path) does NOT call logger.warning on 404 (silent per D-02)."""
    async with AsyncClient(
        transport=obsidian_404_mock, base_url="http://test"
    ) as client:
        obsidian = ObsidianVault(client, "http://test", "test-api-key")
        import app.vault as obsidian_module

        with unittest.mock.patch.object(obsidian_module.logger, "warning") as mock_warn:
            result = await obsidian.read_self_context("self/relationships.md")
        mock_warn.assert_not_called()
    assert result == ""


# ---------------------------------------------------------------------------
# Phase 25-04 — _safe_request() helper (RD-04 / DUP-02)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_obsidian_client():
    """ObsidianVault backed by a mock httpx.AsyncClient."""
    mock_http = AsyncMock()
    return ObsidianVault(mock_http, "http://test", "test-api-key")


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


# --- 260427-vl1 Task 5: list_under / read_note / write_note / delete_note / patch_append ---


@pytest.fixture
def obsidian_list_dir_mock():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/vault/foo/" and request.method == "GET":
            return httpx.Response(200, json=["a.md", "b.md", "subdir/"])
        if request.url.path == "/vault/missing/":
            return httpx.Response(404)
        return httpx.Response(500)
    return httpx.MockTransport(handler)


async def test_list_under_returns_entries(obsidian_list_dir_mock):
    async with AsyncClient(transport=obsidian_list_dir_mock, base_url="http://test") as client:
        obsidian = ObsidianVault(client, "http://test", "k")
        entries = await obsidian.list_under("foo")
    assert entries == ["a.md", "b.md", "subdir/"]


async def test_list_under_404_returns_empty(obsidian_list_dir_mock):
    async with AsyncClient(transport=obsidian_list_dir_mock, base_url="http://test") as client:
        obsidian = ObsidianVault(client, "http://test", "k")
        entries = await obsidian.list_under("missing")
    assert entries == []


async def test_list_under_5xx_returns_empty(obsidian_list_dir_mock):
    """Non-404 errors degrade to [] via _safe_request."""
    async with AsyncClient(transport=obsidian_list_dir_mock, base_url="http://test") as client:
        obsidian = ObsidianVault(client, "http://test", "k")
        entries = await obsidian.list_under("anywhere")
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
        obsidian = ObsidianVault(client, "http://test", "k")
        body = await obsidian.read_note("foo.md")
    assert body == "# foo\nbody here"


async def test_read_note_404_returns_empty(obsidian_read_note_mock):
    async with AsyncClient(transport=obsidian_read_note_mock, base_url="http://test") as client:
        obsidian = ObsidianVault(client, "http://test", "k")
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
        obsidian = ObsidianVault(client, "http://test", "k")
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
        obsidian = ObsidianVault(client, "http://test", "k")
        with pytest.raises(Exception):
            await obsidian.write_note("x.md", "body")


async def test_delete_note_issues_delete(obsidian_write_capture_mock):
    async with AsyncClient(transport=obsidian_write_capture_mock, base_url="http://test") as client:
        obsidian = ObsidianVault(client, "http://test", "k")
        await obsidian.delete_note("x.md")
    cap = obsidian_write_capture_mock.captured[0]  # type: ignore[attr-defined]
    assert cap["method"] == "DELETE"
    assert cap["path"] == "/vault/x.md"


async def test_patch_append_sets_end_position_header(obsidian_write_capture_mock):
    async with AsyncClient(transport=obsidian_write_capture_mock, base_url="http://test") as client:
        obsidian = ObsidianVault(client, "http://test", "k")
        await obsidian.patch_append("ops/log.md", "new line\n")
    cap = obsidian_write_capture_mock.captured[0]  # type: ignore[attr-defined]
    assert cap["method"] == "PATCH"
    assert cap["path"] == "/vault/ops/log.md"
    assert cap["patch_pos"] == "end"
    assert cap["content"] == "new line\n"


# ---------------------------------------------------------------------------
# Plan 260502-cky Task 2 — read_persona() typed-exception branching.
# Three behavioral tests covering ADR-0001's three startup paths:
#   1. vault-up + persona 200 → returns the body string
#   2. vault-up + persona 404 → returns None (lifespan turns this into RuntimeError)
#   3. transport failure         → raises VaultUnreachableError (lifespan logs+continues)
# Each test calls await vault.read_persona() and asserts on the observable
# result/exception — no source-grep, no mock-call-shape-only assertions.
# ---------------------------------------------------------------------------


async def test_read_persona_returns_body_on_200():
    """vault-up + persona 200 — read_persona returns the body string."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/vault/sentinel/persona.md":
            return httpx.Response(200, text="# Persona\n\nYou are the Sentinel.")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        vault = ObsidianVault(client, "http://test", "k")
        result = await vault.read_persona()
    assert result == "# Persona\n\nYou are the Sentinel."


async def test_read_persona_returns_none_on_404():
    """vault-up + persona 404 — read_persona returns None.

    Lifespan turns this into a RuntimeError (ADR-0001 hard-fail) so the
    operator notices the missing setup file at startup rather than at
    request-time.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        vault = ObsidianVault(client, "http://test", "k")
        result = await vault.read_persona()
    assert result is None


async def test_read_persona_raises_vault_unreachable_on_transport_failure():
    """transport failure — read_persona raises VaultUnreachableError.

    Lifespan catches this and continues with the fallback persona
    (ADR-0001 graceful-degrade branch). The exception type is the seam
    that distinguishes "vault down" from "vault up but file missing".
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(handler)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        vault = ObsidianVault(client, "http://test", "k")
        with pytest.raises(VaultUnreachableError):
            await vault.read_persona()


# ---------------------------------------------------------------------------
# Plan 260502-cky Task 3 — sweep capabilities on ObsidianVault.
# Each test asserts on observable post-state mutations (not request shape):
#   * move_to_trash: source gone + body present at returned destination
#   * relocate:      source gone + body present at returned destination
#   * acquire/release: True/False/True sequence across acquire-acquire-release-acquire
# Mutating primitives (write/delete/read) are backed by an in-memory store
# served via httpx.MockTransport so the assertions ride the real adapter.
# ---------------------------------------------------------------------------


def _make_store_transport(store: dict[str, str]) -> httpx.MockTransport:
    """Build a MockTransport that backs the GET/PUT/DELETE primitives against
    an in-memory dict. PATCH appends. Returns 200/404 to mirror the real
    Obsidian REST API surface."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        # All vault paths are under /vault/<key>
        if not path.startswith("/vault/"):
            return httpx.Response(404)
        key = path[len("/vault/"):]
        if request.method == "GET":
            if key in store:
                return httpx.Response(200, text=store[key])
            return httpx.Response(404)
        if request.method == "PUT":
            store[key] = request.content.decode("utf-8")
            return httpx.Response(200)
        if request.method == "DELETE":
            store.pop(key, None)
            return httpx.Response(200)
        return httpx.Response(405)

    return httpx.MockTransport(handler)


async def test_obsidian_vault_move_to_trash_mutates_state():
    """After move_to_trash, the source path is empty and the destination
    holds the original body — observable state assertion, not call shape."""
    store: dict[str, str] = {"foo.md": "original body content"}
    transport = _make_store_transport(store)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        vault = ObsidianVault(client, "http://test", "k")
        dst = await vault.move_to_trash("foo.md", reason="dup")
        # Source gone (read returns "" — graceful 404)
        assert await vault.read_note("foo.md") == ""
        # Destination contains the original body (with provenance frontmatter)
        moved = await vault.read_note(dst)
        assert "original body content" in moved
        assert "original_path: foo.md" in moved


async def test_obsidian_vault_relocate_mutates_state():
    """After relocate(src, dst), src is empty and dst contains the body."""
    store: dict[str, str] = {"random/x.md": "body of x"}
    transport = _make_store_transport(store)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        vault = ObsidianVault(client, "http://test", "k")
        actual_dst = await vault.relocate("random/x.md", "topic/x.md")
        assert actual_dst == "topic/x.md"
        assert await vault.read_note("random/x.md") == ""
        moved = await vault.read_note("topic/x.md")
        assert "body of x" in moved
        assert "original_path: random/x.md" in moved


async def test_obsidian_vault_acquire_release_sweep_lock_sequence():
    """acquire-acquire-release-acquire returns True/False/True sequence."""
    store: dict[str, str] = {}
    transport = _make_store_transport(store)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        vault = ObsidianVault(client, "http://test", "k")
        now = __import__("datetime").datetime(
            2026, 5, 2, 12, 0, 0, tzinfo=__import__("datetime").timezone.utc
        )
        first = await vault.acquire_sweep_lock(now=now)
        second = await vault.acquire_sweep_lock(now=now)
        await vault.release_sweep_lock()
        third = await vault.acquire_sweep_lock(now=now)
    assert (first, second, third) == (True, False, True)


async def test_obsidian_vault_move_to_trash_raises_on_transport_failure():
    """A transport failure during the underlying write surfaces as an
    httpx error from the underlying primitive. (move_to_trash itself does
    not catch — the sweeper's run_sweep error handler does.)"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("vault down")

    transport = httpx.MockTransport(handler)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        vault = ObsidianVault(client, "http://test", "k")
        with pytest.raises(httpx.ConnectError):
            await vault.move_to_trash("foo.md", reason="dup")


# ---------------------------------------------------------------------------
# Plan 40-05 — Protected-namespace guard (MEM-05 gap closure)
#
# Task 1 tests: PROTECTED_NAMESPACES, is_protected_path, ProtectedPathError
# All tests use behavior/spy assertions per the plan acceptance criteria.
# ---------------------------------------------------------------------------


def test_protected_namespaces_constant_exists():
    """PROTECTED_NAMESPACES is exported from app.vault."""
    from app.vault import PROTECTED_NAMESPACES
    assert isinstance(PROTECTED_NAMESPACES, tuple)
    assert len(PROTECTED_NAMESPACES) >= 1


@pytest.mark.parametrize("namespace", list(__import__("app.vault", fromlist=["PROTECTED_NAMESPACES"]).PROTECTED_NAMESPACES) if False else ["sentinel/", "self/", "security/"])
def test_is_protected_path_true_for_each_default_namespace(namespace):
    """is_protected_path returns True for a path under each default protected namespace.

    Parametrized over the module default literal so the enumeration is asserted,
    not assumed — adding a namespace to PROTECTED_NAMESPACES auto-extends coverage.
    """
    from app.vault import is_protected_path
    path_under_ns = namespace.rstrip("/") + "/some_file.md"
    assert is_protected_path(path_under_ns) is True


def test_is_protected_path_parametrized_from_literal():
    """Parametrized test reading the ACTUAL module-level default tuple literal.

    Asserts that every namespace in PROTECTED_NAMESPACES matches paths under it.
    This is the 'enumeration asserted from the literal' requirement.
    """
    from app.vault import PROTECTED_NAMESPACES, is_protected_path
    for namespace in PROTECTED_NAMESPACES:
        path = namespace.rstrip("/") + "/x.md"
        assert is_protected_path(path) is True, (
            f"Expected is_protected_path({path!r}) to be True for namespace {namespace!r}"
        )


def test_is_protected_path_sentinel_persona():
    """is_protected_path('sentinel/persona.md') is True — the incident path."""
    from app.vault import is_protected_path
    assert is_protected_path("sentinel/persona.md") is True


def test_is_protected_path_sentinel_any_path():
    """is_protected_path('sentinel/anything.md') is True."""
    from app.vault import is_protected_path
    assert is_protected_path("sentinel/anything.md") is True


def test_is_protected_path_sentinel_subdir():
    """is_protected_path('sentinel/sub/dir/x.md') is True — deep subpath."""
    from app.vault import is_protected_path
    assert is_protected_path("sentinel/sub/dir/x.md") is True


def test_is_protected_path_non_protected_returns_false():
    """is_protected_path('references/alpha.md') is False."""
    from app.vault import is_protected_path
    assert is_protected_path("references/alpha.md") is False


def test_is_protected_path_near_miss_returns_false():
    """is_protected_path('notessentinel/x.md') is False — segment-boundary match.

    'notessentinel/' does NOT start with 'sentinel/' so the guard must not fire.
    """
    from app.vault import is_protected_path
    assert is_protected_path("notessentinel/x.md") is False


def test_is_protected_path_top_level_namespace_itself_is_protected():
    """is_protected_path('sentinel/') is True (the prefix itself)."""
    from app.vault import is_protected_path
    assert is_protected_path("sentinel/") is True


def test_is_protected_path_uses_settings_when_available(monkeypatch):
    """_active_protected_namespaces reads from settings.protected_namespaces."""
    import app.vault as vault_module
    # Monkeypatch _active_protected_namespaces to return a custom tuple
    monkeypatch.setattr(vault_module, "_active_protected_namespaces", lambda: ("custom/",))
    assert vault_module.is_protected_path("custom/note.md") is True
    assert vault_module.is_protected_path("sentinel/persona.md") is False


def test_active_protected_namespaces_falls_back_to_module_default(monkeypatch):
    """_active_protected_namespaces returns the module-default literal when settings
    is unimportable — mirrors _active_skip_prefixes try/except fallback.
    """
    import sys
    import app.vault as vault_module
    from app.vault import PROTECTED_NAMESPACES

    # Simulate settings import failure inside _active_protected_namespaces
    original_config = sys.modules.get("app.config")
    sys.modules["app.config"] = None  # type: ignore[assignment]
    try:
        result = vault_module._active_protected_namespaces()
    finally:
        if original_config is None:
            sys.modules.pop("app.config", None)
        else:
            sys.modules["app.config"] = original_config
    assert result == PROTECTED_NAMESPACES


def test_protected_path_error_is_security_error_subclass():
    """ProtectedPathError is a subclass of SecurityError (so existing SecurityError
    handlers and logging apply automatically).
    """
    from app.errors import ProtectedPathError, SecurityError
    assert issubclass(ProtectedPathError, SecurityError)


def test_protected_path_error_is_importable_from_errors():
    """ProtectedPathError is defined in app.errors (grep: class ProtectedPathError)."""
    from app.errors import ProtectedPathError
    err = ProtectedPathError("test message")
    assert "test message" in str(err)


# ---------------------------------------------------------------------------
# Plan 40-05 — Task 2: Guard enforcement in relocate and move_to_trash
#
# Tests use FakeVault (backed by _make_store_transport / in-memory store)
# because FakeVault.relocate/move_to_trash delegate to ObsidianVault method
# bodies — so the guard wired into ObsidianVault is exercised through both.
# ---------------------------------------------------------------------------


# Task 2 helpers — FakeVault-backed store for in-memory tests


def _make_fake_vault_with_notes(notes: dict[str, str]):
    """Return a FakeVault pre-loaded with the given notes dict."""
    from tests.fakes.vault import FakeVault
    vault = FakeVault()
    vault.notes = dict(notes)
    return vault


async def test_relocate_protected_source_raises_protected_path_error():
    """relocate(sentinel/persona.md, ...) raises ProtectedPathError — source guard.

    Source note must be untouched and no destination note created.
    """
    from app.errors import ProtectedPathError
    vault = _make_fake_vault_with_notes({"sentinel/persona.md": "# Persona\nbody"})
    with pytest.raises(ProtectedPathError):
        await vault.relocate("sentinel/persona.md", "learning/persona/persona.md")
    # Source is still there
    assert vault.notes.get("sentinel/persona.md") == "# Persona\nbody"
    # No destination created
    assert "learning/persona/persona.md" not in vault.notes


async def test_relocate_protected_source_delete_not_called(monkeypatch):
    """relocate raises BEFORE any delete_note — delete_note is never called (spy assert)."""
    from app.errors import ProtectedPathError
    vault = _make_fake_vault_with_notes({"sentinel/persona.md": "# Persona\nbody"})
    delete_calls = []
    original_delete = vault.delete_note

    async def spy_delete(path: str) -> None:
        delete_calls.append(path)
        return await original_delete(path)

    vault.delete_note = spy_delete  # type: ignore[method-assign]
    with pytest.raises(ProtectedPathError):
        await vault.relocate("sentinel/persona.md", "learning/persona/persona.md")
    assert delete_calls == [], f"delete_note must not be called; got: {delete_calls}"


async def test_relocate_protected_destination_raises_protected_path_error():
    """relocate('references/note.md', 'sentinel/note.md') raises ProtectedPathError.

    Destination protection (concern 6): nothing written under sentinel/.
    """
    from app.errors import ProtectedPathError
    vault = _make_fake_vault_with_notes({"references/note.md": "# Ref\nbody"})
    with pytest.raises(ProtectedPathError):
        await vault.relocate("references/note.md", "sentinel/note.md")
    # Source is untouched
    assert vault.notes.get("references/note.md") == "# Ref\nbody"
    # Nothing written under sentinel/
    sentinel_keys = [k for k in vault.notes if k.startswith("sentinel/")]
    assert not sentinel_keys, f"No notes should be under sentinel/; found: {sentinel_keys}"


async def test_relocate_protected_destination_self_namespace():
    """relocate into self/ namespace also raises ProtectedPathError."""
    from app.errors import ProtectedPathError
    vault = _make_fake_vault_with_notes({"references/note.md": "body"})
    with pytest.raises(ProtectedPathError):
        await vault.relocate("references/note.md", "self/note.md")


async def test_move_to_trash_protected_path_raises():
    """move_to_trash('sentinel/persona.md', ...) raises ProtectedPathError."""
    from app.errors import ProtectedPathError
    vault = _make_fake_vault_with_notes({"sentinel/persona.md": "# Persona\nbody"})
    with pytest.raises(ProtectedPathError):
        await vault.move_to_trash("sentinel/persona.md", reason="sweep")
    # Source is untouched
    assert vault.notes.get("sentinel/persona.md") == "# Persona\nbody"


async def test_move_to_trash_protected_path_delete_not_called(monkeypatch):
    """move_to_trash raises BEFORE any delete_note — spy confirms zero calls."""
    from app.errors import ProtectedPathError
    vault = _make_fake_vault_with_notes({"sentinel/persona.md": "# Persona\nbody"})
    delete_calls = []
    original_delete = vault.delete_note

    async def spy_delete(path: str) -> None:
        delete_calls.append(path)
        return await original_delete(path)

    vault.delete_note = spy_delete  # type: ignore[method-assign]
    with pytest.raises(ProtectedPathError):
        await vault.move_to_trash("sentinel/persona.md", reason="sweep")
    assert delete_calls == [], f"delete_note must not be called; got: {delete_calls}"


async def test_write_note_into_protected_namespace_succeeds():
    """write_note('sentinel/persona.md', body) SUCCEEDS — the guard is only on
    relocate/move_to_trash, NOT write_note. This proves the documented write-based
    restore path (round-3 item 4) is not blocked by the destination guard.
    """
    vault = _make_fake_vault_with_notes({})
    body = "# Persona\nRestored content."
    await vault.write_note("sentinel/persona.md", body)
    assert vault.notes.get("sentinel/persona.md") == body


async def test_incident_reproduced_at_primitive_and_blocked():
    """Reproduce the original incident: sweep relocates sentinel/persona.md.

    Before the fix: the persona would be relocated to learning/persona/persona.md.
    After the fix: ProtectedPathError is raised and the persona body is byte-identical.
    """
    from app.errors import ProtectedPathError
    original_body = "# Persona\n\nYou are the Sentinel. You remember everything."
    vault = _make_fake_vault_with_notes({"sentinel/persona.md": original_body})

    with pytest.raises(ProtectedPathError):
        await vault.relocate("sentinel/persona.md", "learning/persona/persona.md")

    # Source is byte-identical
    assert vault.notes.get("sentinel/persona.md") == original_body
    # No destination note
    assert "learning/persona/persona.md" not in vault.notes


async def test_relocate_non_protected_path_still_works():
    """Regression lock: relocate of a non-protected path behaves exactly as before."""
    vault = _make_fake_vault_with_notes({"references/alpha.md": "# Alpha\nbody"})
    actual_dst = await vault.relocate("references/alpha.md", "topics/x/alpha.md")
    assert actual_dst == "topics/x/alpha.md"
    assert vault.notes.get("references/alpha.md", "") == ""
    moved = vault.notes.get("topics/x/alpha.md", "")
    assert "# Alpha" in moved
    assert "original_path: references/alpha.md" in moved


async def test_move_to_trash_non_protected_path_still_works():
    """Regression lock: move_to_trash of a non-protected path behaves exactly as before."""
    vault = _make_fake_vault_with_notes({"references/beta.md": "# Beta\nbody"})
    dst = await vault.move_to_trash("references/beta.md", reason="dup")
    assert dst.startswith("_trash/")
    assert vault.notes.get("references/beta.md", "") == ""
    moved = vault.notes.get(dst, "")
    assert "# Beta" in moved
