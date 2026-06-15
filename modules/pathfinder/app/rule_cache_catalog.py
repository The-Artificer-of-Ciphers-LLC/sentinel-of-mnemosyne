"""Cached Pathfinder ruling catalog."""

from __future__ import annotations

import logging
from typing import Any

from app.rules import RULING_CACHE_PATH_PREFIX, _parse_ruling_cache, coerce_topic

logger = logging.getLogger(__name__)


class RuleCacheCatalog:
    """Read-only catalog for cached Pathfinder rulings."""

    def __init__(self, obsidian: Any) -> None:
        self._obsidian = obsidian

    async def show_topic(self, topic: str) -> dict:
        """List rulings under one topic, newest reuse first."""
        coerced = coerce_topic(topic)
        prefix = f"{RULING_CACHE_PATH_PREFIX}/{coerced}/"
        collected = await self._collect_rulings_under(prefix)
        entries = [
            self._build_ruling_index_entry(path, parsed, topic=coerced)
            for path, parsed in collected
        ]
        entries.sort(key=lambda entry: entry.get("last_reused_at", ""), reverse=True)
        return {"topic": coerced, "count": len(entries), "rulings": entries}

    async def history(self, n: int) -> dict:
        """Return the N most recent rulings across all topics."""
        root_prefix = f"{RULING_CACHE_PATH_PREFIX}/"
        entries: list[dict] = []
        for path, parsed in await self._collect_rulings_under(root_prefix):
            stripped = path.removeprefix(root_prefix)
            topic = stripped.split("/", 1)[0] if "/" in stripped else "misc"
            entries.append(self._build_ruling_index_entry(path, parsed, topic=topic))
        entries.sort(key=lambda entry: entry.get("last_reused_at", ""), reverse=True)
        return {"n": n, "rulings": entries[:n]}

    async def topics(self) -> dict:
        """Enumerate topic folders and their cache activity."""
        root_prefix = f"{RULING_CACHE_PATH_PREFIX}/"
        per_topic: dict[str, dict] = {}
        for path, parsed in await self._collect_rulings_under(root_prefix):
            stripped = path.removeprefix(root_prefix)
            if "/" not in stripped:
                continue
            topic = stripped.split("/", 1)[0]
            bucket = per_topic.setdefault(
                topic, {"slug": topic, "count": 0, "last_activity": ""}
            )
            bucket["count"] += 1
            last_activity = parsed.get("last_reused_at", parsed.get("composed_at", ""))
            if last_activity > bucket["last_activity"]:
                bucket["last_activity"] = last_activity
        topics = list(per_topic.values())
        topics.sort(key=lambda item: item.get("last_activity", ""), reverse=True)
        return {"topics": topics}

    async def _collect_rulings_under(self, prefix: str) -> list[tuple[str, dict]]:
        """Walk a ruling prefix and return parsed cache notes."""
        try:
            paths = await self._obsidian.list_directory(prefix)
        except Exception as exc:
            logger.warning("rule catalog: list_directory %s failed: %s", prefix, exc)
            return []

        collected: list[tuple[str, dict]] = []
        for path in paths:
            if not path.endswith(".md"):
                continue
            text = await self._obsidian.get_note(path)
            if not text:
                continue
            parsed = _parse_ruling_cache(text)
            if parsed is None:
                logger.warning("rule catalog: malformed cache at %s, skipping", path)
                continue
            collected.append((path, parsed))
        return collected

    @staticmethod
    def _build_ruling_index_entry(
        path: str, parsed: dict, topic: str | None = None
    ) -> dict:
        """Extract the summary fields a UI or Discord adapter would list."""
        hash_part = path.rsplit("/", 1)[-1].removesuffix(".md")
        return {
            "hash": hash_part,
            "topic": topic or parsed.get("topic"),
            "question": parsed.get("question", ""),
            "composed_at": parsed.get("composed_at", ""),
            "last_reused_at": parsed.get(
                "last_reused_at", parsed.get("composed_at", "")
            ),
            "marker": parsed.get("marker", ""),
            "source": parsed.get("source"),
        }


__all__ = ["RuleCacheCatalog"]
