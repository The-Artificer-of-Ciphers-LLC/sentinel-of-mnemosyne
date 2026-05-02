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

from app.composition import build_provider_router
from app.config import settings
from app.vault import ObsidianVault, VaultUnreachableError
from app.routes.message import router as message_router
from app.routes.modules import router as modules_router
from app.routes.note import router as note_router
from app.routes.status import router as status_router
from app.services.injection_filter import InjectionFilter
from app.services.message_processing import MessageProcessor
from app.services.model_selector import probe_embedding_model_loaded
from app.services.output_scanner import OutputScanner

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

    # Provider router + associated metadata (model registry, context window,
    # stop sequences, provider name) — extracted to app.composition.
    _provider_bundle = await build_provider_router(settings, http_client)
    app.state.model_registry = _provider_bundle.model_registry
    app.state.context_window = _provider_bundle.context_window
    app.state.lmstudio_stop_sequences = _provider_bundle.lmstudio_stop_sequences
    app.state.ai_provider = _provider_bundle.router
    # Expose provider name for /status endpoint (RD-05)
    app.state.ai_provider_name = _provider_bundle.ai_provider_name

    # Vault adapter — degrades gracefully if Obsidian is not running
    vault = ObsidianVault(
        http_client,
        settings.obsidian_api_url,
        settings.obsidian_api_key,
    )
    app.state.vault = vault

    # ADR-0001 startup contract — preserved end-to-end via the Vault seam:
    #   * vault reachable + persona 200 → log success
    #   * vault reachable + persona 404 → hard fail (operator setup error)
    #   * vault unreachable (transport failure) → warn + continue with fallback
    try:
        persona = await vault.read_persona()
    except VaultUnreachableError as exc:
        logger.warning(
            "Obsidian REST API unavailable at startup — memory features degraded. "
            "Ensure Obsidian is running with Local REST API plugin enabled "
            "(HTTP mode port 27123). %s",
            exc,
        )
    else:
        if persona is None:
            raise RuntimeError(
                "sentinel/persona.md missing from Vault — operator setup required (see README)"
            )
        logger.info("Persona loaded from vault (%d chars)", len(persona))

    # Security services — instantiated once, shared across all requests (SEC-01, SEC-02).
    # OutputScanner routes through the Sentinel's configured AI provider (AI-agnostic
    # design). Construction details live in the scanner itself; lifespan only injects
    # the provider router.
    app.state.injection_filter = InjectionFilter()
    app.state.output_scanner = OutputScanner(ai_provider=app.state.ai_provider)
    app.state.message_processor = MessageProcessor(
        vault=app.state.vault,
        ai_provider=app.state.ai_provider,
        injection_filter=app.state.injection_filter,
        output_scanner=app.state.output_scanner,
    )
    logger.info("Security services initialized: InjectionFilter, OutputScanner")

    # Module registry — in-memory; populated by POST /modules/register at runtime (Phase 27)
    app.state.module_registry = {}

    # 260427-vl1: note classifier + embedder for the vault sweeper
    from app.clients.embeddings import embed_texts as _embed_texts
    from app.services.note_classifier import classify_note as _classify_note

    async def _embedder_fn(texts: list[str]) -> list[list[float]]:
        api_base = settings.lmstudio_base_url or "http://host.docker.internal:1234"
        if not api_base.rstrip("/").endswith("/v1"):
            api_base = f"{api_base.rstrip('/')}/v1"
        # Provider prefix added at the call site, not stored in settings
        # (260502-1zv D-03).
        return await _embed_texts(
            texts,
            api_base=api_base,
            model=f"openai/{settings.embedding_model}",
        )

    app.state.note_classifier_fn = _classify_note
    app.state.note_embedder_fn = _embedder_fn

    # 260502-1zv D-02: probe LM Studio for the embedding model state at startup.
    # Graceful degrade — never raises. Surfaces via /health and via WARNING log
    # so operators see the problem at boot rather than via opaque
    # BadRequestError when the vault sweeper / note classifier first runs.
    embedding_loaded = await probe_embedding_model_loaded(
        http_client,
        settings.lmstudio_base_url,
        settings.embedding_model,
    )
    app.state.embedding_model_loaded = embedding_loaded
    if embedding_loaded:
        logger.info("Embedding model `%s` loaded ✓", settings.embedding_model)
    else:
        logger.warning(
            "Embedding model `%s` NOT loaded on LM Studio — vault sweeper / "
            "note classifier will fail until you `lms load %s`.",
            settings.embedding_model,
            settings.embedding_model,
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
    obsidian_ok = False
    try:
        obsidian_ok = await request.app.state.vault.check_health()
    except Exception:
        pass

    # Re-run the probe on each /health call rather than serving a cached
    # boot-time result — operators may load the model after startup, and a
    # stale "not_loaded" would mislead them. The probe itself is graceful
    # and bounded by a 5s timeout in probe_embedding_model_loaded.
    embedding_loaded = False
    try:
        embedding_loaded = await probe_embedding_model_loaded(
            request.app.state.http_client,
            settings.lmstudio_base_url,
            settings.embedding_model,
        )
    except Exception:
        pass

    return JSONResponse(
        {
            "status": "ok",
            "obsidian": "ok" if obsidian_ok else "degraded",
            "embedding_model": "loaded" if embedding_loaded else "not_loaded",
        }
    )
