"""ObsidianClient for pathfinder module — direct Obsidian REST API access (D-27).

Mirrors sentinel-core/app/clients/obsidian.py patterns.
All methods are async and expect an httpx.AsyncClient injected at construction.
"""
import json
import logging

import httpx

logger = logging.getLogger(__name__)


class ObsidianClient:
    """Thin async client for the Obsidian Local REST API v3.

    Instantiated once per lifespan in main.py and stored on app.state.
    The caller passes a persistent httpx.AsyncClient — do not create one here.
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

    async def get_note(self, path: str) -> str | None:
        """GET /vault/{path}. Returns note text or None if not found or on error."""

        async def _inner():
            resp = await self._client.get(
                f"{self._base_url}/vault/{path}",
                headers=self._headers,
                timeout=5.0,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text

        return await self._safe_request(_inner(), None, f"get_note({path})")

    async def put_note(self, path: str, content: str) -> None:
        """PUT /vault/{path} — create or fully replace a note.

        Raises httpx.HTTPStatusError on 4xx/5xx so callers can return HTTPException.
        """
        resp = await self._client.put(
            f"{self._base_url}/vault/{path}",
            headers={**self._headers, "Content-Type": "text/markdown"},
            content=content.encode("utf-8"),
            timeout=10.0,
        )
        resp.raise_for_status()

    async def put_binary(self, path: str, data: bytes, content_type: str) -> None:
        """PUT /vault/{path} with a binary body (images, PDFs, etc.).

        Sends the raw bytes with the caller-provided content_type header.
        Used for token images (content_type='image/png') stored under
        pf2e/tokens/<slug>.png. Raises httpx.HTTPStatusError on 4xx/5xx.
        """
        resp = await self._client.put(
            f"{self._base_url}/vault/{path}",
            headers={**self._headers, "Content-Type": content_type},
            content=data,
            timeout=15.0,
        )
        resp.raise_for_status()

    async def get_binary(self, path: str) -> bytes | None:
        """GET /vault/{path} returning raw bytes. Returns None on 404 or error.

        Mirrors get_note() error handling (silent fallback to None) but returns
        response.content instead of response.text.
        """

        async def _inner():
            resp = await self._client.get(
                f"{self._base_url}/vault/{path}",
                headers=self._headers,
                timeout=15.0,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.content

        return await self._safe_request(_inner(), None, f"get_binary({path})")

    async def list_directory(
        self,
        prefix: str,
        *,
        _depth: int = 0,
        _max_depth: int = 8,
    ) -> list[str]:
        """Recursively list full paths of files under a vault directory prefix.

        Used by the rules-engine reuse-match scan (D-05) and the /rule/show,
        /rule/history, /rule/list enumeration endpoints.

        Obsidian's `GET /vault/{dir}/` returns `{"files": [...]}` listing the
        immediate children: files end without a trailing slash, subdirectories
        end with `/`. We recurse into subdirectories so the returned list
        contains leaf file paths only (rooted at the vault, matching the shape
        expected by route-layer callers).

        Returns empty list on 404 or any error (silent fallback, mirrors
        get_note's degrade-gracefully shape).

        WR-06: max recursion depth bounded at 8 to prevent stack overflow on
        pathological vault structures (symlink loops, plugin-mounted dynamic
        directories). Emits a WARN log on overrun rather than silent return.
        Depth 8 is generous for mnemosyne/pf2e/rulings/{topic}/... —
        normal usage fits in depth 2-3.
        """
        if _depth > _max_depth:
            logger.warning(
                "list_directory(%s) hit max recursion depth %d — truncating",
                prefix, _max_depth,
            )
            return []
        # Ensure trailing slash — Obsidian REST distinguishes dir vs file by slash.
        dir_path = prefix if prefix.endswith("/") else f"{prefix}/"

        async def _inner() -> list[str]:
            resp = await self._client.get(
                f"{self._base_url}/vault/{dir_path}",
                headers=self._headers,
                timeout=10.0,
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            try:
                data = resp.json()
            except Exception:
                return []
            children = data.get("files") if isinstance(data, dict) else None
            if not isinstance(children, list):
                return []
            out: list[str] = []
            for child in children:
                if not isinstance(child, str):
                    continue
                full = f"{dir_path}{child}"
                if child.endswith("/"):
                    # Recurse into subdirectory; strip inner trailing slash on the join.
                    sub = await self.list_directory(
                        full, _depth=_depth + 1, _max_depth=_max_depth
                    )
                    out.extend(sub)
                else:
                    out.append(full)
            return out

        return await self._safe_request(
            _inner(), [], f"list_directory({dir_path})"
        )

    async def patch_heading(
        self,
        path: str,
        heading: str,
        content: str,
        operation: str = "append",
    ) -> None:
        """PATCH /vault/{path} targeting a markdown heading section body.

        IMPORTANT: Uses Content-Type: text/markdown and Target-Type: heading.
        Do NOT reuse patch_frontmatter_field — that uses application/json + frontmatter.
        (RESEARCH.md §Pitfall 1 — content-type mismatch causes silent corruption)

        heading: bare heading text without ## (e.g. "Events Log" not "## Events Log")
                 (RESEARCH.md §Pitfall 2 — heading name mismatch causes 404/invalid-target)
        operation: "append" | "replace"
        """
        resp = await self._client.patch(
            f"{self._base_url}/vault/{path}",
            headers={
                **self._headers,
                "Content-Type": "text/markdown",
                "Target-Type": "heading",
                "Target": heading,
                "Operation": operation,
            },
            content=content.encode("utf-8"),
            timeout=10.0,
        )
        resp.raise_for_status()

    async def patch_frontmatter_field(self, path: str, field: str, value) -> None:
        """PATCH /vault/{path} — replace ONE frontmatter field.

        Obsidian REST API v3: each PATCH targets exactly one field named by the
        `Target` header. The body is the complete new value for that field (D-29).
        Use this ONLY for single-field updates (e.g., `relationships` list replace).
        For multi-field updates, use get_note() then put_note() (GET-then-PUT).
        """
        resp = await self._client.patch(
            f"{self._base_url}/vault/{path}",
            headers={
                **self._headers,
                "Content-Type": "application/json",
                "Target-Type": "frontmatter",
                "Target": field,
                "Operation": "replace",
            },
            content=json.dumps(value).encode("utf-8"),
            timeout=10.0,
        )
        resp.raise_for_status()
