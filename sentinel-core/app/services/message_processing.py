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
from app.model import ModelProfile
from app.services.response_anomaly import EXCERPT_MAX_CHARS, detect_anomalies
from app.services.token_budget import DEFAULT_ENCODING, TokenBudget, TokenLimitError

if TYPE_CHECKING:
    from app.model import ActiveModel
    from app.services.recall import Recall, RecalledContext, SearchResult

logger = logging.getLogger(__name__)

#: The error code a resolution failure surfaces under. Deliberately distinct
#: from ``provider_unavailable``: the backend is not down, it is ambiguous or
#: misconfigured, and conflating the two would tell an operator to check the
#: wrong thing. ``map_message_exception`` maps unrecognised codes to 502.
MODEL_UNRESOLVED_CODE = "model_unresolved"

#: What the caller is told when resolution fails. Deliberately free of model ids
#: and api_base values — the same leak rule POST /provider/complete follows
#: (T-42-08). The detail is logged server-side instead.
_MODEL_UNRESOLVED_DETAIL = (
    "Could not determine which model to use. See the server log for detail."
)


@dataclass(frozen=True)
class MessageRequest:
    """The transport input. Carries no model facts beyond a recorded name.

    ``context_window`` and ``stop_sequences`` used to ride along here, copied
    off ``RouteContext``'s startup-pinned scalars; ADR-0007 step 4 removed both.
    The processor resolves a :class:`~app.model.ModelProfile` per request and
    budgets against THAT window, so a request cannot carry a stale one.

    ``model_name`` survives for a different reason: it is what gets RECORDED
    (session-summary frontmatter, the response-anomaly log) when no seam is
    wired, and the factory fills it from the seam's cached profile when one is.
    """

    content: str
    user_id: str
    model_name: str


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
        active_model: "ActiveModel | None" = None,
    ) -> None:
        self._vault = vault
        self._ai_provider = ai_provider
        self._injection_filter = injection_filter
        self._output_scanner = output_scanner
        # The Active model seam for the PRIMARY provider (ADR-0007). Wired only
        # when the seam describes the backend this processor's provider talks to;
        # composition leaves it None for a non-LM-Studio AI_PROVIDER, where the
        # request then falls back to the request's own scalars exactly as before.
        self._active_model = active_model
        self._budget = TokenBudget()
        # One TokenBudget per distinct encoding, memoised. Building a tiktoken
        # encoding is not free and the resolved profile is stable across
        # requests in the ordinary case, so this is a per-encoding cache rather
        # than a per-request construction.
        self._budgets: dict[str, TokenBudget] = {
            self._budget.encoding_name: self._budget
        }
        if recall is not None:
            self._recall = recall
        else:
            # Late import to avoid circular import at module load time.
            # (recall.py imports MessageRequest from this module at module level.)
            from app.services.recall import Recall  # noqa: PLC0415
            self._recall = Recall(vault=vault)

    async def _resolve_profile(self, req: MessageRequest) -> ModelProfile:
        """Ask the seam which model will answer.

        A resolution failure surfaces as a clean ``MessageProcessingError`` rather
        than an unhandled 500 — and it deliberately does NOT fall back to the
        cloud provider. ``_FALLBACK_TRIGGERS`` exists for a backend that is DOWN;
        an undisambiguatable or misconfigured local backend is neither, and
        diverting it to the paid provider would convert an operator error into a
        bill while hiding the very condition ADR decision 4's raise exists to
        announce (ADR-0007 decision 4 as amended 2026-09-08).

        A processor built with NO seam is the same refusal rather than a
        different code path. Until step 4 it could bridge from
        ``MessageRequest``'s own ``context_window`` / ``stop_sequences``; those
        scalars are gone, and inventing a declared-4096 profile in their place
        would silently truncate context on a real deployment. Composition always
        wires a seam — LM Studio's when it is primary, that provider's own
        config-derived one otherwise.
        """
        if self._active_model is None:
            logger.error(
                "MessageProcessor has no ActiveModel — cannot determine which "
                "model will answer, and will not guess a context window"
            )
            raise MessageProcessingError(
                MODEL_UNRESOLVED_CODE, _MODEL_UNRESOLVED_DETAIL
            )
        try:
            return await self._active_model.for_task("chat")
        except Exception as exc:
            logger.error(
                "Active model resolution failed on the chat path (%s: %s) — "
                "refusing the request rather than falling back to the cloud "
                "provider with an unconfirmed model",
                type(exc).__name__,
                exc,
            )
            raise MessageProcessingError(
                MODEL_UNRESOLVED_CODE, _MODEL_UNRESOLVED_DETAIL
            ) from exc

    def _budget_for(self, profile: ModelProfile) -> TokenBudget:
        """The TokenBudget for this profile's declared encoding, memoised.

        Keyed on the encoding NAME rather than the model, because two models
        counted with the same encoding want the same budget object and building
        a tiktoken encoding per request is waste. The memo is keyed on the name
        the budget ENDED UP with, so an unrecognised name that degraded to
        cl100k_base does not re-warn on every subsequent request.
        """
        requested = getattr(profile, "tokenizer_encoding", "") or DEFAULT_ENCODING
        existing = self._budgets.get(requested)
        if existing is not None:
            return existing
        budget = TokenBudget.for_profile(profile)
        # Memoise under BOTH the requested name and the effective one: the
        # requested key is what the next lookup presents, and the effective key
        # keeps a degraded budget shared with everything else using cl100k_base.
        self._budgets.setdefault(requested, budget)
        self._budgets.setdefault(budget.encoding_name, budget)
        return budget

    async def process(self, req: MessageRequest) -> MessageResult:
        # ADR-0007: one resolution per request, before any budgeting, so every
        # token count below is against the window the backend will actually
        # honour (the live box: 119552 loaded, not 262144 maximum).
        profile = await self._resolve_profile(req)
        context_window = profile.context_window
        model_name = profile.model_id or req.model_name
        # ADR-0007 step 5: count against the encoding the profile NAMES, so the
        # approximation is stated rather than assumed. An unrecognised name
        # degrades to cl100k_base with a warning inside TokenBudget; it never
        # fails the request.
        budget = self._budget_for(profile)

        # Delegate hot+warm assembly to Recall (MEM-01).
        recalled = await self._recall.assemble(req, context_window)

        # Per-tier budgets — sourced from Recall's allocator so the ratio
        # constants live only in RecallConfig (MEM-02).
        budgets = self._recall.allocate(context_window)
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
            # Plan 41-05 lockstep: recalled.sessions is list[SessionSummary]; join s.body.
            # Guard against empty-body sessions (e.g. note read returned ""):
            # mirroring the warm-tier empty-body skip to avoid stray "---" separators.
            non_empty_sessions = [s for s in recalled.sessions if s.body.strip()]
            if non_empty_sessions:
                context_parts.append(
                    "Recent session history:\n"
                    + "\n---\n".join(s.body for s in non_empty_sessions)
                )
        if context_parts:
            raw_context = "\n\n".join(context_parts)
            safe_context = budget.truncate(raw_context, sessions_budget)
            filtered_context = self._injection_filter.wrap_context(safe_context)
            messages.append({"role": "user", "content": filtered_context})
            messages.append({"role": "assistant", "content": "Understood."})

        # Inventory injection (presentation, D-04) -- meta-question about
        # vault CONTENTS ("what topics do you have?"), populated by Recall
        # only when the request matched vault_inventory.is_inventory_query.
        if recalled.inventory:
            inventory_block = (
                "Vault contents (the notes currently in the user's second brain):\n"
                + recalled.inventory
            )
            safe_inventory = budget.truncate(inventory_block, search_budget)
            filtered_inventory = self._injection_filter.wrap_context(safe_inventory)
            messages.append({"role": "user", "content": filtered_inventory})
            messages.append({"role": "assistant", "content": "Understood."})

        # Warm-tier injection (presentation, D-04).
        if recalled.warm:
            vault_block = self._format_search_results(recalled.warm)
            safe_vault = budget.truncate(vault_block, search_budget)
            filtered_vault = self._injection_filter.wrap_context(safe_vault)
            messages.append({"role": "user", "content": filtered_vault})
            messages.append({"role": "assistant", "content": "Understood."})

        safe_input, _ = self._injection_filter.filter_input(req.content)
        messages.append({"role": "user", "content": safe_input})

        try:
            budget.check(messages, context_window)
        except TokenLimitError as exc:
            raise MessageProcessingError("context_overflow", str(exc)) from exc

        try:
            # The profile carries the stop sequences now. `stop=` is still passed
            # explicitly so the 93df616 defect cannot come back by omission: that
            # bug was the chat path silently DROPPING stop sequences because the
            # Protocol did not declare the parameter, and a call site that names
            # the argument cannot drop it again.
            stop_sequences = list(profile.stop_sequences) or None
            content = await self._ai_provider.complete(
                messages, profile=profile, stop=stop_sequences
            )
        except ProviderUnavailableError as exc:
            raise MessageProcessingError("provider_unavailable", str(exc)) from exc
        except ContextLengthError as exc:
            raise MessageProcessingError("context_overflow", str(exc)) from exc
        except Exception as exc:
            raise MessageProcessingError(
                "provider_misconfigured", f"AI provider error: {type(exc).__name__}"
            ) from exc

        # Response-anomaly detection (observability only -- see
        # app/services/response_anomaly.py for the full "why"). This is
        # detection, not a gate: it must never block, alter, or retry the
        # response -- output_scanner (below) owns safety blocking. The call
        # is wrapped because an observability feature must NEVER be able to
        # take down the message path; detect_anomalies() also never raises
        # on its own, but we don't rely on that guarantee here.
        # finish_reason: the provider abstraction (ai_provider.complete)
        # only returns the completion text, not a finish_reason, so we pass
        # None rather than contorting the provider interface for this.
        try:
            anomaly = detect_anomalies(content, prompt_text=req.content, finish_reason=None)
            if anomaly.suspicious:
                excerpt = content[:EXCERPT_MAX_CHARS]
                logger.warning(
                    "response-anomaly: signals=%s model=%s content_len=%d excerpt=%r",
                    anomaly.signals,
                    model_name,
                    len(content),
                    excerpt,
                )
        except Exception:
            logger.debug("response-anomaly: detector raised; skipping", exc_info=True)

        is_safe, _reason = await self._output_scanner.scan(content)
        if not is_safe:
            raise MessageProcessingError(
                "security_blocked", "Response blocked by security scanner"
            )

        # ADR-0007 Defect B, second half: the recorded model is the one this
        # request actually resolved, not the one configuration names. The
        # message-request factory reads the seam's CACHED profile for the same
        # reason; this reads the freshly resolved one, which is strictly closer
        # to "what answered".
        summary_path, summary_content = self._build_session_summary(
            req.user_id,
            req.content,
            content,
            model_name,
        )
        return MessageResult(
            content=content,
            model=model_name,
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
#
# NOTE (D-03b, 44-03): the former ``_WARM_TIER_EXCLUDE_PREFIXES`` re-export
# is dropped here — recall.py no longer defines that stale duplicate tuple.
# The single source of truth is ``RecallConfig.exclude_prefixes``.
# ---------------------------------------------------------------------------
from app.services.recall import SEARCH_SCORE_THRESHOLD as SEARCH_SCORE_THRESHOLD  # noqa: E402
