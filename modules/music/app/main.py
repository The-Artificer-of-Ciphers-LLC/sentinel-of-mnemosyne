"""
music-module — Music Lesson Tracker FastAPI service (Phase 48 scaffold, MUS-01/MUS-02).

Endpoints:
  GET /healthz — module health check (proxied by sentinel-core at GET /modules/music/healthz)

Startup:
  lifespan calls POST /modules/register on sentinel-core with exponential backoff retry.
  If all 5 attempts fail, module exits with code 1 (Docker restart policy brings it back).
  lifespan also creates a persistent ObsidianClient on app.state (core-only, D-03/MUS-02)
  and starts a 30s re-registration heartbeat so a sentinel-core restart self-heals (D-12).

Phase-48 scope is deliberately minimal: only the healthz route is registered.
Real practice-logging / idea-capture / history-query / routine-builder routes
arrive in Phases 49+ — this module ships with zero Core code changes (MUS-01).
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import settings
from app.obsidian import ObsidianClient
from app.seed import seed_music_hub

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Registration payload (D-11, D-12).
# name: "music" — module registry name. Docker service name is also
# "music-module" (no pf2e-style profile/registry-name split — that split
# only exists because pf2e's Docker service predates its logical rename).
# base_url: "http://music-module:8000" — must match the compose service name.
# Minimal route set for Phase 48: healthz only.
REGISTRATION_PAYLOAD = {
    "name": "music",
    "base_url": "http://music-module:8000",
    "routes": [
        {"path": "healthz", "description": "music module health check"},
    ],
}


async def _registration_heartbeat() -> None:
    """Re-register with Sentinel Core every 30 s so a sentinel-core restart self-heals.

    Non-fatal: a failed heartbeat logs a warning and retries on the next tick.
    Cancelled cleanly by the lifespan on shutdown.
    """
    while True:
        await asyncio.sleep(30)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{settings.sentinel_core_url}/modules/register",
                    json=REGISTRATION_PAYLOAD,
                    headers={"X-Sentinel-Key": os.environ.get("SENTINEL_API_KEY", "")},
                    timeout=10.0,
                )
                resp.raise_for_status()
                logger.debug("Heartbeat: re-registered with Sentinel Core")
        except Exception as exc:
            logger.warning("Heartbeat: re-registration failed: %s", exc)


async def _register_with_retry(client: httpx.AsyncClient) -> None:
    """Register with Sentinel Core — 5 attempts, exponential backoff 1s->2s->4s->8s->16s.

    Exits with SystemExit(1) if all attempts fail so Docker restart policy can recover.
    """
    delays = [1, 2, 4, 8, 16]
    for attempt, delay in enumerate(delays, start=1):
        try:
            resp = await client.post(
                f"{settings.sentinel_core_url}/modules/register",
                json=REGISTRATION_PAYLOAD,
                headers={"X-Sentinel-Key": os.environ.get("SENTINEL_API_KEY", "")},
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info("Registered with Sentinel Core (attempt %d)", attempt)
            return
        except Exception as exc:
            logger.warning("Registration attempt %d/%d failed: %s", attempt, len(delays), exc)
            if attempt < len(delays):
                await asyncio.sleep(delay)
    logger.error("All %d registration attempts failed — exiting", len(delays))
    raise SystemExit(1)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: register with Sentinel Core + create persistent core-only ObsidianClient."""
    # Registration uses a short-lived client (registration is a one-shot op)
    async with httpx.AsyncClient() as client:
        await _register_with_retry(client)

    # Persistent ObsidianClient (core-only, D-03/MUS-02) for future vault-write routes.
    # The client lives for the module's full lifetime — created once, shared across requests.
    async with httpx.AsyncClient() as obsidian_http_client:
        obsidian_client = ObsidianClient(
            http_client=obsidian_http_client,
            base_url=settings.obsidian_base_url,
            api_key=settings.obsidian_api_key,
        )
        app.state.obsidian_client = obsidian_client
        # Seed the music/ hub-mesh (MUS-05, D-08). Graceful: a vault outage at
        # startup is logged and swallowed, never crashes the module (mirrors
        # the degrade-gracefully shape of ObsidianClientCore's own methods).
        try:
            await seed_music_hub(obsidian_client)
        except Exception:
            logger.exception("Failed to seed music/ hub-mesh at startup")
        heartbeat_task = asyncio.create_task(_registration_heartbeat())
        try:
            yield
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
    # obsidian_http_client closes when the async with block exits (on shutdown)


app = FastAPI(
    title="Music Module",
    version="0.1.0",
    description="Music Lesson Tracker module for Sentinel of Mnemosyne",
    lifespan=lifespan,
)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Module health check — proxied by sentinel-core at GET /modules/music/healthz.

    Returns {"status": "ok", "module": "music"}.
    """
    return JSONResponse({"status": "ok", "module": "music"})
