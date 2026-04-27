"""Foundry VTT event helpers — LLM narration and Discord notification dispatch (Phase 35).

Calls acompletion_with_profile() for roll narration (D-11).
POSTs to Discord bot internal endpoint via httpx.AsyncClient (D-14).

Never raises on LLM or HTTP failure — D-13 fallback policy.
"""
from __future__ import annotations

import logging

import httpx

from sentinel_shared.llm_call import acompletion_with_profile
from sentinel_shared.model_profiles import ModelProfile

logger = logging.getLogger(__name__)


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
    model: str,
    api_base: str | None = None,
    profile: ModelProfile | None = None,
) -> str:
    """Generate a max-20-word dramatic narrative for a PF2e roll result (D-11).

    Returns plain string. On failure, returns "" — caller uses build_narrative_fallback.
    Never raises (D-13 fallback policy).
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
        response = await acompletion_with_profile(
            model=model,
            messages=[
                {"role": "system", "content": _NARRATOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            profile=profile,
            api_base=api_base,
            timeout=15.0,
        )
        content = response.choices[0].message.content or ""
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
