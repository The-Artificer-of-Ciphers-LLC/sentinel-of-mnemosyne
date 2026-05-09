"""Wave 0 RED tests for ``interfaces/discord/dialog_router.py``.

These tests lock the hit/miss contract of the new pre-router gate
``dialog_router.maybe_consume_as_answer`` BEFORE any implementation lands
(Phase 38, plan 38-02, TDD wave 0).

Hit conditions (D-02 in 38-CONTEXT.md — all must hold):
  1. ``message`` does NOT start with ``":"`` (raw user prefix check; ignore
     leading whitespace per ``command_router.py:8-34`` conventions).
  2. ``channel`` is an instance of ``discord.Thread``.
  3. A draft exists at
     ``mnemosyne/pf2e/players/_drafts/{channel.id}-{user_id}.md`` (HTTP GET
     returns 200).

Miss → return ``None``. The bridge falls through to ``command_router`` unchanged.

Conventions:
- Function-scope ``from dialog_router import ...`` so collection fails with
  ImportError until ``dialog_router.py`` ships in Wave 2 (38-05) — the RED state.
- ``pathfinder_player_dialog.consume_as_answer`` is also lazily imported and
  stubbed via monkeypatch; both modules are net-new in Phase 38, so the import
  is wrapped in a small helper that keeps the ImportError on ``dialog_router``
  as the canonical RED signal.
- Discord stubs come from ``conftest.py`` (Phase 33-01 decision). The conftest
  stub sets ``discord.Thread = object``, so for the "not a Thread" miss test we
  monkeypatch ``discord.Thread`` to a distinguishing class — otherwise
  ``isinstance`` would always be True against ``object``.
- Behavioral assertions only (no source-grep, no vacuous truth).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord  # provided by conftest stub
import httpx


# --- helpers ---------------------------------------------------------------


class _RealThread:
    """Stand-in for the real ``discord.Thread`` class so ``isinstance`` checks
    inside ``dialog_router`` actually discriminate threads from non-threads.

    The conftest stub aliases ``discord.Thread = object``, which makes every
    Python object satisfy ``isinstance(x, discord.Thread)``. For the RED tests
    we monkeypatch ``discord.Thread`` to this class so the contract under test
    can be exercised behaviorally once the implementation ships.
    """


class _RealNonThread:
    """Stand-in for a non-thread channel type (e.g. ``discord.TextChannel``)."""


def _make_response(status_code: int, body: str = "step: character_name\n") -> httpx.Response:
    """Build a real ``httpx.Response`` so production code can call ``.status_code``,
    ``.text``, and ``.raise_for_status()`` against a realistic object."""
    return httpx.Response(status_code=status_code, text=body)


def _stub_consume_as_answer(monkeypatch, *, return_value: str | None = "next question"):
    """Install an ``AsyncMock`` at ``pathfinder_player_dialog.consume_as_answer``.

    Both ``pathfinder_player_dialog`` and ``dialog_router`` are net-new — the
    test's authoritative RED signal is ImportError on ``dialog_router``. We try
    to patch ``pathfinder_player_dialog`` if it exists; if not, we register a
    minimal stub module so the import inside ``dialog_router`` (once it ships)
    can resolve in test runs that import ``dialog_router`` first.
    """
    import sys
    import types

    mock = AsyncMock(return_value=return_value)
    mod = sys.modules.get("pathfinder_player_dialog")
    if mod is None:
        mod = types.ModuleType("pathfinder_player_dialog")
        sys.modules["pathfinder_player_dialog"] = mod
    monkeypatch.setattr(mod, "consume_as_answer", mock, raising=False)
    return mock


# --- miss: colon prefix ----------------------------------------------------


async def test_miss_when_message_has_colon_prefix(monkeypatch):
    monkeypatch.setattr(discord, "Thread", _RealThread, raising=False)
    consume = _stub_consume_as_answer(monkeypatch)

    from dialog_router import maybe_consume_as_answer

    channel = MagicMock(spec=_RealThread)
    channel.id = 42
    http_client = MagicMock()
    http_client.get = AsyncMock(return_value=_make_response(200))
    sentinel_client = MagicMock()

    result = await maybe_consume_as_answer(
        user_id="u-1",
        message=":pf player note hi",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )

    assert result is None
    assert consume.await_count == 0


# --- miss: leading whitespace then colon -----------------------------------


async def test_miss_when_message_has_leading_whitespace_then_colon(monkeypatch):
    """Locks the "raw user prefix check ignores leading whitespace" alignment
    with ``command_router.py``: ``"  :pf player ask foo"`` is still a command,
    not an onboarding answer."""
    monkeypatch.setattr(discord, "Thread", _RealThread, raising=False)
    consume = _stub_consume_as_answer(monkeypatch)

    from dialog_router import maybe_consume_as_answer

    channel = MagicMock(spec=_RealThread)
    channel.id = 42
    http_client = MagicMock()
    http_client.get = AsyncMock(return_value=_make_response(200))
    sentinel_client = MagicMock()

    result = await maybe_consume_as_answer(
        user_id="u-1",
        message="  :pf player ask foo",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )

    assert result is None
    assert consume.await_count == 0


# --- miss: channel is not a Thread -----------------------------------------


async def test_miss_when_channel_is_not_thread(monkeypatch):
    """Channel-type early-out: not a Thread → return None WITHOUT issuing the
    HTTP GET (D-02 ordering — cheapest check first to keep blast radius zero
    in regular text channels)."""
    monkeypatch.setattr(discord, "Thread", _RealThread, raising=False)
    consume = _stub_consume_as_answer(monkeypatch)

    from dialog_router import maybe_consume_as_answer

    channel = MagicMock(spec=_RealNonThread)  # NOT a Thread
    channel.id = 42
    http_client = MagicMock()
    http_client.get = AsyncMock(return_value=_make_response(200))
    sentinel_client = MagicMock()

    result = await maybe_consume_as_answer(
        user_id="u-1",
        message="Kaela",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )

    assert result is None
    assert http_client.get.await_count == 0  # early-out before listing
    assert consume.await_count == 0


# --- miss: draft does not exist --------------------------------------------


async def test_miss_when_draft_does_not_exist(monkeypatch):
    monkeypatch.setattr(discord, "Thread", _RealThread, raising=False)
    consume = _stub_consume_as_answer(monkeypatch)

    from dialog_router import maybe_consume_as_answer

    channel = MagicMock(spec=_RealThread)
    channel.id = 42
    http_client = MagicMock()
    http_client.get = AsyncMock(return_value=_make_response(404, body="not found"))
    sentinel_client = MagicMock()

    result = await maybe_consume_as_answer(
        user_id="u-1",
        message="Kaela",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )

    assert result is None
    assert consume.await_count == 0


# --- hit: invokes consume_as_answer ----------------------------------------


async def test_hit_invokes_consume_as_answer(monkeypatch):
    """All three hit conditions hold: no colon, real Thread, draft 200.
    Result MUST be the string returned by ``consume_as_answer`` and the call
    args MUST forward thread/user_id/message_text/sentinel_client/http_client
    by keyword."""
    monkeypatch.setattr(discord, "Thread", _RealThread, raising=False)
    consume = _stub_consume_as_answer(monkeypatch, return_value="next question")

    from dialog_router import maybe_consume_as_answer

    channel = MagicMock(spec=_RealThread)
    channel.id = 42
    http_client = MagicMock()
    http_client.get = AsyncMock(return_value=_make_response(200))
    sentinel_client = MagicMock()

    result = await maybe_consume_as_answer(
        user_id="u-1",
        message="Kaela",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )

    assert result == "next question"
    assert consume.await_count == 1
    kwargs = consume.await_args.kwargs
    assert kwargs["thread"] is channel
    assert kwargs["user_id"] == "u-1"
    assert kwargs["message_text"] == "Kaela"
    assert kwargs["sentinel_client"] is sentinel_client
    assert kwargs["http_client"] is http_client


# --- hit: thread id used in draft path lookup ------------------------------


async def test_hit_uses_thread_id_in_draft_path_lookup(monkeypatch):
    """The HTTP GET URL must include the canonical draft path
    ``mnemosyne/pf2e/players/_drafts/{thread.id}-{user_id}.md`` so the gate
    is keyed strictly on ``(thread_id, user_id)`` (38-CONTEXT.md D-02)."""
    monkeypatch.setattr(discord, "Thread", _RealThread, raising=False)
    _stub_consume_as_answer(monkeypatch, return_value="next question")

    from dialog_router import maybe_consume_as_answer

    channel = MagicMock(spec=_RealThread)
    channel.id = 999
    http_client = MagicMock()
    http_client.get = AsyncMock(return_value=_make_response(200))
    sentinel_client = MagicMock()

    await maybe_consume_as_answer(
        user_id="u-1",
        message="Kaela",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )

    assert http_client.get.await_count == 1
    # First positional arg or "url" kwarg must end with the canonical draft path.
    call = http_client.get.await_args
    url = call.args[0] if call.args else call.kwargs.get("url", "")
    assert url.endswith("/vault/mnemosyne/pf2e/players/_drafts/999-u-1.md"), (
        f"draft path must be keyed on (thread_id, user_id); got url={url!r}"
    )


# --- miss: empty message ---------------------------------------------------


async def test_empty_message_is_miss(monkeypatch):
    """Avoids treating Discord embed-only messages (or whitespace-only edits)
    as onboarding answers."""
    monkeypatch.setattr(discord, "Thread", _RealThread, raising=False)
    consume = _stub_consume_as_answer(monkeypatch)

    from dialog_router import maybe_consume_as_answer

    channel = MagicMock(spec=_RealThread)
    channel.id = 42
    http_client = MagicMock()
    http_client.get = AsyncMock(return_value=_make_response(200))
    sentinel_client = MagicMock()

    result = await maybe_consume_as_answer(
        user_id="u-1",
        message="",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )

    assert result is None
    assert consume.await_count == 0


# --- miss: Obsidian GET error falls through --------------------------------


async def test_obsidian_get_error_falls_through(monkeypatch):
    """Defensive: the GATE before commit is non-fatal. A network error from
    Obsidian during the existence check must not crash the message handler —
    the router treats it as a miss so ``command_router`` still runs."""
    monkeypatch.setattr(discord, "Thread", _RealThread, raising=False)
    consume = _stub_consume_as_answer(monkeypatch)

    from dialog_router import maybe_consume_as_answer

    channel = MagicMock(spec=_RealThread)
    channel.id = 42
    http_client = MagicMock()
    http_client.get = AsyncMock(side_effect=httpx.RequestError("boom"))
    sentinel_client = MagicMock()

    result = await maybe_consume_as_answer(
        user_id="u-1",
        message="Kaela",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=http_client,
    )

    assert result is None
    assert consume.await_count == 0
