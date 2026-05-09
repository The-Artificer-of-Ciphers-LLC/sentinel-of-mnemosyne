"""Wave 0 RED tests for Discord pathfinder_player_adapter command classes.

These tests assert the contract the Wave 7 adapter must satisfy:
- Each ``:pf player <verb>`` maps to a PathfinderCommand subclass.
- handle() builds a payload dict and posts to the correct module route.
- ``user_id`` is forwarded as ``str`` (Pitfall 4: type-drift guard).
- Empty/invalid invocations return a usage hint and do NOT post to module.

Conventions (mirrors ``test_pathfinder_foundry_adapter.py``):
- ``async def test_*`` with no ``@pytest.mark.asyncio`` decorator (asyncio_mode = "auto").
- Function-scope ``from pathfinder_player_adapter import ...`` so collection fails
  with ImportError until Wave 7 lands the adapter — the RED state.
- ``AsyncMock`` for ``sentinel_client.post_to_module``; assertion via ``call_args``.
- Discord stubs come from ``conftest.py`` (no per-file stubs — Phase 33-01 decision).
"""

from unittest.mock import AsyncMock

from pathfinder_types import PathfinderRequest


# --- :pf player start -------------------------------------------------------


# NOTE: ``test_player_start_with_empty_rest_returns_usage_no_post`` was the
# Phase 37 stop-gap test that locked the legacy "empty rest → usage hint"
# behaviour. Phase 38 D-15 replaces that stop-gap with the multi-step dialog
# (see ``test_player_start_no_args_creates_thread_and_draft`` below). Removing
# this test is authorized by 38-06's plan ("12 existing tests still GREEN" —
# i.e. 13 originals minus this stop-gap).


async def test_player_start_with_args_posts_full_onboard_payload():
    """Pipe-separated args satisfy the /player/onboard Pydantic contract."""
    from pathfinder_player_adapter import PlayerStartCommand

    cmd = PlayerStartCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(
        return_value={"path": "mnemosyne/pf2e/players/p-abc/profile.md"}
    )
    request = PathfinderRequest(
        noun="player",
        verb="start",
        rest="Kael Stormblade | Kael | Tactician",
        user_id="u1",
        sentinel_client=client,
    )
    await cmd.handle(request)
    assert client.post_to_module.await_count == 1
    args = client.post_to_module.call_args[0]
    assert args[0] == "modules/pathfinder/player/onboard"
    payload = args[1]
    assert payload["user_id"] == "u1"
    assert isinstance(payload["user_id"], str)
    assert payload["character_name"] == "Kael Stormblade"
    assert payload["preferred_name"] == "Kael"
    assert payload["style_preset"] == "Tactician"


async def test_player_start_rejects_invalid_style_preset():
    from pathfinder_player_adapter import PlayerStartCommand

    cmd = PlayerStartCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock()
    request = PathfinderRequest(
        noun="player",
        verb="start",
        rest="Kael | Kael | Bard-Mode",
        user_id="u1",
        sentinel_client=client,
    )
    response = await cmd.handle(request)
    assert client.post_to_module.await_count == 0
    assert response.kind == "text"
    assert "Invalid style preset" in response.content


# --- :pf player note --------------------------------------------------------


async def test_player_note_payload_shape():
    from pathfinder_player_adapter import PlayerNoteCommand

    cmd = PlayerNoteCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(
        return_value={"path": "mnemosyne/pf2e/players/p-abc/inbox.md"}
    )
    request = PathfinderRequest(
        noun="player",
        verb="note",
        rest="I trust Varek.",
        user_id="u1",
        sentinel_client=client,
    )
    await cmd.handle(request)
    args = client.post_to_module.call_args[0]
    assert args[0] == "modules/pathfinder/player/note"
    payload = args[1]
    assert payload == {"user_id": "u1", "text": "I trust Varek."}


async def test_player_note_empty_returns_usage():
    from pathfinder_player_adapter import PlayerNoteCommand

    cmd = PlayerNoteCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock()
    request = PathfinderRequest(
        noun="player",
        verb="note",
        rest="",
        user_id="u1",
        sentinel_client=client,
    )
    response = await cmd.handle(request)
    assert response.kind == "text"
    assert "Usage:" in response.content
    assert client.post_to_module.await_count == 0


# --- :pf player ask ---------------------------------------------------------


