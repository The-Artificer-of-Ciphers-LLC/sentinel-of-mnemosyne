"""
POST /message route — Phase 10: 5-file parallel self/ context read (D-02).

Flow:
  1. Retrieve 5 self/ context files in parallel via asyncio.gather() (graceful skip on failure per D-02)
  2. Retrieve hot-tier session summaries (last 3, graceful skip on failure)
  3. Build hot-tier context pair (self_contents + sessions, truncated to SESSIONS_BUDGET_RATIO=0.15)
  4. Search vault for relevant notes (warm tier, fires on every exchange — MEM-08)
  5. Filter search results to those with score >= SEARCH_SCORE_THRESHOLD (MEM-08b: relevance gate)
  6. Build warm-tier context pair (top-3 high-relevance vault results, truncated to SEARCH_BUDGET_RATIO=0.10)
     — skipped entirely if no results pass the relevance gate (D-05)
  7. Apply injection filter (SEC-01) to BOTH context blocks before appending to messages
  8. Token guard on full messages array
  9. Call AI provider via ProviderRouter (primary with fallback per PROV-05)
  10. Write session summary to Obsidian via BackgroundTasks (best-effort, D-2/MEM-06)

Note: Pi harness is NOT used in the message route. Pi is a coding agent that makes multiple
LLM calls per request (tool use loop), which spams LM Studio with stacked requests at 0%.
Chat completion goes directly to LiteLLMProvider → LM Studio as a single OpenAI-compatible
/v1/chat/completions call.
"""
import asyncio
import logging
from datetime import datetime, timezone

import tiktoken
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from litellm import BadRequestError as LiteLLMBadRequestError

from app.models import MessageEnvelope, ResponseEnvelope
from app.services.provider_router import ProviderUnavailableError
from app.services.token_guard import TokenLimitError, check_token_limit

logger = logging.getLogger(__name__)
router = APIRouter()

SESSIONS_BUDGET_RATIO = 0.15  # hot tier: user_context + recent_sessions (D-08)
SEARCH_BUDGET_RATIO = 0.10    # warm tier: vault search results (D-08)
# Combined = 0.25 (unchanged total ceiling)

