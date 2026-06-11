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
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Awaitable, Callable, Protocol, runtime_checkable

import numpy as np

from sentinel_shared.embedding_codec import decode_embedding
from sentinel_shared.similarity import cosine_similarity

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

    semantic_cosine_floor: float = 0.50
    """Minimum cosine similarity for a semantic candidate to enter the RRF pool.
    Conservative 0.50 default per RESEARCH Pattern 7 — UAT-tunable."""

    semantic_top_k: int = 20
    """Number of top semantic candidates sent into RRF per D-10."""

    keyword_top_k: int = 20
    """Number of top keyword candidates sent into RRF per D-10."""

    rrf_k: int = 60
    """RRF k constant (smoothing factor). k=60 is the empirically validated default."""

    semantic_lru_size: int = 128
    """Max number of query embeddings cached in-process (keyed on query+model)."""

    index_path: str = "ops/sweeps/embedding-index.json"
    """Relative path (vault-seam key) for the sweeper-maintained embedding index sidecar.
    Must equal EMBEDDING_INDEX_PATH in vault_sweeper.py."""

    index_ttl_seconds: float = 60.0
    """TTL for the in-memory index cache (seconds). After expiry, SemanticRecall
    reloads the index via vault.read_note() on the next search call."""


__all__ = [
    "Recall",
    "RecallConfig",
    "RecalledContext",
    "RetrievalStrategy",
    "KeywordRecall",
    "SemanticRecall",
    "SearchResult",
    "SEARCH_SCORE_THRESHOLD",
    "NOMIC_QUERY_PREFIX",
]

# Nomic-embed-text-v1.5 instruction prefix for query embeddings.
# Mirrors NOMIC_DOCUMENT_PREFIX in vault_sweeper.py (which prefixes note bodies).
NOMIC_QUERY_PREFIX = "search_query: "


# ---------------------------------------------------------------------------
# RetrievalStrategy Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class RetrievalStrategy(Protocol):
    """Strategy seam for warm-tier retrieval (ADR-0004).

    Both adapters (KeywordRecall, SemanticRecall) satisfy this Protocol.
    async search(query, *, budget) -> list[SearchResult]

    ``budget`` is the maximum number of candidates the strategy should return
    before RRF merging. Strategies apply their own relevance thresholds first;
    the budget is an additional hard cap on the returned list length.
    """

    async def search(self, query: str, *, budget: int) -> list[SearchResult]: ...


# ---------------------------------------------------------------------------
# KeywordRecall adapter — verbatim lift of _warm_search keyword logic
# ---------------------------------------------------------------------------


class KeywordRecall:
    """Keyword retrieval adapter wrapping vault.find() (Obsidian BM25).

    Provides the same behavior as the original Recall._warm_search keyword
    path: _best_search_query extraction, relevance_threshold filter,
    exclude_prefixes filter, WR-01 empty-body skip, SearchResult construction.

    The only behavioral difference from the original _warm_search:
    - ``budget`` (from the RetrievalStrategy interface) replaces ``warm_top_n``
      for the candidate slice — callers (Recall._warm_search RRF orchestrator)
      pass ``keyword_top_k`` as budget.
    """

    def __init__(self, vault: "Vault", config: RecallConfig) -> None:
        self._vault = vault
        self._config = config

    async def search(self, query: str, *, budget: int) -> list[SearchResult]:
        """Keyword search via vault.find() — today's _warm_search behavior, verbatim.

        Returns [] when query is blank (WR-01 guard moved to _warm_search orchestrator).
        Slices to ``budget`` instead of ``warm_top_n`` so the RRF pool size is
        controlled by the caller.
        """
        words = query.split()
        if len(words) > _KEYWORD_SEARCH_THRESHOLD:
            search_q = _best_search_query(query)
        else:
            search_q = query

        search_results = await self._vault.find(search_q)

        relevant = [
            r for r in search_results
            if r.get("score", float("-inf")) >= self._config.relevance_threshold
            and not r.get("filename", "").startswith(self._config.exclude_prefixes)
        ]
        if not relevant:
            return []

        top = relevant[:budget]
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
                matches = r.get("matches", [])
                note_body = matches[0].get("context", "").strip() if matches else ""
            if not note_body.strip():
                # WR-01: skip contentless notes
                continue
            results.append(SearchResult(path=r["filename"], score=r["score"], body=note_body))
        return results


# ---------------------------------------------------------------------------
# SemanticRecall adapter — cosine search over TTL-cached embedding sidecar
# ---------------------------------------------------------------------------


