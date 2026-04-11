"""
Sentinel Core — FastAPI application entry point.

Architecture:
  POST /message → APIKeyMiddleware → token guard → Pi harness (Fastify bridge) → Pi subprocess → AI provider
  GET  /health  → always 200, reports obsidian status as non-blocking field

Lifespan creates shared resources (httpx client, model registry, ProviderRouter) at startup.
Uses lifespan context manager (not deprecated @app.on_event — see Pitfall 5).
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from app.clients.litellm_provider import LiteLLMProvider
from app.clients.llamacpp_provider import LlamaCppProvider
from app.clients.obsidian import ObsidianClient
from app.clients.ollama_provider import OllamaProvider
from app.clients.pi_adapter import PiAdapterClient
from app.config import settings
from app.routes.message import router as message_router
from app.services.model_registry import build_model_registry
from app.services.provider_router import ProviderRouter

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

    # Single shared httpx client for all outbound calls
    http_client = httpx.AsyncClient(timeout=30.0)
    app.state.http_client = http_client
    app.state.settings = settings

    # Build model registry (live fetch + seed fallback) — non-fatal if providers unavailable
    model_registry = await build_model_registry(settings, http_client)
    app.state.model_registry = model_registry

    # Determine active model id for context window lookup
    _active_model = (
        settings.model_name if settings.ai_provider == "lmstudio"
        else settings.claude_model if settings.ai_provider == "claude"
        else settings.ollama_model if settings.ai_provider == "ollama"
        else settings.llamacpp_model
    )
    _model_info = model_registry.get(_active_model)
    context_window = _model_info.context_window if _model_info else 4096
    if not _model_info:
        logger.warning(
            f"Active model '{_active_model}' not found in registry — using 4096 token default"
        )
    else:
        logger.info(f"Context window: {context_window} tokens (model: {_active_model})")
    app.state.context_window = context_window

    # Instantiate all providers
    lmstudio_provider = LiteLLMProvider(
        model_string=f"openai/{settings.model_name}",
        api_base=settings.lmstudio_base_url,
        api_key="lmstudio",
    )
    claude_provider = (
        LiteLLMProvider(
            model_string=settings.claude_model,
            api_key=settings.anthropic_api_key or "no-key",
        )
        if settings.anthropic_api_key
        else None
    )

    ollama_provider = OllamaProvider(settings.ollama_base_url, settings.ollama_model)
    llamacpp_provider = LlamaCppProvider(settings.llamacpp_base_url, settings.llamacpp_model)

    # Select primary provider
    _provider_map = {
        "lmstudio": lmstudio_provider,
        "claude": claude_provider,
        "ollama": ollama_provider,
        "llamacpp": llamacpp_provider,
    }
    primary = _provider_map.get(settings.ai_provider, lmstudio_provider)
    if primary is None:
        logger.error(
            f"AI_PROVIDER='{settings.ai_provider}' selected but provider could not be instantiated "
            "(likely missing API key). Falling back to LM Studio."
        )
        primary = lmstudio_provider

    # Select fallback provider
    fallback = None
    if settings.ai_fallback_provider == "claude":
        fallback = claude_provider
        if fallback is None:
            logger.warning(
                "AI_FALLBACK_PROVIDER=claude but ANTHROPIC_API_KEY not set — no fallback available"
            )

    # Wire ProviderRouter into app.state
    app.state.ai_provider = ProviderRouter(primary, fallback_provider=fallback)
    logger.info(
        f"AI provider: {settings.ai_provider} "
        f"(fallback: {settings.ai_fallback_provider})"
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

app.add_middleware(APIKeyMiddleware)
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