async def test_player_ask_payload_shape():
    """Adapter must send `text`, not `question` — the route's PlayerAskRequest
    schema was aligned to `text` per plan-37-08 SUMMARY (RED-test-driven).
    Adapter shipped sending `question` and 422'd live; UAT-18 caught it."""
    from pathfinder_player_adapter import PlayerAskCommand

    cmd = PlayerAskCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(
        return_value={"ok": True, "slug": "p-x", "path": "mnemosyne/pf2e/players/p-x/questions.md"}
    )
    request = PathfinderRequest(
        noun="player",
        verb="ask",
        rest="What rule applies to vital strike?",
        user_id="u1",
        sentinel_client=client,
    )
    response = await cmd.handle(request)
    args = client.post_to_module.call_args[0]
    assert args[0] == "modules/pathfinder/player/ask"
    payload = args[1]
    assert payload["user_id"] == "u1"
    assert payload["text"] == "What rule applies to vital strike?"
    assert "question" not in payload  # explicit regression guard
    # Response references the vault path, not a fabricated question_id.
    assert response.kind == "text"
    assert "questions.md" in response.content
    assert "id: `?`" not in response.content


# --- :pf player npc <name> <note> -------------------------------------------


async def test_player_npc_parses_npc_name_and_note():
    from pathfinder_player_adapter import PlayerNpcCommand

    cmd = PlayerNpcCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"path": "..."})
    request = PathfinderRequest(
        noun="player",
        verb="npc",
        rest="Varek trustworthy after the bridge fight",
        user_id="u1",
        sentinel_client=client,
    )
    await cmd.handle(request)
    args = client.post_to_module.call_args[0]
    assert args[0] == "modules/pathfinder/player/npc"
    payload = args[1]
    assert payload == {
        "user_id": "u1",
        "npc_name": "Varek",
        "note": "trustworthy after the bridge fight",
    }


async def test_player_npc_missing_note_returns_usage():
    from pathfinder_player_adapter import PlayerNpcCommand

    cmd = PlayerNpcCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock()
    request = PathfinderRequest(
        noun="player",
        verb="npc",
        rest="Varek",
        user_id="u1",
        sentinel_client=client,
    )
    response = await cmd.handle(request)
    assert response.kind == "text"
    assert "Usage:" in response.content
    assert client.post_to_module.await_count == 0


# --- :pf player recall ------------------------------------------------------


async def test_player_recall_no_query():
    from pathfinder_player_adapter import PlayerRecallCommand

    cmd = PlayerRecallCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"results": []})
    request = PathfinderRequest(
        noun="player",
        verb="recall",
        rest="",
        user_id="u1",
        sentinel_client=client,
    )
    await cmd.handle(request)
    args = client.post_to_module.call_args[0]
    assert args[0] == "modules/pathfinder/player/recall"
    payload = args[1]
    assert payload.get("user_id") == "u1"
    assert isinstance(payload["user_id"], str)
    # If a query key is present, it must be the empty string for the no-query case.
    if "query" in payload:
        assert payload["query"] == ""


async def test_player_recall_with_query():
    from pathfinder_player_adapter import PlayerRecallCommand

    cmd = PlayerRecallCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"results": []})
    request = PathfinderRequest(
        noun="player",
        verb="recall",
        rest="Varek bridge",
        user_id="u1",
        sentinel_client=client,
    )
    await cmd.handle(request)
    args = client.post_to_module.call_args[0]
    assert args[0] == "modules/pathfinder/player/recall"
    payload = args[1]
    assert payload["user_id"] == "u1"
    assert payload["query"] == "Varek bridge"


# --- :pf player todo --------------------------------------------------------


async def test_player_todo_payload_shape():
    from pathfinder_player_adapter import PlayerTodoCommand

    cmd = PlayerTodoCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"path": "..."})
    request = PathfinderRequest(
        noun="player",
        verb="todo",
        rest="Buy potions before next session",
        user_id="u1",
        sentinel_client=client,
    )
    await cmd.handle(request)
    args = client.post_to_module.call_args[0]
    assert args[0] == "modules/pathfinder/player/todo"
    payload = args[1]
    assert payload["user_id"] == "u1"
    assert payload["text"] == "Buy potions before next session"


# --- :pf player style {list|set <preset>} -----------------------------------


async def test_player_style_list():
    from pathfinder_player_adapter import PlayerStyleCommand

    cmd = PlayerStyleCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(
        return_value={
            "presets": ["Tactician", "Lorekeeper", "Cheerleader", "Rules-Lawyer Lite"]
        }
    )
    request = PathfinderRequest(
        noun="player",
        verb="style",
        rest="list",
        user_id="u1",
        sentinel_client=client,
    )
    response = await cmd.handle(request)
    args = client.post_to_module.call_args[0]
    assert args[0] == "modules/pathfinder/player/style"
    payload = args[1]
    assert payload == {"user_id": "u1", "action": "list"}
    # Response surfaces the four preset names back to the user.
    for preset in ("Tactician", "Lorekeeper", "Cheerleader", "Rules-Lawyer Lite"):
        assert preset in response.content


