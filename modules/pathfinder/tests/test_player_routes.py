"""Wave 0 RED tests for /player/* FastAPI routes (PVL-01..05, PVL-07 isolation slice).

Symbols referenced below land in Wave 1 (plan 37-06):
  - app.routes.player (router, module-level `obsidian` singleton)
  - app.main REGISTRATION_PAYLOAD updates + lifespan wiring

Imports are function-scope inside each test so pytest collection succeeds
before the implementation lands (pattern from Phase 33/34/36/37-01 Wave 0).

Behavioral-Test-Only Rule: every assertion is on observable I/O — HTTP
status, exact obsidian method called, exact path argument, substring match
in body argument. No source-grep, no `assert True`, no mock.assert_called as
sole assertion.
"""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch


_HEADERS = {"X-Sentinel-Key": "test-key-for-pytest"}


def _onboarded_profile(slug: str = "p-anything") -> str:
    """Frontmatter for a fully-onboarded player (passes the gate)."""
    return (
        "---\n"
        "onboarded: true\n"
        "character_name: Aria\n"
        "preferred_name: Ari\n"
        f"slug: {slug}\n"
        "style_preset: Tactician\n"
        "---\n"
    )


def _resolved_slug(user_id: str) -> str:
    """Compute the canonical slug for a user_id via the resolver under test.

    Function-scope import keeps collection green pre-implementation; tests
    that need the slug for path assertions go through this helper so the
    expected path matches whatever Wave 1 decides slug shape to be.
    """
    from app.player_identity_resolver import slug_from_discord_user_id
    return slug_from_discord_user_id(user_id)


# ---------------------------------------------------------------------------
# PVL-01 — POST /player/onboard creates profile.md with frontmatter
# ---------------------------------------------------------------------------


async def test_post_onboard_creates_profile_md():
    """POST /player/onboard creates profile.md with onboarded:true + style preset (PVL-01)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)  # profile does not yet exist
    mock_obs.put_note = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.player.obsidian", mock_obs):
        slug = _resolved_slug("u1")
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/player/onboard",
                json={
                    "user_id": "u1",
                    "character_name": "Aria",
                    "preferred_name": "Ari",
                    "style_preset": "Tactician",
                },
                headers=_HEADERS,
            )
    assert resp.status_code == 200
    mock_obs.put_note.assert_awaited()
    # Find the profile.md write among potentially many put_note calls.
    profile_calls = [
        c for c in mock_obs.put_note.await_args_list
        if c.args and c.args[0].endswith(f"players/{slug}/profile.md")
    ]
    assert profile_calls, (
        f"expected put_note on .../players/{slug}/profile.md; "
        f"saw {[c.args[0] for c in mock_obs.put_note.await_args_list]}"
    )
    body = profile_calls[0].args[1]
    assert "onboarded: true" in body
    assert "character_name: Aria" in body
    assert "preferred_name: Ari" in body
    assert "style_preset: Tactician" in body


async def test_post_onboard_rejects_invalid_style_preset():
    """style_preset='MadeUp' rejected as 422 (closed-enum, mirrors VALID_RELATIONS in npc.py)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.player.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/player/onboard",
                json={
                    "user_id": "u1",
                    "character_name": "Aria",
                    "preferred_name": "Ari",
                    "style_preset": "MadeUp",
                },
                headers=_HEADERS,
            )
    assert resp.status_code == 422
    mock_obs.put_note.assert_not_awaited()


# ---------------------------------------------------------------------------
# PVL-02 — POST /player/note writes to per-player inbox.md (gated)
# ---------------------------------------------------------------------------


async def test_post_note_writes_to_player_inbox():
    """POST /player/note writes to mnemosyne/pf2e/players/{slug}/inbox.md when onboarded (PVL-02)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=_onboarded_profile())
    mock_obs.put_note = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.player.obsidian", mock_obs):
        slug = _resolved_slug("u1")
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/player/note",
                json={"user_id": "u1", "text": "I trust Varek"},
                headers=_HEADERS,
            )
    assert resp.status_code == 200
    inbox_calls = [
        c for c in mock_obs.put_note.await_args_list
        if c.args and c.args[0] == f"mnemosyne/pf2e/players/{slug}/inbox.md"
    ]
    assert inbox_calls, (
        f"expected put_note on mnemosyne/pf2e/players/{slug}/inbox.md; "
        f"saw {[c.args[0] for c in mock_obs.put_note.await_args_list]}"
    )
    assert "I trust Varek" in inbox_calls[0].args[1]


async def test_post_note_blocked_when_not_onboarded():
    """POST /player/note returns 409 with onboarding hint when profile.md absent."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)  # profile not present → not onboarded
    mock_obs.put_note = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.player.obsidian", mock_obs):
        slug = _resolved_slug("u1")
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/player/note",
                json={"user_id": "u1", "text": "I trust Varek"},
                headers=_HEADERS,
            )
    assert resp.status_code == 409
    body_text = resp.text  # detail may be dict or str — substring match either way
    assert ":pf player start" in body_text
    inbox_path = f"mnemosyne/pf2e/players/{slug}/inbox.md"
    inbox_writes = [
        c for c in mock_obs.put_note.await_args_list
        if c.args and c.args[0] == inbox_path
    ]
    assert not inbox_writes, "inbox.md must NOT be written when player is not onboarded"


