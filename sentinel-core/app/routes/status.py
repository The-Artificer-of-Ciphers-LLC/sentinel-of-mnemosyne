"""System status and debug endpoints — RD-05 / STUB-06."""

import asyncio

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

router = APIRouter()


@router.get("/status")
async def system_status(request: Request) -> JSONResponse:
    obsidian = request.app.state.obsidian_client
    http_client = request.app.state.http_client
    pi_url = request.app.state.settings.pi_harness_url

    obsidian_ok = await obsidian.check_health()
    pi_ok = False
    try:
        resp = await http_client.get(f"{pi_url}/health", timeout=5.0)
        pi_ok = resp.status_code == 200
    except Exception:
        pass

    return JSONResponse(
        {
            "status": "ok" if (obsidian_ok and pi_ok) else "degraded",
            "obsidian": "ok" if obsidian_ok else "unreachable",
            "pi_harness": "ok" if pi_ok else "unreachable",
            "ai_provider": request.app.state.ai_provider_name,
        }
    )


@router.get("/context/{user_id}")
async def debug_context(request: Request, user_id: str) -> JSONResponse:
    obsidian = request.app.state.obsidian_client
    self_paths = [
        "self/identity.md",
        "self/methodology.md",
        "self/goals.md",
        "self/relationships.md",
        "ops/reminders.md",
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
