"""
Sentinel Core — FastAPI application entry point.

Architecture:
  POST /message → APIKeyMiddleware → token guard → AI provider
  GET  /health  → always 200, reports obsidian status as non-blocking field
  GET  /status  → authenticated system status (obsidian, pi_harness, ai_provider)
  GET  /context/{user_id} → authenticated debug context dump

Lifespan creates shared resources (httpx client, model registry, ProviderRouter) at startup.
Uses lifespan context manager (not deprecated @app.on_event — see Pitfall 5).
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

from app.clients.litellm_provider import LiteLLMProvider
from app.clients.obsidian import ObsidianClient
from app.config import settings
from app.routes.message import router as message_router
from app.routes.modules import router as modules_router
from app.routes.status import router as status_router
from app.services.injection_filter import InjectionFilter
from app.services.model_registry import build_model_registry
from app.services.model_selector import discover_active_model
from app.services.output_scanner import OutputScanner
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

    # Discover active model for the configured provider (non-fatal)
    _lmstudio_model_str = await discover_active_model(settings, http_client)
    _lmstudio_model_name = _lmstudio_model_str.split("/", 1)[-1]

    # Determine active model id for context window lookup
    _active_model = (
        _lmstudio_model_name
        if settings.ai_provider == "lmstudio"
        else settings.claude_model
        if settings.ai_provider == "claude"
        else settings.ollama_model
        if settings.ai_provider == "ollama"
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

    # Fetch model profile for stop sequences — non-fatal; defaults to no stop sequences.
    # Only meaningful for lmstudio provider (local models need explicit stop tokens).
    # Cloud providers (Claude) manage termination via their own chat templates.
    _lmstudio_api_base = settings.lmstudio_base_url or "http://host.docker.internal:1234"
    try:
        _profile = await get_profile(
            _lmstudio_model_name,
            api_base=_lmstudio_api_base,
        )
        app.state.lmstudio_stop_sequences = _profile.stop_sequences or []
        logger.info(
            "Model stop sequences: %s (arch: %s)",
            _profile.stop_sequences,
            _profile.arch if hasattr(_profile, "arch") else _profile.family,
        )
    except Exception as exc:
        logger.warning(
            "Model profile fetch failed for %r — no stop sequences will be sent: %s",
            _lmstudio_model_name,
            exc,
        )
        app.state.lmstudio_stop_sequences = []

    # All 4 backends route through LiteLLMProvider (RD-02 — eliminate stub providers)
    _provider_map = {
        "lmstudio": LiteLLMProvider(
            model_string=_lmstudio_model_str,  # discovered, not hardcoded
            api_base=settings.lmstudio_base_url,
            api_key="lmstudio",
        ),
        "ollama": LiteLLMProvider(
            model_string=f"ollama/{settings.ollama_model}",
            api_base=settings.ollama_base_url,
        ),
        "llamacpp": LiteLLMProvider(
            model_string=f"openai/{settings.llamacpp_model}",
            api_base=settings.llamacpp_base_url,
        ),
    }
    if settings.anthropic_api_key:
        _provider_map["claude"] = LiteLLMProvider(
            model_string=settings.claude_model,
            api_key=settings.anthropic_api_key,
        )

    lmstudio_provider = _provider_map["lmstudio"]
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
        fallback = _provider_map.get("claude")
        if fallback is None:
            logger.warning(
                "AI_FALLBACK_PROVIDER=claude but ANTHROPIC_API_KEY not set — no fallback available"
            )

    # Wire ProviderRouter into app.state
    app.state.ai_provider = ProviderRouter(primary, fallback_provider=fallback)
    # Expose provider name for /status endpoint (RD-05)
    app.state.ai_provider_name = settings.ai_provider
    logger.info(
        f"AI provider: {settings.ai_provider} "
        f"(fallback: {settings.ai_fallback_provider})"
    )

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

    # Security services — instantiated once, shared across all requests (SEC-01, SEC-02)
    #
    # Build the secondary classifier as a thin closure over ai_provider.complete so that
    # OutputScanner routes through the Sentinel's configured AI engine (AI-agnostic design).
    # The closure builds a minimal two-message conversation (system + user) and returns the
    # first content token from the provider response.
    _scanner_ai_provider = app.state.ai_provider

    async def _secondary_classifier(excerpt: str, fired_patterns: list[str]) -> str:
        from app.services.output_scanner import _CLASSIFIER_SYSTEM

        messages = [
            {"role": "system", "content": _CLASSIFIER_SYSTEM},
            {
                "role": "user",
                "content": f"Triggered patterns: {fired_patterns}\n\nText excerpt:\n{excerpt}",
            },
        ]
        return await _scanner_ai_provider.complete(messages)

    app.state.injection_filter = InjectionFilter()
    app.state.output_scanner = OutputScanner(_secondary_classifier)
    logger.info("Security services initialized: InjectionFilter, OutputScanner")

    # Module registry — in-memory; populated by POST /modules/register at runtime (Phase 27)
    app.state.module_registry = {}

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


@app.get("/health")
async def health(request: Request) -> JSONResponse:
    """Health check — always 200. Reports obsidian status as non-blocking field."""
    obsidian_ok = False
    try:
        obsidian_ok = await request.app.state.obsidian_client.check_health()
    except Exception:
        pass
    return JSONResponse(
        {
            "status": "ok",
            "obsidian": "ok" if obsidian_ok else "degraded",
        }
    )