# ---------------------------------------------------------------------------
# PVL-02 — POST /player/ask stores question, makes NO LLM call (v1)
# ---------------------------------------------------------------------------


async def test_post_ask_stores_question_no_llm():
    """POST /player/ask writes to questions.md and does NOT call any LLM endpoint (v1: store-only)."""
    import httpx as _httpx
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=_onboarded_profile())
    mock_obs.put_note = AsyncMock()
    real_async_client = _httpx.AsyncClient
    llm_call_count = {"n": 0}

    class _SpyAsyncClient(real_async_client):
        async def post(self, url, *a, **kw):  # type: ignore[override]
            if "1234" in str(url) or "/v1/" in str(url) or "completions" in str(url):
                llm_call_count["n"] += 1
            return await super().post(url, *a, **kw)

    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.player.obsidian", mock_obs), \
         patch.object(_httpx, "AsyncClient", _SpyAsyncClient):
        slug = _resolved_slug("u1")
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/player/ask",
                json={"user_id": "u1", "text": "Does cover stack with concealment?"},
                headers=_HEADERS,
            )
    assert resp.status_code == 200
    questions_calls = [
        c for c in mock_obs.put_note.await_args_list
        if c.args and c.args[0] == f"mnemosyne/pf2e/players/{slug}/questions.md"
    ]
    assert questions_calls, (
        f"expected put_note on questions.md; "
        f"saw {[c.args[0] for c in mock_obs.put_note.await_args_list]}"
    )
    assert "Does cover stack with concealment?" in questions_calls[0].args[1]
    assert llm_call_count["n"] == 0, "v1 ask must NOT call any LLM endpoint"


# ---------------------------------------------------------------------------
# PVL-07 — POST /player/npc writes per-player namespace, never global
# ---------------------------------------------------------------------------


async def test_post_npc_writes_per_player_namespace():
    """POST /player/npc writes mnemosyne/pf2e/players/{slug}/npcs/varek.md, NEVER the global path."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=_onboarded_profile())
    mock_obs.put_note = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.player.obsidian", mock_obs):
        slug = _resolved_slug("u1")
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/player/npc",
                json={"user_id": "u1", "npc_name": "Varek", "note": "trustworthy"},
                headers=_HEADERS,
            )
    assert resp.status_code == 200
    expected = f"mnemosyne/pf2e/players/{slug}/npcs/varek.md"
    forbidden = "mnemosyne/pf2e/npcs/varek.md"
    paths = [c.args[0] for c in mock_obs.put_note.await_args_list if c.args]
    assert expected in paths, f"expected put_note on {expected}; saw {paths}"
    assert forbidden not in paths, (
        f"PVL-07 isolation violation: writes to global NPC namespace at {forbidden}"
    )


# ---------------------------------------------------------------------------
# PVL-02 — POST /player/todo writes to per-player todo.md
# ---------------------------------------------------------------------------


async def test_post_todo_writes_per_player_todo():
    """POST /player/todo writes mnemosyne/pf2e/players/{slug}/todo.md."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=_onboarded_profile())
    mock_obs.put_note = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.player.obsidian", mock_obs):
        slug = _resolved_slug("u1")
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/player/todo",
                json={"user_id": "u1", "text": "Buy healing potions"},
                headers=_HEADERS,
            )
    assert resp.status_code == 200
    todo_path = f"mnemosyne/pf2e/players/{slug}/todo.md"
    todo_calls = [
        c for c in mock_obs.put_note.await_args_list
        if c.args and c.args[0] == todo_path
    ]
    assert todo_calls, (
        f"expected put_note on {todo_path}; "
        f"saw {[c.args[0] for c in mock_obs.put_note.await_args_list]}"
    )
    assert "Buy healing potions" in todo_calls[0].args[1]


# ---------------------------------------------------------------------------
# PVL-03 — POST /player/recall returns only requesting slug's content (isolation)
# ---------------------------------------------------------------------------