async def test_player_style_set_with_preset():
    from pathfinder_player_adapter import PlayerStyleCommand

    cmd = PlayerStyleCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"preset": "Tactician"})
    request = PathfinderRequest(
        noun="player",
        verb="style",
        rest="set Tactician",
        user_id="u1",
        sentinel_client=client,
    )
    await cmd.handle(request)
    args = client.post_to_module.call_args[0]
    assert args[0] == "modules/pathfinder/player/style"
    payload = args[1]
    assert payload == {"user_id": "u1", "action": "set", "preset": "Tactician"}


async def test_player_style_set_missing_preset_returns_usage():
    from pathfinder_player_adapter import PlayerStyleCommand

    cmd = PlayerStyleCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock()
    request = PathfinderRequest(
        noun="player",
        verb="style",
        rest="set",
        user_id="u1",
        sentinel_client=client,
    )
    response = await cmd.handle(request)
    assert response.kind == "text"
    assert "Usage:" in response.content
    assert client.post_to_module.await_count == 0


# --- :pf player canonize ----------------------------------------------------


async def test_player_canonize_payload_shape():
    from pathfinder_player_adapter import PlayerCanonizeCommand

    cmd = PlayerCanonizeCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"path": "..."})
    request = PathfinderRequest(
        noun="player",
        verb="canonize",
        rest="green q-uuid-1 Vital strike applies on first attack only",
        user_id="u1",
        sentinel_client=client,
    )
    await cmd.handle(request)
    args = client.post_to_module.call_args[0]
    assert args[0] == "modules/pathfinder/player/canonize"
    payload = args[1]
    assert payload == {
        "user_id": "u1",
        "outcome": "green",
        "question_id": "q-uuid-1",
        "rule_text": "Vital strike applies on first attack only",
    }


# --- Pitfall 4: user_id type-drift guard ------------------------------------


async def test_user_id_is_forwarded_as_str():
    """user_id MUST be forwarded to the module exactly as the str received from
    the bridge — no int coercion, no normalization. This guards against silently
    re-deriving slugs because hashlib hashes a different bytes payload for
    ``"123"`` vs ``123``.
    """
    from pathfinder_player_adapter import PlayerNoteCommand

    cmd = PlayerNoteCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"path": "..."})
    request = PathfinderRequest(
        noun="player",
        verb="note",
        rest="hello",
        user_id="123",
        sentinel_client=client,
    )
    await cmd.handle(request)
    payload = client.post_to_module.call_args[0][1]
    assert payload["user_id"] == "123"
    assert isinstance(payload["user_id"], str)
    assert not isinstance(payload["user_id"], bool)
    # Explicit: must not have been coerced to int.
    assert payload["user_id"] != 123


# ============================================================================
# Phase 38-03 Wave 0 RED tests — APPENDED ONLY. Do not modify tests above.
# ============================================================================
#
# Coverage:
#   * No-args branch of PlayerStartCommand (D-15) — RED until 38-06.
#   * Pipe-syntax regression contracts — GREEN-on-day-zero, locked forever.
#   * PlayerCancelCommand incl. multi-draft symmetry (D-16, D-17) — RED until 38-06.
#   * Mid-dialog rejection guard for 7 verbs (D-05/07/08, SPEC Req 5) — RED until 38-07.
#
# Note on `discord.Thread`: conftest stubs it as `object`, so `isinstance(x, Thread)`
# is True for everything. Tests that exercise the thread-vs-non-thread branch install
# a real `_FakeThread` class via monkeypatch on `discord.Thread` for the test scope.
# ============================================================================

import sys
import types as _types
from unittest.mock import MagicMock, AsyncMock as _AsyncMock

import pytest


class _FakeThread:
    """Stand-in for a real ``discord.Thread`` instance.

    Conftest's ``discord.Thread = object`` cannot distinguish thread vs non-thread
    via isinstance — tests that need that distinction monkeypatch ``discord.Thread``
    to this class for the test's scope.
    """

    def __init__(self, thread_id: int):
        self.id = thread_id
        self.edit = _AsyncMock()


class _FakeTextChannel:
    """Stand-in for a non-Thread channel (e.g. a regular ``discord.TextChannel``)."""

    def __init__(self, channel_id: int = 1):
        self.id = channel_id


def _install_fake_dialog_module(monkeypatch, **funcs):
    """Install a fake ``pathfinder_player_dialog`` module with given coroutines.

    Returns the fake module so individual tests can introspect call args.
    """
    fake = _types.ModuleType("pathfinder_player_dialog")
    fake.start_dialog = funcs.get("start_dialog", _AsyncMock())
    fake.resume_dialog = funcs.get("resume_dialog", _AsyncMock())
    fake.cancel_dialog = funcs.get("cancel_dialog", _AsyncMock())
    monkeypatch.setitem(sys.modules, "pathfinder_player_dialog", fake)
    return fake


