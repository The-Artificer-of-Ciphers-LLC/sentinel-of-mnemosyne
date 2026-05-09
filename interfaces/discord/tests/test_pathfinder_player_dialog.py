"""Wave 0 RED tests for Discord pathfinder_player_dialog module (Phase 38).

These tests assert the contract the Wave 1 implementation (38-04) must satisfy:
- Step ordering and question text constants are locked verbatim (D-13).
- Draft path scheme is `mnemosyne/pf2e/players/_drafts/{thread_id}-{user_id}.md` (D-05).
- Draft I/O round-trips frontmatter via Obsidian REST PUT/GET/DELETE.
- start_dialog creates a public Discord thread, registers it in SENTINEL_THREAD_IDS,
  persists the first draft (step="character_name"), and posts the first prompt.
- resume_dialog re-posts the prompt for the draft's current step without mutating it.
- consume_as_answer advances the step on each valid reply, validates style preset
  case-insensitively against `_VALID_STYLE_PRESETS`, and on the final step calls
  `/player/onboard` exactly once with the four-field payload, deletes the draft,
  archives the thread, and removes the thread id from SENTINEL_THREAD_IDS.
- cancel_dialog deletes the draft, archives the thread, and replies with the
  cancel-acknowledgement; with no draft replies "No onboarding dialog in progress."

Conventions (mirrors test_pathfinder_player_adapter.py):
- ``async def test_*`` with no ``@pytest.mark.asyncio`` decorator (asyncio_mode = "auto").
- Function-scope ``from pathfinder_player_dialog import ...`` so collection succeeds
  but every test fails with ImportError until 38-04 lands the module — the RED state.
- ``AsyncMock`` for ``http_client`` and ``sentinel_client.post_to_module``.
- Discord stubs come from ``conftest.py`` (no per-file stubs — Phase 33-01 decision).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import yaml

from pathfinder_types import PathfinderRequest  # noqa: F401  (stable type, parity with sibling test file)


# ---------------------------------------------------------------------------
# Test helpers (file-scope, do not import pathfinder_player_dialog).
# ---------------------------------------------------------------------------


def _fake_resp(status: int, text: str) -> MagicMock:
    """Build a MagicMock httpx.Response with .status_code and .text set."""
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.json = MagicMock(return_value={})
    return resp


def _fake_draft_body(**fields) -> str:
    """Emit a markdown body whose YAML frontmatter contains the given fields."""
    block = yaml.safe_dump(fields, sort_keys=False, allow_unicode=True, default_flow_style=False).strip()
    return f"---\n{block}\n---\n"


# ---------------------------------------------------------------------------
# Task 1: Constants + draft I/O contract
# ---------------------------------------------------------------------------


async def test_steps_tuple_locked():
    """STEPS locks the three-step ordering verbatim (D-13)."""
    from pathfinder_player_dialog import STEPS

    assert STEPS == ("character_name", "preferred_name", "style_preset")


async def test_questions_dict_locked():
    """QUESTIONS dict locks each prompt verbatim (D-13)."""
    from pathfinder_player_dialog import QUESTIONS

    assert QUESTIONS["character_name"] == "What is your character's name?"
    assert QUESTIONS["preferred_name"] == "How would you like me to address you?"
    assert (
        QUESTIONS["style_preset"]
        == "Pick a style: Tactician, Lorekeeper, Cheerleader, Rules-Lawyer Lite"
    )


async def test_draft_path_format():
    """draft_path returns the canonical _drafts/ path (D-05, SPEC Req 3)."""
    from pathfinder_player_dialog import draft_path

    assert draft_path(thread_id=12345, user_id="u-1") == "mnemosyne/pf2e/players/_drafts/12345-u-1.md"


async def test_draft_path_coerces_user_id_to_str():
    """draft_path coerces non-str user_id to str (Pitfall 6)."""
    from pathfinder_player_dialog import draft_path

    assert draft_path(thread_id=12345, user_id=99) == "mnemosyne/pf2e/players/_drafts/12345-99.md"


async def test_save_draft_puts_frontmatter_only_body():
    """save_draft PUTs to /vault/{draft_path} with a frontmatter-only body."""
    from pathfinder_player_dialog import save_draft

    http = AsyncMock()
    http.put = AsyncMock(return_value=_fake_resp(200, ""))
    draft = {
        "step": "character_name",
        "thread_id": 42,
        "user_id": "u-1",
        "started_at": "2026-05-08T00:00:00Z",
    }
    await save_draft(thread_id=42, user_id="u-1", draft=draft, http_client=http)

    assert http.put.await_count == 1
    call = http.put.call_args
    url = call.args[0] if call.args else call.kwargs.get("url", "")
    assert url.endswith("/vault/mnemosyne/pf2e/players/_drafts/42-u-1.md")

    # Body may be passed positionally, as `data=`, or as `content=`.
    body = None
    if len(call.args) >= 2:
        body = call.args[1]
    if body is None:
        body = call.kwargs.get("data") or call.kwargs.get("content")
    assert isinstance(body, (str, bytes))
    body_str = body.decode() if isinstance(body, bytes) else body
    assert body_str.startswith("---\n")
    assert "step: character_name" in body_str
    assert "thread_id: 42" in body_str
    assert "user_id: u-1" in body_str


async def test_load_draft_returns_frontmatter_dict():
    """load_draft GETs the path and returns parsed frontmatter as a dict."""
    from pathfinder_player_dialog import load_draft

    body = (
        "---\n"
        "step: preferred_name\n"
        "thread_id: 42\n"
        "user_id: u-1\n"
        "character_name: Kaela\n"
        "started_at: 2026-05-08T00:00:00Z\n"
        "---\n"
    )
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))

    result = await load_draft(42, "u-1", http_client=http)
    assert result == {
        "step": "preferred_name",
        "thread_id": 42,
        "user_id": "u-1",
        "character_name": "Kaela",
        "started_at": "2026-05-08T00:00:00Z",
    }


async def test_load_draft_404_returns_none():
    """load_draft returns None on 404 (Pitfall 4 — vault.py:307-308 pattern)."""
    from pathfinder_player_dialog import load_draft

    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(404, ""))

    assert await load_draft(42, "u-1", http_client=http) is None


async def test_delete_draft_calls_http_delete():
    """delete_draft DELETEs the same URL save_draft PUTs to."""
    from pathfinder_player_dialog import delete_draft

    http = AsyncMock()
    http.delete = AsyncMock(return_value=_fake_resp(200, ""))
    await delete_draft(42, "u-1", http_client=http)

    assert http.delete.await_count == 1
    call = http.delete.call_args
    url = call.args[0] if call.args else call.kwargs.get("url", "")
    assert url.endswith("/vault/mnemosyne/pf2e/players/_drafts/42-u-1.md")


# ---------------------------------------------------------------------------
# Task 2: start_dialog + resume_dialog (SPEC Req 1, 7)
# ---------------------------------------------------------------------------


def _make_fake_thread(thread_id: int = 999) -> MagicMock:
    """Build a Discord Thread stand-in: .id, .send (AsyncMock), .edit (AsyncMock)."""
    fake = MagicMock()
    fake.id = thread_id
    fake.send = AsyncMock()
    fake.edit = AsyncMock()
    return fake


async def test_start_dialog_creates_public_thread(monkeypatch):
    """start_dialog creates a PUBLIC thread, PUTs initial draft, posts char-name prompt."""
    import bot as bot_module
    import discord

    from pathfinder_player_dialog import start_dialog, QUESTIONS

    fake_thread = _make_fake_thread(thread_id=999)
    invoking_channel = MagicMock()
    invoking_channel.create_thread = AsyncMock(return_value=fake_thread)

    http = AsyncMock()
    http.put = AsyncMock(return_value=_fake_resp(200, ""))

    monkeypatch.setattr(bot_module, "_persist_thread_id", AsyncMock())
    bot_module.SENTINEL_THREAD_IDS.discard(999)

    try:
        result = await start_dialog(
            invoking_channel=invoking_channel,
            user_id="u-1",
            message_author_display_name="alice",
            http_client=http,
        )

        assert invoking_channel.create_thread.await_count == 1
        kwargs = invoking_channel.create_thread.call_args.kwargs
        assert "Onboarding" in kwargs["name"]
        assert "alice" in kwargs["name"]
        assert kwargs["type"] == discord.ChannelType.public_thread  # Pitfall 1
        assert kwargs["auto_archive_duration"] == 60

        assert http.put.await_count == 1
        put_call = http.put.call_args
        url = put_call.args[0] if put_call.args else put_call.kwargs.get("url", "")
        assert url.endswith("/_drafts/999-u-1.md")
        body = (put_call.args[1] if len(put_call.args) >= 2
                else put_call.kwargs.get("data") or put_call.kwargs.get("content"))
        body_str = body.decode() if isinstance(body, bytes) else body
        assert "step: character_name" in body_str

        assert fake_thread.send.await_count == 1
        sent = fake_thread.send.call_args
        sent_text = sent.args[0] if sent.args else sent.kwargs.get("content", "")
        assert sent_text == QUESTIONS["character_name"]

        assert result is fake_thread
    finally:
        bot_module.SENTINEL_THREAD_IDS.discard(999)


async def test_start_dialog_thread_name_truncated_to_100_chars(monkeypatch):
    """Discord caps thread names at 100 chars — start_dialog must truncate."""
    import bot as bot_module

    from pathfinder_player_dialog import start_dialog

    fake_thread = _make_fake_thread(thread_id=1001)
    invoking_channel = MagicMock()
    invoking_channel.create_thread = AsyncMock(return_value=fake_thread)
    http = AsyncMock()
    http.put = AsyncMock(return_value=_fake_resp(200, ""))

    monkeypatch.setattr(bot_module, "_persist_thread_id", AsyncMock())
    bot_module.SENTINEL_THREAD_IDS.discard(1001)
    try:
        await start_dialog(
            invoking_channel=invoking_channel,
            user_id="u-1",
            message_author_display_name="x" * 200,
            http_client=http,
        )
        kwargs = invoking_channel.create_thread.call_args.kwargs
        assert len(kwargs["name"]) <= 100
    finally:
        bot_module.SENTINEL_THREAD_IDS.discard(1001)


async def test_start_dialog_registers_thread_id_in_sentinel_set(monkeypatch):
    """Newly-created onboarding thread MUST be added to SENTINEL_THREAD_IDS (D-11 inverse)."""
    import bot as bot_module

    from pathfinder_player_dialog import start_dialog

    fake_thread = _make_fake_thread(thread_id=4242)
    invoking_channel = MagicMock()
    invoking_channel.create_thread = AsyncMock(return_value=fake_thread)
    http = AsyncMock()
    http.put = AsyncMock(return_value=_fake_resp(200, ""))

    monkeypatch.setattr(bot_module, "_persist_thread_id", AsyncMock())
    bot_module.SENTINEL_THREAD_IDS.discard(4242)
    try:
        await start_dialog(
            invoking_channel=invoking_channel,
            user_id="u-1",
            message_author_display_name="alice",
            http_client=http,
        )
        assert 4242 in bot_module.SENTINEL_THREAD_IDS
    finally:
        bot_module.SENTINEL_THREAD_IDS.discard(4242)


async def test_resume_dialog_reposts_current_step():
    """resume_dialog re-posts QUESTIONS for the draft's CURRENT step (Req 7)."""
    from pathfinder_player_dialog import resume_dialog, QUESTIONS

    body = _fake_draft_body(
        step="preferred_name",
        thread_id=42,
        user_id="u-1",
        character_name="Kaela",
    )
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    fake_thread = _make_fake_thread(thread_id=42)

    result = await resume_dialog(thread=fake_thread, user_id="u-1", http_client=http)

    assert fake_thread.send.await_count == 1
    sent = fake_thread.send.call_args
    sent_text = sent.args[0] if sent.args else sent.kwargs.get("content", "")
    assert sent_text == QUESTIONS["preferred_name"]
    assert QUESTIONS["preferred_name"] in result


async def test_resume_dialog_does_not_reset_existing_answers():
    """resume_dialog MUST NOT mutate the draft (Req 7 acceptance)."""
    from pathfinder_player_dialog import resume_dialog

    body = _fake_draft_body(
        step="preferred_name",
        thread_id=42,
        user_id="u-1",
        character_name="Kaela",
    )
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    http.put = AsyncMock(return_value=_fake_resp(200, ""))
    fake_thread = _make_fake_thread(thread_id=42)

    await resume_dialog(thread=fake_thread, user_id="u-1", http_client=http)

    assert http.put.await_count == 0
