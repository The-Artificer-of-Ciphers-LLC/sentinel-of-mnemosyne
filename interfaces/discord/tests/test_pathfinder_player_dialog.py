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
    """QUESTIONS dict locks each prompt verbatim (D-13).

    style_preset is a numbered-list prompt as of UAT G-06 (operator-approved
    behavior change) — see test_normalise_style_preset_accepts_numeric_index
    for the corresponding answer-side support.
    """
    from pathfinder_player_dialog import QUESTIONS

    assert QUESTIONS["character_name"] == "What is your character's name?"
    assert QUESTIONS["preferred_name"] == "How would you like me to address you?"
    expected_style_prompt = (
        "Pick a style — reply with a number or the name:\n"
        "1) Tactician\n"
        "2) Lorekeeper\n"
        "3) Cheerleader\n"
        "4) Rules-Lawyer Lite"
    )
    assert QUESTIONS["style_preset"] == expected_style_prompt


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

    # resume_dialog must NOT post directly — bot's response_renderer sends the
    # returned text. In-module thread.send would double-post (UAT G-03).
    assert fake_thread.send.await_count == 0
    assert result == QUESTIONS["preferred_name"]


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


# ---------------------------------------------------------------------------
# Task 3: consume_as_answer + cancel_dialog (SPEC Req 2, 4, 6)
# ---------------------------------------------------------------------------


def _put_body(http: AsyncMock) -> str:
    """Extract the body string of the most recent http.put call."""
    call = http.put.call_args
    body = (call.args[1] if len(call.args) >= 2
            else call.kwargs.get("data") or call.kwargs.get("content"))
    return body.decode() if isinstance(body, bytes) else body


def _make_sentinel_client() -> MagicMock:
    """Build a sentinel_client with AsyncMock post_to_module + chat/call_core stubs.

    chat/call_core are AsyncMock so the test can prove they were NOT called.
    """
    client = MagicMock()
    client.post_to_module = AsyncMock(return_value={"path": "mnemosyne/pf2e/players/k/profile.md"})
    client.chat = AsyncMock()
    client.call_core = AsyncMock()
    return client


async def test_consume_as_answer_first_step_advances_to_preferred_name():
    """Replying at step=character_name advances to step=preferred_name; AI not invoked."""
    from pathfinder_player_dialog import consume_as_answer, QUESTIONS

    body = _fake_draft_body(
        step="character_name",
        thread_id=42,
        user_id="u-1",
        started_at="2026-05-08T00:00:00Z",
    )
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    http.put = AsyncMock(return_value=_fake_resp(200, ""))
    fake_thread = _make_fake_thread(thread_id=42)
    sentinel_client = _make_sentinel_client()

    result = await consume_as_answer(
        thread=fake_thread,
        user_id="u-1",
        message_text="Kaela",
        sentinel_client=sentinel_client,
        http_client=http,
    )

    assert http.put.await_count == 1
    body_str = _put_body(http)
    assert "step: preferred_name" in body_str
    assert "character_name: Kaela" in body_str

    # consume_as_answer must NOT post directly — bot.py's response_renderer
    # sends the returned text. In-module thread.send would double-post (UAT G-03).
    assert fake_thread.send.await_count == 0
    assert result == QUESTIONS["preferred_name"]

    assert sentinel_client.post_to_module.await_count == 0


async def test_consume_as_answer_second_step_advances_to_style_preset():
    """Replying at step=preferred_name preserves character_name and advances to style_preset."""
    from pathfinder_player_dialog import consume_as_answer, QUESTIONS

    body = _fake_draft_body(
        step="preferred_name",
        thread_id=42,
        user_id="u-1",
        character_name="Kaela",
        started_at="2026-05-08T00:00:00Z",
    )
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    http.put = AsyncMock(return_value=_fake_resp(200, ""))
    fake_thread = _make_fake_thread(thread_id=42)
    sentinel_client = _make_sentinel_client()

    result = await consume_as_answer(
        thread=fake_thread,
        user_id="u-1",
        message_text="Kae",
        sentinel_client=sentinel_client,
        http_client=http,
    )

    body_str = _put_body(http)
    assert "character_name: Kaela" in body_str
    assert "preferred_name: Kae" in body_str
    assert "step: style_preset" in body_str

    # No in-module send (UAT G-03); bot's response_renderer handles posting.
    assert fake_thread.send.await_count == 0
    assert result == QUESTIONS["style_preset"]

    assert sentinel_client.post_to_module.await_count == 0


