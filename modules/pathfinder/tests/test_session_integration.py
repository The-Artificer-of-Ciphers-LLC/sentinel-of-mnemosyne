"""Integration tests for /session — full vault round-trip with mocked LLM (SES-01..03).

Wave 0 RED scaffolding — implementation lands in Waves 2-3.
Stubs reference app.routes.session (Wave 2 / Plan 34-03) which does not yet exist.
Collection succeeds; runtime `patch()` of the missing attribute fails with
AttributeError — the honest RED signal.

Decision coverage: D-05 (state in note), D-06 (collision), D-14 (event format),
D-16 (PATCH append), D-17 (undo replace), D-18/D-19 (show + story patch),
D-25 (location stub), D-27 (LLM structured output), D-31 (LLM failure skeleton).
"""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# StatefulMockVault — extends Phase 33 pattern with patch_heading for session
# ---------------------------------------------------------------------------


class StatefulMockVault:
    """In-memory vault mock with heading-PATCH support for session tests.

    Extends Phase 33 pattern (get_note, put_note, list_directory) with
    patch_heading for Operation: append and Operation: replace.
    The heading content is stored per (path, heading) key for test introspection.
    """

    def __init__(self, initial: dict[str, str]):
        self._store: dict[str, str] = dict(initial)
        self._heading_appends: dict[tuple, list[str]] = {}  # (path, heading) -> lines appended
        self.get_note = AsyncMock(side_effect=self._get)
        self.put_note = AsyncMock(side_effect=self._put)
        self.list_directory = AsyncMock(side_effect=self._list)
        self.patch_frontmatter_field = AsyncMock()
        self.patch_heading = AsyncMock(side_effect=self._patch_heading)

    async def _get(self, path: str) -> str | None:
        return self._store.get(path)

    async def _put(self, path: str, content: str) -> None:
        self._store[path] = content

    async def _list(self, prefix: str) -> list[str]:
        return sorted(k for k in self._store.keys() if k.startswith(prefix))

    async def _patch_heading(
        self, path: str, heading: str, content: str, operation: str = "append"
    ) -> None:
        key = (path, heading)
        if operation == "append":
            self._heading_appends.setdefault(key, []).append(content)
            # Update in-store content (append to existing body)
            existing = self._store.get(path, "")
            self._store[path] = existing + content
        elif operation == "replace":
            self._heading_appends[key] = [content]
            # Replace: just track replacement (full GET-then-PUT used in undo)


# ---------------------------------------------------------------------------
# Helper: open session note seed
# ---------------------------------------------------------------------------

_OPEN_NOTE = """\
---
schema_version: 1
date: 2026-04-25
status: open
started_at: 2026-04-25T19:00:00+00:00
ended_at: null
event_count: 2
npcs: []
locations: []
recap: ""
---

## Recap

_Session in progress — recap generated at session end._

## Story So Far

_No narrative yet._

## NPCs Encountered

_Populated at session end._

## Locations

_Populated at session end._

## Events Log

- 19:00 Party arrived in Westcrown
- 19:15 [combat] Party fought 3 goblins

"""

_OPEN_NOTE_PATH = "mnemosyne/pf2e/sessions/2026-04-25.md"


# ---------------------------------------------------------------------------
# Integration tests — Wave 2 GREEN target
# ---------------------------------------------------------------------------


async def test_start_writes_open_note():
    """SES-01 / D-05: start with no collision PUTs an open session note."""
    vault = StatefulMockVault({})

    with (
        patch("app.main._register_with_retry", new=AsyncMock(return_value=None)),
        patch("app.routes.session.obsidian", vault),
        patch("app.routes.session.npc_roster_cache", {}),
    ):
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/modules/pathfinder/session",
                json={"verb": "start", "args": "", "flags": {}, "user_id": "u1"},
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )

    assert vault.put_note.await_count == 1
    call_path = vault.put_note.call_args[0][0]
    assert "mnemosyne/pf2e/sessions/" in call_path
    assert call_path.endswith(".md")
    written_content = vault.put_note.call_args[0][1]
    assert "status: open" in written_content
    assert "schema_version: 1" in written_content


