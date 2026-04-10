"""POST /message route — receives MessageEnvelope, returns ResponseEnvelope."""
from fastapi import APIRouter, HTTPException, Request
import httpx

from app.models import MessageEnvelope, ResponseEnvelope
from app.services.token_guard import check_token_limit, TokenLimitError

router = APIRouter()


@router.post("/message", response_model=ResponseEnvelope)
async def post_message(envelope: MessageEnvelope, request: Request) -> ResponseEnvelope:
    """
    Receive a user message, check token budget, forward to Pi harness, return AI response.

    Error responses:
      422 — message exceeds context window (token guard)
      503 — Pi harness or LM Studio unavailable
    """
    # 1. Token guard — check before sending to Pi
    messages = [{"role": "user", "content": envelope.content}]
    try:
        check_token_limit(messages, request.app.state.context_window)
    except TokenLimitError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 2. Forward to Pi harness
    pi_adapter = request.app.state.pi_adapter
    settings = request.app.state.settings

    try:
        content = await pi_adapter.send_prompt(envelope.content)
    except (httpx.ConnectError, httpx.RemoteProtocolError):
        raise HTTPException(status_code=503, detail="AI backend not ready")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (503, 504):
            raise HTTPException(status_code=503, detail="AI backend not ready")
        raise HTTPException(status_code=502, detail="Pi harness error")

    return ResponseEnvelope(content=content, model=settings.model_name)