async def test_consume_as_answer_final_step_calls_onboard_route():
    """Final step posts /player/onboard, deletes draft, archives thread, removes id."""
    import bot as bot_module

    from pathfinder_player_dialog import consume_as_answer

    body = _fake_draft_body(
        step="style_preset",
        thread_id=999,
        user_id="u-1",
        character_name="Kaela",
        preferred_name="Kae",
        started_at="2026-05-08T00:00:00Z",
    )
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    http.put = AsyncMock(return_value=_fake_resp(200, ""))
    http.delete = AsyncMock(return_value=_fake_resp(200, ""))
    fake_thread = _make_fake_thread(thread_id=999)
    sentinel_client = _make_sentinel_client()

    bot_module.SENTINEL_THREAD_IDS.add(999)
    try:
        result = await consume_as_answer(
            thread=fake_thread,
            user_id="u-1",
            message_text="Lorekeeper",
            sentinel_client=sentinel_client,
            http_client=http,
        )

        assert sentinel_client.post_to_module.await_count == 1
        post_args = sentinel_client.post_to_module.call_args
        assert post_args.args[0] == "modules/pathfinder/player/onboard"
        payload = post_args.args[1]
        assert payload == {
            "user_id": "u-1",
            "character_name": "Kaela",
            "preferred_name": "Kae",
            "style_preset": "Lorekeeper",
        }

        assert http.delete.await_count == 1
        del_url = http.delete.call_args.args[0] if http.delete.call_args.args else http.delete.call_args.kwargs.get("url", "")
        assert del_url.endswith("/_drafts/999-u-1.md")

        # Success message posted directly to thread BEFORE archive (UAT G-04 —
        # post-after-archive auto-unarchives the thread).
        assert fake_thread.send.await_count == 1
        success_sent = fake_thread.send.call_args.args[0] if fake_thread.send.call_args.args else fake_thread.send.call_args.kwargs.get("content", "")
        assert "onboarded" in success_sent.lower()
        assert "mnemosyne/pf2e/players/k/profile.md" in success_sent

        assert fake_thread.edit.await_count == 1
        assert fake_thread.edit.call_args.kwargs.get("archived") is True

        assert 999 not in bot_module.SENTINEL_THREAD_IDS

        # Empty-string sentinel — bot's response_renderer no-ops (UAT G-04).
        assert result == ""
    finally:
        bot_module.SENTINEL_THREAD_IDS.discard(999)


async def test_consume_as_answer_style_preset_case_insensitive_normalised():
    """Lowercase 'lorekeeper' is normalised to canonical 'Lorekeeper' in the payload."""
    import bot as bot_module

    from pathfinder_player_dialog import consume_as_answer

    body = _fake_draft_body(
        step="style_preset",
        thread_id=42,
        user_id="u-1",
        character_name="Kaela",
        preferred_name="Kae",
    )
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    http.put = AsyncMock(return_value=_fake_resp(200, ""))
    http.delete = AsyncMock(return_value=_fake_resp(200, ""))
    fake_thread = _make_fake_thread(thread_id=42)
    sentinel_client = _make_sentinel_client()

    bot_module.SENTINEL_THREAD_IDS.add(42)
    try:
        await consume_as_answer(
            thread=fake_thread,
            user_id="u-1",
            message_text="lorekeeper",
            sentinel_client=sentinel_client,
            http_client=http,
        )
        payload = sentinel_client.post_to_module.call_args.args[1]
        assert payload["style_preset"] == "Lorekeeper"
    finally:
        bot_module.SENTINEL_THREAD_IDS.discard(42)