def _make_http_client(*, get_responses=None, delete_recorder=None):
    """Build an AsyncMock httpx-style client. ``get_responses`` is a queue or
    callable returning responses with ``.status_code`` and ``.json()``."""
    client = _AsyncMock()
    if get_responses is not None:
        client.get = _AsyncMock(side_effect=get_responses)
    else:
        client.get = _AsyncMock()
    client.delete = _AsyncMock() if delete_recorder is None else delete_recorder
    client.put = _AsyncMock()
    return client


def _resp(status_code: int, json_body=None, text_body: str = ""):
    r = MagicMock()
    r.status_code = status_code
    r.json = MagicMock(return_value=json_body if json_body is not None else {})
    r.text = text_body
    return r


# --- Task 1: PlayerStartCommand no-args branch (RED) ------------------------


async def test_player_start_no_args_creates_thread_and_draft(monkeypatch):
    """RED until 38-06: empty rest with non-Thread channel must create a new
    onboarding thread + draft via ``pathfinder_player_dialog.start_dialog``,
    NOT return the legacy ``_USAGE`` string. Asserts the new ``author_display_name``
    field on PathfinderRequest is forwarded to ``start_dialog`` as ``display_name``.
    """
    from pathfinder_player_adapter import PlayerStartCommand

    fake_thread = _FakeThread(thread_id=12345)
    start_dialog = _AsyncMock(return_value=fake_thread)
    fake_dialog = _install_fake_dialog_module(monkeypatch, start_dialog=start_dialog)

    channel = _FakeTextChannel(channel_id=999)
    http_client = _make_http_client(get_responses=[_resp(404)])
    sentinel_client = _AsyncMock()
    sentinel_client.post_to_module = _AsyncMock()

    request = PathfinderRequest(
        noun="player",
        verb="start",
        rest="",
        user_id="u-1",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=http_client,
        author_display_name="Trekkie",
    )
    response = await PlayerStartCommand().handle(request)

    assert fake_dialog.start_dialog.await_count == 1
    kwargs = fake_dialog.start_dialog.call_args.kwargs
    assert kwargs.get("invoking_channel") is channel
    assert kwargs.get("user_id") == "u-1"
    assert kwargs.get("display_name") == "Trekkie"
    assert kwargs.get("http_client") is http_client
    assert sentinel_client.post_to_module.await_count == 0
    assert response.kind == "text"
    assert f"<#{fake_thread.id}>" in response.content


async def test_player_start_no_args_in_thread_with_existing_draft_resumes(monkeypatch):
    """RED until 38-06: empty rest inside a Thread that already has a draft
    must call ``resume_dialog``, not ``start_dialog`` and not mutate the draft."""
    from pathfinder_player_adapter import PlayerStartCommand

    monkeypatch.setattr("discord.Thread", _FakeThread)
    channel = _FakeThread(thread_id=42)

    resume_dialog = _AsyncMock(return_value="What is your preferred name?")
    start_dialog = _AsyncMock()
    fake_dialog = _install_fake_dialog_module(
        monkeypatch, resume_dialog=resume_dialog, start_dialog=start_dialog
    )

    draft_body = "---\nstep: preferred_name\nuser_id: u-1\n---\n"
    http_client = _make_http_client(
        get_responses=[_resp(200, text_body=draft_body)]
    )
    # http_client.put would be the mutation channel — assert it's never awaited.
    sentinel_client = _AsyncMock()
    sentinel_client.post_to_module = _AsyncMock()

    request = PathfinderRequest(
        noun="player",
        verb="start",
        rest="",
        user_id="u-1",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=http_client,
        author_display_name="Trekkie",
    )
    response = await PlayerStartCommand().handle(request)

    assert fake_dialog.resume_dialog.await_count == 1
    rkwargs = fake_dialog.resume_dialog.call_args.kwargs
    assert rkwargs.get("thread") is channel
    assert rkwargs.get("user_id") == "u-1"
    assert fake_dialog.start_dialog.await_count == 0
    assert response.content == "What is your preferred name?"
    # SPEC Req 7: existing answers must not be re-written by resume.
    assert http_client.put.await_count == 0


# --- Task 1: Pipe-syntax regression contracts (GREEN-on-day-zero) ----------


async def test_pipe_syntax_regression_three_part_call_unchanged():
    """REGRESSION: pipe-syntax MUST keep working through Phase 38 (SPEC Constraint).
    Three-part pipe call posts the full onboard payload — same path it took in v0.x."""
    from pathfinder_player_adapter import PlayerStartCommand

    client = _AsyncMock()
    client.post_to_module = _AsyncMock(
        return_value={"path": "mnemosyne/pf2e/players/p-ari/profile.md"}
    )
    request = PathfinderRequest(
        noun="player",
        verb="start",
        rest="Aria | Ari | Tactician",
        user_id="u-1",
        sentinel_client=client,
    )
    response = await PlayerStartCommand().handle(request)
    assert client.post_to_module.await_count == 1
    args = client.post_to_module.call_args[0]
    assert args[0] == "modules/pathfinder/player/onboard"
    payload = args[1]
    assert payload["user_id"] == "u-1"
    assert payload["character_name"] == "Aria"
    assert payload["preferred_name"] == "Ari"
    assert payload["style_preset"] == "Tactician"
    assert response.kind == "text"
    assert "`Ari`" in response.content
    assert "Tactician" in response.content


