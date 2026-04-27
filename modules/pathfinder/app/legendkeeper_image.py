"""LegendKeeper CDN image downloader (260427-czb Task 2).

Reuses the Phase 30 token plumbing (`obsidian.put_binary`) — does NOT
re-implement vault image writes. Tokens always land at
``mnemosyne/pf2e/tokens/<slug>.png`` regardless of source content-type:

  * image/png → written verbatim
  * image/jpeg → re-encoded to PNG via Pillow (vault tokens are uniformly
    .png so token_image schema doesn't have to branch on extension)
  * image/webp → decoded with Pillow, re-encoded to PNG
  * anything else, 404, timeout, or any exception → returns None and logs
    a warning (the importer treats this as "no token image" and continues)

Per CLAUDE.md No-Risk-Commentary: no defensive fallbacks beyond the four
above — failure modes that aren't network/CDN/codec issues are treated
as bugs to fix, not edge cases to swallow.
"""
from __future__ import annotations

import logging
from io import BytesIO
from typing import Protocol

import httpx
from PIL import Image

logger = logging.getLogger(__name__)


_TOKENS_DIR = "mnemosyne/pf2e/tokens"


class _PutsBinary(Protocol):
    async def put_binary(self, path: str, data: bytes, content_type: str) -> None: ...


async def download_token(
    url: str,
    *,
    dest_slug: str,
    obsidian_client: _PutsBinary,
    http_client: httpx.AsyncClient,
) -> str | None:
    """Download a LegendKeeper image and write a PNG to the vault tokens dir.

    Args:
      url: the LegendKeeper CDN URL (typically https://assets.legendkeeper.com/<uuid>.<ext>).
      dest_slug: the NPC slug — the final vault path is
        ``mnemosyne/pf2e/tokens/<dest_slug>.png``.
      obsidian_client: anything exposing an async ``put_binary(path, data, ct)``.
      http_client: caller-owned httpx.AsyncClient (so tests can inject
        MockTransport without monkeypatching).

    Returns:
      The vault path on success, ``None`` on any failure path.
    """
    dest = f"{_TOKENS_DIR}/{dest_slug}.png"
    try:
        resp = await http_client.get(
            url,
            headers={"Accept": "image/png,image/jpeg;q=0.8,image/webp;q=0.5"},
        )
    except httpx.TimeoutException as exc:
        logger.warning("download_token timeout for %s: %s", url, exc)
        return None
    except httpx.HTTPError as exc:
        logger.warning("download_token http error for %s: %s", url, exc)
        return None

    if resp.status_code != 200:
        logger.warning(
            "download_token: %s returned %d; skipping token", url, resp.status_code
        )
        return None

    content_type = (resp.headers.get("content-type") or "").lower().split(";", 1)[0].strip()
    raw = resp.content

    try:
        png_bytes = _to_png_bytes(raw, content_type)
    except Exception as exc:  # Pillow raises a variety of decode exceptions
        logger.warning(
            "download_token: failed to convert %s (%s) to PNG: %s",
            url, content_type, exc,
        )
        return None

    if png_bytes is None:
        logger.warning(
            "download_token: unsupported content-type %r at %s; skipping",
            content_type, url,
        )
        return None

    try:
        await obsidian_client.put_binary(dest, png_bytes, "image/png")
    except Exception as exc:
        logger.warning("download_token: vault write failed for %s: %s", dest, exc)
        return None
    return dest


def _to_png_bytes(raw: bytes, content_type: str) -> bytes | None:
    """Convert raw image bytes to PNG.

    Returns the PNG bytes on success, or ``None`` if ``content_type`` is not
    a supported image format (caller logs + returns None).
    """
    if content_type == "image/png":
        # Already PNG — return verbatim. We do not re-encode because the
        # source is already in the canonical format.
        return raw
    if content_type in {"image/jpeg", "image/jpg", "image/webp"}:
        with Image.open(BytesIO(raw)) as img:
            img = img.convert("RGBA")
            buf = BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
    return None
