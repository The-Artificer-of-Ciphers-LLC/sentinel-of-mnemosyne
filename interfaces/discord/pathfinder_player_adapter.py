"""Pathfinder player verb adapter for Discord ``:pf player <verb>`` commands.

One PathfinderCommand subclass per verb. Each ``handle()`` validates input,
builds the route-specific payload, calls ``request.sentinel_client.post_to_module``,
and returns a ``PathfinderResponse`` with a friendly text summary.

Pitfall 4 guard: ``user_id`` is coerced via ``str(request.user_id)`` to honour
the contract that the module receives the same string the bridge handed us —
slug derivation downstream depends on byte-stable identity.

Sub-verbs: start, note, ask, npc, recall, todo, style, canonize.
"""

from __future__ import annotations

from pathfinder_command_catalog import PLAYER_USAGE
from pathfinder_player_draft_store import (
    delete_draft,
    list_user_thread_ids,
    load_draft,
)
from pathfinder_types import (
    PathfinderCommand,
    PathfinderRequest,
    PathfinderResponse,
)
from pathfinder_player_contract import (
    PLAYER_STYLE_PRESETS as _VALID_STYLE_PRESETS,
    ask_call,
    canonize_call,
    note_call,
    npc_call,
    onboard_call,
    recall_call,
    style_call,
    todo_call,
)


_USAGE = (
    PLAYER_USAGE + "\n"
    "Start: `:pf player start <character_name> | <preferred_name> | <style_preset>`\n"
    "Style presets: " + ", ".join(f"`{p}`" for p in _VALID_STYLE_PRESETS) + ".\n"
    "Multi-step onboarding dialog tracked under Phase 38."
)


async def _post_player_call(request: PathfinderRequest, call):
    """Post one route-shaped player module call through the injected client."""
    return await request.sentinel_client.post_to_module(
        call.route, call.payload, request.http_client
    )


def _is_real_thread(channel) -> bool:
    """Robust thread-check that works with the test stub (``discord.Thread = object``).

    Returns True only when ``discord.Thread`` is a *specific* class (production
    or a test ``_FakeThread``) AND ``channel`` is an instance. The conftest
    stub aliases ``discord.Thread`` to ``object``, which would otherwise make
    every channel test as a thread.
    """
    import discord

    if discord.Thread is object:
        return False
    return isinstance(channel, discord.Thread)


class PlayerStartCommand(PathfinderCommand):
    """Handle ``:pf player start`` — onboard a player and create their vault profile.

    Until Phase 38 ships the multi-step dialog, this verb takes pipe-separated
    args: ``character_name | preferred_name | style_preset``. With no args it
    returns a usage message instead of letting the route 422.
    """

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        user_id = str(request.user_id)
        rest = (request.rest or "").strip()
        if not rest:
            # No-args: multi-step onboarding dialog (Phase 38, D-15).
            import pathfinder_player_dialog as ppd

            channel = request.channel
            if _is_real_thread(channel):
                existing = await load_draft(
                    channel.id, user_id, http_client=request.http_client
                )
                if existing is not None:
                    text = await ppd.resume_dialog(
                        thread=channel,
                        user_id=user_id,
                        http_client=request.http_client,
                    )
                    return PathfinderResponse(kind="text", content=text)
            display_name = request.author_display_name or f"player {user_id}"
            thread = await ppd.start_dialog(
                invoking_channel=channel,
                user_id=user_id,
                display_name=display_name,
                http_client=request.http_client,
            )
            return PathfinderResponse(
                kind="text",
                content=(
                    f"Onboarding started in <#{thread.id}>. "
                    "Reply there to answer the questions."
                ),
            )

        parts = [p.strip() for p in rest.split("|")]
        if len(parts) != 3 or not all(parts):
            return PathfinderResponse(kind="text", content=_USAGE)

        character_name, preferred_name, style_preset = parts
        if style_preset not in _VALID_STYLE_PRESETS:
            return PathfinderResponse(
                kind="text",
                content=(
                    f"Invalid style preset `{style_preset}`. Valid: "
                    + ", ".join(f"`{p}`" for p in _VALID_STYLE_PRESETS)
                ),
            )

        result = await _post_player_call(
            request,
            onboard_call(
                user_id=user_id,
                character_name=character_name,
                preferred_name=preferred_name,
                style_preset=style_preset,
            ),
        )
        path = result.get("path", "?")
        return PathfinderResponse(
            kind="text",
            content=f"Player onboarded as `{preferred_name}` ({style_preset}). Profile: `{path}`",
        )