async def test_consume_as_answer_invalid_style_preset_reasks():
    """Invalid style preset re-asks (no PUT, no POST) and lists the four valid presets."""
    from pathfinder_player_dialog import consume_as_answer

    body = _fake_draft_body(
        step="style_preset",
        thread_id=42,
        user_id="u-1",
        character_name="Kaela",
        preferred_name="Kae",
    )
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    http.put = AsyncMock(return_value=_fake_resp(200, ""))
    http.delete = AsyncMock(return_value=_fake_resp(200, ""))
    fake_thread = _make_fake_thread(thread_id=42)
    sentinel_client = _make_sentinel_client()

    result = await consume_as_answer(
        thread=fake_thread,
        user_id="u-1",
        message_text="Wizard",
        sentinel_client=sentinel_client,
        http_client=http,
    )

    assert sentinel_client.post_to_module.await_count == 0
    assert http.put.await_count == 0

    # No in-module send (UAT G-03); bot's response_renderer handles posting.
    assert fake_thread.send.await_count == 0
    for preset in ("Tactician", "Lorekeeper", "Cheerleader", "Rules-Lawyer Lite"):
        assert preset in result


async def test_consume_as_answer_archive_swallows_already_archived():
    """An already-archived thread (HTTPException on edit) does not re-raise (Pitfall 2)."""
    import bot as bot_module
    import discord

    from pathfinder_player_dialog import consume_as_answer

    body = _fake_draft_body(
        step="style_preset",
        thread_id=42,
        user_id="u-1",
        character_name="Kaela",
        preferred_name="Kae",
    )
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    http.put = AsyncMock(return_value=_fake_resp(200, ""))
    http.delete = AsyncMock(return_value=_fake_resp(200, ""))
    fake_thread = _make_fake_thread(thread_id=42)
    fake_thread.edit = AsyncMock(side_effect=discord.HTTPException("already archived"))
    sentinel_client = _make_sentinel_client()

    bot_module.SENTINEL_THREAD_IDS.add(42)
    try:
        result = await consume_as_answer(
            thread=fake_thread,
            user_id="u-1",
            message_text="Tactician",
            sentinel_client=sentinel_client,
            http_client=http,
        )
        # Onboard + delete must have happened BEFORE the failing archive call.
        assert sentinel_client.post_to_module.await_count == 1
        assert http.delete.await_count == 1
        # Success posted to thread even when archive subsequently fails.
        assert fake_thread.send.await_count == 1
        success_sent = fake_thread.send.call_args.args[0] if fake_thread.send.call_args.args else fake_thread.send.call_args.kwargs.get("content", "")
        assert "onboarded" in success_sent.lower()
        # Empty-string sentinel — bot's response_renderer no-ops (UAT G-04).
        assert result == ""
    finally:
        bot_module.SENTINEL_THREAD_IDS.discard(42)


async def test_consume_as_answer_does_not_invoke_ai():
    """consume_as_answer MUST NOT call sentinel_client.chat or call_core (SPEC Req 2)."""
    import bot as bot_module

    from pathfinder_player_dialog import consume_as_answer

    body = _fake_draft_body(
        step="style_preset",
        thread_id=42,
        user_id="u-1",
        character_name="Kaela",
        preferred_name="Kae",
    )
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    http.put = AsyncMock(return_value=_fake_resp(200, ""))
    http.delete = AsyncMock(return_value=_fake_resp(200, ""))
    fake_thread = _make_fake_thread(thread_id=42)
    sentinel_client = _make_sentinel_client()

    bot_module.SENTINEL_THREAD_IDS.add(42)
    try:
        await consume_as_answer(
            thread=fake_thread,
            user_id="u-1",
            message_text="Cheerleader",
            sentinel_client=sentinel_client,
            http_client=http,
        )
        assert sentinel_client.chat.await_count == 0
        assert sentinel_client.call_core.await_count == 0
    finally:
        bot_module.SENTINEL_THREAD_IDS.discard(42)


