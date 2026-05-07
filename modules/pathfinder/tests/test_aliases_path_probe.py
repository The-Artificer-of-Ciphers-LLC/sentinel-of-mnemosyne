"""Probe test for Phase 37 / Plan 37-05 — Research Open Question #5 / Assumption A1.

Confirms that the project's `ObsidianClient` wrapper (modules/pathfinder/app/obsidian.py)
accepts an underscore-prefixed JSON path (`mnemosyne/pf2e/players/_aliases.json`) on
both `get_note()` and `put_note()` without client-side validation rejecting it before
the HTTP call is issued.

This is a unit-level probe — no live Obsidian. We use `httpx.MockTransport` to capture
the exact request URL/path/headers the client emits, which is the observable behavior
that matters for Wave 1 plan 37-06's `player_identity_resolver` alias map location.

Empirical result (recorded for SUMMARY.md):
- ObsidianClient.get_note(underscore_path) — accepted, HTTP path preserved verbatim
- ObsidianClient.put_note(underscore_path, content) — accepted, HTTP path preserved verbatim
- The plain `aliases.json` fallback also works (locked in as fallback option)

Implication for Plan 37-06: the alias map path string is
`mnemosyne/pf2e/players/_aliases.json` (underscore variant). The client does no
path validation — it only string-concatenates `{base_url}/vault/{path}` and lets
httpx URL-encode the path segments. Underscore is a valid URL character so no
encoding shenanigans either.
"""
from __future__ import annotations

import httpx
import pytest

from app.obsidian import ObsidianClient

UNDERSCORE_PATH = "mnemosyne/pf2e/players/_aliases.json"
PLAIN_PATH = "mnemosyne/pf2e/players/aliases.json"
BASE_URL = "https://obsidian.test:27124"
API_KEY = "test-key"


def _make_client(handler):
    """Build an ObsidianClient backed by a MockTransport that records requests."""
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return ObsidianClient(http_client, BASE_URL, API_KEY), http_client


@pytest.mark.asyncio
async def test_obsidian_client_accepts_underscore_prefixed_path_get():
    """get_note() with underscore-prefixed path issues HTTP GET to that exact path."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, text="{}")

    client, http_client = _make_client(handler)
    try:
        result = await client.get_note(UNDERSCORE_PATH)
    finally:
        await http_client.aclose()

    assert result == "{}", "get_note should return response text on 200"
    assert len(captured) == 1
    req = captured[0]
    assert req.method == "GET"
    # URL path is `/vault/{path}`; underscore must be preserved verbatim.
    assert req.url.path == f"/vault/{UNDERSCORE_PATH}", (
        f"expected underscore path to round-trip verbatim, got {req.url.path}"
    )
    assert req.headers.get("Authorization") == f"Bearer {API_KEY}"


@pytest.mark.asyncio
async def test_obsidian_client_accepts_underscore_prefixed_path_put():
    """put_note() with underscore-prefixed path issues HTTP PUT to that exact path."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(204)

    client, http_client = _make_client(handler)
    body = '{"alias_map": {}}'
    try:
        await client.put_note(UNDERSCORE_PATH, body)
    finally:
        await http_client.aclose()

    assert len(captured) == 1
    req = captured[0]
    assert req.method == "PUT"
    assert req.url.path == f"/vault/{UNDERSCORE_PATH}", (
        f"expected underscore path to round-trip verbatim, got {req.url.path}"
    )
    assert req.headers.get("Content-Type") == "text/markdown"
    assert req.content == body.encode("utf-8")


@pytest.mark.asyncio
async def test_obsidian_client_accepts_plain_aliases_json_path_get():
    """Fallback option lock-down: plain `aliases.json` (no underscore) also works."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, text="{}")

    client, http_client = _make_client(handler)
    try:
        result = await client.get_note(PLAIN_PATH)
    finally:
        await http_client.aclose()

    assert result == "{}"
    assert len(captured) == 1
    assert captured[0].url.path == f"/vault/{PLAIN_PATH}"


@pytest.mark.asyncio
async def test_obsidian_client_accepts_plain_aliases_json_path_put():
    """Fallback option lock-down: put_note() to plain `aliases.json` also works."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(204)

    client, http_client = _make_client(handler)
    try:
        await client.put_note(PLAIN_PATH, "{}")
    finally:
        await http_client.aclose()

    assert len(captured) == 1
    assert captured[0].url.path == f"/vault/{PLAIN_PATH}"
