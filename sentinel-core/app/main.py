"""
Sentinel Core — FastAPI application entry point.

Architecture:
  POST /message → APIKeyMiddleware → token guard → AI provider
  GET  /health  → always 200, reports obsidian status as non-blocking field
  GET  /status  → authenticated system status (obsidian, pi_harness, ai_provider)
  GET  /context/{user_id} → authenticated debug context dump

Lifespan delegates startup wiring and policy enforcement to
``app.composition.initialize_startup``.

Route handlers consume ``app.state.route_ctx``; we avoid scattering the full
``AppGraph`` onto ``app.state``.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from app.composition import initialize_startup
from app.config import settings
from app.routes.message import router as message_router
from app.runtime_config import runtime_config_from_settings
from app.routes.modules import router as modules_router
from app.routes.note import router as note_router
from app.routes.status import router as status_router
from app.services.health_response import build_health_payload
from app.services.model_selector import probe_embedding_model_loaded
from app.services.runtime_probe import probe_runtime

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Require X-Sentinel-Key header on all non-health endpoints (IFACE-06)."""

    async def dispatch(self, request: StarletteRequest, call_next) -> Response:
        if request.url.path == "/health":
            return await call_next(request)
        key = request.headers.get("X-Sentinel-Key", "")
        if key != settings.sentinel_api_key:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Create shared resources at startup; clean up at shutdown."""
    logger.info("Sentinel Core starting...")

    http_client = httpx.AsyncClient(timeout=30.0)
    app.state.http_client = http_client
    app.state.settings = settings

    startup = await initialize_startup(app, settings, http_client)
    for warning in startup.warnings:
        logger.warning(warning)

    logger.info("Sentinel Core ready.")
    yield

    # Shutdown
    await http_client.aclose()
    logger.info("Sentinel Core shutdown complete.")


app = FastAPI(
    title="Sentinel Core",
    version="0.50.0",
    description="Sentinel of Mnemosyne — Core message processing API",
    lifespan=lifespan,
)

app.add_middleware(APIKeyMiddleware)  # call 1 — innermost, runs second
_cors_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)  # call 2 — outermost, runs first (intercepts OPTIONS before auth)
# CORSMiddleware added AFTER APIKeyMiddleware in source order.
# FastAPI add_middleware() is LIFO — last added = outermost = runs FIRST on requests.
# Outermost means OPTIONS preflight hits CORSMiddleware before APIKeyMiddleware can 401 it.
# DO NOT move this block above app.add_middleware(APIKeyMiddleware).
app.include_router(message_router)
app.include_router(status_router)
app.include_router(modules_router)
app.include_router(note_router)


@app.get("/health")
async def health(request: Request) -> JSONResponse:
    """Health check — always 200. Reports obsidian + embedding-model state
    as non-blocking fields. (260502-1zv D-02 — embedding_model field added.)"""
    http_client = getattr(request.app.state, "http_client", None)

    snapshot = await probe_runtime(
        vault=getattr(request.app.state, "vault", None),
        http_client=http_client,
        runtime_config=runtime_config_from_settings(settings),
        include_embedding_probe=False,
    )

    embedding_loaded = False
    try:
        embedding_loaded = await probe_embedding_model_loaded(
            http_client,
            settings.lmstudio_base_url,
            settings.embedding_model,
        )
    except Exception:
        pass

    return JSONResponse(build_health_payload(snapshot, embedding_loaded))
