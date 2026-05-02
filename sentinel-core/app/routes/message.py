"""POST /message route adapter."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.models import MessageEnvelope, ResponseEnvelope
from app.services.message_processing import (
    MessageProcessingError,
    MessageRequest,
    MessageResult,
    SEARCH_SCORE_THRESHOLD,
)

# Re-exported for tests; consumed in app.services.message_processing.
_ = SEARCH_SCORE_THRESHOLD

router = APIRouter()


@router.post("/message", response_model=ResponseEnvelope)
async def post_message(
    envelope: MessageEnvelope,
    request: Request,
    background_tasks: BackgroundTasks,
) -> ResponseEnvelope:
    app_state = request.app.state
    processor = app_state.message_processor
    stop_sequences = getattr(app_state, "lmstudio_stop_sequences", None) or None
    req = MessageRequest(
        content=envelope.content,
        user_id=envelope.user_id,
        model_name=app_state.settings.model_name,
        context_window=app_state.context_window,
        stop_sequences=stop_sequences,
    )

    try:
        result = await processor.process(req)
    except MessageProcessingError as exc:
        match exc.code:
            case "context_overflow":
                status_code = 422
            case "provider_unavailable":
                status_code = 503
            case "provider_misconfigured":
                status_code = 502
            case "security_blocked":
                status_code = 500
            case _:
                status_code = 502
        raise HTTPException(status_code=status_code, detail=str(exc))

    _schedule_session_summary(background_tasks, request, result)
    return ResponseEnvelope(content=result.content, model=result.model)


def _schedule_session_summary(
    background_tasks: BackgroundTasks, request: Request, result: MessageResult
) -> None:
    background_tasks.add_task(
        request.app.state.obsidian_client.write_session_summary,
        result.summary_path,
        result.summary_content,
    )
