"""Transport-neutral message processing module."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.errors import (
    ContextLengthError,
    MessageProcessingError,
    ProviderUnavailableError,
)
from app.services.token_budget import TokenBudget, TokenLimitError

if TYPE_CHECKING:
    from app.services.recall import Recall, RecalledContext, SearchResult

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        vault,
        ai_provider,
        injection_filter,
        output_scanner,
        *,
        recall: "Recall | None" = None,
    ) -> None:
        self._vault = vault
        self._ai_provider = ai_provider
        self._injection_filter = injection_filter
        self._output_scanner = output_scanner
        self._budget = TokenBudget()
        if recall is not None:
            self._recall = recall
        else:
            # Late import to avoid circular import at module load time.
            # (recall.py imports MessageRequest from this module at module level.)
            from app.services.recall import Recall  # noqa: PLC0415
            self._recall = Recall(vault=vault)

    async def process(self, req: MessageRequest) -> MessageResult:
        # Delegate hot+warm assembly to Recall (MEM-01).
        recalled = await self._recall.assemble(req, req.context_window)

        # Per-tier budgets — sourced from Recall's allocator so the ratio
        # constants live only in RecallConfig (MEM-02).
        budgets = self._recall.allocate(req.context_window)
        sessions_budget = budgets.sessions_budget
        search_budget = budgets.search_budget

        # Start with fallback persona as messages[0]; swap if vault persona is non-empty.
        messages: list[dict] = [{"role": "system", "content": self._FALLBACK_PERSONA}]

        # Persona swap (D-04, Pitfall 1) — stays in MessageProcessor.
        persona_result = await self._vault.read_self_context("sentinel/persona.md")
        if isinstance(persona_result, str) and persona_result.strip():
            messages[0] = {"role": "system", "content": persona_result}
        else:
            logger.warning(
                "Sentinel persona vault read returned empty; using fallback"
            )

        # Hot-tier injection (presentation, D-04).
        context_parts: list[str] = []
        if recalled.self_context:
            context_parts.append(
                "Personal context:\n" + "\n\n---\n\n".join(recalled.self_context)
            )
        if recalled.sessions:
            # Plan 41-04 bridge: recalled.sessions is now list[SessionSummary]; extract .body
            # until Plan 41-05 retypes this consumer in lockstep.
            from app.services.recall import SessionSummary as _SessionSummary
            session_bodies = [
                s.body if isinstance(s, _SessionSummary) else str(s)
                for s in recalled.sessions
            ]
            context_parts.append(
                "Recent session history:\n" + "\n---\n".join(session_bodies)
            )
        if context_parts:
            raw_context = "\n\n".join(context_parts)
            safe_context = self._budget.truncate(raw_context, sessions_budget)
            filtered_context = self._injection_filter.wrap_context(safe_context)
            messages.append({"role": "user", "content": filtered_context})
            messages.append({"role": "assistant", "content": "Understood."})

        # Warm-tier injection (presentation, D-04).
        if recalled.warm:
            vault_block = self._format_search_results(recalled.warm)
            safe_vault = self._budget.truncate(vault_block, search_budget)
            filtered_vault = self._injection_filter.wrap_context(safe_vault)
            messages.append({"role": "user", "content": filtered_vault})
            messages.append({"role": "assistant", "content": "Understood."})

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

    @staticmethod
    def _format_search_results(warm: "list[SearchResult]") -> str:
        """Format warm-tier ``SearchResult`` objects into the vault-notes block.

        Presentation stays in MessageProcessor per D-04 / Pitfall 6.
        """
        lines = ["Relevant vault notes:"]
        for r in warm:
            filename = r.path
            body = r.body
            if isinstance(body, str) and body.strip():
                lines.append(f"### {filename}\n\n{body.strip()}")
            else:
                lines.append(f"- **{filename}**")
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


# ---------------------------------------------------------------------------
# Re-export: ``SEARCH_SCORE_THRESHOLD`` moved to recall.py (MEM-02).
# Placed at the bottom to break the circular import:
#   message_processing imports MessageRequest-dependent recall.py;
#   recall.py imports MessageRequest from this module.
# By the time Python reaches this line, MessageRequest is already defined.
# ---------------------------------------------------------------------------
from app.services.recall import SEARCH_SCORE_THRESHOLD as SEARCH_SCORE_THRESHOLD  # noqa: E402
from app.services.recall import _WARM_TIER_EXCLUDE_PREFIXES as _WARM_TIER_EXCLUDE_PREFIXES  # noqa: E402
