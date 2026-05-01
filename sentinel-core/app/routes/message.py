"""POST /message route adapter."""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.models import MessageEnvelope, ResponseEnvelope
from app.services.message_processing import (
    MessageProcessingError,
    MessageRequest,
    MessageResult,
    MessageProcessor,
    SEARCH_SCORE_THRESHOLD,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/message", response_model=ResponseEnvelope)
async def post_message(
    envelope: MessageEnvelope,
    request: Request,
    background_tasks: BackgroundTasks,
) -> ResponseEnvelope:
    factory = getattr(request.app.state, "message_processor_factory", None)
    if callable(factory):
        processor = factory()
    else:
        processor = MessageProcessor(
            obsidian=request.app.state.obsidian_client,
            ai_provider=request.app.state.ai_provider,
            injection_filter=request.app.state.injection_filter,
            output_scanner=request.app.state.output_scanner,
        )
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
        if exc.code == "context_overflow":
            raise HTTPException(status_code=422, detail=str(exc))
        if exc.code == "provider_unavailable":
            raise HTTPException(status_code=503, detail=str(exc))
        if exc.code == "provider_misconfigured":
            raise HTTPException(status_code=502, detail=str(exc))
        if exc.code == "security_blocked":
            raise HTTPException(status_code=500, detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))

    _schedule_session_summary(background_tasks, request, result)
    return ResponseEnvelope(content=result.content, model=result.model)


def _schedule_session_summary(background_tasks: BackgroundTasks, request: Request, result: MessageResult) -> None:
    background_tasks.add_task(
        _write_session_summary,
        request.app.state.obsidian_client,
        result.summary_path,
        result.summary_content,
    )


async def _write_session_summary(obsidian, path: str, content: str) -> None:
    try:
        await obsidian.write_session_summary(path, content)
        logger.debug("Session summary written: %s", path)
    except Exception as exc:
        logger.warning("Session summary write failed for %s: %s", path, exc)
