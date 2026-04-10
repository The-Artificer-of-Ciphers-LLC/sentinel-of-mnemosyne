"""
Sentinel Core — FastAPI application entry point.

Architecture:
  POST /message → token guard → Pi harness (Fastify bridge) → Pi subprocess → LM Studio
  GET  /health  → always 200

Lifespan creates shared resources (httpx client, context window cache) at startup.
Uses lifespan context manager (not deprecated @app.on_event — see Pitfall 5).
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.clients.lmstudio import LMStudioClient, get_context_window
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
    context_window = await get_context_window(http_client, settings.lmstudio_base_url, settings.model_name)
    if context_window == 4096:
        logger.warning(
            "LM Studio unavailable at startup — using conservative 4096-token context window. "
            "Core will continue serving requests in degraded mode."
        )
    else:
        logger.info(f"Context window: {context_window} tokens (fetched from LM Studio)")
    app.state.context_window = context_window

    # Client instances
    app.state.lm_client = LMStudioClient(http_client, settings.lmstudio_base_url, settings.model_name)
    app.state.pi_adapter = PiAdapterClient(http_client, settings.pi_harness_url)

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
async def health() -> JSONResponse:
    """Health check — always returns 200. Does not check downstream dependencies."""
    return JSONResponse({"status": "ok"})
