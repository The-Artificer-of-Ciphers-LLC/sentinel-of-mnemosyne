"""Deterministic per-player recall engine (PVL-03 / PVL-07).

CONTEXT lock (Phase 37 v1): keyword-match + recency-weight scoring ONLY.
NO LLM. NO embeddings. v2 may layer embeddings on top — out of scope here.

Single public entry point::

    async def recall(slug, query, *, obsidian, limit=10) -> list[dict]

Reads happen exclusively under ``mnemosyne/pf2e/players/{slug}/`` — the same
slug-prefix isolation invariant enforced by ``player_vault_store._resolve_player_path``.
The slug shape is validated against the same regex used by the store; an
invalid slug raises ``ValueError`` before any I/O is attempted.

Scoring::

    score = keyword_count(case-insensitive token overlap) + recency_weight(path)

  - ``keyword_count`` is the sum, across each whitespace-separated query token,
    of case-insensitive substring occurrences in the file body. Empty query
    contributes 0 keyword score and falls back to pure recency ordering.
  - ``recency_weight`` parses ``sessions/(YYYY-MM-DD)\\.md`` filenames and returns
    ``max(0.0, 1.0 - days_since/365)``. Non-session files get a fixed 0.1.

Sort: descending by ``(score, recency)``; ties broken by path (string sort) so
output is deterministic across calls.

Snippets: a ~80-char window around the first matched query token, or the first
80 chars of the body if the query is missing or unmatched.

Result shape::

    {"path": str, "snippet": str, "score": float}
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

_PLAYER_NAMESPACE_PREFIX = "mnemosyne/pf2e/players"

# Mirror player_vault_store._SLUG_RE so an invalid slug fails fast here too.
_SLUG_RE = re.compile(r"^(?:p-[a-f0-9]{12}|[a-zA-Z0-9_-]{1,40})$")

_SESSION_DATE_RE = re.compile(r"sessions/(\d{4})-(\d{2})-(\d{2})\.md$")
_NON_SESSION_RECENCY = 0.1
_SNIPPET_HALF_WIDTH = 40  # chars on each side of the matched token


def _today_iso() -> str:
    """Today's date as ISO YYYY-MM-DD. Patched in unit tests for determinism."""
    return date.today().isoformat()


def _validate_slug(slug: str) -> None:
    if not isinstance(slug, str) or not slug:
        raise ValueError(f"player slug must be a non-empty string, got {slug!r}")
    if slug.startswith(".") or "/" in slug or ".." in slug:
        raise ValueError(f"player slug contains forbidden chars: {slug!r}")
    if not _SLUG_RE.match(slug):
        raise ValueError(f"player slug failed shape validation: {slug!r}")


def _parse_iso_date(s: str) -> date | None:
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def _recency_weight(path: str, today_iso: str) -> float:
    """Return a recency weight in [0.0, 1.0].

    Session files (`.../sessions/YYYY-MM-DD.md`) are weighted by date proximity
    to ``today_iso``; non-session files get a fixed lower weight.
    """
    m = _SESSION_DATE_RE.search(path)
    if not m:
        return _NON_SESSION_RECENCY
    file_date = _parse_iso_date(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    today = _parse_iso_date(today_iso)
    if file_date is None or today is None:
        return _NON_SESSION_RECENCY
    days_since = (today - file_date).days
    if days_since < 0:
        # Future-dated session — clamp to 1.0 (treat as "today").
        return 1.0
    return max(0.0, 1.0 - days_since / 365.0)


def _keyword_count(body: str, query: str | None) -> int:
    """Sum of case-insensitive substring occurrences for each query token."""
    if not query:
        return 0
    tokens = [t for t in query.split() if t]
    if not tokens:
        return 0
    haystack = body.lower()
    total = 0
    for t in tokens:
        needle = t.lower()
        if not needle:
            continue
        # str.count counts non-overlapping occurrences — adequate for ranking.
        total += haystack.count(needle)
    return total


def _build_snippet(body: str, query: str | None) -> str:
    """Return a ~80-char window around the first query-token match.

    Falls back to the first 80 chars of the body when the query is missing or
    no token matches.
    """
    if not body:
        return ""
    fallback = body[: _SNIPPET_HALF_WIDTH * 2].strip()
    if not query:
        return fallback
    tokens = [t for t in query.split() if t]
    if not tokens:
        return fallback
    haystack_lower = body.lower()
    for t in tokens:
        needle = t.lower()
        idx = haystack_lower.find(needle)
        if idx == -1:
            continue
        start = max(0, idx - _SNIPPET_HALF_WIDTH)
        end = min(len(body), idx + len(t) + _SNIPPET_HALF_WIDTH)
        return body[start:end].strip()
    return fallback


async def recall(
    slug: str,
    query: str | None,
    *,
    obsidian: Any,
    limit: int = 10,
) -> list[dict]:
    """Score and rank notes under players/{slug}/ for ``query``.

    See module docstring for scoring contract. Reads ONLY under the requesting
    slug's namespace; never reaches outside ``mnemosyne/pf2e/players/{slug}/``.
    """
    _validate_slug(slug)
    if limit <= 0:
        return []

    prefix = f"{_PLAYER_NAMESPACE_PREFIX}/{slug}/"
    paths = await obsidian.list_directory(prefix)
    if not paths:
        return []

    today_iso = _today_iso()
    scored: list[tuple[float, float, str, str]] = []
    # Defensive isolation guard: drop any path that somehow doesn't sit under
    # the requesting slug's prefix. This belt-and-braces check makes PVL-07
    # impossible to violate even if a future obsidian client returns extras.
    for path in paths:
        if not isinstance(path, str) or not path.startswith(prefix):
            continue
        body = await obsidian.get_note(path)
        if body is None:
            body = ""
        recency = _recency_weight(path, today_iso)
        kw = _keyword_count(body, query)
        score = float(kw) + recency
        snippet = _build_snippet(body, query)
        scored.append((score, recency, path, snippet))

    # Sort desc by (score, recency); break remaining ties by path string for
    # deterministic ordering. Python sort is stable; we negate via reverse=True
    # using a tuple of negative numerics + path string.
    scored.sort(key=lambda t: (-t[0], -t[1], t[2]))

    return [
        {"path": path, "snippet": snippet, "score": score}
        for (score, _recency, path, snippet) in scored[:limit]
    ]


__all__ = ["recall"]
