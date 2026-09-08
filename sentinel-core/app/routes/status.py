"""System status and debug endpoints — RD-05 / STUB-06."""

import logging

from fastapi import APIRouter, Path, Request
from starlette.responses import JSONResponse

from app.model import DECLARED_DEFAULT_CONTEXT_WINDOW
from app.runtime_config import runtime_config_from_settings
from app.services.message_processing import MessageRequest
from app.services.runtime_probe import probe_runtime
from app.state import get_route_context

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status")
async def system_status(request: Request) -> JSONResponse:
    ctx = get_route_context(request)
    snapshot = await probe_runtime(
        vault=ctx.vault,
        http_client=ctx.http_client,
        runtime_config=runtime_config_from_settings(ctx.settings),
        include_embedding_probe=False,
    )

    ai_provider = ctx.ai_provider_name or getattr(ctx.settings, "ai_provider_name", None)

    return JSONResponse(
        {
            "status": "ok" if snapshot.obsidian_ok else "degraded",
            "obsidian": "ok" if snapshot.obsidian_ok else "unreachable",
            "ai_provider": ai_provider,
        }
    )


@router.get("/context/{user_id}")
async def debug_context(
    request: Request,
    user_id: str = Path(..., pattern=r"^[a-zA-Z0-9_-]+$"),
) -> JSONResponse:
    ctx = get_route_context(request)
    fake_req = MessageRequest(content="", user_id=user_id, model_name="")
    if ctx.recall is None:
        raise RuntimeError("RouteContext.recall is not configured")
    # ADR-0007 step 4: the budget used to be ``ctx.context_window``, a scalar
    # pinned at startup. This debug view must show what the REAL path would
    # assemble, so it asks the same seam the chat path does. A resolution
    # failure degrades to the declared floor rather than 500-ing a debug
    # endpoint — showing a smaller view is a better failure than showing none.
    budget = DECLARED_DEFAULT_CONTEXT_WINDOW
    if ctx.active_model is not None:
        try:
            budget = (await ctx.active_model.for_task("chat")).context_window
        except Exception as exc:
            logger.warning(
                "debug_context: model resolution failed (%s) — showing the "
                "declared %d-token view",
                exc,
                budget,
            )
    recalled = await ctx.recall.assemble(fake_req, budget=budget)
    # Plan 41-05: serialize typed fields only — body excluded (debug endpoint only,
    # not injection path; body contains raw markdown not suitable for external APIs).
    return JSONResponse(
        {
            "user_id": user_id,
            "self_context": recalled.self_context,
            "sessions": [
                {
                    "date": s.date,
                    "user_id": s.user_id,
                    "time": s.time,
                    "user_msg": s.user_msg,
                    "sentinel_msg": s.sentinel_msg,
                    "path": s.path,
                }
                for s in recalled.sessions
            ],
            "warm": [{"path": r.path, "score": r.score} for r in recalled.warm],
            "recent_sessions_count": len(recalled.sessions),
        }
    )
