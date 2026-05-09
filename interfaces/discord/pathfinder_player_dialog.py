"""Multi-step PF2E onboarding dialog: state machine + draft I/O.

Owns:
  - STEPS / QUESTIONS module-level constants (D-13)
  - Draft frontmatter round-trip against Obsidian REST (D-12)
  - start_dialog / resume_dialog / consume_as_answer / cancel_dialog (D-12, D-15)

Persistence layer mirrors bot.py:_persist_thread_id (bot.py:536) — direct httpx +
OBSIDIAN_API_URL + bearer key from _read_secret. Frontmatter helpers are inlined
here because sentinel-core/app/markdown_frontmatter.py lives in a different
deployable.
"""
from __future__ import annotations

import datetime
import logging
import os
import re

import discord
import yaml

from pathfinder_player_adapter import _VALID_STYLE_PRESETS

logger = logging.getLogger(__name__)


# --- Module-level constants (D-13, locked verbatim against 38-01 RED tests) ---

STEPS: tuple[str, str, str] = ("character_name", "preferred_name", "style_preset")

QUESTIONS: dict[str, str] = {
    "character_name": "What is your character's name?",
    "preferred_name": "How would you like me to address you?",
    "style_preset": "Pick a style: Tactician, Lorekeeper, Cheerleader, Rules-Lawyer Lite",
}


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_DRAFT_DIR = "mnemosyne/pf2e/players/_drafts"


class _NoTimestampLoader(yaml.SafeLoader):
    """SafeLoader that keeps ISO-8601 timestamps as plain strings.

    The default SafeLoader resolves ``2026-05-08T00:00:00Z`` to ``datetime``,
    but our draft round-trip stores ``started_at`` as a string and tests assert
    the raw ISO form survives the GET (D-12 contract).
    """