class PlayerNoteCommand(PathfinderCommand):
    """Handle ``:pf player note <text>`` — append a free-form note to the player's inbox."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        rejection = await reject_if_draft_open(request)
        if rejection is not None:
            return rejection
        text = request.rest.strip()
        if not text:
            return PathfinderResponse(
                kind="text", content="Usage: `:pf player note <text>`"
            )
        user_id = str(request.user_id)
        result = await _post_player_call(
            request,
            note_call(user_id=user_id, text=text),
        )
        path = result.get("path", "?")
        return PathfinderResponse(
            kind="text",
            content=f"Note recorded for player. Inbox: `{path}`",
        )


class PlayerAskCommand(PathfinderCommand):
    """Handle ``:pf player ask <question>`` — log a question for the GM."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        rejection = await reject_if_draft_open(request)
        if rejection is not None:
            return rejection
        text = request.rest.strip()
        if not text:
            return PathfinderResponse(
                kind="text", content="Usage: `:pf player ask <question>`"
            )
        user_id = str(request.user_id)
        result = await _post_player_call(
            request,
            ask_call(user_id=user_id, text=text),
        )
        # Route returns {ok, slug, path} — no question_id is generated; the
        # questions.md append is a free-form line. Operator finds the entry
        # in the vault to canonize it later.
        path = result.get("path", "?")
        return PathfinderResponse(
            kind="text",
            content=f"Question logged at `{path}`. The GM can canonize it via `:pf player canonize`.",
        )


class PlayerNpcCommand(PathfinderCommand):
    """Handle ``:pf player npc <npc_name> <note>`` — record a personal NPC note."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        rejection = await reject_if_draft_open(request)
        if rejection is not None:
            return rejection
        rest = request.rest.strip()
        if not rest:
            return PathfinderResponse(
                kind="text", content="Usage: `:pf player npc <npc_name> <note>`"
            )
        # First whitespace-bounded token is the npc_name; remainder is the note.
        parts = rest.split(None, 1)
        if len(parts) < 2 or not parts[1].strip():
            return PathfinderResponse(
                kind="text", content="Usage: `:pf player npc <npc_name> <note>`"
            )
        npc_name, note = parts[0], parts[1].strip()
        user_id = str(request.user_id)
        result = await _post_player_call(
            request,
            npc_call(user_id=user_id, npc_name=npc_name, note=note),
        )
        path = result.get("path", "?")
        return PathfinderResponse(
            kind="text",
            content=f"Personal note on **{npc_name}** recorded. Path: `{path}`",
        )


class PlayerRecallCommand(PathfinderCommand):
    """Handle ``:pf player recall [query]`` — fetch personal recall snippets."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        rejection = await reject_if_draft_open(request)
        if rejection is not None:
            return rejection
        query = request.rest.strip()
        user_id = str(request.user_id)
        result = await _post_player_call(
            request,
            recall_call(user_id=user_id, query=query),
        )
        results = result.get("results") or []
        if not results:
            return PathfinderResponse(
                kind="text",
                content="No recall snippets found."
                if query
                else "No personal memory yet.",
            )
        lines = [f"Recall ({len(results)} hit{'s' if len(results) != 1 else ''}):"]
        for item in results[:10]:
            if isinstance(item, dict):
                snippet = item.get("text") or item.get("snippet") or str(item)
            else:
                snippet = str(item)
            lines.append(f"- {snippet}")
        return PathfinderResponse(kind="text", content="\n".join(lines))


