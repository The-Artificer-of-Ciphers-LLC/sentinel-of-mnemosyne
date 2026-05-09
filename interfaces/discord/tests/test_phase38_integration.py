"""Phase 38 end-to-end acceptance tests.

One test per SPEC acceptance-criteria checkbox 1..9. Tests use an in-memory
FakeVault fixture to exercise the full bridge -> dialog_router ->
pathfinder_player_dialog pipeline without touching live Obsidian/Discord.

SPEC criterion 10 (Wave-0 RED tests committed BEFORE implementation) is a
property of the git history, not of the test corpus, and is verified
manually in 38-09 Task 3 via ``git log --diff-filter=A``. It does NOT have
a test in this file.
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from pathfinder_types import PathfinderRequest


# ---------------------------------------------------------------------------
# FakeVault — in-memory dict-backed Obsidian REST stand-in.
# ---------------------------------------------------------------------------


class FakeVault:
    """Dict-backed mock of the Obsidian REST API.

    Exposes ``.client`` with AsyncMock-shaped ``get``, ``put``, ``delete``
    that read/write ``self._files: dict[str, str]`` keyed by the *vault path*
    (i.e. the part after ``/vault/`` in the URL). Tests assert on
    ``self._files`` directly to verify side-effects.
    """

    _URL_RE = re.compile(r"^https?://[^/]+/vault/(.+?)/?$")

    def __init__(self) -> None:
        self._files: dict[str, str] = {}
        self.client = MagicMock()
        self.client.get = AsyncMock(side_effect=self._get)
        self.client.put = AsyncMock(side_effect=self._put)
        self.client.delete = AsyncMock(side_effect=self._delete)

    @classmethod
    def _path(cls, url: str) -> str:
        m = cls._URL_RE.match(url)
        return m.group(1) if m else url

    def _resp(self, status: int, body: str = "", json_body=None) -> MagicMock:
        r = MagicMock()
        r.status_code = status
        r.text = body
        r.json = MagicMock(return_value=json_body if json_body is not None else {})
        r.raise_for_status = MagicMock()
        return r

    async def _get(self, url, *args, **kwargs):
        path = self._path(str(url))
        # Directory listing — used by reject_if_draft_open.
        if path.endswith("/") or path == "mnemosyne/pf2e/players/_drafts":
            prefix = path.rstrip("/") + "/"
            files = [k.split("/")[-1] for k in self._files if k.startswith(prefix)]
            if not files and not any(k.startswith(prefix) for k in self._files):
                return self._resp(404, "")
            return self._resp(200, "", json_body={"files": files})
        body = self._files.get(path)
        if body is None:
            return self._resp(404, "")
        return self._resp(200, body)

    async def _put(self, url, *args, **kwargs):
        path = self._path(str(url))
        body = None
        if args:
            body = args[0]
        if body is None:
            body = kwargs.get("content") or kwargs.get("data")
        if isinstance(body, bytes):
            body = body.decode()
        self._files[path] = body or ""
        return self._resp(200, "")

    async def _delete(self, url, *args, **kwargs):
        path = self._path(str(url))
        self._files.pop(path, None)
        return self._resp(200, "")


def _draft_path(thread_id: int, user_id: str) -> str:
    return f"mnemosyne/pf2e/players/_drafts/{thread_id}-{user_id}.md"


def _seed_draft(vault: FakeVault, *, thread_id: int, user_id: str, **fields) -> None:
    """Write a frontmatter-only draft body to the vault."""
    import yaml

    payload = {"thread_id": thread_id, "user_id": user_id, **fields}
    block = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True).strip()
    vault._files[_draft_path(thread_id, user_id)] = f"---\n{block}\n---\n\n"


# ---------------------------------------------------------------------------
# Discord stand-ins.
# ---------------------------------------------------------------------------


class _FakeThread:
    """Stand-in for a real ``discord.Thread`` instance.

    Conftest stubs ``discord.Thread = object`` which makes isinstance always
    true; tests that exercise the thread-vs-non-thread branch monkeypatch
    ``discord.Thread`` to this class for the test scope.
    """

    def __init__(self, thread_id: int) -> None:
        self.id = thread_id
        self.send = AsyncMock()
        self.edit = AsyncMock()


class _FakeTextChannel:
    """Stand-in for a non-Thread channel."""

    def __init__(self, channel_id: int = 1) -> None:
        self.id = channel_id
        self.send = AsyncMock()
        # create_thread defaults: tests override per-case.
        self.create_thread = AsyncMock()


def _make_sentinel_client(profile_path: str = "mnemosyne/pf2e/players/k/profile.md") -> MagicMock:
    client = MagicMock()
    client.post_to_module = AsyncMock(return_value={"path": profile_path, "ok": True})
    return client


# ---------------------------------------------------------------------------
# SPEC Acceptance 1: `:pf player start` no-args creates thread + posts Q1.
# ---------------------------------------------------------------------------


async def test_acceptance_01_start_no_args_creates_thread_and_posts_first_question(monkeypatch):
    """SPEC Acceptance 1: ``:pf player start`` with no args creates a new thread
    and posts the character-name prompt as its first message."""
    import bot as bot_module
    import discord

    from pathfinder_player_adapter import PlayerStartCommand
    from pathfinder_player_dialog import QUESTIONS

    monkeypatch.setattr(bot_module, "_persist_thread_id", AsyncMock())
    bot_module.SENTINEL_THREAD_IDS.discard(7777)

    fake_thread = _FakeThread(thread_id=7777)
    channel = _FakeTextChannel(channel_id=1)
    channel.create_thread = AsyncMock(return_value=fake_thread)
    vault = FakeVault()
    sentinel_client = _make_sentinel_client()

    request = PathfinderRequest(
        noun="player",
        verb="start",
        rest="",
        user_id="u-1",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=vault.client,
        author_display_name="Trekkie",
    )
    try:
        response = await PlayerStartCommand().handle(request)

        # Thread created with onboarding name + public type.
        assert channel.create_thread.await_count == 1
        kwargs = channel.create_thread.call_args.kwargs
        assert kwargs["name"].startswith("Onboarding")
        assert "Trekkie" in kwargs["name"]
        assert kwargs["type"] == discord.ChannelType.public_thread
        assert kwargs["auto_archive_duration"] == 60

        # First message inside the new thread is the character-name prompt.
        assert fake_thread.send.await_count == 1
        sent = fake_thread.send.call_args
        sent_text = sent.args[0] if sent.args else sent.kwargs.get("content", "")
        assert sent_text == QUESTIONS["character_name"]

        # Draft persisted with step=character_name.
        draft_body = vault._files.get(_draft_path(7777, "u-1"))
        assert draft_body is not None, "draft must be persisted in vault"
        assert "step: character_name" in draft_body

        # Adapter response acknowledges the new thread.
        assert response.kind == "text"
        assert f"<#{fake_thread.id}>" in response.content

        # Sentinel core / AI not invoked during start.
        assert sentinel_client.post_to_module.await_count == 0
    finally:
        bot_module.SENTINEL_THREAD_IDS.discard(7777)


# ---------------------------------------------------------------------------
# SPEC Acceptance 2: plain text in draft thread advances draft, no AI.
# ---------------------------------------------------------------------------


async def test_acceptance_02_thread_reply_updates_draft_no_ai(monkeypatch):
    """SPEC Acceptance 2: A plain-text reply in a draft-bearing thread updates
    the draft and posts the next prompt; the AI is not invoked."""
    import discord_router_bridge
    from pathfinder_player_dialog import QUESTIONS

    monkeypatch.setattr("discord.Thread", _FakeThread)

    vault = FakeVault()
    _seed_draft(
        vault,
        thread_id=42,
        user_id="u-1",
        step="character_name",
        started_at="2026-05-08T00:00:00Z",
    )
    fake_thread = _FakeThread(thread_id=42)
    sentinel_client = _make_sentinel_client()

    # AsyncMock command_router whose route_message must NEVER be called — proves
    # the AI / normal command path was bypassed (SPEC Req 2).
    fake_command_router = MagicMock()
    fake_command_router.route_message = AsyncMock()
    call_core = AsyncMock()
    handle_subcommand = AsyncMock()

    result = await discord_router_bridge.route_message(
        user_id="u-1",
        message="Kaela",
        attachments=None,
        channel=fake_thread,
        command_router=fake_command_router,
        handle_subcommand=handle_subcommand,
        call_core=call_core,
        subcommand_help="",
        sentinel_client=sentinel_client,
        http_client=vault.client,
        author_display_name="Trekkie",
    )

    # AI bypassed — neither command_router.route_message nor call_core were touched.
    assert fake_command_router.route_message.await_count == 0
    assert call_core.await_count == 0

    # Draft mutated: step advanced to preferred_name, character_name=Kaela.
    body = vault._files[_draft_path(42, "u-1")]
    assert "step: preferred_name" in body
    assert "character_name: Kaela" in body

    # Bridge returns the next prompt as text. bot.py's response_renderer is
    # responsible for posting it to the channel — consume_as_answer must NOT
    # post directly (in-module thread.send would double-post; UAT G-03).
    assert fake_thread.send.await_count == 0
    assert result == QUESTIONS["preferred_name"]


# ---------------------------------------------------------------------------
# SPEC Acceptance 3: bot restart preserves draft; resume completes.
# ---------------------------------------------------------------------------


async def test_acceptance_03_restart_between_answers_preserves_draft(monkeypatch):
    """SPEC Acceptance 3: Bot restart between answers preserves the draft;
    resuming with the next answer completes correctly.

    "Restart" is simulated by clearing SENTINEL_THREAD_IDS / any in-process
    Python state. Per D-06 the vault is the sole source of truth, so the
    draft survives and the dialog continues mid-flow.
    """
    import bot as bot_module

    from pathfinder_player_dialog import consume_as_answer

    vault = FakeVault()
    _seed_draft(
        vault,
        thread_id=42,
        user_id="u-1",
        step="preferred_name",
        character_name="Kaela",
        started_at="2026-05-08T00:00:00Z",
    )
    fake_thread = _FakeThread(thread_id=42)
    sentinel_client = _make_sentinel_client()

    # Simulate bot restart: in-process thread set wiped; vault is sole truth.
    bot_module.SENTINEL_THREAD_IDS.clear()
    monkeypatch.setattr(bot_module, "_persist_thread_id", AsyncMock())

    # Step 2 of 3: answer "Kae" -> step advances to style_preset.
    await consume_as_answer(
        thread=fake_thread,
        user_id="u-1",
        message_text="Kae",
        sentinel_client=sentinel_client,
        http_client=vault.client,
    )
    body = vault._files[_draft_path(42, "u-1")]
    assert "step: style_preset" in body
    assert "preferred_name: Kae" in body
    assert "character_name: Kaela" in body
    assert sentinel_client.post_to_module.await_count == 0

    # Step 3 of 3: answer "Lorekeeper" -> POST /player/onboard, draft deleted.
    await consume_as_answer(
        thread=fake_thread,
        user_id="u-1",
        message_text="Lorekeeper",
        sentinel_client=sentinel_client,
        http_client=vault.client,
    )

    assert sentinel_client.post_to_module.await_count == 1
    call = sentinel_client.post_to_module.call_args
    route = call.args[0]
    payload = call.args[1]
    assert route == "modules/pathfinder/player/onboard"
    assert payload == {
        "user_id": "u-1",
        "character_name": "Kaela",
        "preferred_name": "Kae",
        "style_preset": "Lorekeeper",
    }

    # Draft removed and thread archived.
    assert _draft_path(42, "u-1") not in vault._files
    assert fake_thread.edit.await_count == 1
    assert fake_thread.edit.call_args.kwargs.get("archived") is True


# ---------------------------------------------------------------------------
# SPEC Acceptance 4: dialog vs pipe-syntax payload byte-for-byte equality.
# ---------------------------------------------------------------------------


async def test_acceptance_04_dialog_completion_payload_byte_for_byte_matches_pipe_syntax(monkeypatch):
    """SPEC Acceptance 4: After all three answers, the ``/player/onboard``
    payload matches the pipe-syntax outcome byte-for-byte (modulo timestamps,
    which are server-side concerns — the client payload is identical)."""
    import bot as bot_module

    from pathfinder_player_adapter import PlayerStartCommand
    from pathfinder_player_dialog import consume_as_answer

    monkeypatch.setattr(bot_module, "_persist_thread_id", AsyncMock())

    # ----- Path A: dialog completion with three replies ------------------
    vault_a = FakeVault()
    _seed_draft(
        vault_a,
        thread_id=100,
        user_id="u-1",
        step="character_name",
        started_at="2026-05-08T00:00:00Z",
    )
    thread_a = _FakeThread(thread_id=100)
    sentinel_a = _make_sentinel_client()

    for answer in ("Aria", "Ari", "Tactician"):
        await consume_as_answer(
            thread=thread_a,
            user_id="u-1",
            message_text=answer,
            sentinel_client=sentinel_a,
            http_client=vault_a.client,
        )
    assert sentinel_a.post_to_module.await_count == 1
    dialog_payload = sentinel_a.post_to_module.call_args.args[1]

    # ----- Path B: pipe-syntax single-shot --------------------------------
    vault_b = FakeVault()
    sentinel_b = _make_sentinel_client()
    channel = _FakeTextChannel(channel_id=2)
    request = PathfinderRequest(
        noun="player",
        verb="start",
        rest="Aria | Ari | Tactician",
        user_id="u-1",
        channel=channel,
        sentinel_client=sentinel_b,
        http_client=vault_b.client,
    )
    await PlayerStartCommand().handle(request)
    assert sentinel_b.post_to_module.await_count == 1
    pipe_payload = sentinel_b.post_to_module.call_args.args[1]

    # Strict equality — same keys, same values, no extras.
    assert dialog_payload == pipe_payload
    assert dialog_payload == {
        "user_id": "u-1",
        "character_name": "Aria",
        "preferred_name": "Ari",
        "style_preset": "Tactician",
    }


# ---------------------------------------------------------------------------
# SPEC Acceptance 5: mid-dialog `:pf player <verb>` rejected, no vault mutation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command_cls,verb,rest",
    [
        ("PlayerNoteCommand", "note", "I trust Varek"),
        ("PlayerAskCommand", "ask", "What's the rule on flanking?"),
        ("PlayerNpcCommand", "npc", "Varek The smith is honest"),
        ("PlayerRecallCommand", "recall", "Varek"),
        ("PlayerTodoCommand", "todo", "buy rope"),
        ("PlayerStyleCommand", "style", "list"),
        ("PlayerCanonizeCommand", "canonize", "green q-1 The rule is..."),
    ],
)
async def test_acceptance_05_mid_dialog_verb_rejected_no_vault_mutation(
    monkeypatch, command_cls, verb, rest
):
    """SPEC Acceptance 5: Mid-dialog ``:pf player note|ask|npc|recall|todo|style|canonize``
    returns the rejection template and does NOT mutate the vault."""
    import pathfinder_player_adapter as adapter

    cmd_cls = getattr(adapter, command_cls)

    vault = FakeVault()
    _seed_draft(
        vault,
        thread_id=999,
        user_id="u-1",
        step="preferred_name",
        character_name="Kaela",
    )
    snapshot = dict(vault._files)

    channel = _FakeTextChannel(channel_id=1)
    sentinel_client = _make_sentinel_client()

    request = PathfinderRequest(
        noun="player",
        verb=verb,
        rest=rest,
        user_id="u-1",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=vault.client,
    )

    response = await cmd_cls().handle(request)

    # Rejection content references the active thread + cancel command.
    assert response.kind == "text"
    assert "<#999>" in response.content
    assert ":pf player cancel" in response.content

    # No HTTP write of any kind to the vault — draft snapshot byte-stable.
    assert vault._files == snapshot
    assert vault.client.put.await_count == 0
    assert vault.client.delete.await_count == 0

    # Sentinel core never called — no notes.md / inbox.md / etc. mutated.
    assert sentinel_client.post_to_module.await_count == 0


# ---------------------------------------------------------------------------
# SPEC Acceptance 6: `:pf player cancel` with draft deletes + acks.
# ---------------------------------------------------------------------------


async def test_acceptance_06_cancel_with_draft_deletes_and_acks(monkeypatch):
    """SPEC Acceptance 6: ``:pf player cancel`` with a draft deletes the draft
    file and replies with the cancel-acknowledgement message."""
    from pathfinder_player_adapter import PlayerCancelCommand

    monkeypatch.setattr("discord.Thread", _FakeThread)

    vault = FakeVault()
    _seed_draft(
        vault,
        thread_id=999,
        user_id="u-1",
        step="preferred_name",
        character_name="Kaela",
    )
    channel = _FakeThread(thread_id=999)
    sentinel_client = _make_sentinel_client()

    request = PathfinderRequest(
        noun="player",
        verb="cancel",
        rest="",
        user_id="u-1",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=vault.client,
    )
    response = await PlayerCancelCommand().handle(request)

    # Draft deleted and thread archived.
    assert _draft_path(999, "u-1") not in vault._files
    assert channel.edit.await_count == 1
    assert channel.edit.call_args.kwargs.get("archived") is True

    assert response.kind == "text"
    assert "cancelled" in response.content.lower()
    assert ":pf player start" in response.content
    assert sentinel_client.post_to_module.await_count == 0


# ---------------------------------------------------------------------------
# SPEC Acceptance 7: `:pf player cancel` with no draft -> no progress.
# ---------------------------------------------------------------------------


async def test_acceptance_07_cancel_no_draft_returns_no_progress(monkeypatch):
    """SPEC Acceptance 7: ``:pf player cancel`` with no draft replies
    ``No onboarding dialog in progress.`` and does nothing."""
    from pathfinder_player_adapter import PlayerCancelCommand

    monkeypatch.setattr("discord.Thread", _FakeThread)

    vault = FakeVault()  # empty
    channel = _FakeThread(thread_id=42)
    sentinel_client = _make_sentinel_client()

    request = PathfinderRequest(
        noun="player",
        verb="cancel",
        rest="",
        user_id="u-1",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=vault.client,
    )
    response = await PlayerCancelCommand().handle(request)

    assert response.kind == "text"
    assert response.content == "No onboarding dialog in progress."
    assert vault.client.delete.await_count == 0
    assert channel.edit.await_count == 0
    assert vault._files == {}
    assert sentinel_client.post_to_module.await_count == 0


# ---------------------------------------------------------------------------
# SPEC Acceptance 8: re-issuing `start` in a draft-bearing thread resumes.
# ---------------------------------------------------------------------------


async def test_acceptance_08_start_with_draft_in_thread_resumes_no_reset(monkeypatch):
    """SPEC Acceptance 8: ``:pf player start`` re-issued in a thread with an
    in-flight draft re-posts the prompt for the current ``step`` and does NOT
    reset prior answers."""
    from pathfinder_player_adapter import PlayerStartCommand
    from pathfinder_player_dialog import QUESTIONS

    monkeypatch.setattr("discord.Thread", _FakeThread)

    vault = FakeVault()
    _seed_draft(
        vault,
        thread_id=42,
        user_id="u-1",
        step="preferred_name",
        character_name="Kaela",
        started_at="2026-05-08T00:00:00Z",
    )
    snapshot_before = dict(vault._files)
    snapshot_put_count = vault.client.put.await_count

    channel = _FakeThread(thread_id=42)
    sentinel_client = _make_sentinel_client()

    request = PathfinderRequest(
        noun="player",
        verb="start",
        rest="",
        user_id="u-1",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=vault.client,
        author_display_name="Trekkie",
    )
    response = await PlayerStartCommand().handle(request)

    # Resume returns the CURRENT step's prompt — preferred_name, not character_name.
    # resume_dialog must NOT post directly; bot.py's response_renderer sends
    # the returned text (UAT G-03 — in-module thread.send would double-post).
    assert channel.send.await_count == 0
    assert response.kind == "text"
    assert response.content == QUESTIONS["preferred_name"]

    # Draft NOT mutated: byte-stable, no new PUTs.
    assert vault._files == snapshot_before
    assert vault.client.put.await_count == snapshot_put_count

    # character_name still preserved in the body.
    assert "character_name: Kaela" in vault._files[_draft_path(42, "u-1")]

    # No new thread created (we're already inside the draft's thread).
    assert sentinel_client.post_to_module.await_count == 0
    assert response.kind == "text"


# ---------------------------------------------------------------------------
# SPEC Acceptance 9: pipe-syntax regression — no thread created.
# ---------------------------------------------------------------------------


async def test_acceptance_09_pipe_syntax_creates_no_thread():
    """SPEC Acceptance 9: ``:pf player start a | b | c`` (pipe syntax)
    regression: produces the same ``profile.md`` it did before this phase,
    with no thread created."""
    from pathfinder_player_adapter import PlayerStartCommand

    vault = FakeVault()
    sentinel_client = _make_sentinel_client(profile_path="mnemosyne/pf2e/players/ari/profile.md")

    channel = _FakeTextChannel(channel_id=99)
    # Booby-trap: any thread creation on this channel is a regression.
    channel.create_thread = AsyncMock(
        side_effect=AssertionError(
            "create_thread MUST NOT be called for pipe-syntax (regression)"
        )
    )

    request = PathfinderRequest(
        noun="player",
        verb="start",
        rest="Aria | Ari | Tactician",
        user_id="u-1",
        channel=channel,
        sentinel_client=sentinel_client,
        http_client=vault.client,
    )
    response = await PlayerStartCommand().handle(request)

    # Single POST to /player/onboard with the four-field payload.
    assert sentinel_client.post_to_module.await_count == 1
    call = sentinel_client.post_to_module.call_args
    assert call.args[0] == "modules/pathfinder/player/onboard"
    assert call.args[1] == {
        "user_id": "u-1",
        "character_name": "Aria",
        "preferred_name": "Ari",
        "style_preset": "Tactician",
    }

    # No draft persisted — pipe syntax skips the dialog state machine.
    assert not any(p.startswith("mnemosyne/pf2e/players/_drafts/") for p in vault._files)

    # Response references the resulting profile path, not a thread mention.
    assert response.kind == "text"
    assert "mnemosyne/pf2e/players/ari/profile.md" in response.content
    assert "Onboarding started in <#" not in response.content