class SemanticRecall:
    """Semantic retrieval adapter over the sweeper-maintained embedding sidecar.

    Reads ``ops/sweeps/embedding-index.json`` once via vault.read_note() and
    caches it in memory for ``config.index_ttl_seconds``. Never calls vault.find()
    or performs per-note REST reads at query time (MEM-05, D-09 REVISED, D-01).

    Model-mismatch entries (embedding_model != active_model) are skipped per
    D-12/D-13. All-mismatch degrades to [] with a WARNING (D-14). Blank query
    returns [] without calling embed_fn (D-16).

    Bodies are returned as empty strings; Recall._warm_search reads real bodies
    for post-RRF survivors (Open Question 3 / A5 — cheaper: 3 reads vs 20).
    """

    def __init__(
        self,
        vault: "Vault",
        *,
        embed_fn: Callable[[list[str]], Awaitable[list[list[float]]]],
        active_model: str,
        config: RecallConfig,
    ) -> None:
        self._vault = vault
        self._embed_fn = embed_fn
        self._active_model = active_model  # exact string, no "openai/" prefix (D-12)
        self._config = config
        # In-memory TTL cache for the index
        self._index: dict[str, dict] = {}
        self._index_loaded_at: float = 0.0  # monotonic timestamp of last load
        # Bounded dict cache for query vectors, keyed on (query_text, active_model)
        self._vec_cache: dict[tuple[str, str], list[float]] = {}

    async def _load_index_if_stale(self) -> None:
        """Reload the embedding index via vault.read_note() if the TTL has expired.

        Uses monotonic clock for the TTL check (immune to wall-clock drift).
        On any JSON parse failure, self._index is reset to {} (T-40-05 Tampering mitigation).
        """
        now = time.monotonic()
        if now - self._index_loaded_at <= self._config.index_ttl_seconds:
            return  # cache is fresh
        try:
            raw = await self._vault.read_note(self._config.index_path)
            self._index = json.loads(raw) if raw and raw.strip() else {}
        except Exception as exc:
            logger.warning("SemanticRecall: failed to load index at %r: %r", self._config.index_path, exc)
            self._index = {}
        self._index_loaded_at = time.monotonic()

    async def _get_query_vec(self, query: str) -> list[float] | None:
        """Embed query with nomic search_query: prefix; use bounded dict cache.

        Returns None on embed_fn failure (WR-03) or if embed_fn returns empty result.
        """
        key = (query, self._active_model)
        if key in self._vec_cache:
            return self._vec_cache[key]

        prefixed = f"{NOMIC_QUERY_PREFIX}{query}"
        try:
            vecs = await self._embed_fn([prefixed])
            vec = vecs[0] if vecs else []
        except Exception as exc:
            logger.warning("SemanticRecall: embed_fn failed: %r", exc)
            return None

        if not vec:
            return None

        # Bounded FIFO eviction when cache is full (Pitfall 9)
        if len(self._vec_cache) >= self._config.semantic_lru_size:
            oldest_key = next(iter(self._vec_cache))
            del self._vec_cache[oldest_key]

        self._vec_cache[key] = vec
        return vec

    async def search(self, query: str, *, budget: int) -> list[SearchResult]:
        """Cosine search over in-memory index.

        Returns [] on blank query, empty/absent index, embed failure, or
        all-mismatch model (D-14 silent degrade). Bodies are always empty
        strings — Recall reads them after RRF trim (A5).
        """
        # D-16: blank query early exit — do NOT call embed_fn
        if not query.strip():
            return []

        await self._load_index_if_stale()

        if not self._index:
            logger.warning(
                "SemanticRecall: index is empty or absent at %r", self._config.index_path
            )
            return []

        query_vec = await self._get_query_vec(query)
        if query_vec is None:
            return []

        qv = np.asarray(query_vec, dtype=np.float32)

        candidates: list[tuple[float, str]] = []  # (cosine, path)
        matched_model_count = 0

        for path, entry in self._index.items():
            # T-40-07: apply exclude_prefixes fence (same as KeywordRecall)
            if path.startswith(self._config.exclude_prefixes):
                continue

            em = entry.get("embedding_model", "")
            if not em or em != self._active_model:
                # D-12/D-13: exact-string mismatch or missing → skip
                continue
            matched_model_count += 1

            raw = decode_embedding(entry.get("embedding_b64", ""))
            if not raw:
                # Pitfall 4: zero-length embedding → skip (T-40-06)
                logger.warning("SemanticRecall: zero-length embedding for %r, skipping", path)
                continue

            nv = np.asarray(raw, dtype=np.float32)
            sim = float(cosine_similarity(qv, nv))

            if sim < self._config.semantic_cosine_floor:
                # D-11: cosine floor gates weak candidates before RRF
                continue

            candidates.append((sim, path))

        if matched_model_count == 0 and self._index:
            # D-14: all-mismatch silent degrade — keyword-only via WR-03 path
            logger.warning(
                "SemanticRecall: all %d index entries mismatch active model %r"
                " — degrading to keyword-only",
                len(self._index),
                self._active_model,
            )
            return []

        # Sort by cosine desc, tie-break on path for determinism
        candidates.sort(key=lambda t: (-t[0], t[1]))
        top = candidates[:budget]

        # Return stub SearchResults with body="" — Recall reads bodies post-RRF (A5)
        return [SearchResult(path=path, score=sim, body="") for sim, path in top]


# ---------------------------------------------------------------------------
# _rrf_merge helper — Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


