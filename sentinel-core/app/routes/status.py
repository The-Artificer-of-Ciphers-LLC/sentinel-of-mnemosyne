"""System status and debug endpoints — RD-05 / STUB-06."""

import asyncio

from fastapi import APIRouter, Path, Request
from starlette.responses import JSONResponse

from app.runtime_config import runtime_config_from_settings
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
            "pi_harness": "ok" if snapshot.pi_ok else "unreachable",
            "ai_provider": ai_provider,
        }
    )


@router.get("/context/{user_id}")
async def debug_context(
    request: Request,
    user_id: str = Path(..., pattern=r"^[a-zA-Z0-9_-]+$"),
) -> JSONResponse:
    ctx = get_route_context(request)
    obsidian = ctx.vault
    self_paths = [
        "self/identity.md",
        "self/methodology.md",
        "self/goals.md",
        "self/relationships.md",
        "ops/reminders.md",
        "self/learning-areas.md",
    ]
    results = await asyncio.gather(
        *[obsidian.read_self_context(p) for p in self_paths],
        return_exceptions=True,
    )
    context_files = {
        path: text
        for path, text in zip(self_paths, results)
        if isinstance(text, str) and text
    }
    sessions = await obsidian.get_recent_sessions(user_id)
    return JSONResponse(
        {
            "user_id": user_id,
            "context_files": context_files,
            "recent_sessions_count": len(sessions),
        }
    )
