"""POST /foundry/event — Foundry VTT event ingest route (FVT-01..03).

Receives roll and chat events from the Foundry JS module (sentinel-connector.js).
Validates X-Sentinel-Key, dispatches to app.foundry helpers for LLM narration
and Discord notification.

Module-level singleton:
  discord_bot_url — set by main.py lifespan (set to settings.discord_bot_internal_url)

Tests patch app.foundry.generate_foundry_narrative / app.foundry.notify_discord_bot.
"""
from __future__ import annotations

import logging
import os
from typing import Annotated, Literal, Optional, Union

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import app.foundry as _foundry
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/foundry", tags=["foundry"])

# Module-level singleton — set by main.py lifespan.
# Holds the Discord bot internal URL so tests can patch it without touching settings.
discord_bot_url: str = ""

# X-Sentinel-Key — read from env (mirrors other route modules).
_SENTINEL_API_KEY: str = os.environ.get("SENTINEL_API_KEY", "")


# ---------------------------------------------------------------------------
# Pydantic models (D-05, D-06)
# ---------------------------------------------------------------------------

class FoundryRollEvent(BaseModel):
    event_type: Literal["roll"]
    roll_type: str
    actor_name: str
    target_name: Optional[str] = None
    outcome: Optional[str] = None  # CR-01: None for hidden-DC rolls where outcome is unknown
    roll_total: int
    dc: Optional[int] = None
    dc_hidden: bool = False
    item_name: Optional[str] = None
    timestamp: str


class FoundryChatEvent(BaseModel):
    event_type: Literal["chat"]
    actor_name: str
    content: str
    timestamp: str


FoundryEventUnion = Annotated[
    Union[FoundryRollEvent, FoundryChatEvent],
    Field(discriminator="event_type"),
]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/event")
async def foundry_event(
    req: FoundryEventUnion,
    x_sentinel_key: str = Header(default=""),
) -> JSONResponse:
    """Receive a Foundry VTT event (roll or chat) from sentinel-connector.js (FVT-01..03).

    Auth: X-Sentinel-Key header required — 401 if missing or wrong.
    Validation: Pydantic discriminated union on event_type — 422 if schema invalid.
    """
    # Resolve API key at request time (respects runtime env changes in tests)
    api_key = os.environ.get("SENTINEL_API_KEY", _SENTINEL_API_KEY)
    if x_sentinel_key != api_key:
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})

    if isinstance(req, FoundryRollEvent):
        return await _handle_roll(req)
    # FoundryChatEvent is the only other discriminated branch
    return _handle_chat(req)  # type: ignore[arg-type]


async def _handle_roll(event: FoundryRollEvent) -> JSONResponse:
    """Process a roll event: narrate via LLM, dispatch to Discord bot (FVT-02, FVT-03)."""
    model = settings.foundry_narration_model or settings.litellm_model
    api_base = settings.litellm_api_base or None

    # D-11: LLM narrative (max 20 words)
    narrative = await _foundry.generate_foundry_narrative(
        actor_name=event.actor_name,
        target_name=event.target_name,
        item_name=event.item_name,
        outcome=event.outcome,
        roll_total=event.roll_total,
        dc=event.dc,
        model=model,
        api_base=api_base,
    )
    # D-13: LLM failure fallback — plain-text summary
    if not narrative:
        narrative = _foundry.build_narrative_fallback(
            outcome=event.outcome,
            actor_name=event.actor_name,
            target_name=event.target_name,
            roll_type=event.roll_type,
            roll_total=event.roll_total,
            dc=event.dc,
            dc_hidden=event.dc_hidden,
        )

    # D-14: Notify Discord bot internal endpoint
    bot_url = discord_bot_url or settings.discord_bot_internal_url
    sentinel_key = os.environ.get("SENTINEL_API_KEY", _SENTINEL_API_KEY)
    notify_payload = {
        "event_type": "roll",
        "roll_type": event.roll_type,
        "actor_name": event.actor_name,
        "target_name": event.target_name,
        "outcome": event.outcome,
        "roll_total": event.roll_total,
        "dc": event.dc,
        "dc_hidden": event.dc_hidden,
        "item_name": event.item_name,
        "narrative": narrative,
    }
    await _foundry.notify_discord_bot(notify_payload, bot_url, sentinel_key)

    logger.info(
        "foundry_event: roll actor=%s outcome=%s roll=%d dc=%s",
        event.actor_name,
        event.outcome,
        event.roll_total,
        event.dc,
    )
    return JSONResponse({"status": "ok", "event_type": "roll"})


def _handle_chat(event: FoundryChatEvent) -> JSONResponse:
    """Process a forwarded chat event (D-06). No Discord notify in Phase 35 MVP."""
    logger.info(
        "foundry_event: chat actor=%s content_len=%d",
        event.actor_name,
        len(event.content),
    )
    return JSONResponse({"status": "ok", "event_type": "chat"})
