"""System status and debug endpoints — RD-05 / STUB-06."""

from fastapi import APIRouter, Path, Request
from starlette.responses import JSONResponse

from app.runtime_config import runtime_config_from_settings
from app.services.recall import MessageRequest
from app.services.runtime_probe import probe_runtime
from app.state import get_route_context

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
    fake_req = MessageRequest(
        content="",
        user_id=user_id,
        model_name="",
        context_window=ctx.context_window,
        stop_sequences=None,
    )
    recalled = await ctx.recall.assemble(fake_req, budget=ctx.context_window)
    return JSONResponse(
        {
            "user_id": user_id,
            "self_context": recalled.self_context,
            "sessions": recalled.sessions,
            "warm": [{"path": r.path, "score": r.score} for r in recalled.warm],
            "recent_sessions_count": len(recalled.sessions),
        }
    )
