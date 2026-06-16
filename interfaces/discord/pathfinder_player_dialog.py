"""Multi-step PF2E onboarding dialog: state machine + draft I/O.

Owns:
  - STEPS / QUESTIONS module-level constants (D-13)
  - start_dialog / resume_dialog / consume_as_answer / cancel_dialog (D-12, D-15)

Draft persistence lives in pathfinder_player_draft_store; this module owns
Discord thread lifecycle and dialog step policy.
"""
from __future__ import annotations

import datetime
import logging

import discord

from pathfinder_player_dialog_outcome import DialogOutcome
from pathfinder_player_draft_store import (
    delete_draft,
    draft_path,
    load_draft,
    save_draft,
)
from pathfinder_player_adapter import _VALID_STYLE_PRESETS

logger = logging.getLogger(__name__)

__all__ = [
    "DialogOutcome",
    "QUESTIONS",
    "STEPS",
    "cancel_dialog",
    "cancel_dialog_outcome",
    "consume_as_answer",
    "consume_as_answer_outcome",
    "delete_draft",
    "draft_path",
    "load_draft",
    "resume_dialog",
    "save_draft",
    "start_dialog",
]


# --- Module-level constants (D-13, locked verbatim against 38-01 RED tests) ---

STEPS: tuple[str, str, str] = ("character_name", "preferred_name", "style_preset")

QUESTIONS: dict[str, str] = {
    "character_name": "What is your character's name?",
    "preferred_name": "How would you like me to address you?",
    "style_preset": (
        "Pick a style — reply with a number or the name:\n"
        "1) Tactician\n"
        "2) Lorekeeper\n"
        "3) Cheerleader\n"
        "4) Rules-Lawyer Lite"
    ),
}


# --- Dialog lifecycle ---