async def test_pipe_syntax_regression_invalid_preset_returns_text():
    """REGRESSION: pipe-syntax stays strict — invalid preset returns text and
    does NOT post to the module nor open a dialog (SPEC Constraint)."""
    from pathfinder_player_adapter import PlayerStartCommand

    client = _AsyncMock()
    client.post_to_module = _AsyncMock()
    request = PathfinderRequest(
        noun="player",
        verb="start",
        rest="Aria | Ari | Wizard",
        user_id="u-1",
        sentinel_client=client,
    )
    response = await PlayerStartCommand().handle(request)
    assert response.kind == "text"
    assert "Invalid style preset" in response.content
    for preset in ("Tactician", "Lorekeeper", "Cheerleader", "Rules-Lawyer Lite"):
        assert preset in response.content
    assert client.post_to_module.await_count == 0


async def test_pipe_syntax_regression_no_thread_created(monkeypatch):
    """REGRESSION: pipe-syntax flow MUST NOT create or resume a dialog thread —
    it's the one-shot synchronous path (SPEC Acceptance)."""
    from pathfinder_player_adapter import PlayerStartCommand

    fake_dialog = _install_fake_dialog_module(
        monkeypatch,
        start_dialog=_AsyncMock(),
        resume_dialog=_AsyncMock(),
    )

    client = _AsyncMock()
    client.post_to_module = _AsyncMock(return_value={"path": "x.md"})
    request = PathfinderRequest(
        noun="player",
        verb="start",
        rest="Kael | Kael | Lorekeeper",
        user_id="u-1",
        sentinel_client=client,
    )
    await PlayerStartCommand().handle(request)
    assert fake_dialog.start_dialog.await_count == 0
    assert fake_dialog.resume_dialog.await_count == 0


async def test_pipe_syntax_regression_payload_byte_for_byte_matches_dialog_completion_payload():
    """REGRESSION (RESEARCH Q8): pipe-syntax payload contract — exactly four keys —
    so it stays byte-equivalent to the payload the dialog-completion path will build."""
    from pathfinder_player_adapter import PlayerStartCommand

    client = _AsyncMock()
    client.post_to_module = _AsyncMock(return_value={"path": "x.md"})
    request = PathfinderRequest(
        noun="player",
        verb="start",
        rest="Kael Stormblade | Kael | Cheerleader",
        user_id="u-1",
        sentinel_client=client,
    )
    await PlayerStartCommand().handle(request)
    payload = client.post_to_module.call_args[0][1]
    assert set(payload.keys()) == {
        "user_id",
        "character_name",
        "preferred_name",
        "style_preset",
    }


# --- Task 2: PlayerCancelCommand RED tests (D-16, D-17) --------------------


async def test_player_cancel_with_no_draft_returns_no_progress_text(monkeypatch):
    """RED until 38-06: cancel with zero drafts returns SPEC-verbatim text."""
    from pathfinder_player_adapter import PlayerCancelCommand

    monkeypatch.setattr("discord.Thread", _FakeThread)
    channel = _FakeThread(thread_id=42)

    cancel_dialog = _AsyncMock(return_value="No onboarding dialog in progress.")
    fake_dialog = _install_fake_dialog_module(
        monkeypatch, cancel_dialog=cancel_dialog
    )

    http_client = _make_http_client(get_responses=[_resp(404)])
    sentinel_client = _AsyncMock()
    request = PathfinderRequest(
        noun="player",
        verb="cancel",
        rest="",
        user_id="u-1",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )
    response = await PlayerCancelCommand().handle(request)
    assert response.kind == "text"
    assert response.content == "No onboarding dialog in progress."
    # Either cancel_dialog returned that text or the adapter returned it directly.
    # In both cases the contract is the verbatim string. fake_dialog kept for symmetry.
    _ = fake_dialog


