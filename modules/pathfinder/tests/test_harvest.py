"""Tests for pf2e-module harvest endpoints (HRV-01..06, D-02 fuzzy, D-03b cache).

Wave 0 RED scaffolding — implementation lands in Waves 1-3.
Stubs reference app.harvest (Plan 32-03) and app.routes.harvest (Plan 32-04)
which do not yet exist. Tests are expected to FAIL on run (RED) but MUST collect cleanly.

Per PATTERNS.md §7 Gotcha 1: symbol imports that would AttributeError at collection
live INSIDE test bodies so the module loads.
"""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Module-scope fixture helpers — structural shape per 32-RESEARCH.md §YAML Loader
# ---------------------------------------------------------------------------


STUB_HARVEST_TABLE_DATA = {
    "version": "1.0",
    "source": "foundryvtt-pf2e",
    "levels": [1, 2, 3],
    "monsters": [
        {
            "name": "Boar",
            "level": 2,
            "traits": ["animal"],
            "components": [
                {
                    "name": "Hide",
                    "medicine_dc": 16,
                    "craftable": [
                        {"name": "Leather armor", "crafting_dc": 14, "value": "2 gp"},
                    ],
                },
            ],
        },
        {
            "name": "Wolf",
            "level": 1,
            "traits": ["animal"],
            "components": [
                {
                    "name": "Hide",
                    "medicine_dc": 15,
                    "craftable": [
                        {"name": "Leather armor", "crafting_dc": 14, "value": "2 gp"},
                    ],
                },
                {
                    "name": "Fangs",
                    "medicine_dc": 15,
                    "craftable": [
                        {"name": "Bone charm", "crafting_dc": 14, "value": "5 sp"},
                    ],
                },
            ],
        },
    ],
}


def _make_stub_tables():
    """Build a HarvestTable Pydantic object from STUB_HARVEST_TABLE_DATA.

    Import is inside the function so test collection succeeds before Plan 32-03
    creates app.harvest. Plan 32-03 lands HarvestTable.model_validate.
    """
    from app.harvest import HarvestTable

    return HarvestTable.model_validate(STUB_HARVEST_TABLE_DATA)


CACHED_HARVEST_MD = (
    "---\n"
    "monster: Boar\n"
    "level: 2\n"
    "verified: true\n"
    "source: seed\n"
    "harvested_at: 2026-04-20T12:00:00Z\n"
    "---\n"
    "# Boar\n"
    "\n## Hide\n"
    "- Medicine DC: **16**\n"
    "- Craftable:\n"
    "  - Leather armor — Crafting DC 14, 2 gp\n"
)


# ---------------------------------------------------------------------------
# 1. rapidfuzz smoke test (flips GREEN after Plan 32-02)
# ---------------------------------------------------------------------------


def test_rapidfuzz_importable():
    """Smoke test — rapidfuzz wheel installed in the container (Plan 32-02)."""
    import rapidfuzz

    assert rapidfuzz.__version__ >= "3.14.0"


# ---------------------------------------------------------------------------
# 2-15. Route-level tests (POST /harvest) — Waves 1-3 GREEN target
# ---------------------------------------------------------------------------


async def test_harvest_single_seed_hit():
    """POST /harvest returns seed-hit shape for a monster in the table (HRV-01, HRV-04)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)  # cache miss
    mock_obs.put_note = AsyncMock(return_value=None)
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock(return_value={
        "monster": "unused",
        "level": 0,
        "components": [],
        "source": "llm-generated",
        "verified": False,
    })
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", mock_obs), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/harvest", json={"names": ["Boar"], "user_id": "u1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["monsters"][0]["source"] == "seed"
    assert body["monsters"][0]["level"] == 2
    assert len(body["monsters"][0]["components"]) >= 1
    for comp in body["monsters"][0]["components"]:
        assert isinstance(comp["medicine_dc"], int)


async def test_harvest_components_have_craftable():
    """Each component lists craftable items with name+DC+value (HRV-02, HRV-05)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", mock_obs), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/harvest", json={"names": ["Boar"], "user_id": "u1"})
    assert resp.status_code == 200
    body = resp.json()
    for comp in body["monsters"][0]["components"]:
        assert isinstance(comp["craftable"], list)
        for craft in comp["craftable"]:
            assert isinstance(craft["name"], str)
            assert isinstance(craft["crafting_dc"], int)
            assert isinstance(craft["value"], str)