async def test_post_recall_returns_only_requesting_slug_paths():
    """POST /player/recall scopes results to the requesting slug — no cross-player leakage (PVL-03/PVL-07)."""
    u1_slug = _resolved_slug("u1")
    u2_slug = _resolved_slug("u2")

    mock_obs = MagicMock()
    # Profile.md gate must pass for u1.
    mock_obs.get_note = AsyncMock(return_value=_onboarded_profile(u1_slug))
    # If recall consults list_directory, return ONLY u1's namespace files —
    # the route must not be reaching outside its slug's prefix.
    mock_obs.list_directory = AsyncMock(return_value=[
        f"mnemosyne/pf2e/players/{u1_slug}/inbox.md",
        f"mnemosyne/pf2e/players/{u1_slug}/npcs/varek.md",
    ])
    mock_obs.put_note = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.player.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/player/recall",
                json={"user_id": "u1", "query": "Varek"},
                headers=_HEADERS,
            )
    assert resp.status_code == 200
    # All read-side obsidian calls (list_directory + get_note) must reference
    # only u1's slug — never u2's. This is the PVL-07 regression.
    list_calls = mock_obs.list_directory.await_args_list
    assert list_calls, "recall must invoke list_directory at least once"
    for c in list_calls:
        prefix_arg = c.args[0] if c.args else c.kwargs.get("prefix") or c.kwargs.get("path", "")
        assert u1_slug in str(prefix_arg), (
            f"list_directory called with non-u1 prefix: {prefix_arg}"
        )
        assert u2_slug not in str(prefix_arg), (
            f"list_directory leaked u2's slug into u1's recall: {prefix_arg}"
        )
    # Inspect the response body for any path strings — must not contain u2's slug.
    body = resp.text
    assert u2_slug not in body, "recall response leaked u2's slug into u1's results"


# ---------------------------------------------------------------------------
# PVL-05 — POST /player/style set persists style_preset to profile.md
# ---------------------------------------------------------------------------


async def test_post_style_set_persists_to_profile():
    """POST /player/style action=set re-PUTs profile.md with new style_preset (PVL-05)."""
    u1_slug = _resolved_slug("u1")
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=_onboarded_profile(u1_slug))
    mock_obs.put_note = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.player.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/player/style",
                json={"user_id": "u1", "action": "set", "preset": "Lorekeeper"},
                headers=_HEADERS,
            )
    assert resp.status_code == 200
    profile_path = f"mnemosyne/pf2e/players/{u1_slug}/profile.md"
    profile_writes = [
        c for c in mock_obs.put_note.await_args_list
        if c.args and c.args[0] == profile_path
    ]
    assert profile_writes, (
        f"expected GET-then-PUT on {profile_path}; "
        f"saw {[c.args[0] for c in mock_obs.put_note.await_args_list]}"
    )
    assert "style_preset: Lorekeeper" in profile_writes[-1].args[1]


async def test_post_style_list_returns_four_presets():
    """POST /player/style action=list returns exactly the four canonical presets — read-only, no put_note."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=_onboarded_profile())
    mock_obs.put_note = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.player.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/player/style",
                json={"user_id": "u1", "action": "list"},
                headers=_HEADERS,
            )
    assert resp.status_code == 200
    body = resp.text
    for preset in ("Tactician", "Lorekeeper", "Cheerleader", "Rules-Lawyer Lite"):
        assert preset in body, f"missing preset '{preset}' in style list response"
    mock_obs.put_note.assert_not_awaited()


# ---------------------------------------------------------------------------
# PVL-04 — POST /player/canonize records outcome with question_id provenance
# ---------------------------------------------------------------------------


async def test_post_canonize_records_with_provenance():
    """POST /player/canonize writes outcome marker AND question_id into canonization.md (PVL-04)."""
    u1_slug = _resolved_slug("u1")
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=_onboarded_profile(u1_slug))
    mock_obs.put_note = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.player.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/player/canonize",
                json={
                    "user_id": "u1",
                    "question_id": "q-uuid-1",
                    "outcome": "green",
                    "rule_text": "Cover stacks with concealment per Player Core p.473.",
                },
                headers=_HEADERS,
            )
    assert resp.status_code == 200
    canon_path = f"mnemosyne/pf2e/players/{u1_slug}/canonization.md"
    canon_writes = [
        c for c in mock_obs.put_note.await_args_list
        if c.args and c.args[0] == canon_path
    ]
    assert canon_writes, (
        f"expected put_note on {canon_path}; "
        f"saw {[c.args[0] for c in mock_obs.put_note.await_args_list]}"
    )
    body = canon_writes[-1].args[1]
    assert "green" in body, "canonization entry missing outcome marker"
    assert "q-uuid-1" in body, "canonization entry missing question_id provenance link"


# ---------------------------------------------------------------------------
# PVL-01 — GET /player/state returns onboarding status + slug + style preset
# ---------------------------------------------------------------------------


async def test_get_state_returns_onboarding_status():
    """GET /player/state?user_id=u1 returns {onboarded, slug, style_preset} from profile frontmatter."""
    u1_slug = _resolved_slug("u1")
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=_onboarded_profile(u1_slug))
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.player.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/player/state",
                params={"user_id": "u1"},
                headers=_HEADERS,
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("onboarded") is True
    assert data.get("slug") == u1_slug
    assert data.get("style_preset") == "Tactician"


# ---------------------------------------------------------------------------
# Operational — Obsidian unavailable returns 503 with explicit detail
# ---------------------------------------------------------------------------


async def test_obsidian_unavailable_returns_503():
    """When app.routes.player.obsidian is None, /player/note POST returns 503."""
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.player.obsidian", None):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/player/note",
                json={"user_id": "u1", "text": "test"},
                headers=_HEADERS,
            )
    assert resp.status_code == 503
    assert "obsidian" in resp.text.lower()
    assert "initialised" in resp.text.lower() or "initialized" in resp.text.lower()