class PlayerTodoCommand(PathfinderCommand):
    """Handle ``:pf player todo <text>`` — add an item to the player's todo list."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        rejection = await reject_if_draft_open(request)
        if rejection is not None:
            return rejection
        text = request.rest.strip()
        if not text:
            return PathfinderResponse(
                kind="text", content="Usage: `:pf player todo <text>`"
            )
        user_id = str(request.user_id)
        result = await _post_player_call(
            request,
            todo_call(user_id=user_id, text=text),
        )
        path = result.get("path", "?")
        return PathfinderResponse(
            kind="text",
            content=f"Todo recorded. Path: `{path}`",
        )


class PlayerStyleCommand(PathfinderCommand):
    """Handle ``:pf player style [list|set <preset>]`` — manage GM-style preferences.

    Empty rest defaults to ``list``.
    """

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        rejection = await reject_if_draft_open(request)
        if rejection is not None:
            return rejection
        rest = request.rest.strip()
        user_id = str(request.user_id)

        if not rest or rest.lower() == "list":
            result = await _post_player_call(
                request,
                style_call(user_id=user_id, action="list"),
            )
            presets = result.get("presets") or []
            if not presets:
                return PathfinderResponse(
                    kind="text", content="No style presets available."
                )
            return PathfinderResponse(
                kind="text",
                content="Available style presets:\n"
                + "\n".join(f"- {p}" for p in presets),
            )

        # set <preset>
        parts = rest.split(None, 1)
        action = parts[0].lower()
        if action == "set":
            if len(parts) < 2 or not parts[1].strip():
                return PathfinderResponse(
                    kind="text",
                    content="Usage: `:pf player style set <preset>` or `:pf player style list`",
                )
            preset = parts[1].strip()
            result = await _post_player_call(
                request,
                style_call(user_id=user_id, action="set", preset=preset),
            )
            chosen = result.get("preset", preset)
            return PathfinderResponse(
                kind="text",
                content=f"Style preset set to **{chosen}**.",
            )

        return PathfinderResponse(
            kind="text",
            content="Usage: `:pf player style list` or `:pf player style set <preset>`",
        )


async def reject_if_draft_open(request: PathfinderRequest) -> PathfinderResponse | None:
    """Phase 38 mid-dialog guard. See SPEC Req 5, D-05/D-07/D-08.

    GET ``/vault/mnemosyne/pf2e/players/_drafts/`` ; filter for
    ``*-{user_id}.md`` ; if any matches, return a rejection ``PathfinderResponse``
    listing every active dialog thread link via Discord ``<#thread_id>`` mention
    syntax.

    Returns ``None`` if no draft exists for this user — caller proceeds with
    normal flow. Returns ``None`` on 404 (drafts dir absent — RESEARCH §Pitfall 4).
    """
    user_id = str(request.user_id)
    thread_ids = await list_user_thread_ids(user_id, http_client=request.http_client)
    if not thread_ids:
        return None
    links = ", ".join(f"<#{tid}>" for tid in thread_ids)
    if len(thread_ids) == 1:
        text = (
            f"You have an onboarding dialog open in {links}. "
            f"Reply there to continue, or run `:pf player cancel` to abort."
        )
    else:
        text = (
            f"You have onboarding dialogs open in {links}. "
            f"Reply in one of those threads to continue, or run "
            f"`:pf player cancel` from inside the thread you want to abort."
        )
    return PathfinderResponse(kind="text", content=text)


class PlayerCancelCommand(PathfinderCommand):
    """Handle ``:pf player cancel`` — abort an in-flight onboarding dialog.

    Phase 38, SPEC Requirement 6, D-10, D-16, D-17.

    From inside the dialog thread: cancel that thread directly.
    From any other channel: cancel ALL of the user's in-flight dialogs (D-17
    symmetry — NO "pick one" branch). Per-thread failures aggregate; the loop
    never aborts.
    """

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        import discord

        import pathfinder_player_dialog as ppd

        user_id = str(request.user_id)
        channel = request.channel

        if _is_real_thread(channel):
            outcome = await ppd.cancel_dialog_outcome(
                thread=channel, user_id=user_id, http_client=request.http_client
            )
            return outcome.to_pathfinder_response()

        # Cancel from a non-thread channel — D-17 symmetry: archive ALL drafts.
        thread_ids = await list_user_thread_ids(
            user_id, http_client=request.http_client
        )
        if not thread_ids:
            return PathfinderResponse(
                kind="text", content="No onboarding dialog in progress."
            )

        # Resolve the bot singleton lazily — importing at module scope creates a
        # circular dep (bot imports pathfinder_dispatch which imports this module).
        from bot import bot as discord_bot

        failures: list[int] = []
        for tid in thread_ids:
            thread = discord_bot.get_channel(tid)
            if thread is None:
                # Orphan draft — clean up the file directly.
                try:
                    await delete_draft(tid, user_id, http_client=request.http_client)
                except Exception:
                    pass
                failures.append(tid)
                continue
            try:
                await ppd.cancel_dialog_outcome(
                    thread=thread,
                    user_id=user_id,
                    http_client=request.http_client,
                )
            except discord.HTTPException:
                failures.append(tid)
            except Exception:
                failures.append(tid)

        n = len(thread_ids)
        if n == 1:
            base = "Cancelled the onboarding dialog."
        else:
            base = f"Cancelled {n} onboarding dialogs."
        if failures:
            links = ", ".join(f"<#{tid}>" for tid in failures)
            base += f" (Note: archive failed for {links} — drafts cleaned up.)"
        return PathfinderResponse(kind="text", content=base)


class PlayerCanonizeCommand(PathfinderCommand):
    """Handle ``:pf player canonize <outcome> <question_id> <rule_text>`` — promote a ruling."""

    async def handle(self, request: PathfinderRequest) -> PathfinderResponse:
        rejection = await reject_if_draft_open(request)
        if rejection is not None:
            return rejection
        rest = request.rest.strip()
        if not rest:
            return PathfinderResponse(
                kind="text",
                content="Usage: `:pf player canonize <outcome> <question_id> <rule_text>`",
            )
        # Three-part split: outcome, question_id, rule_text (rule_text may have spaces).
        parts = rest.split(None, 2)
        if len(parts) < 3 or not parts[2].strip():
            return PathfinderResponse(
                kind="text",
                content="Usage: `:pf player canonize <outcome> <question_id> <rule_text>`",
            )
        outcome, question_id, rule_text = parts[0], parts[1], parts[2].strip()
        user_id = str(request.user_id)
        result = await _post_player_call(
            request,
            canonize_call(
                user_id=user_id,
                outcome=outcome,
                question_id=question_id,
                rule_text=rule_text,
            ),
        )
        path = result.get("path", "?")
        return PathfinderResponse(
            kind="text",
            content=f"Ruling canonized ({outcome}). Path: `{path}`",
        )