async def test_cancel_dialog_with_existing_draft_deletes_and_archives():
    """cancel_dialog with a draft: DELETE, archive, remove from set, return cancel text."""
    import bot as bot_module

    from pathfinder_player_dialog import cancel_dialog

    body = _fake_draft_body(
        step="preferred_name",
        thread_id=777,
        user_id="u-1",
        character_name="Kaela",
    )
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    http.delete = AsyncMock(return_value=_fake_resp(200, ""))
    fake_thread = _make_fake_thread(thread_id=777)

    bot_module.SENTINEL_THREAD_IDS.add(777)
    try:
        result = await cancel_dialog(thread=fake_thread, user_id="u-1", http_client=http)

        assert http.delete.await_count == 1
        del_url = http.delete.call_args.args[0] if http.delete.call_args.args else http.delete.call_args.kwargs.get("url", "")
        assert del_url.endswith("/_drafts/777-u-1.md")

        # Ack must be posted directly to the thread BEFORE archive (UAT G-04 —
        # any post after archive auto-unarchives). consume_as_answer/cancel_dialog
        # own the send for terminal messages; bot's response_renderer is a no-op.
        assert fake_thread.send.await_count == 1
        ack_sent = fake_thread.send.call_args.args[0] if fake_thread.send.call_args.args else fake_thread.send.call_args.kwargs.get("content", "")
        assert "cancelled" in ack_sent.lower()
        assert ":pf player start" in ack_sent

        assert fake_thread.edit.await_count == 1
        assert fake_thread.edit.call_args.kwargs.get("archived") is True

        assert 777 not in bot_module.SENTINEL_THREAD_IDS

        # Sentinel return value: empty string signals "already sent — bot, no-op".
        assert result == ""
    finally:
        bot_module.SENTINEL_THREAD_IDS.discard(777)


async def test_cancel_dialog_with_no_draft_returns_no_progress_message():
    """cancel_dialog with 404 draft returns the exact no-progress text and no side effects."""
    from pathfinder_player_dialog import cancel_dialog

    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(404, ""))
    http.delete = AsyncMock(return_value=_fake_resp(200, ""))
    fake_thread = _make_fake_thread(thread_id=42)

    result = await cancel_dialog(thread=fake_thread, user_id="u-1", http_client=http)

    assert result == "No onboarding dialog in progress."
    assert http.delete.await_count == 0
    assert fake_thread.edit.await_count == 0


async def test_cancel_dialog_archive_swallows_http_exception():
    """cancel_dialog still returns cancel text after Thread.edit HTTPException (Pitfall 2)."""
    import bot as bot_module
    import discord

    from pathfinder_player_dialog import cancel_dialog

    body = _fake_draft_body(
        step="preferred_name",
        thread_id=88,
        user_id="u-1",
        character_name="Kaela",
    )
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    http.delete = AsyncMock(return_value=_fake_resp(200, ""))
    fake_thread = _make_fake_thread(thread_id=88)
    fake_thread.edit = AsyncMock(side_effect=discord.HTTPException("already archived"))

    bot_module.SENTINEL_THREAD_IDS.add(88)
    try:
        result = await cancel_dialog(thread=fake_thread, user_id="u-1", http_client=http)
        assert http.delete.await_count == 1
        # Ack still posted to the thread even when archive subsequently fails.
        assert fake_thread.send.await_count == 1
        ack_sent = fake_thread.send.call_args.args[0] if fake_thread.send.call_args.args else fake_thread.send.call_args.kwargs.get("content", "")
        assert "cancelled" in ack_sent.lower()
        # Empty-string sentinel — bot's response_renderer no-ops (UAT G-04).
        assert result == ""
    finally:
        bot_module.SENTINEL_THREAD_IDS.discard(88)


