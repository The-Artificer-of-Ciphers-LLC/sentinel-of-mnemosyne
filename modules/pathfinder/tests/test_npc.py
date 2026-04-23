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
# Phase 31 — NPC say fixtures (DLG-01..03)
# Wave 0 RED scaffolding — implementation lands in Wave 1
# Stubs reference app.dialogue and app.llm.generate_npc_reply which do not yet exist.
# Tests are expected to FAIL on run (RED), but MUST collect cleanly.
# ---------------------------------------------------------------------------

NOTE_VAREK_NEUTRAL = (
    "---\n"
    "name: Varek\nlevel: 1\nancestry: Gnome\nclass: Rogue\n"
    "traits:\n- sneaky\npersonality: Nervous and twitchy.\n"
    "backstory: Fled the thieves' guild after stealing a ledger.\n"
    "mood: neutral\nrelationships: []\nimported_from: null\n"
    "---\n"
)
NOTE_VAREK_HOSTILE = NOTE_VAREK_NEUTRAL.replace("mood: neutral", "mood: hostile")
NOTE_VAREK_WARY = NOTE_VAREK_NEUTRAL.replace("mood: neutral", "mood: wary")
NOTE_VAREK_ALLIED = NOTE_VAREK_NEUTRAL.replace("mood: neutral", "mood: allied")
NOTE_VAREK_INVALID_MOOD = NOTE_VAREK_NEUTRAL.replace("mood: neutral", "mood: grumpy")
NOTE_BARON_HOSTILE = (
    "---\n"
    "name: Baron Aldric\nlevel: 5\nancestry: Human\nclass: Fighter\n"
    "traits:\n- arrogant\npersonality: Cold and calculating.\n"
    "backstory: A noble who seized the keep through betrayal.\n"
    "mood: hostile\nrelationships: []\nimported_from: null\n"
    "---\n"
)
NOTE_VAREK_FEARS_BARON = NOTE_VAREK_NEUTRAL.replace(
    "relationships: []",
    "relationships:\n- target: Baron Aldric\n  relation: fears",
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
    """POST /npc/token-image stores image bytes and updates token_image frontmatter.

    Uses GET-then-PUT (not PATCH) because Obsidian REST API PATCH with
    Operation=replace returns 400 when the target frontmatter key doesn't
    already exist (NPCs created before this feature lack token_image).
    """
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_NO_STATS)
    mock_obs.put_binary = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
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

    # put_note rewrites the note with token_image added to frontmatter
    assert mock_obs.put_note.await_count == 1
    put_path, put_content = mock_obs.put_note.call_args.args
    assert put_path == "mnemosyne/pf2e/npcs/varek.md"
    assert "token_image: mnemosyne/pf2e/tokens/varek.png" in put_content
    # Frontmatter delimiters preserved
    assert put_content.startswith("---\n")
    assert "\n---\n" in put_content


async def test_npc_token_image_rejects_unknown_npc():
    """POST /npc/token-image returns 404 when the NPC note doesn't exist."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_binary = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/npc/token-image",
                json={"name": "UnknownNPC", "image_b64": _PNG_1X1_B64},
            )
    assert resp.status_code == 404
    # No vault writes occurred — 404 fails before put_binary / put_note
    assert mock_obs.put_binary.await_count == 0
    assert mock_obs.put_note.await_count == 0


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


# ---------------------------------------------------------------------------
# Phase 31 — NPC say unit tests (DLG-01..03)
# Wave 0 RED scaffolding — implementation lands in Waves 1-2.
# These tests reference `app.routes.npc.generate_npc_reply` and related symbols
# that do NOT yet exist. Collection succeeds because no top-level import of the
# missing symbols is performed; runtime `patch()` of a not-yet-bound attribute
# raises AttributeError, which is the RED failure signal (not an ImportError).
# ---------------------------------------------------------------------------


async def test_npc_say_solo_happy():
    """POST /npc/say with single NPC returns 200; no mood write when delta=0 (DLG-01)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_VAREK_NEUTRAL)
    mock_obs.put_note = AsyncMock(return_value=None)
    mock_gen = AsyncMock(return_value={"reply": "*nods.* \"Aye.\"", "mood_delta": 0})
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Varek"],
                "party_line": "hello",
                "history": [],
                "user_id": "u1",
            })
    assert resp.status_code == 200
    result = resp.json()
    assert result["replies"][0]["npc"] == "Varek"
    assert result["replies"][0]["new_mood"] == "neutral"
    assert mock_obs.put_note.await_count == 0
    assert result["warning"] is None


