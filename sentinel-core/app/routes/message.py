"""POST /message route adapter."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.models import MessageEnvelope, ResponseEnvelope
from app.services.message_error_mapper import to_http_status
from app.services.message_persistence import write_session_summary_best_effort
from app.services.message_processor_factory import from_app_state
from app.services.message_processing import (
    MessageProcessingError,
    MessageRequest,
    MessageResult,
    SEARCH_SCORE_THRESHOLD,
)

router = APIRouter()


@router.post("/message", response_model=ResponseEnvelope)
async def post_message(
    envelope: MessageEnvelope,
    request: Request,
    background_tasks: BackgroundTasks,
) -> ResponseEnvelope:
    processor = from_app_state(request.app.state)
    stop_sequences = getattr(request.app.state, "lmstudio_stop_sequences", None) or None

    try:
        result = await processor.process(
            MessageRequest(
                content=envelope.content,
                user_id=envelope.user_id,
                model_name=request.app.state.settings.model_name,
                context_window=request.app.state.context_window,
                stop_sequences=stop_sequences,
            )
        )
    except MessageProcessingError as exc:
        raise HTTPException(status_code=to_http_status(exc.code), detail=str(exc))

    _schedule_session_summary(background_tasks, request, result)
    return ResponseEnvelope(content=result.content, model=result.model)


def _schedule_session_summary(background_tasks: BackgroundTasks, request: Request, result: MessageResult) -> None:
    background_tasks.add_task(
        write_session_summary_best_effort,
        request.app.state.obsidian_client,
        result.summary_path,
        result.summary_content,
    )