async def test_start_dialog_from_inside_thread_hoists_to_parent_channel(monkeypatch):
    """Regression: invoking :pf player start from inside a Sentinel thread must create
    the onboarding thread off the parent text channel, not the invoking thread.

    Discord rejects thread-on-thread creation with `'Thread' object has no attribute
    'create_thread'` (or AttributeError on the public API). The user's normal Sentinel
    chat lives in a thread, so this is the dominant flow.
    """
    import bot as bot_module
    import discord

    from pathfinder_player_dialog import start_dialog

    fake_thread = _make_fake_thread(thread_id=777)

    # Parent text channel exposes create_thread; invoking channel is a Thread.
    parent_channel = MagicMock()
    parent_channel.create_thread = AsyncMock(return_value=fake_thread)

    invoking_thread = MagicMock(spec=discord.Thread)
    invoking_thread.parent = parent_channel
    # If the bug regresses, the test will fail because invoking_thread has no create_thread.

    http = AsyncMock()
    http.put = AsyncMock(return_value=_fake_resp(200, ""))

    monkeypatch.setattr(bot_module, "_persist_thread_id", AsyncMock())
    bot_module.SENTINEL_THREAD_IDS.discard(777)

    try:
        result = await start_dialog(
            invoking_channel=invoking_thread,
            user_id="u-1",
            http_client=http,
            display_name="CrankyOldNerd",
        )
        # Onboarding thread was created off the PARENT, not the invoking thread.
        assert parent_channel.create_thread.await_count == 1
        assert result is fake_thread
        assert 777 in bot_module.SENTINEL_THREAD_IDS
    finally:
        bot_module.SENTINEL_THREAD_IDS.discard(777)


async def test_start_dialog_from_thread_with_no_parent_raises(monkeypatch):
    """Edge: orphan thread (parent is None — DM or deleted channel) must raise rather
    than silently fall through to the broken `Thread.create_thread` path."""
    import bot as bot_module
    import discord

    from pathfinder_player_dialog import start_dialog

    invoking_thread = MagicMock(spec=discord.Thread)
    invoking_thread.parent = None

    http = AsyncMock()
    monkeypatch.setattr(bot_module, "_persist_thread_id", AsyncMock())

    try:
        await start_dialog(
            invoking_channel=invoking_thread,
            user_id="u-1",
            http_client=http,
            display_name="Test",
        )
        raise AssertionError("expected RuntimeError on parentless thread")
    except RuntimeError as exc:
        assert "parent" in str(exc).lower()


async def test_normalise_style_preset_strips_trailing_punctuation():
    """UAT G-05: 'Rules-Lawyer Lite.' (trailing period) must validate.

    Users naturally type with terminal punctuation. The valid-list match
    strips trailing `.,!?;:` (and surrounding whitespace) before comparing.
    Case-insensitive matching from RESEARCH Q10 is preserved.
    """
    from pathfinder_player_dialog import _normalise_style_preset

    # Trailing period — the original UAT bug.
    assert _normalise_style_preset("Rules-Lawyer Lite.") == "Rules-Lawyer Lite"
    # Lowercase + trailing period.
    assert _normalise_style_preset("rules-lawyer lite.") == "Rules-Lawyer Lite"
    # Trailing comma.
    assert _normalise_style_preset("Tactician,") == "Tactician"
    # Trailing exclamation.
    assert _normalise_style_preset("Lorekeeper!") == "Lorekeeper"
    # Trailing whitespace + period.
    assert _normalise_style_preset("Cheerleader. ") == "Cheerleader"
    # Still rejects genuinely invalid inputs.
    assert _normalise_style_preset("Wizard") is None
    assert _normalise_style_preset("Wizard.") is None


async def test_normalise_style_preset_accepts_numeric_index():
    """UAT G-06: numeric answers 1..4 map to canonical preset names."""
    from pathfinder_player_dialog import _normalise_style_preset

    assert _normalise_style_preset("1") == "Tactician"
    assert _normalise_style_preset("2") == "Lorekeeper"
    assert _normalise_style_preset("3") == "Cheerleader"
    assert _normalise_style_preset("4") == "Rules-Lawyer Lite"
    # Trailing punctuation tolerated on numeric inputs too.
    assert _normalise_style_preset("1.") == "Tactician"
    assert _normalise_style_preset(" 4 ") == "Rules-Lawyer Lite"
    # Out-of-range numbers reject.
    assert _normalise_style_preset("0") is None
    assert _normalise_style_preset("5") is None
    assert _normalise_style_preset("99") is None
    # Mixed alphanumeric does NOT accidentally match (still goes through name path).
    assert _normalise_style_preset("1tactician") is None
