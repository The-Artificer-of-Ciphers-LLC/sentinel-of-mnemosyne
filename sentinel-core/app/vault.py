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
import re
import secrets
import typing
from datetime import datetime, timedelta, timezone

import httpx
import yaml

logger = logging.getLogger(__name__)


# --- Sweep lockfile constants (kept here because the lockfile lives in the vault) ---

_LOCKFILE_PATH = "ops/sweeps/_in-progress.md"
_STALE_LOCK_SECONDS = 3600  # 1 hour


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _split_frontmatter(body: str) -> tuple[dict, str]:
    m = _FRONTMATTER_RE.match(body or "")
    if not m:
        return ({}, body or "")
    try:
        fm = yaml.safe_load(m.group(1)) or {}
        if not isinstance(fm, dict):
            fm = {}
    except Exception:
        fm = {}
    return (fm, body[m.end():])


def _join_frontmatter(fm: dict, rest: str) -> str:
    if not fm:
        return rest
    block = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).strip()
    return f"---\n{block}\n---\n\n{rest.lstrip()}"


def _iso_utc(now: datetime | None = None) -> str:
    n = now or datetime.now(timezone.utc)
    return n.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_str(now: datetime | None = None) -> str:
    n = now or datetime.now(timezone.utc)
    return n.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _parse_iso(stamp: str) -> datetime | None:
    if not stamp:
        return None
    try:
        s = stamp.rstrip("Z")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


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

    async def read_persona(self) -> str | None: ...

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

    # --- Sweep capabilities (lockfile + trash + relocate) ---

    async def move_to_trash(
        self, path: str, when: datetime, *, reason: str = "", sweep_at: str | None = None
    ) -> str: ...

    async def relocate(
        self, src: str, dst: str, *, sweep_at: str | None = None
    ) -> str: ...

    async def acquire_sweep_lock(self, now: datetime | None = None) -> bool: ...

    async def release_sweep_lock(self) -> None: ...


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

    async def read_persona(self) -> str | None:
        """GET /vault/sentinel/persona.md — distinguishes 404 from transport failure.

        Returns:
          * the response body (str) on 200
          * ``None`` when the vault is reachable but the file does not exist (404)

        Raises:
          ``VaultUnreachableError`` on transport failure (timeout, connection
          error, 5xx). Lifespan branches on this to preserve ADR-0001:
          vault-up + persona 404 → hard fail; vault-down → graceful degrade.
        """
        try:
            resp = await self._client.get(
                f"{self._base_url}/vault/sentinel/persona.md",
                headers=self._headers,
                timeout=5.0,
            )
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            raise VaultUnreachableError(
                f"persona probe transport failure: {exc}"
            ) from exc

        if resp.status_code == 200:
            return resp.text
        if resp.status_code == 404:
            return None
        if 500 <= resp.status_code < 600:
            raise VaultUnreachableError(
                f"persona probe got {resp.status_code} from vault"
            )
        # 4xx other than 404 — treat as reachable but file unavailable
        return None

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

    # --- Sweep capabilities ---
    #
    # Method bodies migrated verbatim from app.services.vault_sweeper. The
    # sweeper module retains only decision logic (is_in_topic_dir,
    # propose_topic_move, run_sweep orchestration); the I/O primitives
    # belong on the Vault because they are vault concerns (lockfile lives
    # in the vault, trash/relocate are vault mutations).

    async def move_to_trash(
        self,
        path: str,
        when: datetime | None = None,
        *,
        reason: str = "",
        sweep_at: str | None = None,
    ) -> str:
        """Copy ``path`` into ``_trash/{when:%Y-%m-%d}/{basename}``, then delete src.

        Mirrors the historical ``vault_sweeper.move_to_trash`` semantics
        verbatim: collision suffix on existing target, frontmatter records
        ``original_path`` / ``reason`` / ``sweep_at``, delete failure is
        logged + swallowed (copy succeeded, duplicate is recoverable but
        lost data is not). Returns the destination path.
        """
        when = when or datetime.now(timezone.utc)
        today = _today_str(when)
        filename = path.rsplit("/", 1)[-1]
        dst = f"_trash/{today}/{filename}"

        existing = await self.read_note(dst)
        if existing:
            suffix = secrets.token_hex(4)
            stem, _, ext = filename.rpartition(".")
            if ext:
                dst = f"_trash/{today}/{stem}-{suffix}.{ext}"
            else:
                dst = f"_trash/{today}/{filename}-{suffix}"

        body = await self.read_note(path)
        fm, rest = _split_frontmatter(body)
        fm = dict(fm or {})
        fm["original_path"] = path
        fm["reason"] = reason
        fm["sweep_at"] = sweep_at or _iso_utc(when)
        annotated = _join_frontmatter(fm, rest)

        await self.write_note(dst, annotated)
        try:
            await self.delete_note(path)
        except Exception as exc:
            logger.warning(
                "move_to_trash: delete failed for %s after copy to %s: %s",
                path,
                dst,
                exc,
            )
        return dst

    async def relocate(
        self,
        src: str,
        dst: str,
        *,
        sweep_at: str | None = None,
    ) -> str:
        """Copy ``src`` to ``dst`` (with provenance frontmatter) then delete src.

        Mirrors ``vault_sweeper.move_to_topic_folder`` semantics: collision
        suffix on the existing target, frontmatter records ``original_path``
        and ``topic_moved_at``, delete failure is logged + swallowed.
        Returns the actual destination path (post collision-suffix).
        """
        existing = await self.read_note(dst)
        if existing:
            filename = dst.rsplit("/", 1)[-1]
            dst_dir = dst.rsplit("/", 1)[0] if "/" in dst else ""
            suffix = secrets.token_hex(4)
            stem, _, ext = filename.rpartition(".")
            if ext:
                base = f"{stem}-{suffix}.{ext}"
            else:
                base = f"{filename}-{suffix}"
            dst = f"{dst_dir}/{base}" if dst_dir else base

        body = await self.read_note(src)
        fm, rest = _split_frontmatter(body)
        fm = dict(fm or {})
        fm["original_path"] = src
        fm["topic_moved_at"] = sweep_at or _iso_utc()
        annotated = _join_frontmatter(fm, rest)

        await self.write_note(dst, annotated)
        try:
            await self.delete_note(src)
        except Exception as exc:
            logger.warning(
                "relocate: delete failed for %s after copy to %s: %s",
                src,
                dst,
                exc,
            )
        return dst

    async def acquire_sweep_lock(self, now: datetime | None = None) -> bool:
        """Return True if lock acquired; False if a fresh lock exists.

        Stale lockfiles (older than 1h) are taken over with a WARNING log
        per RESEARCH Pitfall 1.
        """
        now = now or datetime.now(timezone.utc)
        existing = await self.read_note(_LOCKFILE_PATH)
        if existing.strip():
            fm, _ = _split_frontmatter(existing)
            started = _parse_iso(str(fm.get("started_at", "")))
            if started is not None:
                age = (now - started).total_seconds()
                if age < _STALE_LOCK_SECONDS:
                    return False
                logger.warning(
                    "acquire_sweep_lock: stale lockfile (age %.0fs) — taking over",
                    age,
                )
        fm = {"started_at": _iso_utc(now), "host": "sentinel-core"}
        body = _join_frontmatter(fm, "# Sweep in progress\n")
        await self.write_note(_LOCKFILE_PATH, body)
        return True

    async def release_sweep_lock(self) -> None:
        try:
            await self.delete_note(_LOCKFILE_PATH)
        except Exception as exc:
            logger.warning("release_sweep_lock: delete failed: %s", exc)
