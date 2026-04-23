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


# ---------------------------------------------------------------------------
# Fixtures for NPC output tests (OUT-01 through OUT-04)
# ---------------------------------------------------------------------------

NOTE_WITH_STATS = (
    "---\n"
    "name: Varek\nlevel: 1\nancestry: Gnome\nclass: Rogue\n"
    "traits:\n- sneaky\npersonality: Nervous.\nbackstory: Fled the guild.\n"
    "mood: neutral\nrelationships: []\nimported_from: null\n"
    "---\n"
    "\n## Stats\n```yaml\nac: 18\nhp: 32\nfortitude: 8\nreflex: 12\nwill: 6\nspeed: 25\n```\n"
)

NOTE_NO_STATS = (
    "---\n"
    "name: Varek\nlevel: 1\nancestry: Gnome\nclass: Rogue\n"
    "traits:\n- sneaky\npersonality: Nervous.\nbackstory: Fled the guild.\n"
    "mood: neutral\nrelationships: []\nimported_from: null\n"
    "---\n"
)


# ---------------------------------------------------------------------------
# NPC export-foundry tests (OUT-01)
# ---------------------------------------------------------------------------


async def test_npc_export_foundry_success():
    """POST /npc/export-foundry returns 200 with actor dict and filename (OUT-01)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_WITH_STATS)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/export-foundry", json={"name": "Varek"})
    assert resp.status_code == 200
    data = resp.json()
    assert "actor" in data
    assert data["actor"]["type"] == "npc"
    assert data["actor"]["name"] == "Varek"
    assert data["filename"] == "varek.json"


async def test_npc_export_foundry_not_found():
    """POST /npc/export-foundry returns 404 for unknown NPC (OUT-01)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/export-foundry", json={"name": "Unknown"})
    assert resp.status_code == 404


async def test_npc_export_foundry_no_stats():
    """POST /npc/export-foundry with no stats block returns actor with 0-value defaults (D-05, OUT-01)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_NO_STATS)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/export-foundry", json={"name": "Varek"})
    assert resp.status_code == 200
    actor = resp.json()["actor"]
    assert actor["system"]["attributes"]["ac"]["value"] == 0
    assert actor["system"]["attributes"]["hp"]["value"] == 0


# ---------------------------------------------------------------------------
# NPC token tests (OUT-02)
# ---------------------------------------------------------------------------


async def test_npc_token_success():
    """POST /npc/token returns 200 with prompt string containing MJ params (OUT-02)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_WITH_STATS)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.generate_mj_description", new=AsyncMock(return_value="nervous eyes, disheveled clothing")):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/token", json={"name": "Varek"})
    assert resp.status_code == 200
    assert "prompt" in resp.json()


async def test_npc_token_template_structure():
    """Token prompt contains --ar 1:1 suffix from fixed template (D-09, OUT-02)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_WITH_STATS)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.generate_mj_description", new=AsyncMock(return_value="nervous eyes, disheveled clothing")):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/token", json={"name": "Varek"})
    assert "--ar 1:1" in resp.json()["prompt"]
    assert "--no text" in resp.json()["prompt"]


# ---------------------------------------------------------------------------
# NPC stat tests (OUT-03)
# ---------------------------------------------------------------------------


async def test_npc_stat_success():
    """POST /npc/stat returns 200 with fields and stats keys (OUT-03)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_WITH_STATS)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/stat", json={"name": "Varek"})
    assert resp.status_code == 200
    data = resp.json()
    assert "fields" in data
    assert "stats" in data
    assert data["stats"]["ac"] == 18