def _rrf_merge(
    lists: list[list[SearchResult]],
    *,
    k: int = 60,
    top_n: int = 3,
) -> list[SearchResult]:
    """Reciprocal Rank Fusion over multiple SearchResult lists.

    Each list contributes 1/(k + rank_1based) to each path's cumulative score.
    Paths in only one list still get scored from that list.
    Final list is sorted descending by RRF score (tie-break on path for
    determinism), trimmed to top_n.

    The returned SearchResult.score is the RRF score — not BM25 or cosine.
    Downstream consumers (MessageProcessor) only use .body, so this is safe.
    """
    scores: dict[str, float] = {}
    bodies: dict[str, str] = {}

    for ranked_list in lists:
        for rank_0, result in enumerate(ranked_list):
            rank_1 = rank_0 + 1  # 1-based rank per RRF formula
            scores[result.path] = scores.get(result.path, 0.0) + 1.0 / (k + rank_1)
            bodies.setdefault(result.path, result.body)  # keep first body seen

    # Sort by RRF score desc; secondary sort on path for determinism
    fused = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))

    return [
        SearchResult(path=path, score=rrf_score, body=bodies[path])
        for path, rrf_score in fused[:top_n]
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

    def __init__(
        self,
        vault: "Vault",
        *,
        config: RecallConfig | None = None,
        keyword_strategy: "RetrievalStrategy | None" = None,
        semantic_strategy: "RetrievalStrategy | None" = None,
    ) -> None:
        self._vault = vault
        self._config = config or RecallConfig()
        # Default keyword strategy = KeywordRecall wrapping this vault+config
        self._keyword_strategy: RetrievalStrategy = (
            keyword_strategy or KeywordRecall(vault, self._config)
        )
        # semantic_strategy=None means keyword-only graceful mode (D-14 / D-17)
        self._semantic_strategy: RetrievalStrategy | None = semantic_strategy

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
        """RRF orchestrator: gather keyword + semantic results, merge, read bodies.

        Returns ``[]`` immediately when content is empty (Pitfall 8, Option A).

        Algorithm (MEM-04, D-17):
        1. Run keyword and semantic strategies concurrently (asyncio.gather).
        2. Coerce any BaseException result to [] with a WARNING (WR-03 reuse).
        3. Merge via Reciprocal Rank Fusion (k=rrf_k) → trim to warm_top_n.
        4. Read note bodies for the post-RRF survivors only (≤ warm_top_n reads).
        5. Apply WR-01 empty-body skip on the final body reads.

        When semantic_strategy is None, only keyword results are used (graceful
        keyword-only mode, D-17). All Phase-39 behavior is preserved.
        """
        if not content.strip():
            return []

        # Build coroutines for concurrent execution
        kw_coro = self._keyword_strategy.search(content, budget=self._config.keyword_top_k)

        if self._semantic_strategy is not None:
            sem_coro = self._semantic_strategy.search(content, budget=self._config.semantic_top_k)
            raw_kw, raw_sem = await asyncio.gather(kw_coro, sem_coro, return_exceptions=True)
        else:
            raw_kw = await asyncio.gather(kw_coro, return_exceptions=True)
            raw_kw = raw_kw[0]
            raw_sem = []

        # Coerce exceptions to [] — WR-03 graceful degradation pattern (reused)
        lists: list[list[SearchResult]] = []
        for raw in (raw_kw, raw_sem):
            if isinstance(raw, BaseException):
                logger.warning("retrieval strategy failed: %r", raw)
                lists.append([])
            else:
                lists.append(raw)

        # RRF merge → trim to warm_top_n (stub bodies only at this point)
        merged = _rrf_merge(lists, k=self._config.rrf_k, top_n=self._config.warm_top_n)

        if not merged:
            return []

        # Read real bodies for the post-RRF survivors (A5: ≤ warm_top_n reads)
        survivor_paths = [r.path for r in merged]
        raw_bodies = await asyncio.gather(
            *[self._vault.read_note(p) for p in survivor_paths],
            return_exceptions=True,
        )

        results: list[SearchResult] = []
        for survivor, path, body in zip(merged, survivor_paths, raw_bodies):
            if isinstance(body, str) and body.strip():
                note_body = body
            else:
                # Full note read failed — body stub (no snippet available post-RRF)
                note_body = survivor.body  # may be "" from SemanticRecall stub
            if not note_body.strip():
                # WR-01: skip contentless notes — do not surface empty-body SearchResults
                continue
            results.append(SearchResult(path=path, score=survivor.score, body=note_body))

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
        _self_raw, _sessions_raw, _warm_raw = await asyncio.gather(
            self._hot_self(),
            self._hot_sessions(request.user_id),
            self._warm_search(request.content),
            return_exceptions=True,
        )

        if isinstance(_self_raw, BaseException):
            logger.warning("recall tier failed: %r", _self_raw)
            self_context: list[str] = []
        else:
            self_context = _self_raw

        if isinstance(_sessions_raw, BaseException):
            logger.warning("recall tier failed: %r", _sessions_raw)
            sessions: list[str] = []
        else:
            sessions = _sessions_raw

        if isinstance(_warm_raw, BaseException):
            logger.warning("recall tier failed: %r", _warm_raw)
            warm: list[SearchResult] = []
        else:
            warm = _warm_raw

        return RecalledContext(
            self_context=self_context,
            sessions=sessions,
            warm=warm,
        )