async def test_npc_say_unknown():
    """POST /npc/say with a missing NPC returns 404, detail names the missing NPC (DLG-01)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    mock_gen = AsyncMock(return_value={"reply": "", "mood_delta": 0})
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Ghost"],
                "party_line": "hello",
                "history": [],
                "user_id": "u1",
            })
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    # Accept either dict or string detail shape; inspect both for slug and name.
    detail_str = str(detail)
    assert "ghost" in detail_str.lower()
    assert "Ghost" in detail_str


async def test_npc_say_system_prompt_has_personality():
    """System prompt passed to generate_npc_reply includes NPC personality text (DLG-01)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_VAREK_NEUTRAL)
    mock_obs.put_note = AsyncMock(return_value=None)
    mock_gen = AsyncMock(return_value={"reply": "*nods.*", "mood_delta": 0})
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Varek"],
                "party_line": "hello",
                "history": [],
                "user_id": "u1",
            })
    assert resp.status_code == 200
    # Inspect the system_prompt passed to the LLM — accept either kw or positional.
    call = mock_gen.call_args
    sys_prompt = call.kwargs.get("system_prompt")
    if sys_prompt is None and call.args:
        sys_prompt = call.args[0]
    assert sys_prompt is not None, "generate_npc_reply called without a system_prompt"
    assert "Nervous and twitchy" in sys_prompt


async def test_npc_say_mood_increment():
    """mood_delta=+1 on neutral NPC writes `mood: friendly` via put_note (DLG-02)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_VAREK_NEUTRAL)
    mock_obs.put_note = AsyncMock(return_value=None)
    mock_gen = AsyncMock(return_value={"reply": "*smiles.*", "mood_delta": 1})
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Varek"],
                "party_line": "thank you",
                "history": [],
                "user_id": "u1",
            })
    assert resp.status_code == 200
    assert mock_obs.put_note.await_count == 1
    put_path, put_content = mock_obs.put_note.call_args.args
    assert "mood: friendly" in put_content
    assert resp.json()["replies"][0]["new_mood"] == "friendly"


async def test_npc_say_mood_decrement():
    """mood_delta=-1 on wary NPC writes `mood: hostile` (DLG-02)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_VAREK_WARY)
    mock_obs.put_note = AsyncMock(return_value=None)
    mock_gen = AsyncMock(return_value={"reply": "*scowls.*", "mood_delta": -1})
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Varek"],
                "party_line": "threat",
                "history": [],
                "user_id": "u1",
            })
    assert resp.status_code == 200
    assert mock_obs.put_note.await_count == 1
    put_path, put_content = mock_obs.put_note.call_args.args
    assert "mood: hostile" in put_content
    assert resp.json()["replies"][0]["new_mood"] == "hostile"


async def test_npc_say_mood_zero_no_write():
    """mood_delta=0 on neutral NPC triggers no put_note call (DLG-02)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_VAREK_NEUTRAL)
    mock_obs.put_note = AsyncMock(return_value=None)
    mock_gen = AsyncMock(return_value={"reply": "*shrugs.*", "mood_delta": 0})
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Varek"],
                "party_line": "small talk",
                "history": [],
                "user_id": "u1",
            })
    assert resp.status_code == 200
    assert mock_obs.put_note.await_count == 0
    assert resp.json()["replies"][0]["new_mood"] == "neutral"


async def test_npc_say_mood_clamp_hostile():
    """mood_delta=-1 on hostile NPC does NOT write (clamp floor, DLG-02)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_VAREK_HOSTILE)
    mock_obs.put_note = AsyncMock(return_value=None)
    mock_gen = AsyncMock(return_value={"reply": "*snarls.*", "mood_delta": -1})
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Varek"],
                "party_line": "more threats",
                "history": [],
                "user_id": "u1",
            })
    assert resp.status_code == 200
    assert mock_obs.put_note.await_count == 0
    assert resp.json()["replies"][0]["new_mood"] == "hostile"


