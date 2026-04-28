"""
pf2e-module — Pathfinder 2e FastAPI service.

Endpoints:
  GET /healthz — module health check (proxied by sentinel-core at GET /modules/pathfinder/healthz)
  POST /npc/create         — create NPC in Obsidian (NPC-01)
  POST /npc/update         — update NPC fields (NPC-02)
  POST /npc/show           — show NPC summary (NPC-03)
  POST /npc/relate         — add NPC relationship (NPC-04)
  POST /npc/import         — bulk import from Foundry JSON (NPC-05)
  POST /npc/export-foundry — export Foundry VTT actor JSON (OUT-01)
  POST /npc/token          — generate Midjourney /imagine prompt (OUT-02)
  POST /npc/token-image    — upload Midjourney token image to vault (OUT-02 ext)
  POST /npc/stat           — return structured stat block data (OUT-03)
  POST /npc/pdf            — generate PDF stat card (OUT-04, embeds token image)
  POST /npc/say            — in-character NPC dialogue with mood tracking (DLG-01..03)
  POST /harvest            — monster harvest report with Medicine/Crafting DCs and vendor values (HRV-01..06)
  POST /rule/query         — PF2e Remaster rules RAG engine (RUL-01..04)
  POST /rule/show          — list cached rulings by topic (RUL-03)
  POST /rule/history       — recent rulings across all topics (RUL-03)
  POST /rule/list          — enumerate topic folders (RUL-03)
  GET /npcs/               — list all Sentinel NPCs (FVT-04)
  GET /npcs/{slug}/foundry-actor — return PF2e actor JSON for NPC (FVT-04)

Startup:
  lifespan calls POST /modules/register on sentinel-core with exponential backoff retry.
  If all 5 attempts fail, module exits with code 1 (Docker restart policy brings it back).
  lifespan also creates a persistent ObsidianClient on app.state for NPC CRUD endpoints (D-27),
  loads the harvest-tables.yaml seed into the harvest route's module-level singleton, and
  (Phase 33) loads rules-corpus.json + aon-url-map.json and builds the embedding index for
  the rule route's three module-level singletons (obsidian, rules_index, aon_url_map).

Per D-15 through D-18 in Phase 28 CONTEXT.md; updated in Phase 29 for NPC CRUD,
extended in Phase 30 for NPC outputs (OUT-01..OUT-04), Phase 31 for dialogue,
Phase 32 for monster harvesting (HRV-01..06), Phase 33 for rules engine (RUL-01..04),
Phase 36 for Foundry NPC pull import (FVT-04).
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.config import settings
from app.harvest import load_harvest_tables
from app.obsidian import ObsidianClient
import app.routes.foundry as _foundry_module
import app.routes.harvest as _harvest_module
import app.routes.npc as _npc_module
import app.routes.npcs as _npcs_module
import app.routes.rule as _rule_module
import app.routes.session as _session_module
from app.routes.foundry import router as foundry_router
from app.routes.harvest import router as harvest_router
from app.routes.npc import router as npc_router
from app.routes.npcs import router as npcs_router
from app.routes.rule import router as rule_router
from app.routes.session import router as session_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Registration payload per D-17.
# name: "pathfinder" — module registry name (D-11). Different from Docker profile name "pf2e" (D-12).
# base_url: "http://pf2e-module:8000" — Docker service name must match (D-17, Pitfall 3).
# All routes registered upfront (Pitfall 7 — all routes must appear at startup).
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
        {"path": "npc/export-foundry", "description": "Export NPC as Foundry VTT actor JSON (OUT-01)"},
        {"path": "npc/token", "description": "Generate Midjourney token prompt (OUT-02)"},
        {"path": "npc/token-image", "description": "Upload NPC token image to vault (OUT-02 extension)"},
        {"path": "npc/stat", "description": "Return structured stat block data (OUT-03)"},
        {"path": "npc/pdf", "description": "Generate PDF stat card (OUT-04)"},
        {"path": "npc/say", "description": "In-character NPC dialogue with mood tracking (DLG-01..03)"},
        {"path": "harvest", "description": "Monster harvest report with Medicine/Crafting DCs and vendor values (HRV-01..06)"},
        {"path": "rule", "description": "PF2e Remaster rules RAG engine with Paizo citations (RUL-01..04)"},
        {"path": "session", "description": "Session notes — start/log/end/show/undo with Obsidian persistence (SES-01..03)"},
        {"path": "foundry/event", "description": "Receive Foundry VTT game events (FVT-01..03)"},
        {"path": "npcs/", "description": "List all Sentinel NPCs (FVT-04)"},
        {"path": "npcs/{slug}/foundry-actor", "description": "Return PF2e actor JSON for NPC (FVT-04)"},
        {"path": "ingest", "description": "Bulk import PF2e archive subfolder (260427-cui)"},
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
    """Startup: register with Sentinel Core + create persistent ObsidianClient + load harvest + rules seeds."""
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
        # Phase 32: wire the harvest route's module-level singletons (PATTERNS.md §3 Analog D).
        # load_harvest_tables raises fail-fast on missing or malformed YAML — Docker restart
        # policy surfaces the problem at startup rather than at first /harvest request.
        _harvest_module.obsidian = obsidian_client
        _harvest_module.harvest_tables = load_harvest_tables(
            Path(__file__).parent.parent / "data" / "harvest-tables.yaml"
        )
        # Phase 33: wire the rule route's module-level singletons.
        # Function-scope imports (L-4) — app.rules + app.llm import chain stays isolated
        # until lifespan runs, keeping module-load test-infra compatible.
        from app.llm import embed_texts
        from app.rules import build_rules_index, load_aon_url_map, load_rules_corpus

        _rule_module.obsidian = obsidian_client
        _rule_module.aon_url_map = load_aon_url_map(
            Path(__file__).parent.parent / "data" / "aon-url-map.json"
        )
        _rule_corpus_chunks = load_rules_corpus(
            Path(__file__).parent.parent / "data" / "rules-corpus.json"
        )

        async def _rule_embed_fn(texts: list[str]) -> list[list[float]]:
            # Closure captures settings at definition time so env overrides of
            # rules_embedding_model are honoured on every call.
            return await embed_texts(
                texts,
                api_base=settings.litellm_api_base or None,
                model=settings.rules_embedding_model,
            )

        # L-10 fail-fast: build_rules_index awaits _rule_embed_fn -> embed_texts, which
        # raises if LM Studio is unreachable or the embedding model isn't loaded. The
        # exception propagates to FastAPI startup -> SystemExit -> Docker restart-loop,
        # so the operator sees the error in the container log instead of at first /query.
        _rule_module.rules_index = await build_rules_index(
            _rule_corpus_chunks, _rule_embed_fn
        )
        logger.info(
            "Phase 33 rules engine: loaded %d corpus chunks, embedding model=%s",
            len(_rule_corpus_chunks), settings.rules_embedding_model,
        )
        # Phase 34: wire the session route's module-level singletons.
        _session_module.obsidian = obsidian_client
        # NPC roster cache: load from vault at startup for fast-pass wikilink rewriting (D-22).
        # If vault is unreachable, start with empty cache (non-fatal — next session start retries).
        try:
            from app.session import build_npc_roster_cache
            _session_module.npc_roster_cache = await build_npc_roster_cache(obsidian_client)
            logger.info(
                "Phase 34 session engine: NPC roster cache loaded (%d entries)",
                len(_session_module.npc_roster_cache),
            )
        except Exception as exc:
            logger.warning(
                "Phase 34 session engine: NPC roster cache load failed (%s) — starting empty",
                exc,
            )
            _session_module.npc_roster_cache = {}
        # Phase 35: wire foundry route's module-level discord_bot_url singleton (D-14).
        _foundry_module.discord_bot_url = settings.discord_bot_internal_url
        # Phase 36: wire npcs route's module-level obsidian singleton.
        _npcs_module.obsidian = obsidian_client
        # 260427-cui: wire ingest route's module-level obsidian singleton.
        import app.routes.ingest as _ingest_module
        _ingest_module.obsidian = obsidian_client
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
    _npc_module.obsidian = None
    _harvest_module.obsidian = None
    _harvest_module.harvest_tables = None
    _rule_module.obsidian = None
    _rule_module.rules_index = None
    _rule_module.aon_url_map = None
    _session_module.obsidian = None
    _session_module.npc_roster_cache = None
    _foundry_module.discord_bot_url = ""
    _npcs_module.obsidian = None
    import app.routes.ingest as _ingest_module_shutdown
    _ingest_module_shutdown.obsidian = None


app = FastAPI(
    title="pf2e Module",
    version="0.1.0",
    description="Pathfinder 2e module for Sentinel of Mnemosyne",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS middleware with Private Network Access support (Phase 35 gap closure)
#
# Starlette 1.0+ supports allow_private_network natively — it injects the
# Access-Control-Allow-Private-Network header only on OPTIONS preflight responses,
# as required by the WICG PNA spec. No subclass needed.
#
# allow_origin_regex covers per-user Forge subdomains (https://*.forge-vtt.com).
# Starlette does exact-string matching on allow_origins so the wildcard pattern
# must go in allow_origin_regex instead.
#
# X-Sentinel-Key is a non-standard header — must be listed in allow_headers or
# the CORS preflight will block credentialed requests.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://forge-vtt.com",
        "http://localhost:30000",
        "http://localhost:8000",
        "http://127.0.0.1:30000",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"https://[a-zA-Z0-9-]+\.forge-vtt\.com",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Sentinel-Key"],
    allow_credentials=False,
    allow_private_network=True,
)

# D-10: Serve Foundry JS module assets (module.json, sentinel-connector.zip).
# IMPORTANT: mount StaticFiles BEFORE include_router(foundry_router) to prevent
# the /foundry prefix router from capturing /foundry/static paths (Pitfall 3).
FOUNDRY_CLIENT_DIR = Path(__file__).parent.parent / "foundry-client"
if FOUNDRY_CLIENT_DIR.exists():
    app.mount(
        "/foundry/static",
        StaticFiles(directory=str(FOUNDRY_CLIENT_DIR)),
        name="foundry_static",
    )

# Phase 35: Foundry VTT event ingest route (FVT-01..03) — must come AFTER StaticFiles mount.
app.include_router(foundry_router)
app.include_router(npc_router)
app.include_router(harvest_router)
app.include_router(rule_router)
app.include_router(session_router)
# Also mount at /modules/pathfinder/session so integration tests that simulate
# the sentinel-core proxy path work against the pathfinder app directly.
app.include_router(session_router, prefix="/modules/pathfinder")
# Phase 36: NPC listing and Foundry actor export routes (FVT-04).
app.include_router(npcs_router)
# Quick task 260427-cui: PF2e archive ingester (generalised from cartosia importer).
from app.routes.ingest import router as ingest_router  # noqa: E402
app.include_router(ingest_router)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Module health check — proxied by sentinel-core at GET /modules/pathfinder/healthz.

    Returns {"status": "ok", "module": "pathfinder"} per D-18.
    """
    return JSONResponse({"status": "ok", "module": "pathfinder"})
