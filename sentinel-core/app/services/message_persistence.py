"""Best-effort persistence helpers for message route."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def write_session_summary_best_effort(obsidian, path: str, content: str) -> None:
    try:
        await obsidian.write_session_summary(path, content)
        logger.debug("Session summary written: %s", path)
    except Exception as exc:
        logger.warning("Session summary write failed for %s: %s", path, exc)
