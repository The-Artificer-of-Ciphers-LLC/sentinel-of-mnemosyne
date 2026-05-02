"""Vault capability seam.

This module owns the *Vault* concept end-to-end:

  * ``Vault`` is a ``typing.Protocol`` describing every capability the rest
    of the app uses against the vault — domain-shaped methods (user-context,
    recent-sessions, session-summary, find) plus the lower-level note
    primitives. Sweep capabilities and the persona probe are appended in
    later tasks of the same plan; this is the initial surface.
  * ``ObsidianVault`` is the concrete adapter that fulfills the Protocol
    by talking to the Obsidian Local REST API over HTTP.
  * ``VaultUnreachableError`` distinguishes "vault reachable, file missing"
    from "vault transport failure" so the lifespan can keep ADR-0001's
    contract (vault-up + persona 404 → hard fail; vault-down → graceful
    degrade).

ADR-0002 records the convention break: Vault Protocol + adapter live here,
not in ``app/clients/``, because the Vault is a domain capability seam,
not one HTTP adapter among many.
"""
from __future__ import annotations

import logging
import typing
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)


class VaultUnreachableError(Exception):
    """Raised when the vault is unreachable (transport failure / 5xx).

    Distinguishes from "reachable but file missing" (which surfaces as
    ``None`` / empty / ``False`` per the relevant capability's contract).
    Pairs with ``ContextLengthError`` / ``EmbeddingModelUnavailable`` /
    ``ProviderUnavailableError`` as a typed transport-failure exception.
    """


@typing.runtime_checkable
class Vault(typing.Protocol):
    """Capability surface for the vault. Tests use ``FakeVault``; production
    uses ``ObsidianVault``."""

    async def check_health(self) -> bool: ...

    async def get_user_context(self, user_id: str) -> str | None: ...

    async def read_self_context(self, path: str) -> str: ...

    async def get_recent_sessions(self, user_id: str, limit: int = 3) -> list[str]: ...

    async def write_session_summary(self, path: str, content: str) -> None: ...

    async def find(self, query: str) -> list[dict]: ...

    async def list_under(self, prefix: str = "") -> list[str]: ...

    async def read_note(self, path: str) -> str: ...

    async def write_note(self, path: str, body: str) -> None: ...

    async def delete_note(self, path: str) -> None: ...

    async def patch_append(self, path: str, body: str) -> None: ...


