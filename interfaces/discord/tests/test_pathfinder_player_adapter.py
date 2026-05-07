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


async def test_player_start_posts_to_onboard_route():
    from pathfinder_player_adapter import PlayerStartCommand

    cmd = PlayerStartCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(
        return_value={"path": "mnemosyne/pf2e/players/p-abc/profile.md"}
    )
    request = PathfinderRequest(
        noun="player",
        verb="start",
        rest="",
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
    from pathfinder_player_adapter import PlayerAskCommand

    cmd = PlayerAskCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"question_id": "q-1"})
    request = PathfinderRequest(
        noun="player",
        verb="ask",
        rest="What rule applies to vital strike?",
        user_id="u1",
        sentinel_client=client,
    )
    await cmd.handle(request)
    args = client.post_to_module.call_args[0]
    assert args[0] == "modules/pathfinder/player/ask"
    payload = args[1]
    assert payload["user_id"] == "u1"
    assert payload["question"] == "What rule applies to vital strike?"


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
