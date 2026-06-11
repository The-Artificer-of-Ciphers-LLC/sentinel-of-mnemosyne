"""POST /message route adapter."""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.errors import MessageProcessingError
from app.models import MessageEnvelope, ResponseEnvelope
from app.services.message_processing import MessageResult, SEARCH_SCORE_THRESHOLD
from app.services.message_http_mapping import map_message_exception
from app.services.message_request_factory import build_message_request
from app.services.note_intake import NoteIntake
from app.state import RouteContext, get_route_context

# Re-exported for tests; consumed in app.services.message_processing.
_ = SEARCH_SCORE_THRESHOLD

logger = logging.getLogger(__name__)

# Minimum character length for chat content to be filed as a Vault note.
# Content shorter than this is almost certainly a greeting or acknowledgement
# that carries no memory value.  NoteIntake's own cheap-filter also catches
# many short openers; this guard is a fast pre-check that avoids constructing
# NoteIntake at all for clearly trivial messages.
_CHAT_NOTE_MIN_LENGTH = 20

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
    _schedule_chat_note(background_tasks, ctx, envelope.content)
    return ResponseEnvelope(content=result.content, model=result.model)


def _schedule_session_summary(
    background_tasks: BackgroundTasks, ctx: RouteContext, result: MessageResult
) -> None:
    background_tasks.add_task(
        ctx.vault.write_session_summary,
        result.summary_path,
        result.summary_content,
    )


def _schedule_chat_note(
    background_tasks: BackgroundTasks, ctx: RouteContext, content: str
) -> None:
    """Schedule a best-effort Vault note write for substantive user content.

    Uses NoteIntake.classify_and_apply() so the note lands in a topic-organised
    path outside ops/ and is therefore reachable by warm-tier vault search on
    future turns.  Trivially short content is skipped before NoteIntake is
    constructed; NoteIntake's own cheap-filter drops noise/greetings.
    Any exception is caught and logged — this must never delay or fail the
    /message response.
    """
    stripped = content.strip() if content else ""
    if len(stripped) < _CHAT_NOTE_MIN_LENGTH:
        return

    intake = NoteIntake(vault=ctx.vault, classify_note_fn=ctx.classify)
    background_tasks.add_task(_safe_file_chat_note, intake, stripped)


async def _safe_file_chat_note(intake: NoteIntake, content: str) -> None:
    """Invoke NoteIntake.classify_and_apply(); swallow and log any exception.

    Passes searchable_only=True so that notes whose classifier-chosen topic
    maps to a warm-tier-excluded prefix (e.g. observation → ops/observations/)
    are silently redirected to a searchable journal path instead.  The note
    content is always preserved; only the destination changes.
    """
    try:
        await intake.classify_and_apply(content, searchable_only=True)
    except Exception as exc:
        logger.warning("chat note filing failed (best-effort): %s", exc)
