"""
pf2e-module — Pathfinder 2e FastAPI service.

Endpoints:
  GET /healthz — module health check (proxied by sentinel-core at GET /modules/pathfinder/healthz)
  POST /npc/create — create NPC in Obsidian (NPC-01)
  POST /npc/update — update NPC fields (NPC-02)
  POST /npc/show   — show NPC summary (NPC-03)
  POST /npc/relate — add NPC relationship (NPC-04, Plan 05)
  POST /npc/import — bulk import from Foundry JSON (NPC-05, Plan 05)

Startup:
  lifespan calls POST /modules/register on sentinel-core with exponential backoff retry.
  If all 5 attempts fail, module exits with code 1 (Docker restart policy brings it back).
  lifespan also creates a persistent ObsidianClient on app.state for NPC CRUD endpoints (D-27).

Per D-15 through D-18 in Phase 28 CONTEXT.md; updated in Phase 29 for NPC CRUD.
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
from app.routes.npc import router as npc_router
import app.routes.npc as _npc_module

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Registration payload per D-17.
# name: "pathfinder" — module registry name (D-11). Different from Docker profile name "pf2e" (D-12).
# base_url: "http://pf2e-module:8000" — Docker service name must match (D-17, Pitfall 3).
# All 5 NPC routes registered upfront (Pitfall 7 — all routes must appear at startup).
REGISTRATION_PAYLOAD = {
    "name": "pathfinder",
    "base_url": "http://pf2e-module:8000",
    "routes": [
        {"path": "healthz", "description": "pf2e module health check"},
        {"path": "npc/create", "description": "Create NPC in Obsidian (NPC-01)"},
        {"path": "npc/update", "description": "Update NPC fields (NPC-02)"},
        {"path": "npc/show", "description": "Show NPC summary (NPC-03)"},
        {"path": "npc/relate", "description": "Add NPC relationship (NPC-04)"},
        {"path": "npc/import", "description": "Bulk import NPCs from Foundry JSON (NPC-05)"},
    ],
}


async def _register_with_retry(client: httpx.AsyncClient) -> None:
    """Register with Sentinel Core — 5 attempts, exponential backoff 1s->2s->4s->8s->16s.

    Exits with SystemExit(1) if all attempts fail so Docker restart policy can recover (D-16).
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
    """Startup: register with Sentinel Core + create persistent ObsidianClient."""
    # Registration uses a short-lived client (registration is a one-shot op)
    async with httpx.AsyncClient() as client:
        await _register_with_retry(client)

    # Persistent ObsidianClient for NPC CRUD endpoints (D-27).
    # The client lives for the module's full lifetime — created once, shared across requests.
    # Also set on the module-level `obsidian` variable so tests can patch it.
    async with httpx.AsyncClient() as obsidian_http_client:
        obsidian_client = ObsidianClient(
            http_client=obsidian_http_client,
            base_url=settings.obsidian_base_url,
            api_key=settings.obsidian_api_key,
        )
        app.state.obsidian_client = obsidian_client
        _npc_module.obsidian = obsidian_client
        yield
    # obsidian_http_client closes when the async with block exits (on shutdown)
    _npc_module.obsidian = None


app = FastAPI(
    title="pf2e Module",
    version="0.1.0",
    description="Pathfinder 2e module for Sentinel of Mnemosyne",
    lifespan=lifespan,
)

app.include_router(npc_router)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Module health check — proxied by sentinel-core at GET /modules/pathfinder/healthz.

    Returns {"status": "ok", "module": "pathfinder"} per D-18.
    """
    return JSONResponse({"status": "ok", "module": "pathfinder"})
