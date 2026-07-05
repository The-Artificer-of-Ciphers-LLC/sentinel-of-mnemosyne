"""Foundry VTT event helpers — LLM narration and Discord notification dispatch (Phase 35).

Phase 42 (D-09, SC-6): the roll-narration chat call site reaches the LLM through
sentinel-core's POST /provider/complete via `SentinelCoreClient.complete()` (core
resolves provider/model — exo/LM Studio selection + fallback are centralized on
the core side). foundry.py no longer calls litellm directly for chat.

POSTs to Discord bot internal endpoint via httpx.AsyncClient (D-14).

Never raises on LLM or HTTP failure — D-13 fallback policy.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings
from sentinel_client import SentinelCoreClient

logger = logging.getLogger(__name__)

# pf2e -> sentinel-core chat handoff (D-09, SC-6). Single client instance built
# from existing settings (no new URL literal) — mirrors the module-level
# SentinelCoreClient singleton convention established in app/llm.py (42-04).
_core_client = SentinelCoreClient(
    base_url=settings.sentinel_core_url,
    api_key=settings.sentinel_api_key,
)


# Outcome display maps (shared by generate_foundry_narrative and build_narrative_fallback)
OUTCOME_EMOJIS: dict[str, str] = {
    "criticalSuccess": "🎯",
    "success": "✅",
    "failure": "❌",
    "criticalFailure": "💀",
}
OUTCOME_LABELS: dict[str, str] = {
    "criticalSuccess": "Critical Hit!",
    "success": "Success",
    "failure": "Failure",
    "criticalFailure": "Critical Failure!",
}

_NARRATOR_SYSTEM_PROMPT = (
    "You are a Pathfinder 2e DM narrator. Given a dice roll result, write ONE dramatic "
    "sentence (max 20 words) describing the outcome in third-person past-tense narrative. "
    "No headings. No bullet points. Use the actor and target names."
)


async def generate_foundry_narrative(
    actor_name: str,
    target_name: str | None,
    item_name: str | None,
    outcome: str | None,        # CR-02 fix: None for hidden-DC rolls
    roll_total: int,
    dc: int | None,
) -> str:
    """Generate a max-20-word dramatic narrative for a PF2e roll result (D-11).

    Returns plain string. On failure, returns "" — caller uses build_narrative_fallback.
    Never raises (D-13 fallback policy).

    Phase 42 (D-09, SC-6): no model/api_base/profile parameters — core resolves
    provider+model itself. This is the sole call site for this helper
    (app.routes.foundry._handle_roll), so the now-unused parameters were
    dropped from the signature rather than kept as vestigial dead weight.
    """
    outcome_label = OUTCOME_LABELS.get(outcome or "", outcome.capitalize() if outcome else "unknown")
    dc_str = str(dc) if dc is not None else "hidden"
    user_content = (
        f"Actor: {actor_name}. "
        f"Target: {target_name or 'none'}. "
        f"Item: {item_name or 'none'}. "
        f"Outcome: {outcome_label}. "
        f"Roll total: {roll_total}. "
        f"DC: {dc_str}."
    )
    try:
        async with httpx.AsyncClient() as client:
            result = await _core_client.complete(
                messages=[
                    {"role": "system", "content": _NARRATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                client=client,
            )
        content = result["content"] or ""
        return content.strip()
    except Exception as exc:
        logger.warning("generate_foundry_narrative: LLM call failed: %s", exc)
        return ""


def build_narrative_fallback(
    outcome: str,
    actor_name: str,
    target_name: str | None,
    roll_type: str,
    roll_total: int,
    dc: int | None,
    dc_hidden: bool,
) -> str:
    """Build plain-text fallback narrative when LLM is unavailable (D-13).

    Format: "{emoji} {label} | {actor}{target_or_type} | Roll: {total} {dc_str}"
    """
    emoji = OUTCOME_EMOJIS.get(outcome, "🎲")
    label = OUTCOME_LABELS.get(outcome, outcome.capitalize() if outcome else "Roll")
    target_or_type = f" → {target_name}" if target_name else f" ({roll_type})"
    dc_str = f"vs DC {dc}" if not dc_hidden and dc is not None else ""
    result = f"{emoji} {label} | {actor_name}{target_or_type} | Roll: {roll_total}"
    if dc_str:
        result += f" {dc_str}"
    return result.strip()


async def notify_discord_bot(payload: dict, bot_url: str, api_key: str) -> None:
    """POST embed payload to Discord bot internal endpoint (D-14).

    Fire-and-forget: errors are logged but not raised (D-13 policy).
    Uses per-call AsyncClient — bot endpoint is not high-frequency.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{bot_url}/internal/notify",
                json=payload,
                headers={"X-Sentinel-Key": api_key},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("notify_discord_bot: POST to %s failed: %s", bot_url, exc)
