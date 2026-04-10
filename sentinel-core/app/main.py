"""
Sentinel Core — FastAPI application entry point.

Architecture:
  POST /message → token guard → Pi harness (Fastify bridge) → Pi subprocess → LM Studio
  GET  /health  → always 200, reports obsidian status as non-blocking field

Lifespan creates shared resources (httpx client, context window cache) at startup.
Uses lifespan context manager (not deprecated @app.on_event — see Pitfall 5).
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.clients.obsidian import ObsidianClient
from app.clients.pi_adapter import PiAdapterClient
from app.config import settings
from app.routes.message import router as message_router

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Create shared resources at startup; clean up at shutdown."""
    logger.info("Sentinel Core starting...")

    # Single shared httpx client for all outbound calls
    http_client = httpx.AsyncClient(timeout=30.0)
    app.state.http_client = http_client
    app.state.settings = settings

    # Fetch context window from LM Studio at startup; fall back to 4096 if unavailable
    context_window = await get_context_window_from_lmstudio(
        http_client, settings.lmstudio_base_url, settings.model_name
    )
    if context_window == 4096:
        logger.warning(
            "LM Studio unavailable at startup — using conservative 4096-token context window. "
            "Core will continue serving requests in degraded mode."
        )
    else:
        logger.info(f"Context window: {context_window} tokens (fetched from LM Studio)")
    app.state.context_window = context_window

    # Client instances — LiteLLMProvider replaces LMStudioClient (Phase 4)
    app.state.lm_client = LiteLLMProvider(
        model_string=f"openai/{settings.model_name}",
        api_base=settings.lmstudio_base_url,
        api_key="lmstudio",
    )
    app.state.pi_adapter = PiAdapterClient(http_client, settings.pi_harness_url)

    # Obsidian client — degrades gracefully if Obsidian is not running
    obsidian_client = ObsidianClient(
        http_client,
        settings.obsidian_api_url,
        settings.obsidian_api_key,
    )
    app.state.obsidian_client = obsidian_client

    obsidian_ok = await obsidian_client.check_health()
    if not obsidian_ok:
        logger.warning(
            "Obsidian REST API unavailable at startup — memory features degraded. "
            "Ensure Obsidian is running with Local REST API plugin enabled (HTTP mode port 27123)."
        )

    logger.info("Sentinel Core ready.")
    yield

    # Shutdown
    await http_client.aclose()
    logger.info("Sentinel Core shutdown complete.")


app = FastAPI(
    title="Sentinel Core",
    version="0.1.0",
    description="Sentinel of Mnemosyne — Core message processing API",
    lifespan=lifespan,
)

app.include_router(message_router)


@app.get("/health")
async def health(request: Request) -> JSONResponse:
    """Health check — always 200. Reports obsidian status as non-blocking field."""
    obsidian_ok = False
    try:
        obsidian_ok = await request.app.state.obsidian_client.check_health()
    except Exception:
        pass
    return JSONResponse({
        "status": "ok",
        "obsidian": "ok" if obsidian_ok else "degraded",
    })
