"""
pf2e-module — Pathfinder 2e FastAPI service.

Endpoints:
  GET /healthz — module health check (proxied by sentinel-core at GET /modules/pathfinder/healthz)

Startup:
  lifespan calls POST /modules/register on sentinel-core with exponential backoff retry.
  If all 5 attempts fail, module exits with code 1 (Docker restart policy brings it back).

Per D-15 through D-18 in Phase 28 CONTEXT.md.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SENTINEL_CORE_URL = os.getenv("SENTINEL_CORE_URL", "http://sentinel-core:8000")

# Registration payload per D-17.
# name: "pathfinder" — module registry name (D-11). Different from Docker profile name "pf2e" (D-12).
# base_url: "http://pf2e-module:8000" — Docker service name must match (D-17, Pitfall 3).
REGISTRATION_PAYLOAD = {
    "name": "pathfinder",
    "base_url": "http://pf2e-module:8000",
    "routes": [{"path": "healthz", "description": "pf2e module health check"}],
}


async def _register_with_retry(client: httpx.AsyncClient) -> None:
    """Register with Sentinel Core — 5 attempts, exponential backoff 1s→2s→4s→8s→16s.

    Exits with SystemExit(1) if all attempts fail so Docker restart policy can recover (D-16).
    """
    delays = [1, 2, 4, 8, 16]
    for attempt, delay in enumerate(delays, start=1):
        try:
            resp = await client.post(
                f"{SENTINEL_CORE_URL}/modules/register",
                json=REGISTRATION_PAYLOAD,
                headers={"X-Sentinel-Key": os.getenv("SENTINEL_API_KEY", "")},
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
    """Startup: register with Sentinel Core. Short-lived httpx client for registration only."""
    async with httpx.AsyncClient() as client:
        await _register_with_retry(client)
    yield
    # No persistent resources to clean up in Phase 28 skeleton.


app = FastAPI(
    title="pf2e Module",
    version="0.1.0",
    description="Pathfinder 2e module for Sentinel of Mnemosyne",
    lifespan=lifespan,
)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Module health check — proxied by sentinel-core at GET /modules/pathfinder/healthz.

    Returns {"status": "ok", "module": "pathfinder"} per D-18.
    """
    return JSONResponse({"status": "ok", "module": "pathfinder"})