async def test_player_cancel_with_draft_delegates_to_cancel_dialog(monkeypatch):
    """RED until 38-06: cancel from inside a thread delegates to ``cancel_dialog``."""
    from pathfinder_player_adapter import PlayerCancelCommand

    monkeypatch.setattr("discord.Thread", _FakeThread)
    channel = _FakeThread(thread_id=42)

    ack = "Onboarding cancelled. Run `:pf player start` to begin again."
    cancel_dialog = _AsyncMock(return_value=ack)
    fake_dialog = _install_fake_dialog_module(
        monkeypatch, cancel_dialog=cancel_dialog
    )

    draft_body = "---\nstep: preferred_name\n---\n"
    http_client = _make_http_client(get_responses=[_resp(200, text_body=draft_body)])
    sentinel_client = _AsyncMock()
    request = PathfinderRequest(
        noun="player",
        verb="cancel",
        rest="",
        user_id="u-1",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )
    response = await PlayerCancelCommand().handle(request)
    assert fake_dialog.cancel_dialog.await_count == 1
    ckwargs = fake_dialog.cancel_dialog.call_args.kwargs
    assert ckwargs.get("thread") is channel
    assert ckwargs.get("user_id") == "u-1"
    assert ckwargs.get("http_client") is http_client
    assert response.content == ack


async def test_player_cancel_from_non_thread_channel_single_draft_archives_remote_thread(monkeypatch):
    """Locks D-10 + D-17: cancel from outside the dialog thread MUST archive the remote thread."""
    from pathfinder_player_adapter import PlayerCancelCommand
    import bot as bot_module

    monkeypatch.setattr("discord.Thread", _FakeThread)
    channel = _FakeTextChannel(channel_id=1)  # NOT a Thread

    resolved_thread = _FakeThread(thread_id=999)
    get_channel = MagicMock(return_value=resolved_thread)
    monkeypatch.setattr(bot_module.bot, "get_channel", get_channel, raising=False)

    cancel_dialog = _AsyncMock(return_value="Cancelled the onboarding dialog.")
    fake_dialog = _install_fake_dialog_module(
        monkeypatch, cancel_dialog=cancel_dialog
    )

    # _drafts/ directory listing — single user-owned draft for u-1.
    listing = _resp(200, json_body=["999-u-1.md"])
    http_client = _make_http_client(get_responses=[listing])
    sentinel_client = _AsyncMock()

    request = PathfinderRequest(
        noun="player",
        verb="cancel",
        rest="",
        user_id="u-1",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )
    response = await PlayerCancelCommand().handle(request)

    get_channel.assert_called_once_with(999)
    assert fake_dialog.cancel_dialog.await_count == 1
    ckwargs = fake_dialog.cancel_dialog.call_args.kwargs
    assert ckwargs.get("thread") is resolved_thread
    assert "Cancelled the onboarding dialog." in response.content


async def test_player_cancel_from_non_thread_channel_with_two_drafts_archives_both(monkeypatch):
    """Locks D-17 multi-draft symmetry: cancel from outside ANY dialog thread
    archives ALL of THIS user's open dialogs. NO 'pick one' branch."""
    from pathfinder_player_adapter import PlayerCancelCommand
    import bot as bot_module
    import pathfinder_player_adapter as adapter_module

    monkeypatch.setattr("discord.Thread", _FakeThread)
    channel = _FakeTextChannel(channel_id=1)

    threads = {
        111: _FakeThread(thread_id=111),
        222: _FakeThread(thread_id=222),
        333: _FakeThread(thread_id=333),
        999: _FakeThread(thread_id=999),
    }

    def _get_channel(tid):
        return threads.get(tid)

    monkeypatch.setattr(bot_module.bot, "get_channel", MagicMock(side_effect=_get_channel), raising=False)

    fake_set = {111, 222, 333, 999}
    monkeypatch.setattr(adapter_module, "SENTINEL_THREAD_IDS", fake_set, raising=False)
    # Some implementations import the symbol at module load — also patch on bot.
    monkeypatch.setattr(bot_module, "SENTINEL_THREAD_IDS", fake_set, raising=False)

    # cancel_dialog mimics 38-06 behaviour: deletes draft via http_client AND
    # archives the thread AND removes id from SENTINEL_THREAD_IDS.
    delete_calls = []

    async def _cancel_dialog(*, thread, user_id, http_client):
        await http_client.delete(f"_drafts/{thread.id}-{user_id}.md")
        await thread.edit(archived=True)
        fake_set.discard(thread.id)
        return "ok"

    fake_dialog = _install_fake_dialog_module(
        monkeypatch, cancel_dialog=_AsyncMock(side_effect=_cancel_dialog)
    )

    listing = _resp(
        200,
        json_body=["111-u-1.md", "222-u-1.md", "333-u-2.md"],
    )
    http_client = _make_http_client(get_responses=[listing])

    async def _track_delete(url, *args, **kwargs):
        delete_calls.append(url)
        return _resp(200)

    http_client.delete = _AsyncMock(side_effect=_track_delete)

    sentinel_client = _AsyncMock()
    request = PathfinderRequest(
        noun="player",
        verb="cancel",
        rest="",
        user_id="u-1",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )
    response = await PlayerCancelCommand().handle(request)

    # cancel_dialog called for 111 and 222, NOT 333.
    targeted_ids = sorted(
        c.kwargs["thread"].id for c in fake_dialog.cancel_dialog.await_args_list
    )
    assert targeted_ids == [111, 222]

    # Both draft files deleted; not 333.
    joined = "|".join(delete_calls)
    assert "111-u-1.md" in joined
    assert "222-u-1.md" in joined
    assert "333-u-2.md" not in joined

    # Both threads archived.
    assert threads[111].edit.await_count == 1
    assert threads[222].edit.await_count == 1
    assert threads[111].edit.await_args.kwargs.get("archived") is True
    assert threads[222].edit.await_args.kwargs.get("archived") is True

    # Thread-id set: 111, 222 removed; 333 + 999 remain.
    assert 111 not in fake_set
    assert 222 not in fake_set
    assert 333 in fake_set
    assert 999 in fake_set

    # Multi-draft response phrasing.
    assert "Cancelled 2 onboarding dialogs." in response.content
    assert "pick one" not in response.content.lower()
    assert "from inside the thread" not in response.content.lower()


