"""Integration tests for /harvest — full vault round-trip with mocked LLM (HRV-01..06, D-03b).

Wave 0 RED scaffolding — implementation lands in Waves 1-3.
Stubs reference app.routes.harvest which does not yet exist. Collection succeeds;
runtime `patch()` of the missing attribute fails with AttributeError — the honest RED signal.
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
# Module-level fixtures — structural shape per 32-RESEARCH.md §YAML Loader
# ---------------------------------------------------------------------------


STUB_HARVEST_TABLE_DATA = {
    "version": "1.0",
    "source": "foundryvtt-pf2e",
    "levels": [1, 2, 3],
    "monsters": [
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


class StatefulMockVault:
    """In-memory vault mock — get_note returns last put_note content per path.

    Allows integration tests to observe the full round-trip: first POST writes the
    cache; second POST reads the cache and skips the LLM (D-03b).
    """

    def __init__(self, initial: dict[str, str]):
        self._store: dict[str, str] = dict(initial)
        self.get_note = AsyncMock(side_effect=self._get)
        self.put_note = AsyncMock(side_effect=self._put)

    async def _get(self, path: str) -> str | None:
        return self._store.get(path)

    async def _put(self, path: str, content: str) -> None:
        self._store[path] = content


# ---------------------------------------------------------------------------
# Integration tests — Waves 1-3 GREEN target
# ---------------------------------------------------------------------------


async def test_first_query_writes_cache_second_reads_cache():
    """Two-call round trip: call 1 writes cache (LLM hit); call 2 reads cache (no LLM) (D-03b)."""
    vault = StatefulMockVault({})
    mock_llm = AsyncMock(return_value={
        "monster": "Unicorn",
        "level": 3,
        "components": [
            {
                "type": "Horn",
                "medicine_dc": 18,
                "craftable": [
                    {"name": "Horn dust", "crafting_dc": 18, "value": "10 gp"},
                ],
            },
        ],
        "source": "llm-generated",
        "verified": False,
    })
    stub_tables = _make_stub_tables()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", vault), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Call 1: Unicorn is NOT in stub tables → LLM fallback → cache write.
            resp1 = await client.post("/harvest", json={"names": ["Unicorn"], "user_id": "u1"})
            assert resp1.status_code == 200
            assert vault.put_note.await_count == 1
            assert mock_llm.await_count == 1
            body1 = resp1.json()
            assert body1["monsters"][0]["source"] == "llm-generated"
            cached = vault._store.get("mnemosyne/pf2e/harvest/unicorn.md")
            assert cached is not None
            assert "source: llm-generated" in cached
            assert "verified: false" in cached.lower()

            # Call 2: identical payload — cache hit, LLM must NOT be called again,
            # put_note must NOT re-write.
            resp2 = await client.post("/harvest", json={"names": ["Unicorn"], "user_id": "u1"})
            assert resp2.status_code == 200
            assert mock_llm.await_count == 1  # unchanged
            assert vault.put_note.await_count == 1  # unchanged
            body2 = resp2.json()
            horn_components = [
                c for c in body2["monsters"][0]["components"] if c.get("type") == "Horn"
            ]
            assert horn_components, "Expected cached Horn component to be reflected"
            assert body2["monsters"][0]["verified"] is False


async def test_seed_hit_writes_cache_with_source_seed():
    """Seed hit path → cache file written with 'source: seed' frontmatter; LLM never called (D-03b)."""
    vault = StatefulMockVault({})
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock(side_effect=AssertionError("LLM must not be called for seed hit"))
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", vault), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/harvest", json={"names": ["Wolf"], "user_id": "u1"})
    assert resp.status_code == 200
    assert mock_llm.await_count == 0
    assert vault.put_note.await_count == 1
    stored_path = "mnemosyne/pf2e/harvest/wolf.md"
    assert stored_path in vault._store
    stored = vault._store[stored_path]
    assert "source: seed" in stored
    # Seed-default verify disposition is planner-dependent; assert the field is present.
    assert "verified:" in stored
    body = resp.json()
    assert body["monsters"][0]["source"] == "seed"


async def test_batch_mixed_sources_footer():
    """Batch with Wolf (seed) + Unicorn (LLM) → footer mentions mixed sources (D-04)."""
    vault = StatefulMockVault({})
    stub_tables = _make_stub_tables()
    mock_llm = AsyncMock(return_value={
        "monster": "Unicorn",
        "level": 3,
        "components": [
            {"type": "Horn", "medicine_dc": 18, "craftable": []},
        ],
        "source": "llm-generated",
        "verified": False,
    })
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", vault), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/harvest",
                json={"names": ["Wolf", "Unicorn"], "user_id": "u1"},
            )
    assert resp.status_code == 200
    # Wolf hits seed → LLM called exactly once (for Unicorn only).
    assert mock_llm.await_count == 1
    # Both monsters cached → two put_note calls.
    assert vault.put_note.await_count == 2
    body = resp.json()
    footer = body["footer"]
    assert "1 seed" in footer
    assert "1 generated" in footer
    # Aggregation lists both monsters' component types.
    agg_types = {a["type"] for a in body["aggregated"]}
    assert "Hide" in agg_types
    assert "Horn" in agg_types