# MEM-08b: minimum relevance score for vault search results to be injected as context.
# Obsidian simple search scores are unbounded floats; results are already sorted descending.
# A score below this threshold indicates a low-confidence keyword match from an unrelated
# domain (e.g. pf2e notes matching on "sing" when the user mentions "singing course").
# Without this gate, garbled or off-topic vault content pollutes the LLM prompt context.
SEARCH_SCORE_THRESHOLD = 0.5


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to fit within max_tokens. Appends truncation marker if cut."""
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return text
    truncated = enc.decode(tokens[:max_tokens])
    return truncated + "\n\n[...context truncated to fit token budget]"


def _format_search_results(results: list[dict]) -> str:
    """Format top vault search results as a markdown list. MEM-08 warm tier formatter."""
    lines = ["Relevant vault notes:"]
    for r in results:
        filename = r.get("filename", "unknown")
        matches = r.get("matches", [])
        snippet = matches[0].get("context", "").strip() if matches else ""
        if snippet:
            lines.append(f"- **{filename}**: {snippet}")
        else:
            lines.append(f"- **{filename}**")
    return "\n".join(lines)


@router.post("/message", response_model=ResponseEnvelope)
async def post_message(
    envelope: MessageEnvelope,
    request: Request,
    background_tasks: BackgroundTasks,
) -> ResponseEnvelope:
    """
    Receive a user message, inject Obsidian memory context, call AI provider, write session summary.

    Error responses:
      422 — message + context exceeds context window after truncation, or model rejected request
      503 — AI provider (primary and fallback) unavailable
      502 — unexpected AI provider error
    """
    obsidian = request.app.state.obsidian_client
    ai_provider = request.app.state.ai_provider
    settings = request.app.state.settings
    context_window: int = request.app.state.context_window
    sessions_budget = int(context_window * SESSIONS_BUDGET_RATIO)
    search_budget = int(context_window * SEARCH_BUDGET_RATIO)
    injection_filter = request.app.state.injection_filter

    # 1. Session-start parallel reads: 5 self/ files + recent sessions (D-02, 2B-02)
    _SELF_PATHS = [
        "self/identity.md",
        "self/methodology.md",
        "self/goals.md",
        "self/relationships.md",
        "ops/reminders.md",
    ]
    self_results = await asyncio.gather(
        *[obsidian.read_self_context(p) for p in _SELF_PATHS],
        return_exceptions=True,
    )
    # Filter: keep only non-empty strings (return_exceptions=True makes exceptions plain values)
    self_contents = [r for r in self_results if isinstance(r, str) and r.strip()]
    recent_sessions = await obsidian.get_recent_sessions(envelope.user_id, limit=3)

    # 2. Build messages array — system prompt first, then context pairs (per D-1)
    messages: list[dict] = [
        {
            "role": "system",
            "content": (
                "You are the Sentinel, a personal AI assistant. "
                "You help the user with tasks, answer questions, and maintain context "
                "about their goals and projects via an Obsidian vault. "
                "Respond naturally and helpfully. "
                "Do not describe internal tools, system internals, or implementation details."
            ),
        }
    ]

    context_parts: list[str] = []
    if self_contents:
        context_parts.append("Personal context:\n" + "\n\n---\n\n".join(self_contents))
    if recent_sessions:
        context_parts.append("Recent session history:\n" + "\n---\n".join(recent_sessions))

    if context_parts:
        raw_context = "\n\n".join(context_parts)

        # 3. Truncate injected context to hot-tier budget before token guard (SESSIONS_BUDGET_RATIO)
        safe_context = _truncate_to_tokens(raw_context, sessions_budget)
        if safe_context != raw_context:
            logger.warning(
                f"Context for user '{envelope.user_id}' truncated to {sessions_budget} tokens "
                f"(budget ratio {SESSIONS_BUDGET_RATIO})"
            )

        # 4. Apply injection filter to vault context (SEC-01: framing wrapper + blocklist)
        filtered_context = injection_filter.wrap_context(safe_context)

        messages.append({"role": "user", "content": filtered_context})
        messages.append({"role": "assistant", "content": "Understood."})

    # [WARM TIER] MEM-08: search vault on every exchange, inject top-3 high-relevance results
    # search_vault uses raw envelope.content — search happens before injection filtering (D-06)
    search_results = await obsidian.search_vault(envelope.content)

    # MEM-08b: filter to results with score >= SEARCH_SCORE_THRESHOLD before slicing.
    # This prevents low-confidence cross-domain keyword matches (e.g. pf2e gaming notes
    # matching on a word that also appears in an unrelated 2nd-brain query) from being
    # injected as context. Without this gate, garbled vault content poisons the LLM prompt.
    relevant_results = [r for r in search_results if r.get("score", 0.0) >= SEARCH_SCORE_THRESHOLD]

    if relevant_results:  # D-05: skip entirely if no high-relevance results
        vault_block = _format_search_results(relevant_results[:3])  # D-07: top-3 hardcoded
        safe_vault = _truncate_to_tokens(vault_block, search_budget)  # D-09: independent budget
        # Apply SEC-01 injection guard — vault content is untrusted user-controlled data
        filtered_vault = injection_filter.wrap_context(safe_vault)
        messages.append({"role": "user", "content": filtered_vault})
        messages.append({"role": "assistant", "content": "Understood."})
    elif search_results:
        logger.debug(
            f"Warm tier: {len(search_results)} vault result(s) returned but all scored below "
            f"threshold {SEARCH_SCORE_THRESHOLD} — skipping injection"
        )

    # Apply injection filter to user input (SEC-01: same code path as vault content)
    safe_input, _input_modified = injection_filter.filter_input(envelope.content)
    messages.append({"role": "user", "content": safe_input})

    # 5. Token guard on full messages array (MEM-07)
    try:
        check_token_limit(messages, context_window)
    except TokenLimitError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 6. Call AI provider via ProviderRouter (primary with fallback per PROV-05)
    # Pi harness is intentionally bypassed here: Pi is a coding agent that runs a
    # tool-use loop and issues multiple LLM calls per request, stacking requests at
    # LM Studio. Chat completion must go directly to LiteLLMProvider.
    try:
        content = await ai_provider.complete(messages)
    except ProviderUnavailableError as exc:
        logger.error(f"All AI providers unavailable: {exc}")
        raise HTTPException(status_code=503, detail=str(exc))
    except LiteLLMBadRequestError as exc:
        logger.warning(f"AI provider rejected request (BadRequestError): {exc}")
        raise HTTPException(
            status_code=422,
            detail="Message plus context exceeds model capacity. Try a shorter message.",
        )
    except Exception as exc:
        logger.error(f"Unexpected AI provider error: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=502, detail=f"AI provider error: {type(exc).__name__}")

    # 6b. Output leak scan (SEC-02: regex + Haiku secondary classifier, fail-open)
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
    Path: /ops/sessions/{YYYY-MM-DD}/{user_id}-{HH-MM-SS}.md
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
