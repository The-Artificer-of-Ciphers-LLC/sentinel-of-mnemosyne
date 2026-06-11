"""Recall module — owns hot-tier and warm-tier retrieval policy.

Provides ``Recall.assemble(request, budget) -> RecalledContext`` as the single
entry point for all memory retrieval. Constants previously inlined in
``message_processing.py`` move here into ``RecallConfig`` (MEM-02).

``RecalledContext`` is a pure value type — it carries ranked memory items and
never contains chat messages or injection-wrapped text. Presentation concerns
(system-message swap, context filtering, token truncation) remain in
``MessageProcessor`` per D-04.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.vault import Vault
    from app.services.message_processing import MessageRequest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants (moved verbatim from message_processing.py)
# ---------------------------------------------------------------------------

# Obsidian /search/simple/ returns BM25-variant scores that are negative for most queries.
# Calibrated against real data: relevant content notes land around -120, irrelevant ops/sweep
# noise lands around -202. A floor of -200 correctly admits the former and rejects the latter.
SEARCH_SCORE_THRESHOLD = -200.0

# Paths excluded from warm-tier injection: session summaries are already in the hot tier,
# and sweep reports are operational noise with no user-knowledge value.
# All ops/ content is operational Sentinel state (sessions, sweeps, observations, reminders).
# self/ is already injected by the hot tier. _trash/ is archived files.
# None of these belong in warm-tier knowledge retrieval.
_WARM_TIER_EXCLUDE_PREFIXES = ("ops/", "_trash/", "self/")

# Common English function words stripped before keyword-mode vault search.
# Obsidian /search/simple/ is conjunctive: every term must appear in the document.
# For long conversational queries (>5 words) this kills recall — session summaries
# (which contain the verbatim question) score higher than the actual knowledge notes.
# We instead search with each content keyword in parallel, then merge by filename.
_SEARCH_STOPWORDS = frozenset(
    "a about all also an and any are as at be been by can could "
    "did do does for from get go had has have he her here his how "
    "i if in is it its just let may me might more my no not of or "
    "our out see she should so some than that the their then there "
    "they this to up us was we were what when where which who will "
    "with would you your".split()
)

# Queries longer than this many words switch to per-keyword parallel search.
_KEYWORD_SEARCH_THRESHOLD = 5


def _extract_keywords(content: str) -> list[str]:
    """Return deduplicated non-stopword tokens from content, preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for word in content.lower().split():
        token = word.strip(".,!?;:\"'")
        if token and token not in _SEARCH_STOPWORDS and token not in seen:
            seen.add(token)
            result.append(token)
    return result


def _best_search_query(content: str) -> str:
    """Extract the longest run of consecutive non-stopword words from content.

    Obsidian /search/simple/ is conjunctive: every term must appear in the result.
    A run of adjacent content words (e.g. "omie wise synthwave" from "what do you
    know about the omie wise synthwave") forms a specific AND-query that matches the
    target note without admitting generic matches from single function words.
    Falls back to the full content string if no run is found.
    """
    words = content.lower().split()
    tokens = [w.strip(".,!?;:\"'") for w in words]
    indexed = [(i, t) for i, t in enumerate(tokens) if t and t not in _SEARCH_STOPWORDS]
    if not indexed:
        return content
    runs: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = [indexed[0]]
    for prev, curr in zip(indexed, indexed[1:]):
        if curr[0] == prev[0] + 1:
            current.append(curr)
        else:
            runs.append(current)
            current = [curr]
    runs.append(current)
    best = max(runs, key=len)
    return " ".join(t for _, t in best)


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ContextBudget:
    sessions_budget: int
    search_budget: int


@dataclass(frozen=True)
class SearchResult:
    """A single warm-tier search result with its vault path, relevance score, and body."""

    path: str
    score: float
    body: str


@dataclass(frozen=True)
class RecalledContext:
    """Pure value type returned by ``Recall.assemble()``.

    Never contains chat messages or presentation-layer text.
    ``MessageProcessor`` is responsible for formatting and injecting these into
    the message list (D-04).
    """

    self_context: list[str]
    """Raw markdown strings from the self-paths allowlist (non-empty only)."""

    sessions: list[str]
    """Raw markdown strings from ``get_recent_sessions`` (most-recent first)."""

    warm: list[SearchResult]
    """Warm-tier search results filtered by threshold and namespace exclusions."""