async def test_start_collision_open_raises():
    """D-06: start refused when an open session already exists today."""
    vault = StatefulMockVault({_OPEN_NOTE_PATH: _OPEN_NOTE})

    with (
        patch("app.main._register_with_retry", new=AsyncMock(return_value=None)),
        patch("app.routes.session.obsidian", vault),
        patch("app.routes.session.npc_roster_cache", {}),
    ):
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/modules/pathfinder/session",
                json={"verb": "start", "args": "", "flags": {}, "user_id": "u1"},
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )
            body = resp.json()

    # Refuse: error key or type=refuse in response
    assert "error" in body or body.get("type") == "refuse"
    # put_note must NOT be called (no new note created)
    assert vault.put_note.await_count == 0


async def test_log_appends_event():
    """SES-03 / D-14 / D-16: log verb appends formatted event to Events Log heading."""
    vault = StatefulMockVault({_OPEN_NOTE_PATH: _OPEN_NOTE})

    with (
        patch("app.main._register_with_retry", new=AsyncMock(return_value=None)),
        patch("app.routes.session.obsidian", vault),
        patch("app.routes.session.npc_roster_cache", {}),
    ):
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/modules/pathfinder/session",
                json={
                    "verb": "log",
                    "args": "Party arrived in Westcrown",
                    "flags": {},
                    "user_id": "u1",
                },
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )

    assert vault.patch_heading.await_count == 1
    call_kwargs = vault.patch_heading.call_args
    # heading target must be "Events Log"
    heading_arg = (
        call_kwargs.kwargs.get("heading")
        or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
    )
    assert heading_arg == "Events Log"
    operation_arg = (
        call_kwargs.kwargs.get("operation")
        or (call_kwargs.args[3] if len(call_kwargs.args) > 3 else "append")
    )
    assert operation_arg == "append"
    # content must carry the event text
    content_arg = (
        call_kwargs.kwargs.get("content")
        or (call_kwargs.args[2] if len(call_kwargs.args) > 2 else "")
    )
    assert "Party arrived in Westcrown" in content_arg


async def test_undo_removes_last_event():
    """SES-03 / D-17: undo removes the last bullet in Events Log."""
    vault = StatefulMockVault({_OPEN_NOTE_PATH: _OPEN_NOTE})

    with (
        patch("app.main._register_with_retry", new=AsyncMock(return_value=None)),
        patch("app.routes.session.obsidian", vault),
        patch("app.routes.session.npc_roster_cache", {}),
    ):
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/modules/pathfinder/session",
                json={"verb": "undo", "args": "", "flags": {}, "user_id": "u1"},
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )
            body = resp.json()

    # Either GET-then-PUT or PATCH-replace was used
    used_put = vault.put_note.await_count >= 1
    used_patch_replace = (
        vault.patch_heading.await_count >= 1
    )
    assert used_put or used_patch_replace
    # Response should mention the removed event or remaining count
    response_text = str(body)
    assert any(keyword in response_text.lower() for keyword in ("removed", "undo", "event"))


async def test_show_calls_llm_and_patches_story():
    """D-18/D-19: show calls LLM and patches Story So Far heading."""
    vault = StatefulMockVault({_OPEN_NOTE_PATH: _OPEN_NOTE})

    stub_narrative = "The party arrived in Westcrown and found trouble."

    with (
        patch("app.main._register_with_retry", new=AsyncMock(return_value=None)),
        patch("app.routes.session.obsidian", vault),
        patch("app.routes.session.npc_roster_cache", {}),
        patch("litellm.acompletion", new=AsyncMock(return_value=_make_llm_narrative_response(stub_narrative))),
    ):
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/modules/pathfinder/session",
                json={"verb": "show", "args": "", "flags": {}, "user_id": "u1"},
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )
            body = resp.json()

    # LLM was called
    import litellm
    assert litellm.acompletion.await_count >= 1
    # Story So Far section was patched
    assert vault.patch_heading.await_count >= 1
    patch_calls = vault.patch_heading.call_args_list
    story_call = next(
        (c for c in patch_calls if (
            c.kwargs.get("heading") == "Story So Far"
            or (len(c.args) > 1 and c.args[1] == "Story So Far")
        )),
        None,
    )
    assert story_call is not None
    # Response contains narrative
    response_text = str(body)
    assert stub_narrative in response_text or "story" in response_text.lower()