async def test_player_cancel_multi_draft_one_archive_failure_still_completes_others(monkeypatch):
    """Locks D-17 step 3: per-thread archive failures aggregate — loop MUST NOT abort."""
    from pathfinder_player_adapter import PlayerCancelCommand
    import bot as bot_module
    import pathfinder_player_adapter as adapter_module
    import discord as discord_module

    monkeypatch.setattr("discord.Thread", _FakeThread)
    channel = _FakeTextChannel(channel_id=1)

    bad_thread = _FakeThread(thread_id=111)
    bad_thread.edit = _AsyncMock(side_effect=discord_module.HTTPException("archive 403"))
    good_thread = _FakeThread(thread_id=222)

    threads = {111: bad_thread, 222: good_thread}
    monkeypatch.setattr(
        bot_module.bot,
        "get_channel",
        MagicMock(side_effect=lambda tid: threads.get(tid)),
        raising=False,
    )

    fake_set = {111, 222}
    monkeypatch.setattr(adapter_module, "SENTINEL_THREAD_IDS", fake_set, raising=False)
    monkeypatch.setattr(bot_module, "SENTINEL_THREAD_IDS", fake_set, raising=False)

    delete_calls = []

    async def _cancel_dialog(*, thread, user_id, http_client):
        # Always delete the draft file first (vault-side cleanup).
        await http_client.delete(f"_drafts/{thread.id}-{user_id}.md")
        # Then attempt archive; aggregate failure rather than raising.
        try:
            await thread.edit(archived=True)
        except discord_module.HTTPException:
            return "failed-archive"
        fake_set.discard(thread.id)
        return "ok"

    _install_fake_dialog_module(
        monkeypatch, cancel_dialog=_AsyncMock(side_effect=_cancel_dialog)
    )

    listing = _resp(200, json_body=["111-u-1.md", "222-u-1.md"])
    http_client = _make_http_client(get_responses=[listing])

    async def _track_delete(url, *args, **kwargs):
        delete_calls.append(url)
        return _resp(200)

    http_client.delete = _AsyncMock(side_effect=_track_delete)

    sentinel_client = _AsyncMock()
    request = PathfinderRequest(
        noun="player",
        verb="cancel",
        rest="",
        user_id="u-1",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )
    response = await PlayerCancelCommand().handle(request)

    # Both drafts deleted despite 111's archive failure.
    joined = "|".join(delete_calls)
    assert "111-u-1.md" in joined
    assert "222-u-1.md" in joined
    # 222 archived; 111 attempted.
    assert good_thread.edit.await_count == 1
    assert bad_thread.edit.await_count == 1
    # Loop completed — both 'Cancelled 2' total or diagnostic mentioning 111.
    content = response.content
    assert "Cancelled 2 onboarding dialogs." in content or "<#111>" in content


async def test_player_cancel_registered_in_dispatch():
    """Locks D-16: PlayerCancelCommand MUST be registered under player.cancel."""
    import pathfinder_dispatch
    from pathfinder_player_adapter import PlayerCancelCommand

    cmd = pathfinder_dispatch.COMMANDS["player"]["cancel"]
    assert isinstance(cmd, PlayerCancelCommand)


# --- Task 3: Mid-dialog rejection guard (RED) ------------------------------


def _drafts_listing_response(filenames):
    """Build a fake `_drafts/` GET response in the array-of-strings shape."""
    return _resp(200, json_body=list(filenames))


def _drafts_listing_response_object_shape(filenames):
    """Build a fake `_drafts/` GET response in the {files:[{path:...}]} shape
    (Pitfall 5 dual-shape parse)."""
    return _resp(
        200,
        json_body={"files": [{"path": p} for p in filenames]},
    )


