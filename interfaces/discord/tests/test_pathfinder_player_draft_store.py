"""Tests for Player Onboarding Draft Store."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


def _resp(status_code: int, *, json_body=None, text_body: str = ""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_body if json_body is not None else {})
    resp.text = text_body
    return resp


async def test_draft_exists_true_only_on_200():
    from pathfinder_player_draft_store import draft_exists

    http = AsyncMock()
    http.get = AsyncMock(return_value=_resp(200))

    assert await draft_exists(42, "u-1", http_client=http) is True
    call = http.get.await_args
    url = call.args[0] if call.args else call.kwargs.get("url", "")
    assert url.endswith("/vault/mnemosyne/pf2e/players/_drafts/42-u-1.md")

    http.get = AsyncMock(return_value=_resp(404))
    assert await draft_exists(42, "u-1", http_client=http) is False


async def test_draft_exists_degrades_to_false_on_http_error():
    from pathfinder_player_draft_store import draft_exists

    http = AsyncMock()
    http.get = AsyncMock(side_effect=RuntimeError("network down"))

    assert await draft_exists(42, "u-1", http_client=http) is False


def test_parse_draft_filenames_accepts_list_and_object_shapes():
    from pathfinder_player_draft_store import parse_draft_filenames

    assert parse_draft_filenames(["111-u-1.md", 3, "222-u-1.md"]) == [
        "111-u-1.md",
        "222-u-1.md",
    ]
    assert parse_draft_filenames(
        {"files": [{"path": "_drafts/333-u-1.md"}, {"name": "444-u-1.md"}]}
    ) == ["_drafts/333-u-1.md", "444-u-1.md"]
    assert parse_draft_filenames({"files": "bad-shape"}) == []


async def test_list_user_thread_ids_filters_current_user_and_numeric_threads():
    from pathfinder_player_draft_store import list_user_thread_ids

    http = AsyncMock()
    http.get = AsyncMock(
        return_value=_resp(
            200,
            json_body={
                "files": [
                    {"path": "mnemosyne/pf2e/players/_drafts/111-u-1.md"},
                    {"path": "mnemosyne/pf2e/players/_drafts/not-number-u-1.md"},
                    {"path": "mnemosyne/pf2e/players/_drafts/222-u-2.md"},
                    {"name": "333-u-1.md"},
                ]
            },
        )
    )

    assert await list_user_thread_ids("u-1", http_client=http) == [111, 333]
    call = http.get.await_args
    url = call.args[0] if call.args else call.kwargs.get("url", "")
    assert url.endswith("/vault/mnemosyne/pf2e/players/_drafts/")


async def test_list_user_thread_ids_degrades_to_empty():
    from pathfinder_player_draft_store import list_user_thread_ids

    http = AsyncMock()
    http.get = AsyncMock(return_value=_resp(404))
    assert await list_user_thread_ids("u-1", http_client=http) == []

    http.get = AsyncMock(return_value=_resp(200, json_body=None))
    http.get.return_value.json = MagicMock(side_effect=ValueError("bad json"))
    assert await list_user_thread_ids("u-1", http_client=http) == []