async def test_harvest_medicine_dc_present():
    """Every component has integer medicine_dc; Boar (L2) first component DC==16 (HRV-04)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", mock_obs), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/harvest", json={"names": ["Boar"], "user_id": "u1"})
    assert resp.status_code == 200
    body = resp.json()
    comps = body["monsters"][0]["components"]
    for comp in comps:
        assert isinstance(comp["medicine_dc"], int)
    assert comps[0]["medicine_dc"] == 16


async def test_harvest_batch_aggregated():
    """Batch of [Boar, Wolf] aggregates "Hide" across both monsters (HRV-06, D-04)."""
    mock_obs = MagicMock()
    # 2 monsters → 2 get_note misses; then 2 put_note spies. Provide generous None list.
    mock_obs.get_note = AsyncMock(side_effect=[None, None, None, None])
    mock_obs.put_note = AsyncMock(return_value=None)
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", mock_obs), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/harvest", json={"names": ["Boar", "Wolf"], "user_id": "u1"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["monsters"]) == 2
    aggregated = body["aggregated"]
    hide_entries = [a for a in aggregated if a.get("type") == "Hide"]
    assert len(hide_entries) == 1
    hide_monsters = set(hide_entries[0]["monsters"])
    assert "Boar" in hide_monsters
    assert "Wolf" in hide_monsters
    all_types = {a["type"] for a in aggregated}
    assert {"Hide", "Fangs"}.issubset(all_types)


async def test_harvest_fuzzy_match_returns_note():
    """'Alpha Wolf' fuzzy-matches Wolf seed; source='seed-fuzzy' and note present (D-02)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", mock_obs), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/harvest", json={"names": ["Alpha Wolf"], "user_id": "u1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["monsters"][0]["source"] == "seed-fuzzy"
    note = body["monsters"][0]["note"]
    assert note
    assert "Matched to closest" in note


async def test_harvest_fuzzy_below_threshold_falls_to_llm():
    """'Wolf Lord' scores below fuzzy cutoff 85 → LLM fallback (D-02, Pitfall 2)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock(return_value={
        "monster": "Wolf Lord",
        "level": 3,
        "components": [
            {"type": "Hide", "medicine_dc": 18, "craftable": []},
        ],
        "source": "llm-generated",
        "verified": False,
    })
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", mock_obs), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/harvest", json={"names": ["Wolf Lord"], "user_id": "u1"})
    assert resp.status_code == 200
    assert mock_llm.await_count == 1
    body = resp.json()
    assert body["monsters"][0]["source"] == "llm-generated"
    assert body["monsters"][0]["verified"] is False


async def test_harvest_llm_fallback_marks_generated():
    """Unknown monster → verified=False and footer signals "generated" (D-02, T-32-LLM-01)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock(return_value={
        "monster": "Dracolich",
        "level": 14,
        "components": [
            {"type": "Scale", "medicine_dc": 31, "craftable": []},
        ],
        "source": "llm-generated",
        "verified": False,
    })
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", mock_obs), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/harvest", json={"names": ["Dracolich"], "user_id": "u1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["monsters"][0]["verified"] is False
    assert "generated" in body["footer"].lower()


async def test_harvest_cache_hit_skips_llm():
    """Cached note → no LLM call, no re-write (D-03b)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=CACHED_HARVEST_MD)
    mock_obs.put_note = AsyncMock(return_value=None)
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", mock_obs), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/harvest", json={"names": ["Boar"], "user_id": "u1"})
    assert resp.status_code == 200
    assert mock_llm.await_count == 0
    body = resp.json()
    # Planner accepts either "cache" or preserved frontmatter source per PATTERNS §8 Gotcha 2.
    assert body["monsters"][0]["source"] in {"cache", "seed"}
    assert mock_obs.put_note.await_count == 0


async def test_harvest_cache_write_on_miss():
    """Seed hit writes cache to namespaced path on miss (D-03b)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", mock_obs), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/harvest", json={"names": ["Boar"], "user_id": "u1"})
    assert resp.status_code == 200
    assert mock_obs.put_note.await_count == 1
    call_path = mock_obs.put_note.call_args[0][0]
    assert call_path.startswith("mnemosyne/pf2e/harvest/")
    assert call_path.endswith("boar.md")


async def test_harvest_cache_write_failure_degrades(caplog):
    """put_note raises → 200 still returned; WARNING logged (D-03b graceful degrade)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(side_effect=Exception("obsidian down"))
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock()
    with caplog.at_level(logging.WARNING):
        with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
             patch("app.routes.harvest.obsidian", mock_obs), \
             patch("app.routes.harvest.harvest_tables", stub_tables), \
             patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
            from app.main import app
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/harvest", json={"names": ["Boar"], "user_id": "u1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["monsters"]
    matched = [
        rec for rec in caplog.records
        if "cache" in rec.getMessage().lower() or "harvest" in rec.getMessage().lower()
    ]
    assert matched, "Expected a WARNING log mentioning 'cache' or 'harvest'"


async def test_harvest_empty_names_422():
    """POST with names=[] → 422 (Pydantic field_validator path)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", mock_obs), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/harvest", json={"names": [], "user_id": "u1"})
    assert resp.status_code == 422


async def test_harvest_missing_names_key_422():
    """POST without a 'names' key → 422 (FastAPI required-field path, different from empty-list)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", mock_obs), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/harvest", json={})
    assert resp.status_code == 422


async def test_harvest_invalid_name_control_char():
    """Name containing \\x00 → 422 (T-32-SEC-01, _validate_monster_name)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", mock_obs), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/harvest", json={"names": ["Boar\x00"], "user_id": "u1"})
    assert resp.status_code == 422