@dataclass(frozen=True)
class RecallConfig:
    """Recall policy configuration.

    All constants that were previously inlined in ``message_processing.py``
    are consolidated here (MEM-02). Default values reproduce existing behavior
    exactly.
    """

    relevance_threshold: float = -200.0
    """BM25 score floor; results below this are excluded from warm tier."""

    exclude_prefixes: tuple[str, ...] = ("ops/", "_trash/", "self/")
    """Warm-tier namespace exclusion list. Passed directly to ``str.startswith``."""

    sessions_ratio: float = 0.15
    """Fraction of the total context budget reserved for session summaries."""

    search_ratio: float = 0.10
    """Fraction of the total context budget reserved for warm-tier results."""

    recent_session_limit: int = 3
    """Maximum number of recent session notes to fetch via ``get_recent_sessions``."""

    self_paths: list[str] = field(
        default_factory=lambda: [
            "self/identity.md",
            "self/methodology.md",
            "self/goals.md",
            "self/relationships.md",
            "ops/reminders.md",       # NOTE: intentionally in self_paths even though
            "self/learning-areas.md", # ops/ is in exclude_prefixes — the exclusion
        ]                             # applies only to warm search, never to self_paths.
    )
    """Explicit allowlist of self-context paths for the hot tier.

    ``ops/reminders.md`` is included here deliberately (D-02, Pitfall 2):
    reminders are hot-tier self-context, not warm-tier search results.
    The ``ops/`` entry in ``exclude_prefixes`` blocks ops/ from warm search
    but never applies to this list.
    """

    warm_top_n: int = 3
    """Maximum number of warm-tier results to read and return."""


__all__ = [
    "Recall",
    "RecallConfig",
    "RecalledContext",
    "SearchResult",
    "SEARCH_SCORE_THRESHOLD",
]


# ---------------------------------------------------------------------------
# Recall class
# ---------------------------------------------------------------------------


class Recall:
    """Hot-tier and warm-tier retrieval policy.

    ``assemble(request, budget)`` gathers self-context, recent sessions, and
    warm-tier vault search results into a ``RecalledContext`` value.

    The system identity file is NOT read here — it stays in ``MessageProcessor``
    as a presentation concern (D-04).
    """

    def __init__(self, vault: "Vault", *, config: RecallConfig | None = None) -> None:
        self._vault = vault
        self._config = config or RecallConfig()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def allocate(self, budget: int) -> _ContextBudget:
        """Compute per-tier context budgets using int() truncation (Pitfall 3)."""
        return _ContextBudget(
            sessions_budget=int(budget * self._config.sessions_ratio),
            search_budget=int(budget * self._config.search_ratio),
        )

    async def _hot_self(self) -> list[str]:
        """Read the 6 self-context paths in parallel; return non-empty strings only.

        Reads exactly ``self._config.self_paths`` (the 6-item allowlist).
        The system identity file (``sentinel/*.md``) is NOT in self_paths and
        is NOT read here — that stays in ``MessageProcessor`` per D-04.
        """
        self_results = await asyncio.gather(
            *[self._vault.read_self_context(p) for p in self._config.self_paths],
            return_exceptions=True,
        )
        return [r for r in self_results if isinstance(r, str) and r.strip()]

    async def _hot_sessions(self, user_id: str) -> list[str]:
        """Fetch recent session summaries for the given user."""
        return await self._vault.get_recent_sessions(
            user_id, limit=self._config.recent_session_limit
        )

    async def _warm_search(self, content: str) -> list[SearchResult]:
        """Search the vault for warm-tier context relevant to ``content``.

        Returns ``[]`` immediately when content is empty — avoids calling
        vault.find() with an empty query (Pitfall 8, Option A).

        Raw Vault dicts are translated to ``SearchResult`` at this boundary;
        they never leak past this method.
        """
        if not content.strip():
            return []

        words = content.split()
        if len(words) > _KEYWORD_SEARCH_THRESHOLD:
            query = _best_search_query(content)
        else:
            query = content

        search_results = await self._vault.find(query)

        relevant = [
            r for r in search_results
            if r.get("score", float("-inf")) >= self._config.relevance_threshold
            and not r.get("filename", "").startswith(self._config.exclude_prefixes)
        ]
        if not relevant:
            return []

        top = relevant[: self._config.warm_top_n]
        paths = [r.get("filename", "") for r in top]
        raw_contents = await asyncio.gather(
            *[self._vault.read_note(p) for p in paths],
            return_exceptions=True,
        )

        results: list[SearchResult] = []
        for r, path, body in zip(top, paths, raw_contents):
            if isinstance(body, str) and body.strip():
                note_body = body
            else:
                # Full note read failed — fall back to search snippet
                matches = r.get("matches", [])
                note_body = matches[0].get("context", "").strip() if matches else ""
            results.append(
                SearchResult(
                    path=r["filename"],
                    score=r["score"],
                    body=note_body,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def assemble(self, request: "MessageRequest", budget: int) -> RecalledContext:
        """Assemble recalled memory for the given request.

        Gathers hot-tier self-context, hot-tier session summaries, and
        warm-tier search results concurrently.

        The ``budget`` parameter is accepted for interface stability (D-03).
        Per-tier truncation is the responsibility of ``MessageProcessor``
        (D-04); ``assemble`` returns untruncated content.
        """
        self_context, sessions, warm = await asyncio.gather(
            self._hot_self(),
            self._hot_sessions(request.user_id),
            self._warm_search(request.content),
        )
        return RecalledContext(
            self_context=self_context,
            sessions=sessions,
            warm=warm,
        )