async def test_npc_stat_no_stats():
    """POST /npc/stat with no stats block returns empty stats dict (D-16, OUT-03)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_NO_STATS)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/stat", json={"name": "Varek"})
    assert resp.status_code == 200
    assert resp.json()["stats"] == {}


# ---------------------------------------------------------------------------
# NPC pdf tests (OUT-04)
# ---------------------------------------------------------------------------


async def test_npc_pdf_success():
    """POST /npc/pdf returns 200 with data_b64; decodes to valid PDF bytes (OUT-04)."""
    import base64
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_WITH_STATS)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/pdf", json={"name": "Varek"})
    assert resp.status_code == 200
    data = resp.json()
    assert "data_b64" in data
    assert data["filename"] == "varek-stat-card.pdf"
    pdf_bytes = base64.b64decode(data["data_b64"])
    assert pdf_bytes[:4] == b"%PDF"


async def test_npc_pdf_no_stats():
    """POST /npc/pdf with no stats block returns PDF with header only (D-20, OUT-04)."""
    import base64
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_NO_STATS)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/pdf", json={"name": "Varek"})
    assert resp.status_code == 200
    data = resp.json()
    pdf_bytes = base64.b64decode(data["data_b64"])
    assert pdf_bytes[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# NPC token-image tests (PLAN.md token-image extension)
# ---------------------------------------------------------------------------

# A minimal valid 1×1 PNG (8-byte signature + IHDR + IDAT + IEND), base64-encoded.
# Used as the test payload for binary upload + PDF embedding tests.
_PNG_1X1_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


async def test_npc_token_image_saves_binary_and_frontmatter():
    """POST /npc/token-image stores image bytes and updates token_image frontmatter."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_NO_STATS)
    mock_obs.put_binary = AsyncMock(return_value=None)
    mock_obs.patch_frontmatter_field = AsyncMock(return_value=None)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/npc/token-image",
                json={"name": "Varek", "image_b64": _PNG_1X1_B64},
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "varek"
    assert data["token_path"] == "mnemosyne/pf2e/tokens/varek.png"

    # put_binary called with (path, decoded_bytes, "image/png")
    assert mock_obs.put_binary.await_count == 1
    args, kwargs = mock_obs.put_binary.call_args
    path_arg, bytes_arg, ct_arg = args
    assert path_arg == "mnemosyne/pf2e/tokens/varek.png"
    assert bytes_arg[:8] == b"\x89PNG\r\n\x1a\n"  # PNG signature
    assert ct_arg == "image/png"

    # Frontmatter patch writes token_image field pointing at the stored path
    mock_obs.patch_frontmatter_field.assert_awaited_once_with(
        "mnemosyne/pf2e/npcs/varek.md",
        "token_image",
        "mnemosyne/pf2e/tokens/varek.png",
    )


async def test_npc_token_image_rejects_unknown_npc():
    """POST /npc/token-image returns 404 when the NPC note doesn't exist."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_binary = AsyncMock(return_value=None)
    mock_obs.patch_frontmatter_field = AsyncMock(return_value=None)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/npc/token-image",
                json={"name": "UnknownNPC", "image_b64": _PNG_1X1_B64},
            )
    assert resp.status_code == 404
    # No vault writes occurred — 404 fails before put_binary / patch
    assert mock_obs.put_binary.await_count == 0
    assert mock_obs.patch_frontmatter_field.await_count == 0


async def test_npc_pdf_with_token_image_embeds():
    """POST /npc/pdf fetches token image via get_binary when frontmatter has token_image."""
    import base64
    note_with_token = (
        "---\n"
        "name: Varek\nlevel: 1\nancestry: Gnome\nclass: Rogue\n"
        "traits:\n- sneaky\npersonality: Nervous.\nbackstory: Fled the guild.\n"
        "mood: neutral\nrelationships: []\nimported_from: null\n"
        "token_image: mnemosyne/pf2e/tokens/varek.png\n"
        "---\n"
    )
    png_bytes = base64.b64decode(_PNG_1X1_B64)
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=note_with_token)
    mock_obs.get_binary = AsyncMock(return_value=png_bytes)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/pdf", json={"name": "Varek"})
    assert resp.status_code == 200

    # get_binary was asked for the path recorded in the note's frontmatter
    mock_obs.get_binary.assert_awaited_once_with("mnemosyne/pf2e/tokens/varek.png")

    # PDF bytes decode cleanly and include the image's FlateDecode stream marker —
    # ReportLab wraps embedded raster data in /FlateDecode by default.
    pdf_bytes = base64.b64decode(resp.json()["data_b64"])
    assert pdf_bytes[:4] == b"%PDF"
    assert b"/FlateDecode" in pdf_bytes
