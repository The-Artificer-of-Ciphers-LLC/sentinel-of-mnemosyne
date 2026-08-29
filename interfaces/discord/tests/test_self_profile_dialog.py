"""Tests for self_profile_dialog (the ``:onboard`` multi-step interview).

Conventions mirror test_pathfinder_player_dialog.py: AsyncMock http_client /
sentinel_client, MagicMock discord Thread stand-ins, frontmatter round-trip
via yaml.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import yaml


def _fake_resp(status: int, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.json = MagicMock(return_value={})
    return resp


def _fake_draft_body(**fields) -> str:
    block = yaml.safe_dump(fields, sort_keys=False, allow_unicode=True, default_flow_style=False).strip()
    return f"---\n{block}\n---\n"


def _make_fake_thread(thread_id: int = 999) -> MagicMock:
    fake = MagicMock()
    fake.id = thread_id
    fake.send = AsyncMock()
    fake.edit = AsyncMock()
    return fake


def _make_sentinel_client() -> MagicMock:
    client = MagicMock()
    client.post_to_module = AsyncMock(return_value={"written": True, "path": "self/identity.md"})
    return client


async def test_draft_path_format():
    from self_profile_dialog import draft_path

    assert draft_path(thread_id=42, user_id="u-1") == "ops/onboarding/_drafts/42-u-1.md"


async def test_start_dialog_creates_thread_and_asks_first_unfilled_only(monkeypatch):
    import bot as bot_module
    import discord

    from self_profile_dialog import QUESTIONS, start_dialog

    fake_thread = _make_fake_thread(thread_id=101)
    invoking_channel = MagicMock()
    invoking_channel.create_thread = AsyncMock(return_value=fake_thread)

    http = AsyncMock()
    http.put = AsyncMock(return_value=_fake_resp(200))

    monkeypatch.setattr(bot_module, "_persist_thread_id", AsyncMock())
    bot_module.SENTINEL_THREAD_IDS.discard(101)

    try:
        result = await start_dialog(
            invoking_channel=invoking_channel,
            user_id="u-1",
            unfilled=["self/identity.md", "self/goals.md"],
            message_author_display_name="alice",
            http_client=http,
        )

        assert invoking_channel.create_thread.await_count == 1
        kwargs = invoking_channel.create_thread.call_args.kwargs
        assert "Onboarding" in kwargs["name"] and "alice" in kwargs["name"]
        assert kwargs["type"] == discord.ChannelType.public_thread

        assert http.put.await_count == 1
        body = http.put.call_args.args[1] if len(http.put.call_args.args) >= 2 else http.put.call_args.kwargs.get("content")
        body_str = body.decode() if isinstance(body, bytes) else body
        assert "current: self/identity.md" in body_str
        assert "self/goals.md" in body_str  # queued in `remaining`

        assert fake_thread.send.await_count == 1
        assert fake_thread.send.call_args.args[0] == QUESTIONS["self/identity.md"]
        assert result is fake_thread
        assert 101 in bot_module.SENTINEL_THREAD_IDS
    finally:
        bot_module.SENTINEL_THREAD_IDS.discard(101)


async def test_resume_dialog_reposts_current_step_without_mutating():
    from self_profile_dialog import QUESTIONS, resume_dialog

    body = _fake_draft_body(current="self/goals.md", remaining=[], thread_id=42, user_id="u-1")
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    http.put = AsyncMock()
    fake_thread = _make_fake_thread(thread_id=42)

    result = await resume_dialog(thread=fake_thread, user_id="u-1", http_client=http)

    assert result == QUESTIONS["self/goals.md"]
    assert fake_thread.send.await_count == 0
    assert http.put.await_count == 0


async def test_consume_as_answer_posts_correct_path_and_markdown_body():
    """Answering the current question POSTs /self/profile with path + a wrapped body."""
    from self_profile_dialog import consume_as_answer

    body = _fake_draft_body(
        current="self/identity.md", remaining=["self/goals.md"], thread_id=42, user_id="u-1"
    )
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    http.put = AsyncMock(return_value=_fake_resp(200))
    fake_thread = _make_fake_thread(thread_id=42)
    sentinel_client = _make_sentinel_client()

    result = await consume_as_answer(
        thread=fake_thread,
        user_id="u-1",
        message_text="Tom, dev, likes concise answers.",
        sentinel_client=sentinel_client,
        http_client=http,
    )

    assert sentinel_client.post_to_module.await_count == 1
    call = sentinel_client.post_to_module.call_args
    assert call.args[0] == "self/profile"
    payload = call.args[1]
    assert payload["user_id"] == "u-1"
    assert payload["path"] == "self/identity.md"
    assert payload["content"].startswith("# Identity")
    assert "Tom, dev, likes concise answers." in payload["content"]
    assert "force" not in payload

    # Advances to the next unfilled question.
    from self_profile_dialog import QUESTIONS

    assert result == QUESTIONS["self/goals.md"]
    assert fake_thread.send.await_count == 0  # response_renderer sends, not the dialog


async def test_consume_as_answer_final_step_finishes_and_archives():
    from self_profile_dialog import consume_as_answer

    import bot as bot_module

    body = _fake_draft_body(current="self/goals.md", remaining=[], thread_id=42, user_id="u-1")
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    http.put = AsyncMock(return_value=_fake_resp(200))
    http.delete = AsyncMock(return_value=_fake_resp(200))
    fake_thread = _make_fake_thread(thread_id=42)
    sentinel_client = _make_sentinel_client()

    bot_module.SENTINEL_THREAD_IDS.add(42)
    try:
        result = await consume_as_answer(
            thread=fake_thread,
            user_id="u-1",
            message_text="Ship the onboarding phase.",
            sentinel_client=sentinel_client,
            http_client=http,
        )

        assert http.delete.await_count == 1
        assert fake_thread.send.await_count == 1
        assert "complete" in fake_thread.send.call_args.args[0].lower()
        assert fake_thread.edit.await_count == 1
        assert fake_thread.edit.call_args.kwargs.get("archived") is True
        assert 42 not in bot_module.SENTINEL_THREAD_IDS
        assert result == ""
    finally:
        bot_module.SENTINEL_THREAD_IDS.discard(42)


async def test_consume_as_answer_409_surfaces_message_and_does_not_crash():
    """core rejects the write (409 already filled): surfaced to the user, no
    exception propagates, and the dialog still advances to the next question."""
    from self_profile_dialog import consume_as_answer

    body = _fake_draft_body(
        current="self/identity.md", remaining=["self/goals.md"], thread_id=42, user_id="u-1"
    )
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    http.put = AsyncMock(return_value=_fake_resp(200))
    fake_thread = _make_fake_thread(thread_id=42)

    conflict_resp = MagicMock()
    conflict_resp.status_code = 409
    conflict_resp.json = MagicMock(return_value={"written": False, "reason": "already filled"})
    sentinel_client = MagicMock()
    sentinel_client.post_to_module = AsyncMock(
        side_effect=httpx.HTTPStatusError("conflict", request=MagicMock(), response=conflict_resp)
    )

    result = await consume_as_answer(
        thread=fake_thread,
        user_id="u-1",
        message_text="some answer",
        sentinel_client=sentinel_client,
        http_client=http,
    )

    assert "already filled" in result.lower()
    from self_profile_dialog import QUESTIONS

    assert QUESTIONS["self/goals.md"] in result
    assert fake_thread.send.await_count == 0


async def test_cancel_dialog_with_existing_draft_deletes_and_archives():
    import bot as bot_module

    from self_profile_dialog import cancel_dialog

    body = _fake_draft_body(current="self/identity.md", remaining=[], thread_id=777, user_id="u-1")
    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, body))
    http.delete = AsyncMock(return_value=_fake_resp(200))
    fake_thread = _make_fake_thread(thread_id=777)

    bot_module.SENTINEL_THREAD_IDS.add(777)
    try:
        result = await cancel_dialog(thread=fake_thread, user_id="u-1", http_client=http)

        assert http.delete.await_count == 1
        assert fake_thread.send.await_count == 1
        assert "cancelled" in fake_thread.send.call_args.args[0].lower()
        assert fake_thread.edit.await_count == 1
        assert 777 not in bot_module.SENTINEL_THREAD_IDS
        assert result == ""
    finally:
        bot_module.SENTINEL_THREAD_IDS.discard(777)


async def test_cancel_dialog_with_no_draft_returns_no_progress_message():
    from self_profile_dialog import cancel_dialog

    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(404))
    fake_thread = _make_fake_thread(thread_id=42)

    result = await cancel_dialog(thread=fake_thread, user_id="u-1", http_client=http)

    assert result == "No onboarding dialog in progress."