async def test_npc_say_mood_clamp_allied():
    """mood_delta=+1 on allied NPC does NOT write (clamp ceiling, DLG-02)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_VAREK_ALLIED)
    mock_obs.put_note = AsyncMock(return_value=None)
    mock_gen = AsyncMock(return_value={"reply": "*beams.*", "mood_delta": 1})
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Varek"],
                "party_line": "more praise",
                "history": [],
                "user_id": "u1",
            })
    assert resp.status_code == 200
    assert mock_obs.put_note.await_count == 0
    assert resp.json()["replies"][0]["new_mood"] == "allied"


async def test_npc_say_invalid_mood_normalized(caplog):
    """NOTE with `mood: grumpy` is treated as neutral; warning logged (DLG-02, T-31-SEC-02)."""
    import logging
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_VAREK_INVALID_MOOD)
    mock_obs.put_note = AsyncMock(return_value=None)
    mock_gen = AsyncMock(return_value={"reply": "*nods.*", "mood_delta": 1})
    with caplog.at_level(logging.WARNING):
        with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
             patch("app.routes.npc.obsidian", mock_obs), \
             patch("app.routes.npc.generate_npc_reply", new=mock_gen):
            from app.main import app
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/npc/say", json={
                    "names": ["Varek"],
                    "party_line": "hello",
                    "history": [],
                    "user_id": "u1",
                })
    assert resp.status_code == 200
    log_text = caplog.text.lower()
    assert "invalid" in log_text or "treating as 'neutral'" in log_text or "neutral" in log_text
    # Invalid mood normalizes to neutral, +1 → friendly
    assert resp.json()["replies"][0]["new_mood"] == "friendly"


async def test_npc_say_scene_order():
    """Two-NPC scene: replies come back in the order the names were given (DLG-03)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(side_effect=[NOTE_VAREK_NEUTRAL, NOTE_BARON_HOSTILE])
    mock_obs.put_note = AsyncMock(return_value=None)
    mock_gen = AsyncMock(side_effect=[
        {"reply": "V says", "mood_delta": 0},
        {"reply": "B says", "mood_delta": 0},
    ])
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Varek", "Baron Aldric"],
                "party_line": "we mean no harm",
                "history": [],
                "user_id": "u1",
            })
    assert resp.status_code == 200
    replies = resp.json()["replies"]
    assert replies[0]["npc"] == "Varek"
    assert replies[1]["npc"] == "Baron Aldric"


