"""Shared time/date utilities for Sentinel Core.

Three functions used by the vault, vault_sweeper, and note_intake modules:
  - ``_iso_utc(now)`` → ISO-8601 UTC timestamp string
  - ``_today_str(now)`` → date-only string (YYYY-MM-DD)
  - ``_parse_iso(stamp)`` → parse ISO-8601 back to datetime (timezone-aware)

All callers import here instead of defining local copies.
"""
from __future__ import annotations

from datetime import datetime, timezone


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
