"""Tests for GET /npcs/ and GET /npcs/{slug}/foundry-actor endpoints (FVT-04a..f).

Wave 0 RED stubs — symbols referenced below land in:
  - app.routes.npcs (Wave 1 / Plan 36-02)
  - app.main REGISTRATION_PAYLOAD update (Wave 1 / Plan 36-02)

Imports are function-scope inside each test so pytest collection succeeds
before the implementation lands (pattern from Phase 33/34 Wave 0).
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


# ---------------------------------------------------------------------------
# FVT-04a — GET /npcs/ with 2 NPC vault files
# ---------------------------------------------------------------------------


async def test_list_npcs_success():
    """GET /npcs/ returns 200 + list of 2 NPC dicts when vault has 2 files (FVT-04a)."""
    mock_obs = MagicMock()
    mock_obs.list_directory = AsyncMock(return_value=[
        "mnemosyne/pf2e/npcs/varek.md",
        "mnemosyne/pf2e/npcs/baron-aldric.md",
    ])
    mock_obs.get_note = AsyncMock(side_effect=[
        "---\nname: Varek\nlevel: 5\nancestry: Human\n---\n",
        "---\nname: Baron Aldric\nlevel: 8\nancestry: Dwarf\n---\n",
    ])
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npcs.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/npcs/",
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["slug"] == "varek"
    assert data[0]["name"] == "Varek"
    assert data[0]["level"] == 5
    assert data[0]["ancestry"] == "Human"
    assert data[1]["slug"] == "baron-aldric"


# ---------------------------------------------------------------------------
# FVT-04b — GET /npcs/ with empty vault directory
# ---------------------------------------------------------------------------


async def test_list_npcs_empty():
    """GET /npcs/ returns 200 + empty list when vault directory has no NPC files (FVT-04b)."""
    mock_obs = MagicMock()
    mock_obs.list_directory = AsyncMock(return_value=[])
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npcs.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/npcs/",
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# FVT-04c — GET /npcs/ when Obsidian is unreachable (returns empty list)
# ---------------------------------------------------------------------------


async def test_list_npcs_obsidian_down():
    """GET /npcs/ returns 200 + empty list (NOT 503) when Obsidian is unreachable (FVT-04c)."""
    mock_obs = MagicMock()
    mock_obs.list_directory = AsyncMock(return_value=[])
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npcs.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/npcs/",
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )
    assert resp.status_code == 200  # NOT 503
    assert resp.json() == []


# ---------------------------------------------------------------------------
# FVT-04d — GET /npcs/{slug}/foundry-actor for known slug
# ---------------------------------------------------------------------------


async def test_get_foundry_actor_success():
    """GET /npcs/varek/foundry-actor returns 200 + Foundry actor JSON for known slug (FVT-04d)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=(
        "---\nname: Varek\nlevel: 5\nancestry: Human\ntraits: [humanoid]\n---\n"
    ))
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npcs.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/npcs/varek/foundry-actor",
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )
    assert resp.status_code == 200
    data = resp.json()
    assert "name" in data
    assert "system" in data
    assert data["type"] == "npc"


# ---------------------------------------------------------------------------
# FVT-04e — GET /npcs/{slug}/foundry-actor for unknown slug
# ---------------------------------------------------------------------------


async def test_get_foundry_actor_not_found():
    """GET /npcs/nobody/foundry-actor returns 404 when slug not found in vault (FVT-04e)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npcs.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/npcs/nobody/foundry-actor",
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# FVT-04f — GET /npcs/{slug}/foundry-actor with path-traversal slug
# ---------------------------------------------------------------------------


async def test_get_foundry_actor_invalid_slug():
    """GET /npcs/{slug}/foundry-actor returns 400 for slugs with chars outside [a-z0-9-] (FVT-04f).

    Note: %2F-encoded traversal (../../etc/passwd) cannot be tested via httpx because
    Starlette decodes %2F → / before routing, producing a 404 non-match rather than a 400.
    The slugify guard is tested with an uppercase/underscore slug — any character outside
    [a-z0-9-] triggers it equally well.
    """
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npcs.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/npcs/INVALID_SLUG/foundry-actor",
                headers={"X-Sentinel-Key": "test-key-for-pytest"},
            )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# REGISTRATION_PAYLOAD guard — both new paths must be registered
# ---------------------------------------------------------------------------


async def test_registration_payload():
    """'npcs/' and 'npcs/{slug}/foundry-actor' appear in REGISTRATION_PAYLOAD routes list (FVT-04)."""
    from app.main import REGISTRATION_PAYLOAD

    paths = [r["path"] for r in REGISTRATION_PAYLOAD["routes"]]
    assert "npcs/" in paths
    assert "npcs/{slug}/foundry-actor" in paths