async def start_dialog(
    *,
    invoking_channel,
    user_id: str,
    http_client,
    message_author_display_name: str | None = None,
    display_name: str | None = None,
) -> "discord.Thread":
    """Create the onboarding thread, persist the first draft, post Q1.

    Caller MUST provide a display name as either ``message_author_display_name``
    (legacy 38-04 contract) or ``display_name`` (38-06 adapter contract). The
    no-args branch in PlayerStartCommand substitutes ``f"player {user_id}"``
    if request.author_display_name is None.
    """
    effective_name = message_author_display_name if message_author_display_name is not None else display_name
    if effective_name is None:
        raise TypeError(
            "start_dialog requires either message_author_display_name or display_name"
        )
    name = f"Onboarding — {effective_name}"[:100]
    # Discord threads cannot host child threads. discord.Thread doesn't expose
    # create_thread at all — calling it raises AttributeError. When the user runs
    # `:pf player start` from inside an existing Sentinel chat thread (the dominant
    # flow), hoist the onboarding thread onto the parent text channel so it remains
    # a sibling, not a child. We duck-type via AttributeError because the test
    # conftest stubs discord.Thread = object, which makes isinstance() useless.
    try:
        thread = await invoking_channel.create_thread(
            name=name,
            type=discord.ChannelType.public_thread,
            auto_archive_duration=60,
        )
    except AttributeError:
        parent = getattr(invoking_channel, "parent", None)
        if parent is None:
            raise RuntimeError(
                "Cannot create onboarding thread: invoking thread has no parent channel"
            )
        thread = await parent.create_thread(
            name=name,
            type=discord.ChannelType.public_thread,
            auto_archive_duration=60,
        )
    # Register the new thread so on_message routes through Sentinel (D-11 inverse).
    from bot import SENTINEL_THREAD_IDS, _persist_thread_id

    SENTINEL_THREAD_IDS.add(thread.id)
    try:
        await _persist_thread_id(thread.id)
    except Exception:
        logger.exception("failed to persist thread id %s", thread.id)

    draft = {
        "step": STEPS[0],
        "thread_id": thread.id,
        "user_id": str(user_id),
        "started_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
    await save_draft(thread.id, str(user_id), draft, http_client=http_client)
    await thread.send(QUESTIONS[STEPS[0]])
    return thread


async def resume_dialog(*, thread, user_id: str, http_client) -> str:
    """Return the prompt for the draft's CURRENT step. Does NOT mutate the draft.

    The caller (bot.py on_message via response_renderer) is responsible for
    posting the returned text to the thread. Sending here would double-post.
    """
    draft = await load_draft(thread.id, str(user_id), http_client=http_client)
    if draft is None:
        # Defensive: caller pre-checks; if we got here, restart at step 0 without persisting.
        return QUESTIONS[STEPS[0]]
    step = draft.get("step", STEPS[0])
    return QUESTIONS.get(step, QUESTIONS[STEPS[0]])


# --- Step advancement / completion / cancel ---


async def _archive_and_discard(thread) -> None:
    """Archive the thread (swallowing already-archived HTTPException) and discard the id."""
    try:
        await thread.edit(archived=True, reason="onboarding lifecycle")
    except discord.HTTPException:
        logger.info(
            "thread %s already archived or transient archive failure", thread.id
        )
    from bot import SENTINEL_THREAD_IDS

    SENTINEL_THREAD_IDS.discard(thread.id)


def _normalise_style_preset(answer: str) -> str | None:
    """Resolve a player's style-preset answer to a canonical preset name, or None.

    Accepts three input forms:
      1. Numeric index 1..4 matching the preset's position in _VALID_STYLE_PRESETS
         (e.g. "1" → "Tactician"). Trailing punctuation tolerated ("1." → "Tactician").
      2. Case-insensitive name match (e.g. "tactician" → "Tactician") — RESEARCH Q10.
      3. Case-insensitive name match with trailing punctuation stripped (UAT G-05).

    Whitespace on both sides is always stripped first.
    """
    cleaned = (answer or "").strip().rstrip(".,!?;:").strip()
    if not cleaned:
        return None
    # Numeric index path (1..len(_VALID_STYLE_PRESETS)).
    if cleaned.isdigit():
        idx = int(cleaned) - 1
        if 0 <= idx < len(_VALID_STYLE_PRESETS):
            return _VALID_STYLE_PRESETS[idx]
        return None
    # Name match (case-insensitive).
    target = cleaned.lower()
    for preset in _VALID_STYLE_PRESETS:
        if preset.lower() == target:
            return preset
    return None


async def consume_as_answer_outcome(
    *,
    thread,
    user_id: str,
    message_text: str,
    sentinel_client,
    http_client,
) -> DialogOutcome:
    """Advance the dialog one step. On final step, POST /player/onboard + cleanup.

    Returns an explicit dialog outcome. The caller renders ``message`` outcomes;
    ``suppressed`` means this module already posted directly, which is required
    for terminal send-before-archive ordering (UAT G-04).
    """
    draft = await load_draft(thread.id, str(user_id), http_client=http_client)
    if draft is None:
        # Defensive — caller (dialog_router) pre-checks. Safety net: do nothing.
        return DialogOutcome.suppressed()
    step = draft.get("step", STEPS[0])
    answer = (message_text or "").strip()

    if step == "style_preset":
        normalised = _normalise_style_preset(answer)
        if normalised is None:
            return DialogOutcome.message(
                f"`{answer}` isn't a valid style. Please choose one of: "
                + ", ".join(_VALID_STYLE_PRESETS)
                + "."
            )
        draft["style_preset"] = normalised
    elif step in ("character_name", "preferred_name"):
        if not answer:
            return DialogOutcome.message(QUESTIONS[step])
        draft[step] = answer

    idx = STEPS.index(step)
    if idx + 1 < len(STEPS):
        draft["step"] = STEPS[idx + 1]
        await save_draft(thread.id, str(user_id), draft, http_client=http_client)
        return DialogOutcome.message(QUESTIONS[STEPS[idx + 1]])

    # Final step — POST to /player/onboard with the four-field payload.
    payload = {
        "user_id": str(user_id),
        "character_name": draft["character_name"],
        "preferred_name": draft["preferred_name"],
        "style_preset": draft["style_preset"],
    }
    result = await sentinel_client.post_to_module(
        "modules/pathfinder/player/onboard", payload, http_client
    )
    path = result.get("path", "?") if isinstance(result, dict) else "?"
    await delete_draft(thread.id, str(user_id), http_client=http_client)
    success = (
        f"Player onboarded as `{draft['preferred_name']}` "
        f"({draft['style_preset']}). Profile: `{path}`"
    )
    # Send success BEFORE archive — any message after archive auto-unarchives
    # the thread, defeating the lifecycle invariant (UAT G-04).
    try:
        await thread.send(success)
    except Exception:
        logger.warning("consume_as_answer: success send failed for %s", thread.id)
    await _archive_and_discard(thread)
    return DialogOutcome.suppressed()


async def consume_as_answer(
    *,
    thread,
    user_id: str,
    message_text: str,
    sentinel_client,
    http_client,
) -> str:
    """Compatibility wrapper returning the historical text/suppression sentinel."""
    outcome = await consume_as_answer_outcome(
        thread=thread,
        user_id=user_id,
        message_text=message_text,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )
    return outcome.to_legacy_text()


async def cancel_dialog_outcome(*, thread, user_id: str, http_client) -> DialogOutcome:
    """Delete the draft, post the cancel ack, then archive the thread.

    Returns a renderable dialog outcome. On the with-draft path, posts the ack
    directly to the dialog thread first, archives, and returns ``suppressed``.
    Discord auto-unarchives a thread on any new message, so post-before-archive
    ordering is required to make archival stick (UAT G-04).
    """
    draft = await load_draft(thread.id, str(user_id), http_client=http_client)
    if draft is None:
        return DialogOutcome.message("No onboarding dialog in progress.")
    ack = "Onboarding cancelled. Run `:pf player start` to begin again."
    await delete_draft(thread.id, str(user_id), http_client=http_client)
    # Send ack BEFORE archive — any message after archive auto-unarchives.
    try:
        await thread.send(ack)
    except Exception:
        logger.warning("cancel_dialog: thread.send failed for %s", thread.id)
    await _archive_and_discard(thread)
    return DialogOutcome.suppressed()


async def cancel_dialog(*, thread, user_id: str, http_client) -> str:
    """Compatibility wrapper returning the historical text/suppression sentinel."""
    outcome = await cancel_dialog_outcome(
        thread=thread, user_id=user_id, http_client=http_client
    )
    return outcome.to_legacy_text()
