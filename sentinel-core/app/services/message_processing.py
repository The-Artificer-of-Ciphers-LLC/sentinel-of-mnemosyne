"""Transport-neutral message processing module."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import tiktoken
from litellm import BadRequestError as LiteLLMBadRequestError

from app.services.provider_router import ProviderUnavailableError
from app.services.token_guard import TokenLimitError, check_token_limit

logger = logging.getLogger(__name__)

SEARCH_SCORE_THRESHOLD = 0.5

_CONTEXT_LENGTH_MARKERS: tuple[str, ...] = (
    "context length",
    "context_length",
    "maximum context",
    "context window",
    "too many tokens",
    "tokens. however",
    "reduce the length",
    "prompt is too long",
)


@dataclass(frozen=True)
class _ContextBudget:
    sessions_budget: int
    search_budget: int


class MessageProcessingError(Exception):
    code: str

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


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

    def __init__(self, obsidian, ai_provider, injection_filter, output_scanner) -> None:
        self._obsidian = obsidian
        self._ai_provider = ai_provider
        self._injection_filter = injection_filter
        self._output_scanner = output_scanner

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
            check_token_limit(messages, req.context_window)
        except TokenLimitError as exc:
            raise MessageProcessingError("context_overflow", str(exc)) from exc

        try:
            content = await self._ai_provider.complete(messages)
        except ProviderUnavailableError as exc:
            raise MessageProcessingError("provider_unavailable", str(exc)) from exc
        except LiteLLMBadRequestError as exc:
            if self._is_context_length_error(exc):
                raise MessageProcessingError(
                    "context_overflow",
                    "Message plus context exceeds model capacity. Try a shorter message.",
                ) from exc
            raise MessageProcessingError(
                "provider_misconfigured",
                "AI provider configuration error. Check sentinel-core logs.",
            ) from exc
        except Exception as exc:
            raise MessageProcessingError(
                "provider_misconfigured", f"AI provider error: {type(exc).__name__}"
            ) from exc

        is_safe, _reason = await self._output_scanner.scan(content)
        if not is_safe:
            raise MessageProcessingError("security_blocked", "Response blocked by security scanner")

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
        ]
        self_results = await asyncio.gather(
            *[self._obsidian.read_self_context(p) for p in self_paths],
            return_exceptions=True,
        )
        self_contents = [r for r in self_results if isinstance(r, str) and r.strip()]
        recent_sessions = await self._obsidian.get_recent_sessions(req.user_id, limit=3)

        context_parts: list[str] = []
        if self_contents:
            context_parts.append("Personal context:\n" + "\n\n---\n\n".join(self_contents))
        if recent_sessions:
            context_parts.append("Recent session history:\n" + "\n---\n".join(recent_sessions))
        if not context_parts:
            return

        raw_context = "\n\n".join(context_parts)
        safe_context = self._truncate_to_tokens(raw_context, budget)
        filtered_context = self._injection_filter.wrap_context(safe_context)
        messages.append({"role": "user", "content": filtered_context})
        messages.append({"role": "assistant", "content": "Understood."})

    async def _append_warm_tier(self, messages: list[dict], req: MessageRequest, budget: int) -> None:
        search_results = await self._obsidian.search_vault(req.content)
        relevant_results = [r for r in search_results if r.get("score", 0.0) >= SEARCH_SCORE_THRESHOLD]
        if not relevant_results:
            return

        vault_block = self._format_search_results(relevant_results[:3])
        safe_vault = self._truncate_to_tokens(vault_block, budget)
        filtered_vault = self._injection_filter.wrap_context(safe_vault)
        messages.append({"role": "user", "content": filtered_vault})
        messages.append({"role": "assistant", "content": "Understood."})

    @staticmethod
    def _truncate_to_tokens(text: str, max_tokens: int) -> str:
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return enc.decode(tokens[:max_tokens]) + "\n\n[...context truncated to fit token budget]"

    @staticmethod
    def _format_search_results(results: list[dict]) -> str:
        lines = ["Relevant vault notes:"]
        for r in results:
            filename = r.get("filename", "unknown")
            matches = r.get("matches", [])
            snippet = matches[0].get("context", "").strip() if matches else ""
            lines.append(f"- **{filename}**: {snippet}" if snippet else f"- **{filename}**")
        return "\n".join(lines)

    @staticmethod
    def _is_context_length_error(exc: BaseException) -> bool:
        msg = str(exc).lower()
        return any(marker in msg for marker in _CONTEXT_LENGTH_MARKERS)

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