async def test_end_writes_full_note():
    """SES-01 / D-27 / D-35: end writes full session note with recap and wikilinks."""
    npc_path = "mnemosyne/pf2e/npcs/varek.md"
    vault = StatefulMockVault({
        _OPEN_NOTE_PATH: _OPEN_NOTE,
        npc_path: "---\nname: Varek\nslug: varek\n---\n\n# Varek\n",
    })

    mock_llm_result = {
        "recap": "A brave party arrived in Westcrown and uncovered a smuggling ring.",
        "npcs": ["varek"],
        "locations": ["Westcrown"],
        "npc_notes_per_character": {"varek": "First encounter; revealed guild ties"},
    }

    with (
        patch("app.main._register_with_retry", new=AsyncMock(return_value=None)),
        patch("app.routes.session.obsidian", vault),
        patch("app.routes.session.npc_roster_cache", {"varek": "varek"}),
        patch("litellm.acompletion", new=AsyncMock(return_value=_make_llm_json_response(mock_llm_result))),
    ):
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/modules/pathfinder/session",
                json={"verb": "end", "args": "", "flags": {}, "user_id": "u1"},
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )

    # put_note called with session path
    assert vault.put_note.await_count >= 1
    # Find the session note write
    session_write = next(
        (c for c in vault.put_note.call_args_list if "sessions/" in c.args[0]),
        None,
    )
    assert session_write is not None
    content = session_write.args[1]
    assert "## Recap" in content
    assert "A brave party" in content
    assert "[[varek]]" in content
    assert "status: ended" in content


async def test_end_llm_failure_writes_skeleton():
    """D-31: LLM failure at end writes skeleton note and returns error embed."""
    vault = StatefulMockVault({_OPEN_NOTE_PATH: _OPEN_NOTE})

    with (
        patch("app.main._register_with_retry", new=AsyncMock(return_value=None)),
        patch("app.routes.session.obsidian", vault),
        patch("app.routes.session.npc_roster_cache", {}),
        patch("litellm.acompletion", new=AsyncMock(side_effect=RuntimeError("timeout"))),
    ):
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/modules/pathfinder/session",
                json={"verb": "end", "args": "", "flags": {}, "user_id": "u1"},
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )
            body = resp.json()

    # Session note was still written (skeleton)
    assert vault.put_note.await_count >= 1
    session_write = next(
        (c for c in vault.put_note.call_args_list if "sessions/" in c.args[0]),
        None,
    )
    assert session_write is not None
    content = session_write.args[1]
    assert "status: ended" in content
    # Skeleton marker or retry hint present
    assert "recap generation failed" in content.lower() or "--retry-recap" in content


async def test_location_stub_created():
    """SES-02 / D-25: new location mentioned in recap triggers stub creation."""
    vault = StatefulMockVault({_OPEN_NOTE_PATH: _OPEN_NOTE})

    mock_llm_result = {
        "recap": "A brave party arrived in Westcrown.",
        "npcs": [],
        "locations": ["Westcrown"],
        "npc_notes_per_character": {},
    }

    with (
        patch("app.main._register_with_retry", new=AsyncMock(return_value=None)),
        patch("app.routes.session.obsidian", vault),
        patch("app.routes.session.npc_roster_cache", {}),
        patch("litellm.acompletion", new=AsyncMock(return_value=_make_llm_json_response(mock_llm_result))),
    ):
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/modules/pathfinder/session",
                json={"verb": "end", "args": "", "flags": {}, "user_id": "u1"},
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )

    # Location stub must be created at mnemosyne/pf2e/locations/westcrown.md
    location_write = next(
        (
            c
            for c in vault.put_note.call_args_list
            if c.args[0] == "mnemosyne/pf2e/locations/westcrown.md"
        ),
        None,
    )
    assert location_write is not None, (
        "Expected put_note call for mnemosyne/pf2e/locations/westcrown.md; "
        f"calls were: {[c.args[0] for c in vault.put_note.call_args_list]}"
    )
    content = location_write.args[1]
    assert "name: Westcrown" in content
    assert "schema_version: 1" in content


# ---------------------------------------------------------------------------
# LLM response stub helpers
# ---------------------------------------------------------------------------


def _make_llm_narrative_response(text: str):
    """Build a minimal litellm-shaped response for narrative (show verb)."""
    from types import SimpleNamespace

    choice = SimpleNamespace(message=SimpleNamespace(content=text))
    return SimpleNamespace(choices=[choice])


def _make_llm_json_response(data: dict):
    """Build a minimal litellm-shaped response with JSON content (end verb)."""
    import json
    from types import SimpleNamespace

    choice = SimpleNamespace(message=SimpleNamespace(content=json.dumps(data)))
    return SimpleNamespace(choices=[choice])
