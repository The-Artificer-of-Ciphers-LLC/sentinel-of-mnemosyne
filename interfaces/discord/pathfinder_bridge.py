"""Bridge wrapper for Pathfinder command dispatch.

Deepened: builds a ``PathfinderRequest`` from parsed args, calls the deepened
dispatch (which returns a ``PathfinderResponse``), and converts that response
into a ``str | dict`` for Discord rendering.

HTTP error handling stays here — commands handle validation only (returning
text responses for usage errors).  The bridge catches HTTP exceptions and
maps them to user-facing strings.

The response conversion handles all three kinds:
  - text  → returned as-is (plain string)
  - embed → calls the appropriate builder function to produce a Discord Embed,
            returns ``{"type": "embed" | "suppressed", ...}`` for Discord.
  - file  → returns ``{"type": "file", ...}`` with bytes and filename.

See pathfinder_types.py for the full type contract.
"""
from __future__ import annotations

import logging

import httpx

from pathfinder_dispatch import dispatch
from pathfinder_types import (
    PathfinderResponse,
)

logger = logging.getLogger(__name__)


def _render_response(response: PathfinderResponse) -> str | dict:
    """Convert a PathfinderResponse into a str | dict for Discord rendering.

    Args:
        response: The response from dispatch (text, embed, or file).

    Returns:
        A str for text responses, or a dict with ``type`` key for embed/file.

    Raises:
        KeyError: If an embed response references a builder not in the builders dict.
    """
    if response.kind == "text":
        return response.content

    if response.kind == "embed":
        # Call the appropriate builder function to produce a Discord Embed.
        builders = response.builders or {}  # noqa: SLF001 — bridge-supplied
        builder_name = response.embed_builder
        if not builder_name or builder_name not in builders:
            return f"Error: no embed builder '{builder_name}' found."
        embed = builders[builder_name](response.embed_data)  # type: ignore[arg-type]
        return {
            "type": "embed",
            "content": "",
            "embed": embed,
        }

    if response.kind == "file":
        return {
            "type": "file",
            "content": response.content,
            "file_bytes": response.file_bytes,
            "filename": response.filename,
        }

    # Fallback (should not happen with proper typing).
    return f"Error: unknown response kind '{response.kind}'."


async def dispatch_pf(
    *,
    args: str,
    user_id: str,
    attachments,
    channel,
    bot_user,
    parse_pf_args,
    sent_client,
    http_client,
    is_admin,
    valid_relations: frozenset[str],
    builders: dict | None = None,
    extract_thread_history=None,
    map_http_status,
    log_error,
    author_display_name: str | None = None,
):
    """Bridge: parse args → build request → dispatch → render response.

    This is the entry point called from Discord command handlers.  It:
      1. Parses the raw args string into (noun, verb, rest, parts).
      2. Builds a unified PathfinderRequest with all injected dependencies.
      3. Calls the deepened dispatch (registry lookup → command.handle).
      4. Converts the PathfinderResponse into str | dict for Discord.
      5. Catches HTTP errors and maps them to user-facing strings.

    Args:
        args: Raw argument string from the Discord command (e.g. "npc create Foo | bar").
        user_id: Discord user ID string.
        attachments: Discord message attachments (may be None).
        channel: Discord channel object (may be None).
        bot_user: Discord bot user object (may be None).
        parse_pf_args: Callable that parses args into (noun, verb, rest, parts) or (None, error).
        sent_client: The sentinel-core HTTP client.
        http_client: An already-open httpx.AsyncClient (bridge does NOT manage its lifecycle).
        is_admin: Callable returning whether user_id is an admin.
        valid_relations: Frozenset of valid NPC relation types.
        extract_thread_history: Callable for npc say to extract thread history.
        map_http_status: Callable that maps HTTP status codes to user-facing strings.
        log_error: Callable for logging errors (used when mapping fails).

    Returns:
        A str or dict suitable for sending to Discord.  On HTTP errors, returns
        a user-facing error string.  On command validation errors, returns the
        usage message from the command (as a str).
    """
    parsed, err = parse_pf_args(args)
    if err:
        return err
    assert parsed is not None
    noun, verb, rest, parts = parsed

    try:
        response = await dispatch(
            noun=noun,
            verb=verb,
            rest=rest,
            parts=parts,
            user_id=user_id,
            channel=channel,
            attachments=attachments,
            bot_user=bot_user,
            sentinel_client=sent_client,
            http_client=http_client,
            is_admin=is_admin,
            valid_relations=valid_relations,
            builders=builders or {},
            extract_thread_history=extract_thread_history,
            author_display_name=author_display_name,
        )

        return _render_response(response)

    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except Exception:
            detail = exc.response.text
        if status not in (404, 409):
            log_error(f"Module returned HTTP {status}: {detail}")
        return map_http_status(status, str(detail))
    except httpx.ConnectError:
        return "Cannot reach the Sentinel. Is sentinel-core running?"
    except httpx.TimeoutException:
        return "The pathfinder module took too long to respond. Try again."
    except Exception as exc:
        log_error(f"Unexpected error in pathfinder dispatch: {exc}")
        return "An unexpected error occurred in pathfinder dispatch."