async def test_harvest_llm_malformed_output_graceful_500():
    """LLM returns valid JSON with missing medicine_dc → 500 via route handler (CR-02).

    Before CR-02, the malformed output slipped past the LLM-success catch and
    crashed build_harvest_markdown/_aggregate_by_component with a KeyError
    outside any try/except — unhandled 500. After CR-02 the LLM-shape
    validator raises ValueError inside generate_harvest_fallback, which the
    route's LLM-failure handler catches and returns as a clean 500 WITHOUT
    writing cache.
    """
    # We import here so patching works against the module where the fn lives.
    import json as _json

    # Simulate a real LLM response that returns valid JSON with the wrong shape:
    # component is missing medicine_dc (the blast radius point).
    # We patch litellm.acompletion directly so the real generate_harvest_fallback
    # runs its validator.
    class _FakeResp:
        class _Choice:
            class _Msg:
                content = _json.dumps({
                    "monster": "Bogeyman",
                    "level": 5,
                    "components": [{"type": "Hide", "craftable": []}],  # no medicine_dc
                })
            message = _Msg()
        choices = [_Choice()]

    async def _fake_acompletion(**_kwargs):
        return _FakeResp()

    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    stub_tables = _make_stub_tables()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", mock_obs), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.llm.litellm.acompletion", new=_fake_acompletion):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/harvest",
                json={"names": ["Bogeyman"], "user_id": "u"},
            )
    # 500 (not 200, not unhandled server crash) and NO cache write.
    assert resp.status_code == 500
    assert mock_obs.put_note.await_count == 0


async def test_harvest_unicode_only_name_rejected():
    """Name that slugifies to empty string → 422 (CR-01 cache collision fix).

    Names like "测试龙" (Unicode-only) or "!@#$%" (punctuation-only) slug to
    "" and would otherwise collide at mnemosyne/pf2e/harvest/.md, returning
    the cached data from any prior empty-slug request. Reject at validation.
    """
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", mock_obs), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Unicode-only name
            resp1 = await client.post("/harvest", json={"names": ["测试龙"], "user_id": "u"})
            assert resp1.status_code == 422
            # Punctuation-only name
            resp2 = await client.post("/harvest", json={"names": ["!@#$%"], "user_id": "u"})
            assert resp2.status_code == 422
            # Path-traversal-only name (also slugifies to "")
            resp3 = await client.post("/harvest", json={"names": ["..//"], "user_id": "u"})
            assert resp3.status_code == 422


async def test_harvest_batch_cap_enforced():
    """21 names → 422 (MAX_BATCH_NAMES=20, T-32-SEC DoS)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", mock_obs), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/harvest",
                json={"names": ["M"] * 21, "user_id": "u1"},
            )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 16-18. format_price pure helper (HRV-03, Pitfall 3) — Plan 32-03 GREEN target
# ---------------------------------------------------------------------------


def test_format_price_single_denom():
    """format_price({'gp': 2}) → '2 gp' (HRV-03)."""
    from app.harvest import format_price

    assert format_price({"gp": 2}) == "2 gp"


def test_format_price_mixed_currency():
    """format_price({'gp': 2, 'sp': 5}) → '2 gp 5 sp' (HRV-03, Pitfall 3)."""
    from app.harvest import format_price

    assert format_price({"gp": 2, "sp": 5}) == "2 gp 5 sp"


def test_format_price_empty_dict():
    """format_price({}) → '0 cp' defensive default (HRV-03)."""
    from app.harvest import format_price

    assert format_price({}) == "0 cp"


# ---------------------------------------------------------------------------
# 19-20. lookup_seed fuzzy boundary tests (D-02) — Plan 32-03 GREEN target
# ---------------------------------------------------------------------------


def test_fuzzy_subset_matches():
    """lookup_seed('alpha wolf', tables) → Wolf entry + 'Matched to closest' note (D-02)."""
    from app.harvest import lookup_seed

    tables = _make_stub_tables()
    entry, note = lookup_seed("alpha wolf", tables)
    assert entry is not None
    assert entry.name == "Wolf"
    assert note is not None
    assert "Matched to closest" in note


def test_fuzzy_wolf_lord_falls_through():
    """lookup_seed('wolf lord', tables) → (None, None) — score below cutoff 85 (Pitfall 2)."""
    from app.harvest import lookup_seed

    tables = _make_stub_tables()
    entry, note = lookup_seed("wolf lord", tables)
    assert entry is None
    assert note is None


# ---------------------------------------------------------------------------
# 21. YAML schema validator (§YAML Loader) — Plan 32-03 GREEN target
# ---------------------------------------------------------------------------


def test_invalid_yaml_raises(tmp_path):
    """load_harvest_tables on malformed YAML raises (Pydantic ValidationError)."""
    from app.harvest import load_harvest_tables

    # YAML parses cleanly but violates the MonsterEntry schema: missing required
    # fields (level, components) on the entry. Pydantic rejects at model_validate.
    bad_yaml = (
        "version: \"1.0\"\n"
        "source: foundryvtt-pf2e\n"
        "levels: [1]\n"
        "monsters:\n"
        "  - name: Broken\n"
    )
    bad_path = tmp_path / "bad.yaml"
    bad_path.write_text(bad_yaml)
    with pytest.raises(Exception):
        load_harvest_tables(bad_path)
