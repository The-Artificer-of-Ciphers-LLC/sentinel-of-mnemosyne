"""POST /message route adapter."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.errors import MessageProcessingError
from app.models import MessageEnvelope, ResponseEnvelope
from app.services.message_processing import MessageResult, SEARCH_SCORE_THRESHOLD
from app.services.message_http_mapping import map_message_exception
from app.services.message_request_factory import build_message_request
from app.state import RouteContext, get_route_context

# Re-exported for tests; consumed in app.services.message_processing.
_ = SEARCH_SCORE_THRESHOLD

router = APIRouter()


@router.post("/message", response_model=ResponseEnvelope)
async def post_message(
    envelope: MessageEnvelope,
    request: Request,
    background_tasks: BackgroundTasks,
) -> ResponseEnvelope:
    ctx = get_route_context(request)
    processor = ctx.processor
    if processor is None or ctx.settings is None:
        raise HTTPException(status_code=500, detail="message processor not configured")
    req = build_message_request(ctx, envelope)

    try:
        result = await processor.process(req)
    except Exception as exc:
        raise map_message_exception(exc)

    _schedule_session_summary(background_tasks, ctx, result)
    return ResponseEnvelope(content=result.content, model=result.model)


def _schedule_session_summary(
    background_tasks: BackgroundTasks, ctx: RouteContext, result: MessageResult
) -> None:
    background_tasks.add_task(
        ctx.vault.write_session_summary,
        result.summary_path,
        result.summary_content,
    )
