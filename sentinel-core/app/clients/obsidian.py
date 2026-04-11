"""
Obsidian Local REST API client.
Follows the exact adapter pattern of lmstudio.py and pi_adapter.py.
All methods degrade gracefully on error — callers never need to handle exceptions
from this client (except write_session_summary, which callers wrap in try/except).

HTTP mode: plugin must have non-encrypted server enabled (port 27123).
  Settings → Community Plugins → Local REST API → enable non-encrypted server.
HTTPS mode: use https://host.docker.internal:27124 with OBSIDIAN_VERIFY_SSL=false.

MEM-08: search abstraction — keyword search now, vector later without caller changes.
"""
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)


class ObsidianClient:
    """HTTP client for Obsidian Local REST API."""

    def __init__(self, http_client: httpx.AsyncClient, base_url: str, api_key: str) -> None:
        self._client = http_client
        self._base_url = base_url.rstrip("/")
        self._headers: dict[str, str] = (
            {"Authorization": f"Bearer {api_key}"} if api_key else {}
        )

    async def check_health(self) -> bool:
        """Return True if Obsidian REST API is reachable. Non-raising."""
        try:
            resp = await self._client.get(
                f"{self._base_url}/vault/",
                headers=self._headers,
                timeout=3.0,
            )
            return resp.status_code < 500
        except Exception:
            return False

    async def get_user_context(self, user_id: str) -> str | None:
        """
        GET /vault/core/users/{user_id}.md
        Returns file body or None if 404 or unavailable.
        Per D-4: reads verbatim, no schema enforcement. Missing file = skip injection silently.
        """
        try:
            resp = await self._client.get(
                f"{self._base_url}/vault/core/users/{user_id}.md",
                headers=self._headers,
                timeout=5.0,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except Exception:
            logger.warning("ObsidianClient.get_user_context failed — skipping context injection")
            return None

    async def get_recent_sessions(self, user_id: str, limit: int = 3) -> list[str]:
        """
        Hot tier: return content of last `limit` session files for this user_id.
        Strategy: list today's and yesterday's session directories by filename,
        filter to files matching user_id, sort descending, fetch content for top N.
        Returns [] on any error (graceful degrade per D-3).
        MEM-05: hot-tier implementation.
        """
        try:
            now = datetime.now(timezone.utc)
            dates = [now.strftime("%Y-%m-%d")]
            yesterday = now.replace(day=now.day - 1) if now.day > 1 else now
            dates.append(yesterday.strftime("%Y-%m-%d"))

            candidates: list[tuple[str, str]] = []  # (sort_key, path)
            for date in dates:
                try:
                    resp = await self._client.get(
                        f"{self._base_url}/vault/core/sessions/{date}/",
                        headers=self._headers,
                        timeout=5.0,
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    # Obsidian directory listing returns {"files": [...]} or a list directly
                    files = data if isinstance(data, list) else data.get("files", [])
                    for f in files:
                        filename = f if isinstance(f, str) else f.get("path", "")
                        if f"{user_id}-" in filename and filename.endswith(".md"):
                            # sort_key = date + filename for chronological sort
                            candidates.append((f"{date}/{filename}", f"core/sessions/{date}/{filename}"))
                except Exception:
                    continue

            # Sort descending by sort_key (date+filename encodes timestamp), take top N
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
        except Exception:
            logger.warning("ObsidianClient.get_recent_sessions failed — skipping hot tier")
            return []

    async def write_session_summary(self, path: str, content: str) -> None:
        """
        PUT /vault/{path} — write session summary markdown.
        Per D-2 (MEM-06): always called after every completed exchange.
        Callers wrap in try/except and log warning on failure — do NOT fail the HTTP response.
        """
        resp = await self._client.put(
            f"{self._base_url}/vault/{path}",
            headers={**self._headers, "Content-Type": "text/markdown"},
            content=content.encode("utf-8"),
            timeout=10.0,
        )
        resp.raise_for_status()

    async def search_vault(self, query: str) -> list[dict]:
        """
        POST /search/simple/?query={query} — keyword search abstraction.
        MEM-08: callers use this method; implementation can switch keyword→vector without change.
        Returns [] on any error.
        """
        try:
            resp = await self._client.post(
                f"{self._base_url}/search/simple/",
                headers=self._headers,
                params={"query": query},
                timeout=5.0,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning("ObsidianClient.search_vault failed — returning empty results")
            return []
