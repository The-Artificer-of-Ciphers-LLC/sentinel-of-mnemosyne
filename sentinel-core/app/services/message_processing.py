"""Transport-neutral message processing module."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.errors import (
    ContextLengthError,
    MessageProcessingError,
    ProviderUnavailableError,
)
from app.services.token_budget import TokenBudget, TokenLimitError


logger = logging.getLogger(__name__)

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


@dataclass(frozen=True)
class _ContextBudget:
    sessions_budget: int
    search_budget: int





@dataclass(frozen=True)
class MessageRequest:
    content: str
    user_id: str
    model_name: str
    context_window: int
    stop_sequences: list[str] | None


@dataclass(frozen=True)
class MessageResult:
    content: str
    model: str
    summary_path: str
    summary_content: str


class MessageProcessor:
    _FALLBACK_PERSONA: str = (
        "You are the Sentinel — the user's 2nd brain. "
        "You maintain their context via an Obsidian vault that the system "
        "writes to automatically; the user does not need to manage it. "
        "\n\n"
        "Respond like a friend who has been listening. When the user shares "
        "a fact, milestone, status update, or reflection, acknowledge it "
        "naturally and briefly — usually one or two sentences. Ask a relevant "
        "follow-up only if it would feel natural. Match their tone and length.\n\n"
        "Never lecture the user about how to file, organize, link, tag, "
        "document, summarize, follow up on, plan, or process information. "
        "The system handles persistence and structure. You only respond. "
        "Do not produce numbered procedural how-to lists unless the user "
        "explicitly asks for instructions.\n\n"
        "Do not describe internal tools, system internals, or implementation details."
    )

    _SESSIONS_RATIO: float = 0.15
    _SEARCH_RATIO: float = 0.10

    def __init__(self, vault, ai_provider, injection_filter, output_scanner) -> None:
        self._vault = vault
        self._ai_provider = ai_provider
        self._injection_filter = injection_filter
        self._output_scanner = output_scanner
        self._budget = TokenBudget()

    @classmethod
    def _allocate_budgets(cls, context_window: int) -> _ContextBudget:
        return _ContextBudget(
            sessions_budget=int(context_window * cls._SESSIONS_RATIO),
            search_budget=int(context_window * cls._SEARCH_RATIO),
        )

    async def process(self, req: MessageRequest) -> MessageResult:
        budgets = self._allocate_budgets(req.context_window)
        messages = [{"role": "system", "content": self._FALLBACK_PERSONA}]

        await self._append_hot_tier(messages, req, budgets.sessions_budget)
        await self._append_warm_tier(messages, req, budgets.search_budget)

        safe_input, _ = self._injection_filter.filter_input(req.content)
        messages.append({"role": "user", "content": safe_input})

        try:
            self._budget.check(messages, req.context_window)
        except TokenLimitError as exc:
            raise MessageProcessingError("context_overflow", str(exc)) from exc

        try:
            content = await self._ai_provider.complete(messages)
        except ProviderUnavailableError as exc:
            raise MessageProcessingError("provider_unavailable", str(exc)) from exc
        except ContextLengthError as exc:
            raise MessageProcessingError("context_overflow", str(exc)) from exc
        except Exception as exc:
            raise MessageProcessingError(
                "provider_misconfigured", f"AI provider error: {type(exc).__name__}"
            ) from exc

        is_safe, _reason = await self._output_scanner.scan(content)
        if not is_safe:
            raise MessageProcessingError(
                "security_blocked", "Response blocked by security scanner"
            )

        summary_path, summary_content = self._build_session_summary(
            req.user_id,
            req.content,
            content,
            req.model_name,
        )
        return MessageResult(
            content=content,
            model=req.model_name,
            summary_path=summary_path,
            summary_content=summary_content,
        )

    async def _append_hot_tier(self, messages: list[dict], req: MessageRequest, budget: int) -> None:
        self_paths = [
            "self/identity.md",
            "self/methodology.md",
            "self/goals.md",
            "self/relationships.md",
            "ops/reminders.md",
            "self/learning-areas.md",
        ]
        gather_results = await asyncio.gather(
            *[self._vault.read_self_context(p) for p in self_paths],
            self._vault.read_self_context("sentinel/persona.md"),
            return_exceptions=True,
        )
        self_results = gather_results[: len(self_paths)]
        persona_result = gather_results[-1]

        if isinstance(persona_result, str) and persona_result.strip():
            messages[0] = {"role": "system", "content": persona_result}
        else:
            logger.warning(
                "Sentinel persona vault read returned empty; using fallback"
            )

        self_contents = [r for r in self_results if isinstance(r, str) and r.strip()]
        recent_sessions = await self._vault.get_recent_sessions(req.user_id, limit=3)

        context_parts: list[str] = []
        if self_contents:
            context_parts.append("Personal context:\n" + "\n\n---\n\n".join(self_contents))
        if recent_sessions:
            context_parts.append("Recent session history:\n" + "\n---\n".join(recent_sessions))
        if not context_parts:
            return

        raw_context = "\n\n".join(context_parts)
        safe_context = self._budget.truncate(raw_context, budget)
        filtered_context = self._injection_filter.wrap_context(safe_context)
        messages.append({"role": "user", "content": filtered_context})
        messages.append({"role": "assistant", "content": "Understood."})

    async def _append_warm_tier(self, messages: list[dict], req: MessageRequest, budget: int) -> None:
        words = req.content.split()
        if len(words) > _KEYWORD_SEARCH_THRESHOLD:
            query = _best_search_query(req.content)
            search_results = await self._vault.find(query)
        else:
            search_results = await self._vault.find(req.content)

        relevant_results = [
            r for r in search_results
            if r.get("score", float("-inf")) >= SEARCH_SCORE_THRESHOLD
            and not r.get("filename", "").startswith(_WARM_TIER_EXCLUDE_PREFIXES)
        ]
        if not relevant_results:
            return

        top_results = relevant_results[:3]
        paths = [r.get("filename", "") for r in top_results]
        raw_contents = await asyncio.gather(
            *[self._vault.read_note(p) for p in paths],
            return_exceptions=True,
        )

        vault_block = self._format_search_results(top_results, paths, raw_contents)
        safe_vault = self._budget.truncate(vault_block, budget)
        filtered_vault = self._injection_filter.wrap_context(safe_vault)
        messages.append({"role": "user", "content": filtered_vault})
        messages.append({"role": "assistant", "content": "Understood."})

    @staticmethod
    def _format_search_results(
        results: list[dict], paths: list[str], contents: list
    ) -> str:
        lines = ["Relevant vault notes:"]
        for r, path, content in zip(results, paths, contents):
            filename = r.get("filename", path or "unknown")
            if isinstance(content, str) and content.strip():
                lines.append(f"### {filename}\n\n{content.strip()}")
            else:
                # full read failed — fall back to search snippet
                matches = r.get("matches", [])
                snippet = matches[0].get("context", "").strip() if matches else ""
                lines.append(f"- **{filename}**: {snippet}" if snippet else f"- **{filename}**")
        return "\n\n".join(lines)

    @staticmethod
    def _build_session_summary(
        user_id: str, user_msg: str, ai_msg: str, model: str
    ) -> tuple[str, str]:
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H-%M-%S")
        path = f"ops/sessions/{date_str}/{user_id}-{time_str}.md"
        content = f"""---
timestamp: {now.isoformat()}
user_id: {user_id}
model: {model}
---

## User

{user_msg}

## Sentinel

{ai_msg}
"""
        return path, content
