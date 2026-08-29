"""Multi-step self-profile onboarding dialog: state machine + draft I/O.

Mirrors ``pathfinder_player_dialog.py`` structurally (thread lifecycle, draft
persistence, resumable/cancellable state machine) but drives a *variable*
sequence of steps — one per profile path core reports unfilled via
``GET /self/profile/status`` — instead of a fixed STEPS tuple.

Draft persistence lives in ``self_profile_draft_store``; this module owns
Discord thread lifecycle and dialog step policy.
"""
from __future__ import annotations

import datetime
import logging

import discord
import httpx

import core_gateway
from pathfinder_player_dialog_outcome import DialogOutcome
from self_profile_draft_store import (
    delete_draft,
    draft_path,
    load_draft,
    save_draft,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DialogOutcome",
    "HEADINGS",
    "QUESTIONS",
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


# --- Question wording (short, factual — these files are read into every message
# and share the hot-tier context budget, so prose is expensive). ---

QUESTIONS: dict[str, str] = {
    "self/identity.md": (
        "Who are you? Name, role, and anything essential I should know — "
        "a few lines is plenty."
    ),
    "self/methodology.md": (
        "How do you like to work or think? A few short bullet points on your "
        "methodology or working style is plenty."
    ),
    "self/goals.md": (
        "What are your current top goals? List them briefly — a few lines is plenty."
    ),
    "self/relationships.md": (
        "Who are the key people or relationships I should know about? A short "
        "line each is plenty."
    ),
}

_FALLBACK_QUESTION = (
    "What would you like to tell me for this part of your profile? "
    "A few lines is plenty."
)

HEADINGS: dict[str, str] = {
    "self/identity.md": "# Identity",
    "self/methodology.md": "# Methodology",
    "self/goals.md": "# Goals",
    "self/relationships.md": "# Relationships",
}


def _heading_for(path: str) -> str:
    return HEADINGS.get(path, f"# {path.rsplit('/', 1)[-1].removesuffix('.md').title()}")


def _question_for(path: str) -> str:
    return QUESTIONS.get(path, _FALLBACK_QUESTION)


# --- Dialog lifecycle ---


async def start_dialog(
    *,
    invoking_channel,
    user_id: str,
    unfilled: list[str],
    http_client,
    message_author_display_name: str | None = None,
    display_name: str | None = None,
) -> "discord.Thread":
    """Create the onboarding thread, persist the first draft, post Q1.

    ``unfilled`` MUST be non-empty (caller pre-checks via
    ``GET /self/profile/status``); the first entry becomes the current step,
    the rest are queued in ``remaining``.
    """
    effective_name = message_author_display_name if message_author_display_name is not None else display_name
    if effective_name is None:
        raise TypeError(
            "start_dialog requires either message_author_display_name or display_name"
        )
    if not unfilled:
        raise ValueError("start_dialog requires a non-empty unfilled list")

    name = f"Onboarding — {effective_name}"[:100]
    # Mirrors pathfinder_player_dialog.start_dialog: threads cannot host child
    # threads, so hoist onto the parent text channel when invoked from inside
    # an existing Sentinel thread.
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

    from bot import SENTINEL_THREAD_IDS, _persist_thread_id

    SENTINEL_THREAD_IDS.add(thread.id)
    try:
        await _persist_thread_id(thread.id)
    except Exception:
        logger.exception("failed to persist thread id %s", thread.id)

    current = unfilled[0]
    draft = {
        "current": current,
        "remaining": list(unfilled[1:]),
        "thread_id": thread.id,
        "user_id": str(user_id),
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    await save_draft(thread.id, str(user_id), draft, http_client=http_client)
    await thread.send(_question_for(current))
    return thread


async def resume_dialog(*, thread, user_id: str, http_client) -> str:
    """Return the prompt for the draft's CURRENT step. Does NOT mutate the draft."""
    draft = await load_draft(thread.id, str(user_id), http_client=http_client)
    if draft is None:
        return "No onboarding dialog in progress. Run `:onboard` to start one."
    current = draft.get("current")
    return _question_for(current) if current else _FALLBACK_QUESTION


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


async def _finish(thread, user_id: str, http_client, *, prefix: str = "") -> DialogOutcome:
    """Delete the draft, post the completion ack BEFORE archive, and archive.

    Post-before-archive ordering matches pathfinder_player_dialog: any message
    sent after ``thread.edit(archived=True)`` auto-unarchives the thread.
    """
    await delete_draft(thread.id, user_id, http_client=http_client)
    ack = (prefix + "\n\n" if prefix else "") + (
        "Onboarding complete — thanks! Your profile is filled in."
    )
    try:
        await thread.send(ack)
    except Exception:
        logger.warning("self_profile_dialog: completion send failed for %s", thread.id)
    await _archive_and_discard(thread)
    return DialogOutcome.suppressed()


async def consume_as_answer_outcome(
    *,
    thread,
    user_id: str,
    message_text: str,
    sentinel_client,
    http_client,
) -> DialogOutcome:
    """Advance the dialog one step: POST the answer, then ask the next question
    or finish. On a 409 (already filled — e.g. a race with a manual edit), the
    step is skipped rather than forced, and the reason is surfaced to the user.
    """
    draft = await load_draft(thread.id, str(user_id), http_client=http_client)
    if draft is None:
        # Defensive — caller (dialog gate) pre-checks. Safety net: do nothing.
        return DialogOutcome.suppressed()

    current = draft.get("current")
    remaining = list(draft.get("remaining") or [])
    answer = (message_text or "").strip()

    if not current:
        return await _finish(thread, str(user_id), http_client)

    if not answer:
        return DialogOutcome.message(_question_for(current))

    body = f"{_heading_for(current)}\n\n{answer}\n"
    skip_note = ""
    try:
        await core_gateway.call_core_profile_write(
            user_id=str(user_id),
            path=current,
            content=body,
            sentinel_client=sentinel_client,
            http_client=http_client,
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            try:
                reason = exc.response.json().get("reason", "already filled")
            except Exception:
                reason = "already filled"
            skip_note = f"`{current}` was {reason} — skipping without overwriting it."
            logger.info("self_profile_dialog: 409 on %s (%s)", current, reason)
        else:
            logger.warning(
                "self_profile_dialog: profile write failed for %s: %s", current, exc
            )
            return DialogOutcome.message(
                f"Couldn't save that answer (HTTP {exc.response.status_code}) — "
                "please try again."
            )
    except Exception as exc:
        logger.warning(
            "self_profile_dialog: profile write errored for %s: %s", current, exc
        )
        return DialogOutcome.message(
            "Couldn't reach the Sentinel to save that answer — please try again shortly."
        )

    if remaining:
        next_path = remaining[0]
        draft["current"] = next_path
        draft["remaining"] = remaining[1:]
        await save_draft(thread.id, str(user_id), draft, http_client=http_client)
        next_question = _question_for(next_path)
        return DialogOutcome.message(
            f"{skip_note}\n\n{next_question}" if skip_note else next_question
        )

    return await _finish(thread, str(user_id), http_client, prefix=skip_note)


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
    """Delete the draft, post the cancel ack, then archive the thread."""
    draft = await load_draft(thread.id, str(user_id), http_client=http_client)
    if draft is None:
        return DialogOutcome.message("No onboarding dialog in progress.")
    ack = "Onboarding cancelled. Run `:onboard` to begin again."
    await delete_draft(thread.id, str(user_id), http_client=http_client)
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
