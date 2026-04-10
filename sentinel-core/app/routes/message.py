"""
POST /message route — Phase 2: memory-aware message processing.

Flow:
  1. Retrieve user context file from Obsidian (graceful skip on failure)
  2. Retrieve hot-tier session summaries (last 3, graceful skip on failure)
  3. Build messages array: context user/assistant pair + actual user message (per D-1)
  4. Truncate injected context to 25% of context_window budget (prevents systematic 422s)
  5. Token guard on full messages array
  6. Forward to Pi harness via send_messages()
  7. Call AI provider via ProviderRouter (primary with fallback per PROV-05)
  8. Write session summary to Obsidian via BackgroundTasks (best-effort, D-2/MEM-06)
"""
import logging
from datetime import datetime, timezone

import tiktoken
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.models import MessageEnvelope, ResponseEnvelope
from app.services.provider_router import ProviderUnavailableError
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
    Receive a user message, inject Obsidian memory context, call AI provider, write session summary.

    Error responses:
      422 — message + context exceeds context window after truncation
      503 — AI provider (primary and fallback) unavailable
      502 — unexpected AI provider error
    """
    obsidian = request.app.state.obsidian_client
    context_window: int = request.app.state.context_window
    budget_tokens = int(context_window * CONTEXT_BUDGET_RATIO)

    # 1 + 2. Retrieve context (both calls degrade gracefully — never raise)
    user_context = await obsidian.get_user_context(envelope.user_id)
    recent_sessions = await obsidian.get_recent_sessions(envelope.user_id, limit=3)

    # 3. Build messages array with context prepended as user/assistant pair (per D-1)
    messages: list[dict] = []
    if user_context or recent_sessions:
        context_parts: list[str] = []
        if user_context:
            context_parts.append(f"User profile:\n{user_context}")
        if recent_sessions:
            context_parts.append("Recent session history:\n" + "\n---\n".join(recent_sessions))
        raw_context = "\n\n".join(context_parts)

        # 4. Truncate injected context to budget before token guard
        safe_context = _truncate_to_tokens(raw_context, budget_tokens)
        if safe_context != raw_context:
            logger.warning(
                f"Context for user '{envelope.user_id}' truncated to {budget_tokens} tokens "
                f"(budget ratio {CONTEXT_BUDGET_RATIO})"
            )

        # 4b. Apply injection filter to vault context (SEC-01: framing wrapper + blocklist)
        injection_filter = request.app.state.injection_filter
        filtered_context = injection_filter.wrap_context(safe_context)

        messages.append({"role": "user", "content": filtered_context})
        messages.append({"role": "assistant", "content": "Understood."})

    # Apply injection filter to user input (SEC-01: same code path as vault content)
    injection_filter = request.app.state.injection_filter
    safe_input, _input_modified = injection_filter.filter_input(envelope.content)
    messages.append({"role": "user", "content": safe_input})

    # 5. Token guard on full messages array (MEM-07)
    try:
        check_token_limit(messages, context_window)
    except TokenLimitError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 6. Forward to Pi harness via messages array
    pi_adapter = request.app.state.pi_adapter
    settings = request.app.state.settings

    try:
        content = await pi_adapter.send_messages(messages)
    except Exception:
        # Pi harness unavailable — fall through to direct AI provider call below
        content = None

    # 7. Call AI provider via ProviderRouter (primary with fallback per PROV-05)
    if content is None:
        ai_provider = request.app.state.ai_provider

        try:
            content = await ai_provider.complete(messages)
        except ProviderUnavailableError as exc:
            logger.error(f"All AI providers unavailable: {exc}")
            raise HTTPException(status_code=503, detail=str(exc))
        except Exception as exc:
            logger.error(f"Unexpected AI provider error: {type(exc).__name__}: {exc}")
            raise HTTPException(status_code=502, detail=f"AI provider error: {type(exc).__name__}")

    # 7b. Output leak scan (SEC-02: regex + Haiku secondary classifier, fail-open)
    output_scanner = request.app.state.output_scanner
    is_safe, block_reason = await output_scanner.scan(content)
    if not is_safe:
        logger.error(
            f"Output scanner blocked response for user '{envelope.user_id}': {block_reason}"
        )
        background_tasks.add_task(
            _log_leak_incident,
            obsidian,
            envelope.user_id,
            block_reason or "unknown",
        )
        raise HTTPException(status_code=500, detail="Response blocked by security scanner")

    # 8. Best-effort session summary write (MEM-03, MEM-06: always write)
    model_label = f"{settings.ai_provider}/{settings.model_name}"
    background_tasks.add_task(
        _write_session_summary,
        obsidian,
        envelope.user_id,
        envelope.content,
        content,
        model_label,
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
    Path: /core/sessions/{YYYY-MM-DD}/{user_id}-{HH-MM-SS}.md
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M-%S")
    path = f"core/sessions/{date_str}/{user_id}-{time_str}.md"
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


async def _log_leak_incident(
    obsidian,
    user_id: str,
    block_reason: str,
) -> None:
    """
    Best-effort incident log write. Failures are logged, not raised.
    Path: security/leak-incidents/{timestamp}.md
    """
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%dT%H-%M-%S")
    path = f"security/leak-incidents/{timestamp}.md"
    content = f"""---
timestamp: {now.isoformat()}
user_id: {user_id}
type: output_leak_incident
---

## Leak Incident

**Detected:** {now.isoformat()}
**User:** {user_id}
**Reason:** {block_reason}

Response was blocked. Original content withheld from this log for safety.
"""
    try:
        await obsidian.write_session_summary(path, content)
        logger.info(f"Leak incident logged: {path}")
    except Exception as exc:
        logger.warning(f"Leak incident log write failed: {exc}")
