"""Tests for LegendKeeper image downloader (260427-czb Task 2).

Uses httpx.MockTransport to inject deterministic CDN responses. No real
network calls. Asserts on:
  * PNG / JPEG / WebP content-type handling.
  * Pillow re-encoding when the CDN serves WebP.
  * 404 / timeout → returns None and writes nothing.
  * Final vault path is mnemosyne/pf2e/tokens/<slug>.png with image/png
    content-type.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any

import httpx
import pytest
from PIL import Image

from app.legendkeeper_image import download_token


class _FakeObsidian:
    """Records put_binary calls for assertion."""

    def __init__(self) -> None:
        self.binary_writes: list[tuple[str, bytes, str]] = []

    async def put_binary(self, path: str, data: bytes, content_type: str) -> None:
        self.binary_writes.append((path, data, content_type))


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (1, 1), (0, 255, 0)).save(buf, format="JPEG")
    return buf.getvalue()


def _webp_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (1, 1), (0, 0, 255, 255)).save(buf, format="WEBP")
    return buf.getvalue()


def _make_client(handler: Any) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, follow_redirects=True, timeout=30.0)


# ---------------------------------------------------------------------------
# PNG response → file written, dest path returned, content-type image/png.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_png_response_writes_png_to_vault():
    obs = _FakeObsidian()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_png_bytes(), headers={"content-type": "image/png"})

    async with _make_client(handler) as client:
        path = await download_token(
            "https://assets.legendkeeper.com/abc.png",
            dest_slug="alice-twoorb",
            obsidian_client=obs,
            http_client=client,
        )

    assert path == "mnemosyne/pf2e/tokens/alice-twoorb.png"
    assert len(obs.binary_writes) == 1
    written_path, written_bytes, ct = obs.binary_writes[0]
    assert written_path == "mnemosyne/pf2e/tokens/alice-twoorb.png"
    assert ct == "image/png"
    assert written_bytes.startswith(b"\x89PNG")


# ---------------------------------------------------------------------------
# JPEG response → re-encoded to PNG.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jpeg_response_is_reencoded_to_png():
    obs = _FakeObsidian()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_jpeg_bytes(), headers={"content-type": "image/jpeg"})

    async with _make_client(handler) as client:
        path = await download_token(
            "https://assets.legendkeeper.com/abc.jpeg",
            dest_slug="alice",
            obsidian_client=obs,
            http_client=client,
        )

    assert path == "mnemosyne/pf2e/tokens/alice.png"
    assert len(obs.binary_writes) == 1
    written_path, written_bytes, ct = obs.binary_writes[0]
    assert ct == "image/png"
    assert written_bytes.startswith(b"\x89PNG"), "must be re-encoded to PNG, not stored as JPEG"


# ---------------------------------------------------------------------------
# WebP → Pillow re-encodes to PNG.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webp_response_is_reencoded_to_png():
    obs = _FakeObsidian()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_webp_bytes(), headers={"content-type": "image/webp"})

    async with _make_client(handler) as client:
        path = await download_token(
            "https://assets.legendkeeper.com/abc.webp",
            dest_slug="ragmejom",
            obsidian_client=obs,
            http_client=client,
        )

    assert path == "mnemosyne/pf2e/tokens/ragmejom.png"
    assert len(obs.binary_writes) == 1
    _, written_bytes, ct = obs.binary_writes[0]
    assert ct == "image/png"
    assert written_bytes.startswith(b"\x89PNG")


# ---------------------------------------------------------------------------
# 404 → returns None, writes nothing.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_404_returns_none_and_writes_nothing():
    obs = _FakeObsidian()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with _make_client(handler) as client:
        path = await download_token(
            "https://assets.legendkeeper.com/missing.png",
            dest_slug="x",
            obsidian_client=obs,
            http_client=client,
        )

    assert path is None
    assert obs.binary_writes == []


# ---------------------------------------------------------------------------
# Timeout → returns None.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_returns_none_and_writes_nothing():
    obs = _FakeObsidian()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    async with _make_client(handler) as client:
        path = await download_token(
            "https://assets.legendkeeper.com/slow.png",
            dest_slug="x",
            obsidian_client=obs,
            http_client=client,
        )

    assert path is None
    assert obs.binary_writes == []


# ---------------------------------------------------------------------------
# Accept header sent.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_sends_accept_header_for_png_jpeg():
    obs = _FakeObsidian()
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["accept"] = request.headers.get("accept", "")
        return httpx.Response(200, content=_png_bytes(), headers={"content-type": "image/png"})

    async with _make_client(handler) as client:
        await download_token(
            "https://assets.legendkeeper.com/abc.png",
            dest_slug="x",
            obsidian_client=obs,
            http_client=client,
        )

    assert "image/png" in seen["accept"]
