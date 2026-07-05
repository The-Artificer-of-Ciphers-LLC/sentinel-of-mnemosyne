"""
POST /provider/complete — narrow chat/completion passthrough (D-09, SC-6).

Restores the "everything through Sentinel" gateway design for chat (Phase 42).
pf2e-module (and any other domain module) calls this endpoint via
``SentinelCoreClient.complete()`` instead of hardcoding its own LLM
endpoint/model. The route is a THIN passthrough to
``ctx.ai_provider.complete()`` — it does NOT reuse any part of the /message
pipeline (no memory recall, no prompt-injection filtering, no output
scanning, no note filing). Callers already carry their own context; mixing
in the operator's Discord memory here would be architecturally wrong.

Authentication: APIKeyMiddleware (global, app/main.py) already covers every
non-/health route, including this one — no new auth code is added here.
"""
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.errors import ProviderUnavailableError
from app.state import get_route_context

logger = logging.getLogger(__name__)

router = APIRouter()

# V5 (DoS guard): no message-count cap existed anywhere in this codebase before
# this endpoint (RESEARCH.md Security Domain). This cap comfortably covers a
# multi-turn pf2e chat handoff while bounding worst-case LLM cost/latency from
# a single request — rejected via 422 before any LLM call.
_MAX_MESSAGES = 50
# Mirrors MessageEnvelope.content's existing max_length=32_000 pattern (app/models.py).
_MAX_CONTENT_LENGTH = 32_000


class ProviderMessage(BaseModel):
    role: str
    content: str = Field(max_length=_MAX_CONTENT_LENGTH)


class ProviderCompleteRequest(BaseModel):
    messages: list[ProviderMessage] = Field(min_length=1, max_length=_MAX_MESSAGES)
    stop: list[str] | None = None
    temperature: float | None = None


class ProviderCompleteResponse(BaseModel):
    content: str
    model: str


@router.post("/provider/complete", response_model=ProviderCompleteResponse)
async def post_provider_complete(
    body: ProviderCompleteRequest, request: Request
) -> ProviderCompleteResponse:
    """Thin passthrough to ctx.ai_provider.complete() (D-09).

    Reuses no /message pipeline component — the caller's messages already
    carry their own context.
    """
    ctx = get_route_context(request)
    if ctx.ai_provider is None:
        raise HTTPException(status_code=500, detail="ai_provider not configured")

    messages = [m.model_dump() for m in body.messages]
    try:
        content = await ctx.ai_provider.complete(
            messages, stop=body.stop, temperature=body.temperature
        )
    except ProviderUnavailableError:
        # Generic detail only (T-42-08) — never echo the underlying
        # ProviderRouter/LiteLLMProvider exception text, which may embed
        # provider api_base/api_key.
        raise HTTPException(status_code=503, detail="AI provider unavailable")

    return ProviderCompleteResponse(content=content, model=ctx.ai_provider_name or "")