async def test_npc_say_scene_context_awareness():
    """Second NPC's user_prompt includes the first NPC's reply text (DLG-03)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(side_effect=[NOTE_VAREK_NEUTRAL, NOTE_BARON_HOSTILE])
    mock_obs.put_note = AsyncMock(return_value=None)
    mock_gen = AsyncMock(side_effect=[
        {"reply": "V says", "mood_delta": 0},
        {"reply": "B says", "mood_delta": 0},
    ])
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Varek", "Baron Aldric"],
                "party_line": "we mean no harm",
                "history": [],
                "user_id": "u1",
            })
    assert resp.status_code == 200
    # Second call is index 1. Extract user_prompt from kwargs or args[1].
    call_1 = mock_gen.call_args_list[1]
    user_prompt = call_1.kwargs.get("user_prompt")
    if user_prompt is None and len(call_1.args) >= 2:
        user_prompt = call_1.args[1]
    assert user_prompt is not None, "generate_npc_reply second call missing user_prompt"
    assert "V says" in user_prompt


async def test_npc_say_scene_advance():
    """Empty party_line triggers scene-advance framing: 'silent' + 'Continue the scene' (DLG-03)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(side_effect=[NOTE_VAREK_NEUTRAL, NOTE_BARON_HOSTILE])
    mock_obs.put_note = AsyncMock(return_value=None)
    mock_gen = AsyncMock(side_effect=[
        {"reply": "V says", "mood_delta": 0},
        {"reply": "B says", "mood_delta": 0},
    ])
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Varek", "Baron Aldric"],
                "party_line": "",
                "history": [],
                "user_id": "u1",
            })
    assert resp.status_code == 200
    call_0 = mock_gen.call_args_list[0]
    user_prompt = call_0.kwargs.get("user_prompt")
    if user_prompt is None and len(call_0.args) >= 2:
        user_prompt = call_0.args[1]
    assert user_prompt is not None, "generate_npc_reply first call missing user_prompt"
    assert "silent" in user_prompt
    assert "Continue the scene" in user_prompt


async def test_npc_say_five_npc_warning():
    """5-NPC scene surfaces the soft-cap warning string (DLG-03, D-18)."""
    five_notes = [
        NOTE_VAREK_NEUTRAL.replace("name: Varek", f"name: {n}")
        for n in ("Varek", "Baron Aldric", "Miralla", "Drenn", "Kalla")
    ]
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(side_effect=five_notes)
    mock_obs.put_note = AsyncMock(return_value=None)
    mock_gen = AsyncMock(side_effect=[
        {"reply": f"reply {i}", "mood_delta": 0} for i in range(5)
    ])
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Varek", "Baron Aldric", "Miralla", "Drenn", "Kalla"],
                "party_line": "crowd scene",
                "history": [],
                "user_id": "u1",
            })
    assert resp.status_code == 200
    assert resp.json()["warning"] == "⚠ 5 NPCs in scene — consider splitting for clarity."


async def test_npc_say_scene_missing_fails_fast():
    """Missing NPC in a scene → 404 before any LLM call (DLG-03, D-29)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(side_effect=[NOTE_VAREK_NEUTRAL, None])
    mock_obs.put_note = AsyncMock(return_value=None)
    mock_gen = AsyncMock(return_value={"reply": "", "mood_delta": 0})
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Varek", "Ghost"],
                "party_line": "hello",
                "history": [],
                "user_id": "u1",
            })
    assert resp.status_code == 404
    assert mock_gen.await_count == 0
    detail_str = str(resp.json()["detail"])
    assert "Ghost" in detail_str


async def test_npc_say_json_parse_salvage():
    """Plain-prose LLM output (no JSON) degrades gracefully: mood_delta=0, reply salvaged (DLG-01, T-31-SEC-03)."""
    from types import SimpleNamespace
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_VAREK_NEUTRAL)
    mock_obs.put_note = AsyncMock(return_value=None)
    # Mock the low-level litellm call: returns a response whose choices[0].message.content
    # is plain prose (no JSON) — the real generate_npc_reply salvage path must kick in.
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content="this is plain prose, no JSON at all"
        ))]
    )
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.llm.litellm.acompletion", new=AsyncMock(return_value=fake_response)):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Varek"],
                "party_line": "hello",
                "history": [],
                "user_id": "u1",
            })
    assert resp.status_code == 200
    reply = resp.json()["replies"][0]
    assert reply["reply"]  # non-empty salvaged prose
    assert reply["mood_delta"] == 0


async def test_npc_say_party_line_too_long():
    """party_line > 2000 chars returns 422 (DLG-01, T-31-SEC-04)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=NOTE_VAREK_NEUTRAL)
    mock_obs.put_note = AsyncMock(return_value=None)
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Varek"],
                "party_line": "x" * 2001,
                "history": [],
                "user_id": "u1",
            })
    assert resp.status_code == 422
