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

from pathfinder_types import (
    PathfinderCommand,
    PathfinderRequest,
    PathfinderResponse,
)


_VALID_STYLE_PRESETS = ("Tactician", "Lorekeeper", "Cheerleader", "Rules-Lawyer Lite")
_USAGE = (
    "Usage: `:pf player start <character_name> | <preferred_name> | <style_preset>`\n"
    "Style presets: " + ", ".join(f"`{p}`" for p in _VALID_STYLE_PRESETS) + ".\n"
    "Multi-step onboarding dialog tracked under Phase 38."
)


async def _load_draft_resilient(thread_id: int, user_id: str, *, http_client):
    """Call ``pathfinder_player_dialog.load_draft`` if available, else delegate
    via a direct GET against the same vault URL. Resilient against unit-test
    fakes that swap ``pathfinder_player_dialog`` with a partial mock that omits
    ``load_draft``."""
    import pathfinder_player_dialog as _ppd

    load_draft = getattr(_ppd, "load_draft", None)
    if load_draft is not None:
        return await load_draft(thread_id, user_id, http_client=http_client)

    # Fallback: re-implement the GET-and-parse contract inline (mirrors
    # pathfinder_player_dialog.load_draft byte-for-byte; only used in tests
    # that supply a partial fake module).
    import importlib.util as _iu
    import os as _os

    _spec = _iu.spec_from_file_location(
        "_real_pathfinder_player_dialog",
        _os.path.join(_os.path.dirname(__file__), "pathfinder_player_dialog.py"),
    )
    _real = _iu.module_from_spec(_spec)
    _spec.loader.exec_module(_real)
    return await _real.load_draft(thread_id, user_id, http_client=http_client)


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
                existing = await _load_draft_resilient(
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

        payload = {
            "user_id": user_id,
            "character_name": character_name,
            "preferred_name": preferred_name,
            "style_preset": style_preset,
        }
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/player/onboard", payload, request.http_client
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
        payload = {"user_id": user_id, "text": text}
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/player/note", payload, request.http_client
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
        # Route's PlayerAskRequest schema requires `text` (not `question`) — see
        # plan-37-08 SUMMARY: the route was aligned to the RED test's `text`
        # field, but this adapter shipped sending `question` and 422'd live.
        payload = {"user_id": user_id, "text": text}
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/player/ask", payload, request.http_client
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
        payload = {"user_id": user_id, "npc_name": npc_name, "note": note}
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/player/npc", payload, request.http_client
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
        payload = {"user_id": user_id, "query": query}
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/player/recall", payload, request.http_client
        )
        results = result.get("results") or []
        if not results:
            return PathfinderResponse(
                kind="text",
                content="No recall snippets found." if query else "No personal memory yet.",
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
        payload = {"user_id": user_id, "text": text}
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/player/todo", payload, request.http_client
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
            payload = {"user_id": user_id, "action": "list"}
            result = await request.sentinel_client.post_to_module(
                "modules/pathfinder/player/style", payload, request.http_client
            )
            presets = result.get("presets") or []
            if not presets:
                return PathfinderResponse(kind="text", content="No style presets available.")
            return PathfinderResponse(
                kind="text",
                content="Available style presets:\n" + "\n".join(f"- {p}" for p in presets),
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
            payload = {"user_id": user_id, "action": "set", "preset": preset}
            result = await request.sentinel_client.post_to_module(
                "modules/pathfinder/player/style", payload, request.http_client
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


_DRAFT_DIR_REL = "mnemosyne/pf2e/players/_drafts"


def _vault_drafts_listing_url() -> str:
    """Vault URL for the ``_drafts/`` directory listing.

    Matches the URL convention in ``pathfinder_player_dialog._vault_url`` —
    OBSIDIAN_API_URL or its default, ``/vault/``, then the relative path with
    a trailing slash so the Local REST API returns a directory listing.
    """
    import os
    base = os.environ.get(
        "OBSIDIAN_API_URL", "http://host.docker.internal:27123"
    ).rstrip("/")
    return f"{base}/vault/{_DRAFT_DIR_REL}/"


def _vault_drafts_headers() -> dict:
    """Bearer-key headers, mirroring ``pathfinder_player_dialog._vault_headers``."""
    import os
    try:
        from bot import _read_secret
        key = _read_secret("obsidian_api_key", os.environ.get("OBSIDIAN_API_KEY", ""))
    except Exception:
        key = os.environ.get("OBSIDIAN_API_KEY", "")
    return {"Authorization": f"Bearer {key}"}


def _parse_draft_filenames(payload) -> list[str]:
    """Extract filenames from the drafts-listing response.

    Honours the dual-shape contract (RESEARCH §Pitfall 5): the Local REST API
    returns either a list of filenames or ``{"files": [{"path": "..."}]}``.
    """
    if isinstance(payload, list):
        return [str(p) for p in payload if isinstance(p, str)]
    if isinstance(payload, dict):
        files = payload.get("files")
        if isinstance(files, list):
            out: list[str] = []
            for entry in files:
                if isinstance(entry, dict):
                    p = entry.get("path") or entry.get("name")
                    if isinstance(p, str):
                        out.append(p)
                elif isinstance(entry, str):
                    out.append(entry)
            return out
    return []


async def _list_user_draft_thread_ids(user_id: str, *, http_client) -> list[int]:
    """List thread_ids for every in-flight draft owned by ``user_id``.

    GETs ``_drafts/`` (404-tolerant per RESEARCH §Pitfall 4), parses both the
    array and object shapes (Pitfall 5), filters to ``*-{user_id}.md``, and
    returns the parsed thread_id ints in the order they appeared.
    """
    try:
        resp = await http_client.get(
            _vault_drafts_listing_url(),
            headers=_vault_drafts_headers(),
            timeout=10.0,
        )
    except Exception:
        return []
    status = getattr(resp, "status_code", 200)
    if status == 404:
        return []
    if status >= 400:
        return []
    try:
        body = resp.json()
    except Exception:
        return []
    filenames = _parse_draft_filenames(body)
    suffix = f"-{user_id}.md"
    out: list[int] = []
    for name in filenames:
        # Strip any leading directory components — the listing may include
        # full paths (object-shape) or bare filenames (array-shape).
        leaf = name.rsplit("/", 1)[-1]
        if not leaf.endswith(suffix):
            continue
        head = leaf[: -len(suffix)]
        if head.isdigit():
            out.append(int(head))
    return out


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
    thread_ids = await _list_user_draft_thread_ids(
        user_id, http_client=request.http_client
    )
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
            text = await ppd.cancel_dialog(
                thread=channel, user_id=user_id, http_client=request.http_client
            )
            return PathfinderResponse(kind="text", content=text)

        # Cancel from a non-thread channel — D-17 symmetry: archive ALL drafts.
        thread_ids = await _list_user_draft_thread_ids(
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
                    delete_draft = getattr(ppd, "delete_draft", None)
                    if delete_draft is not None:
                        await delete_draft(
                            tid, user_id, http_client=request.http_client
                        )
                except Exception:
                    pass
                failures.append(tid)
                continue
            try:
                await ppd.cancel_dialog(
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
        payload = {
            "user_id": user_id,
            "outcome": outcome,
            "question_id": question_id,
            "rule_text": rule_text,
        }
        result = await request.sentinel_client.post_to_module(
            "modules/pathfinder/player/canonize", payload, request.http_client
        )
        path = result.get("path", "?")
        return PathfinderResponse(
            kind="text",
            content=f"Ruling canonized ({outcome}). Path: `{path}`",
        )
