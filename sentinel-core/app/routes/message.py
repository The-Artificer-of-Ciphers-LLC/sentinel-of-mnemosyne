"""
POST /message route — Phase 2: memory-aware message processing.

Flow:
  1. Retrieve self context from Obsidian vault (self/identity.md + goals + relationships)
  2. Retrieve current reminders (ops/reminders.md)
  3. Retrieve hot-tier session summaries (last 3, graceful skip on failure)
  4. Build messages array: context user/assistant pair + actual user message (per D-1)
  5. Truncate injected context to 25% of context_window budget (prevents systematic 422s)
  6. Token guard on full messages array
  7. Forward to LM Studio
  8. Write session summary to Obsidian via BackgroundTasks (best-effort, D-2/MEM-06)
"""
import logging
from datetime import datetime, timezone

import httpx
import tiktoken
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.models import MessageEnvelope, ResponseEnvelope
from app.services.token_guard import TokenLimitError, check_token_limit

logger = logging.getLogger(__name__)
router = APIRouter()

CONTEXT_BUDGET_RATIO = 0.25  # 25% of context_window reserved for injected context (D-Claude's Discretion)


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to fit within max_tokens. Appends truncation marker if cut."""
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return text
    truncated = enc.decode(tokens[:max_tokens])
    return truncated + "\n\n[...context truncated to fit token budget]"


@router.post("/message", response_model=ResponseEnvelope)
async def post_message(
    envelope: MessageEnvelope,
    request: Request,
    background_tasks: BackgroundTasks,
) -> ResponseEnvelope:
    """
    Receive a user message, inject Obsidian lifebook context, call LM Studio, write session summary.

    Error responses:
      422 — message + context exceeds context window after truncation
      503 — Pi harness or LM Studio unavailable
      502 — Pi harness error
    """
    obsidian = request.app.state.obsidian_client
    context_window: int = request.app.state.context_window
    budget_tokens = int(context_window * CONTEXT_BUDGET_RATIO)

    # 1 + 2 + 3. Retrieve context (all calls degrade gracefully — never raise)
    self_context = await obsidian.get_self_context()
    reminders = await obsidian.get_reminders()
    recent_sessions = await obsidian.get_recent_sessions(envelope.user_id, limit=3)

    # 4. Build messages array with context prepended as user/assistant pair (per D-1)
    messages: list[dict] = []
    if self_context or reminders or recent_sessions:
        context_parts: list[str] = []
        if self_context:
            context_parts.append(f"Vault context (identity, goals, relationships):\n{self_context}")
        if reminders:
            context_parts.append(f"Current reminders:\n{reminders}")
        if recent_sessions:
            context_parts.append("Recent session history:\n" + "\n---\n".join(recent_sessions))
        raw_context = "\n\n".join(context_parts)

        # 5. Truncate injected context to budget before token guard
        safe_context = _truncate_to_tokens(raw_context, budget_tokens)
        if safe_context != raw_context:
            logger.warning(
                f"Context for user '{envelope.user_id}' truncated to {budget_tokens} tokens "
                f"(budget ratio {CONTEXT_BUDGET_RATIO})"
            )

        messages.append({"role": "user", "content": safe_context})
        messages.append({"role": "assistant", "content": "Understood."})
    messages.append({"role": "user", "content": envelope.content})

    # 6. Token guard on full messages array (MEM-07)
    try:
        check_token_limit(messages, context_window)
    except TokenLimitError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 7. Call LM Studio directly (conversational use — Pi harness reserved for Coder Interface)
    lm_client = request.app.state.lm_client
    settings = request.app.state.settings

    # Prepend Sentinel persona system prompt (lifebook variant)
    full_messages = [
        {
            "role": "system",
            "content": (
                "You are the Sentinel of Mnemosyne — a personal second brain and AI assistant. "
                "You know the user's goals, gear, kids' schedules, and active projects from their Obsidian vault. "
                "You are warm, direct, and unafraid to call out neglected gear or stale goals. "
                "You remember context from prior sessions and reference it naturally. "
                "Answer conversationally. Use markdown only when asked."
            ),
        },
        *messages,
    ]

    try:
        content = await lm_client.complete(full_messages)
    except (httpx.ConnectError, httpx.RemoteProtocolError):
        raise HTTPException(status_code=503, detail="AI backend not ready")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"LM Studio error: {exc.response.status_code}")

    # 8. Best-effort session summary write (MEM-03, MEM-06: always write)
    background_tasks.add_task(
        _write_session_summary,
        obsidian,
        envelope.user_id,
        envelope.content,
        content,
        settings.model_name,
    )

    return ResponseEnvelope(content=content, model=settings.model_name)


async def _write_session_summary(
    obsidian,
    user_id: str,
    user_msg: str,
    ai_msg: str,
    model: str,
) -> None:
    """
    Best-effort session summary write. Failures are logged, not raised.
    Per D-2 (MEM-06): every completed exchange writes a session note.
    Path: ops/sessions/{YYYY-MM-DD}/{user_id}-{HH-MM-SS}.md
    """
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
    try:
        await obsidian.write_session_summary(path, content)
        logger.debug(f"Session summary written: {path}")
    except Exception as exc:
        logger.warning(f"Session summary write failed for {user_id}: {exc}")