class ObsidianVault:
    """Concrete ``Vault`` adapter backed by the Obsidian Local REST API.

    HTTP mode: plugin must have non-encrypted server enabled (port 27123).
      Settings → Community Plugins → Local REST API → enable non-encrypted server.
    HTTPS mode: use https://host.docker.internal:27124 with OBSIDIAN_VERIFY_SSL=false.

    All "graceful-degrade" methods (``check_health``, ``get_user_context``,
    ``read_self_context``, ``get_recent_sessions``, ``write_session_summary``,
    ``find``, ``list_under``, ``read_note``) swallow transport failures and
    return a sensible default. The mutating note primitives (``write_note``,
    ``delete_note``, ``patch_append``) raise on non-2xx — callers that need
    durability assert on success.
    """

    def __init__(self, http_client: httpx.AsyncClient, base_url: str, api_key: str) -> None:
        self._client = http_client
        self._base_url = base_url.rstrip("/")
        self._headers: dict[str, str] = (
            {"Authorization": f"Bearer {api_key}"} if api_key else {}
        )

    async def _safe_request(self, coro, default, operation: str, silent: bool = False):
        """Execute a coroutine, returning default on any failure."""
        try:
            return await coro
        except Exception as exc:
            if not silent:
                logger.warning("%s failed: %s", operation, exc)
            return default

    async def check_health(self) -> bool:
        """Return True if Obsidian REST API is reachable. Non-raising."""

        async def _inner():
            resp = await self._client.get(
                f"{self._base_url}/vault/",
                headers=self._headers,
                timeout=3.0,
            )
            return resp.status_code < 500

        return await self._safe_request(_inner(), False, "check_health", silent=True)

    async def get_user_context(self, user_id: str) -> str | None:
        """
        GET /vault/self/identity.md — single user system (D-01).
        Returns file body or None if 404 or unavailable.
        Per D-4: reads verbatim, no schema enforcement. Missing file = skip injection silently.
        """

        async def _inner():
            resp = await self._client.get(
                f"{self._base_url}/vault/self/identity.md",
                headers=self._headers,
                timeout=5.0,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text

        return await self._safe_request(_inner(), None, "get_user_context")

    async def read_self_context(self, path: str) -> str:
        """
        GET /vault/{path} — reads a single self/ or ops/ context file.
        Returns empty string on 404 silently (no log entry, per D-02).
        Returns empty string on any other error, logs warning.
        Called via asyncio.gather() for all 5 context paths in parallel.
        """

        async def _inner():
            resp = await self._client.get(
                f"{self._base_url}/vault/{path}",
                headers=self._headers,
                timeout=5.0,
            )
            if resp.status_code == 404:
                return ""
            resp.raise_for_status()
            return resp.text

        return await self._safe_request(_inner(), "", "read_self_context")

    async def get_recent_sessions(self, user_id: str, limit: int = 3) -> list[str]:
        """
        Hot tier: return content of last `limit` session files for this user_id.
        Strategy: list today's and yesterday's ops/sessions/ directories by filename,
        filter to files matching user_id, sort descending, fetch content for top N.
        Returns [] on any error (graceful degrade per D-3).
        MEM-05: hot-tier implementation.
        """

        async def _inner():
            now = datetime.now(timezone.utc)
            dates = [now.strftime("%Y-%m-%d")]
            yesterday = now - timedelta(days=1)
            dates.append(yesterday.strftime("%Y-%m-%d"))

            candidates: list[tuple[str, str]] = []  # (sort_key, path)
            for date in dates:
                try:
                    resp = await self._client.get(
                        f"{self._base_url}/vault/ops/sessions/{date}/",
                        headers=self._headers,
                        timeout=5.0,
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    files = data if isinstance(data, list) else data.get("files", [])
                    for f in files:
                        filename = f if isinstance(f, str) else f.get("path", "")
                        if f"{user_id}-" in filename and filename.endswith(".md"):
                            candidates.append(
                                (f"{date}/{filename}", f"ops/sessions/{date}/{filename}")
                            )
                except Exception:
                    continue

            candidates.sort(key=lambda x: x[0], reverse=True)
            top = candidates[:limit]

            contents: list[str] = []
            for _, path in top:
                try:
                    resp = await self._client.get(
                        f"{self._base_url}/vault/{path}",
                        headers=self._headers,
                        timeout=5.0,
                    )
                    if resp.status_code == 200:
                        contents.append(resp.text)
                except Exception:
                    continue
            return contents

        return await self._safe_request(_inner(), [], "get_recent_sessions")

    async def write_session_summary(self, path: str, content: str) -> None:
        """
        PUT /vault/{path} — write session summary markdown.
        Per D-2 (MEM-06): always called after every completed exchange.
        Swallows transport errors and logs a warning, returning None on failure —
        the HTTP response to the user is never blocked by a vault write failure.
        """

        async def _inner():
            resp = await self._client.put(
                f"{self._base_url}/vault/{path}",
                headers={**self._headers, "Content-Type": "text/markdown"},
                content=content.encode("utf-8"),
                timeout=10.0,
            )
            resp.raise_for_status()
            return None

        await self._safe_request(_inner(), None, "write_session_summary")

    async def list_under(self, prefix: str = "") -> list[str]:
        """GET /vault/{prefix}/ — return mixed list of filenames and subdir names.

        Subdir names end with '/'. Returns [] on 404 or any error (graceful degrade).
        Domain-language rename of the historical ``list_directory`` primitive.
        """

        async def _inner():
            url = (
                f"{self._base_url}/vault/{prefix}/" if prefix else f"{self._base_url}/vault/"
            )
            resp = await self._client.get(url, headers=self._headers, timeout=10.0)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
            files = data if isinstance(data, list) else data.get("files", [])
            return [f if isinstance(f, str) else f.get("path", "") for f in files]

        return await self._safe_request(_inner(), [], "list_under")

    async def read_note(self, path: str) -> str:
        """GET /vault/{path} — return body on 200, "" on 404 or error."""

        async def _inner():
            resp = await self._client.get(
                f"{self._base_url}/vault/{path}",
                headers=self._headers,
                timeout=10.0,
            )
            if resp.status_code == 404:
                return ""
            resp.raise_for_status()
            return resp.text

        return await self._safe_request(_inner(), "", "read_note")

    async def write_note(self, path: str, body: str) -> None:
        """PUT /vault/{path} with text/markdown content-type. Raises on non-2xx."""
        resp = await self._client.put(
            f"{self._base_url}/vault/{path}",
            headers={**self._headers, "Content-Type": "text/markdown"},
            content=body.encode("utf-8"),
            timeout=10.0,
        )
        resp.raise_for_status()

    async def delete_note(self, path: str) -> None:
        """DELETE /vault/{path}. Raises on non-2xx."""
        resp = await self._client.delete(
            f"{self._base_url}/vault/{path}",
            headers=self._headers,
            timeout=10.0,
        )
        resp.raise_for_status()

    async def patch_append(self, path: str, body: str) -> None:
        """PATCH /vault/{path} with `Obsidian-API-Content-Insertion-Position: end`.

        Mirrors the bot.py:1303 `_persist_thread_id` pattern. Raises on non-2xx.
        """
        resp = await self._client.patch(
            f"{self._base_url}/vault/{path}",
            headers={
                **self._headers,
                "Content-Type": "text/markdown",
                "Obsidian-API-Content-Insertion-Position": "end",
            },
            content=body.encode("utf-8"),
            timeout=10.0,
        )
        resp.raise_for_status()

    async def find(self, query: str) -> list[dict]:
        """
        POST /search/simple/?query={query} — keyword search abstraction.
        MEM-08: callers use this method; implementation can switch keyword→vector without change.
        Returns [] on any error.
        """

        async def _inner():
            resp = await self._client.post(
                f"{self._base_url}/search/simple/",
                headers=self._headers,
                params={"query": query},
                timeout=5.0,
            )
            resp.raise_for_status()
            return resp.json()

        return await self._safe_request(_inner(), [], "find")