@pytest.mark.parametrize(
    "verb_rest, command_name",
    [
        ("I trust Varek", "PlayerNoteCommand"),
        ("What's the AC of a goblin?", "PlayerAskCommand"),
        ("Varek trustworthy", "PlayerNpcCommand"),
        ("Varek", "PlayerRecallCommand"),
        ("buy rope", "PlayerTodoCommand"),
        ("list", "PlayerStyleCommand"),
        ("green q-1 The rule is...", "PlayerCanonizeCommand"),
    ],
)
async def test_verb_blocked_when_draft_open(verb_rest, command_name):
    """RED until 38-07 ships ``reject_if_draft_open``: every non-start/non-cancel
    verb MUST short-circuit when a draft exists for THIS user (D-05/07/08)."""
    import pathfinder_player_adapter as adapter_module

    cmd = getattr(adapter_module, command_name)()
    client = _AsyncMock()
    client.post_to_module = _AsyncMock()
    http_client = _make_http_client(
        get_responses=[_drafts_listing_response(["999-u-1.md"])]
    )
    request = PathfinderRequest(
        noun="player",
        verb="anyverb",
        rest=verb_rest,
        user_id="u-1",
        sentinel_client=client,
        http_client=http_client,
    )
    response = await cmd.handle(request)
    # Guard tripped — no module call.
    assert client.post_to_module.await_count == 0
    assert response.kind == "text"
    assert "<#999>" in response.content
    assert ":pf player cancel" in response.content
    assert "onboarding" in response.content.lower()


async def test_multi_draft_rejection_lists_all_thread_links_for_this_user():
    """Locks D-08: the rejection text lists EVERY draft for this user, but
    NOT drafts owned by a different user (PVL-07 isolation)."""
    from pathfinder_player_adapter import PlayerNoteCommand

    cmd = PlayerNoteCommand()
    client = _AsyncMock()
    client.post_to_module = _AsyncMock()
    http_client = _make_http_client(
        get_responses=[_drafts_listing_response(["111-u-1.md", "222-u-1.md", "333-u-2.md"])]
    )
    request = PathfinderRequest(
        noun="player",
        verb="note",
        rest="hi",
        user_id="u-1",
        sentinel_client=client,
        http_client=http_client,
    )
    response = await cmd.handle(request)
    assert "<#111>" in response.content
    assert "<#222>" in response.content
    assert "<#333>" not in response.content
    assert client.post_to_module.await_count == 0


async def test_no_draft_passes_through_to_normal_verb():
    """Locks PVL-07: rejection only fires for THIS user's drafts. A draft owned
    by a different user MUST NOT block this user's verb."""
    from pathfinder_player_adapter import PlayerNoteCommand

    cmd = PlayerNoteCommand()
    client = _AsyncMock()
    client.post_to_module = _AsyncMock(return_value={"path": "inbox.md"})
    http_client = _make_http_client(
        get_responses=[_drafts_listing_response(["333-u-2.md"])]
    )
    request = PathfinderRequest(
        noun="player",
        verb="note",
        rest="hello",
        user_id="u-1",
        sentinel_client=client,
        http_client=http_client,
    )
    await cmd.handle(request)
    assert client.post_to_module.await_count == 1
    args = client.post_to_module.call_args[0]
    assert args[0] == "modules/pathfinder/player/note"


async def test_drafts_dir_404_passes_through():
    """Locks RESEARCH §Pitfall 4: missing _drafts/ dir means no rejection — verb
    proceeds normally."""
    from pathfinder_player_adapter import PlayerNoteCommand

    cmd = PlayerNoteCommand()
    client = _AsyncMock()
    client.post_to_module = _AsyncMock(return_value={"path": "inbox.md"})
    http_client = _make_http_client(get_responses=[_resp(404)])
    request = PathfinderRequest(
        noun="player",
        verb="note",
        rest="hello",
        user_id="u-1",
        sentinel_client=client,
        http_client=http_client,
    )
    await cmd.handle(request)
    assert client.post_to_module.await_count == 1


async def test_drafts_listing_object_shape_also_rejected():
    """Locks RESEARCH §Pitfall 5: dual-shape ``_drafts/`` listing — object shape
    ``{"files":[{"path":"..."}]}`` must trigger rejection just like the array shape."""
    from pathfinder_player_adapter import PlayerNoteCommand

    cmd = PlayerNoteCommand()
    client = _AsyncMock()
    client.post_to_module = _AsyncMock()
    http_client = _make_http_client(
        get_responses=[_drafts_listing_response_object_shape(["555-u-1.md"])]
    )
    request = PathfinderRequest(
        noun="player",
        verb="note",
        rest="hi",
        user_id="u-1",
        sentinel_client=client,
        http_client=http_client,
    )
    response = await cmd.handle(request)
    assert client.post_to_module.await_count == 0
    assert "<#555>" in response.content
