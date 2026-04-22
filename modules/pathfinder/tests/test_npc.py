"""Tests for pf2e-module NPC CRUD endpoints."""
import os
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

import json
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# NPC create tests (NPC-01)
# ---------------------------------------------------------------------------


async def test_npc_create_success():
    """POST /npc/create returns 200 + slug when NPC does not exist (NPC-01)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)  # no collision
    mock_obs.put_note = AsyncMock(return_value=None)
    extracted = {
        "name": "Varek", "level": 1, "ancestry": "Gnome", "class": "Rogue",
        "traits": ["sneaky"], "personality": "Nervous", "backstory": "Fled the guild",
        "mood": "neutral",
    }
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.extract_npc_fields", new=AsyncMock(return_value=extracted)):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/create", json={
                "name": "Varek", "description": "young gnome rogue", "user_id": "u1"
            })
    assert resp.status_code == 200
    assert resp.json()["slug"] == "varek"


async def test_npc_create_collision():
    """POST /npc/create returns 409 when NPC already exists in Obsidian (NPC-01)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value="existing content")  # collision
    mock_obs.put_note = AsyncMock(return_value=None)
    extracted = {
        "name": "Varek", "level": 1, "ancestry": "Gnome", "class": "Rogue",
        "traits": [], "personality": "Nervous", "backstory": "Fled the guild",
        "mood": "neutral",
    }
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.extract_npc_fields", new=AsyncMock(return_value=extracted)):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/create", json={
                "name": "Varek", "description": "young gnome rogue", "user_id": "u1"
            })
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# NPC update test (NPC-02)
# ---------------------------------------------------------------------------


async def test_npc_update_identity_fields():
    """POST /npc/update reads note, calls LLM, PUTs updated note; returns 200 (NPC-02)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value="---\nname: Varek\nlevel: 1\n---\n")
    mock_obs.put_note = AsyncMock(return_value=None)
    updated_fields = {"name": "Varek", "level": 7}
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.update_npc_fields", new=AsyncMock(return_value=updated_fields)):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/update", json={
                "name": "Varek", "correction": "now level 7", "user_id": "u1"
            })
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# NPC show tests (NPC-03)
# ---------------------------------------------------------------------------


async def test_npc_show_returns_fields():
    """POST /npc/show returns 200 with expected keys (NPC-03)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(
        return_value=(
            "---\n"
            "name: Varek\n"
            "level: 1\n"
            "ancestry: Gnome\n"
            "class: Rogue\n"
            "traits: []\n"
            "personality: Nervous\n"
            "backstory: Fled.\n"
            "mood: neutral\n"
            "relationships: []\n"
            "imported_from: null\n"
            "---\n"
        )
    )
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/show", json={"name": "Varek"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "varek"
    assert data["name"] == "Varek"
    assert "level" in data
    assert "ancestry" in data
    assert "class" in data


async def test_npc_show_not_found():
    """POST /npc/show returns 404 when NPC not in Obsidian (NPC-03)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/show", json={"name": "UnknownNPC"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# NPC relate tests (NPC-04)
# ---------------------------------------------------------------------------


async def test_npc_relate_valid():
    """POST /npc/relate with valid relation type returns 200 (NPC-04)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value="---\nname: Varek\nrelationships: []\n---\n")
    mock_obs.patch_frontmatter_field = AsyncMock(return_value=None)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/relate", json={
                "name": "Varek", "relation": "trusts", "target": "Baron Aldric"
            })
    assert resp.status_code == 200


async def test_npc_relate_invalid_type():
    """POST /npc/relate with invalid relation type returns 422 (NPC-04)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value="---\nname: Varek\nrelationships: []\n---\n")
    mock_obs.patch_frontmatter_field = AsyncMock(return_value=None)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/relate", json={
                "name": "Varek", "relation": "enemies-with", "target": "Baron Aldric"
            })
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# NPC import tests (NPC-05)
# ---------------------------------------------------------------------------


async def test_npc_import_basic():
    """POST /npc/import with 2 actors returns 200 with imported_count=2 (NPC-05)."""
    actors = [
        {
            "name": "Varek",
            "system": {
                "details": {
                    "level": {"value": 1},
                    "ancestry": {"value": "Gnome"},
                    "class": {"value": "Rogue"},
                },
                "traits": {"value": ["sneaky"]},
            },
        },
        {
            "name": "Baron Aldric",
            "system": {
                "details": {
                    "level": {"value": 5},
                    "ancestry": {"value": "Human"},
                    "class": {"value": "Fighter"},
                },
                "traits": {"value": []},
            },
        },
    ]
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)  # no collisions
    mock_obs.put_note = AsyncMock(return_value=None)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/import", json={
                "actors_json": json.dumps(actors), "user_id": "u1"
            })
    assert resp.status_code == 200
    assert resp.json()["imported_count"] == 2


async def test_npc_import_collision_skipped():
    """POST /npc/import where first actor collides returns skipped list (NPC-05)."""
    actors = [
        {
            "name": "Varek",
            "system": {
                "details": {
                    "level": {"value": 1},
                    "ancestry": {"value": "Gnome"},
                    "class": {"value": "Rogue"},
                },
                "traits": {"value": ["sneaky"]},
            },
        },
        {
            "name": "Baron Aldric",
            "system": {
                "details": {
                    "level": {"value": 5},
                    "ancestry": {"value": "Human"},
                    "class": {"value": "Fighter"},
                },
                "traits": {"value": []},
            },
        },
    ]
    mock_obs = MagicMock()
    # First call (Varek) returns content (collision), second call (Baron Aldric) returns None
    mock_obs.get_note = AsyncMock(side_effect=["existing", None])
    mock_obs.put_note = AsyncMock(return_value=None)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/import", json={
                "actors_json": json.dumps(actors), "user_id": "u1"
            })
    assert resp.status_code == 200
    assert resp.json()["skipped"] == ["Varek"]
    assert resp.json()["imported_count"] == 1
