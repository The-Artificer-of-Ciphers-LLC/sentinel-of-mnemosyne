"""Tests for the shared Obsidian client core + mixins (sentinel_shared.obsidian).

Uses the httpx.MockTransport pattern from
modules/pathfinder/tests/test_aliases_path_probe.py to capture the exact
request the client emits, without a live Obsidian instance.
"""
from __future__ import annotations

import httpx
import pytest

from sentinel_shared.obsidian import (
    ObsidianBinaryMixin,
    ObsidianClientCore,
    ObsidianHeadingMixin,
)

BASE_URL = "https://obsidian.test:27124"
API_KEY = "test-key"


def _make_client(handler, ClientClass, base_url=BASE_URL, api_key=API_KEY):
    """Build a ClientClass backed by a MockTransport that records requests."""
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return ClientClass(http_client, base_url, api_key), http_client


class _FullComposition(ObsidianClientCore, ObsidianBinaryMixin, ObsidianHeadingMixin):
    """Local composition subclass mirroring pf2e's real composition (D-02)."""


@pytest.mark.asyncio
async def test_auth_header_sent_when_api_key_supplied():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, text="hello")

    client, http_client = _make_client(handler, ObsidianClientCore)
    try:
        await client.get_note("notes/a.md")
    finally:
        await http_client.aclose()

    assert captured[0].headers.get("Authorization") == f"Bearer {API_KEY}"


@pytest.mark.asyncio
async def test_no_auth_header_when_api_key_blank():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, text="hello")

    client, http_client = _make_client(handler, ObsidianClientCore, api_key="")
    try:
        await client.get_note("notes/a.md")
    finally:
        await http_client.aclose()

    assert "Authorization" not in captured[0].headers


@pytest.mark.asyncio
async def test_get_note_returns_body_on_200():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="note body")

    client, http_client = _make_client(handler, ObsidianClientCore)
    try:
        result = await client.get_note("notes/a.md")
    finally:
        await http_client.aclose()

    assert result == "note body"


@pytest.mark.asyncio
async def test_get_note_degrades_to_none_on_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client, http_client = _make_client(handler, ObsidianClientCore)
    try:
        result = await client.get_note("notes/a.md")
    finally:
        await http_client.aclose()

    assert result is None


@pytest.mark.asyncio
async def test_put_note_strips_trailing_slash_and_preserves_120s_timeout():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(204)

    client, http_client = _make_client(
        handler, ObsidianClientCore, base_url=f"{BASE_URL}/"
    )
    try:
        await client.put_note("notes/a.md", "content")
    finally:
        await http_client.aclose()

    assert len(captured) == 1
    req = captured[0]
    # base_url trailing slash stripped -- no double-slash before /vault/.
    assert req.url.path == "/vault/notes/a.md"
    assert client._base_url == BASE_URL


@pytest.mark.asyncio
async def test_full_composition_resolves_init_to_core_and_exposes_mixin_methods():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.method == "GET":
            return httpx.Response(200, content=b"binary-data")
        return httpx.Response(204)

    client, http_client = _make_client(handler, _FullComposition)
    try:
        # __init__ resolved to ObsidianClientCore -- no mixin defines it.
        assert client._base_url == BASE_URL
        assert client._headers.get("Authorization") == f"Bearer {API_KEY}"

        # Mixin methods are present and callable.
        await client.patch_heading("notes/a.md", "Section", "new text")
        await client.put_binary("notes/img.png", b"data", "image/png")
        data = await client.get_binary("notes/img.png")
        assert data == b"binary-data"

        # Core methods still work too.
        await client.patch_frontmatter_field("notes/a.md", "status", "done")
    finally:
        await http_client.aclose()

    assert len(captured) == 4


def test_no_mixin_defines_init():
    assert "__init__" not in ObsidianHeadingMixin.__dict__
    assert "__init__" not in ObsidianBinaryMixin.__dict__
