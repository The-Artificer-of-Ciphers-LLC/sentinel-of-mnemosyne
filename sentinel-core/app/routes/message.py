"""POST /message route adapter."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.models import MessageEnvelope, ResponseEnvelope
from app.services.message_error_mapper import to_http_status
from app.services.message_processor_factory import from_app_state
from app.services.message_processing import (
    MessageProcessingError,
    MessageResult,
    SEARCH_SCORE_THRESHOLD,
)

# Re-exported for tests; consumed in app.services.message_processing.
_ = SEARCH_SCORE_THRESHOLD
from app.services.message_route_bridge import build_message_request

router = APIRouter()


@router.post("/message", response_model=ResponseEnvelope)
async def post_message(
    envelope: MessageEnvelope,
    request: Request,
    background_tasks: BackgroundTasks,
) -> ResponseEnvelope:
    processor = from_app_state(request.app.state)
    req = build_message_request(envelope=envelope, app_state=request.app.state)

    try:
        result = await processor.process(req)
    except MessageProcessingError as exc:
        raise HTTPException(status_code=to_http_status(exc.code), detail=str(exc))

    _schedule_session_summary(background_tasks, request, result)
    return ResponseEnvelope(content=result.content, model=result.model)


def _schedule_session_summary(background_tasks: BackgroundTasks, request: Request, result: MessageResult) -> None:
    background_tasks.add_task(
        request.app.state.obsidian_client.write_session_summary,
        result.summary_path,
        result.summary_content,
    )