# Drop the implicit `tag:yaml.org,2002:timestamp` resolver.
_NoTimestampLoader.yaml_implicit_resolvers = {
    ch: [(tag, regexp) for (tag, regexp) in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for ch, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


# --- Path / frontmatter helpers ---


def draft_path(thread_id: int, user_id) -> str:
    """Canonical draft path under the vault (D-05). Coerces user_id to str (Pitfall 6)."""
    return f"{_DRAFT_DIR}/{thread_id}-{str(user_id)}.md"


def _split_frontmatter(body: str) -> tuple[dict, str]:
    """Split a markdown body into (frontmatter dict, remaining body)."""
    match = _FRONTMATTER_RE.match(body or "")
    if not match:
        return ({}, body or "")
    try:
        fm = yaml.load(match.group(1), Loader=_NoTimestampLoader) or {}
        if not isinstance(fm, dict):
            fm = {}
    except yaml.YAMLError:
        fm = {}
    return (fm, body[match.end():])


def _join_frontmatter(fm: dict, rest: str = "") -> str:
    """Render a frontmatter dict + optional body into a markdown string."""
    block = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).strip()
    return f"---\n{block}\n---\n\n{rest.lstrip()}"


# --- Vault REST helpers (mirrors bot.py:_persist_thread_id at bot.py:536) ---


def _vault_url(rel: str) -> str:
    base = os.environ.get("OBSIDIAN_API_URL", "http://host.docker.internal:27123").rstrip("/")
    return f"{base}/vault/{rel}"


def _vault_headers() -> dict:
    # Lazy import: bot module imports this module indirectly via dialog_router (38-05).
    from bot import _read_secret

    key = _read_secret("obsidian_api_key", os.environ.get("OBSIDIAN_API_KEY", ""))
    return {"Authorization": f"Bearer {key}"}


# --- Draft I/O ---


async def save_draft(thread_id: int, user_id, draft: dict, *, http_client) -> None:
    """PUT the draft as a frontmatter-only markdown body."""
    body = _join_frontmatter(draft, "")
    headers = {**_vault_headers(), "Content-Type": "text/markdown"}
    resp = await http_client.put(
        _vault_url(draft_path(thread_id, user_id)),
        headers=headers,
        content=body,
        timeout=10.0,
    )
    # raise_for_status is a sync MagicMock by default; call only if available.
    raise_for_status = getattr(resp, "raise_for_status", None)
    if callable(raise_for_status) and resp.status_code >= 400:
        raise_for_status()


async def load_draft(thread_id: int, user_id, *, http_client) -> dict | None:
    """GET the draft and parse frontmatter. Returns None on 404 (Pitfall 4)."""
    resp = await http_client.get(
        _vault_url(draft_path(thread_id, user_id)),
        headers=_vault_headers(),
        timeout=10.0,
    )
    if resp.status_code == 404:
        return None
    if resp.status_code >= 400:
        raise_for_status = getattr(resp, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
    fm, _rest = _split_frontmatter(resp.text)
    return fm or None


async def delete_draft(thread_id: int, user_id, *, http_client) -> None:
    """DELETE the draft. 404 is tolerated (idempotent cleanup)."""
    resp = await http_client.delete(
        _vault_url(draft_path(thread_id, user_id)),
        headers=_vault_headers(),
        timeout=10.0,
    )
    if resp.status_code not in (200, 204, 404):
        raise_for_status = getattr(resp, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()


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
    """Case-insensitive match → canonical-case preset, or None if invalid (RESEARCH Q10)."""
    target = (answer or "").strip().lower()
    for preset in _VALID_STYLE_PRESETS:
        if preset.lower() == target:
            return preset
    return None


async def consume_as_answer(
    *,
    thread,
    user_id: str,
    message_text: str,
    sentinel_client,
    http_client,
) -> str:
    """Advance the dialog one step. On final step, POST /player/onboard + cleanup.

    Returns the response text. The caller (bot.py on_message via
    response_renderer) is responsible for posting it to the thread —
    sending here would double-post (UAT G-03).
    """
    draft = await load_draft(thread.id, str(user_id), http_client=http_client)
    if draft is None:
        # Defensive — caller (dialog_router) pre-checks. Safety net: do nothing.
        return ""
    step = draft.get("step", STEPS[0])
    answer = (message_text or "").strip()

    if step == "style_preset":
        normalised = _normalise_style_preset(answer)
        if normalised is None:
            return (
                f"`{answer}` isn't a valid style. Please choose one of: "
                + ", ".join(_VALID_STYLE_PRESETS)
                + "."
            )
        draft["style_preset"] = normalised
    elif step in ("character_name", "preferred_name"):
        if not answer:
            return QUESTIONS[step]
        draft[step] = answer

    idx = STEPS.index(step)
    if idx + 1 < len(STEPS):
        draft["step"] = STEPS[idx + 1]
        await save_draft(thread.id, str(user_id), draft, http_client=http_client)
        return QUESTIONS[STEPS[idx + 1]]

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
    return ""  # already sent — signal to bot.py response_renderer to no-op


async def cancel_dialog(*, thread, user_id: str, http_client) -> str:
    """Delete the draft, post the cancel ack, then archive the thread.

    Returns the cancel-ack text on the no-draft path (caller's response_renderer
    sends it to the invoking channel). On the with-draft path, posts the ack
    DIRECTLY to the dialog thread first, archives, and returns "" so bot.py's
    response_renderer skips its send. Discord auto-unarchives a thread on any
    new message, so the post-must-precede-archive ordering is required to make
    archival actually stick (UAT G-04).
    """
    draft = await load_draft(thread.id, str(user_id), http_client=http_client)
    if draft is None:
        return "No onboarding dialog in progress."
    ack = "Onboarding cancelled. Run `:pf player start` to begin again."
    await delete_draft(thread.id, str(user_id), http_client=http_client)
    # Send ack BEFORE archive — any message after archive auto-unarchives.
    try:
        await thread.send(ack)
    except Exception:
        logger.warning("cancel_dialog: thread.send failed for %s", thread.id)
    await _archive_and_discard(thread)
    return ""  # already sent — signal to bot.py response_renderer to no-op
