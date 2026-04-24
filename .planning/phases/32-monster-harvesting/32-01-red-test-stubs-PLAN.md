---
plan_id: 32-01
phase: 32
wave: 0
depends_on: []
files_modified:
  - modules/pathfinder/tests/test_harvest.py
  - modules/pathfinder/tests/test_harvest_integration.py
  - interfaces/discord/tests/test_subcommands.py
autonomous: true
requirements: [HRV-01, HRV-02, HRV-03, HRV-04, HRV-05, HRV-06]
must_haves:
  truths:
    - "modules/pathfinder/tests/test_harvest.py contains exactly 21 test stubs covering HRV-01..06, D-02 fuzzy, D-03b cache, format_price, YAML schema, security caps"
    - "modules/pathfinder/tests/test_harvest_integration.py contains exactly 3 round-trip stubs (StatefulMockVault pattern from 31-01) covering cache write-through, seed-source persistence, batch mixed sources"
    - "interfaces/discord/tests/test_subcommands.py gains exactly 7 test_pf_harvest_* stubs (solo, batch, multi-word name, trimmed commas, empty usage, embed dict shape, noun-recognised)"
    - "All 31 stubs (21 + 3 + 7) collect cleanly — no ImportError — and FAIL on run (RED — implementation not yet present)"
    - "rapidfuzz dependency pinned by a smoke-test stub: test_rapidfuzz_importable asserts rapidfuzz.__version__ >= 3.14.0 (WILL FAIL until Plan 32-02 adds the dep + uv sync runs)"
    - "Stubs reference app.harvest.lookup_seed, app.harvest.format_price, app.harvest.load_harvest_tables, app.harvest.build_harvest_markdown, app.routes.harvest.harvest_tables, app.routes.harvest.obsidian, app.llm.generate_harvest_fallback, bot.build_harvest_embed — all symbols Waves 1-3 must land"
  tests:
    - "cd modules/pathfinder && python -m pytest tests/test_harvest.py --collect-only -q  # → 21 tests collected (no collection errors)"
    - "cd modules/pathfinder && python -m pytest tests/test_harvest_integration.py --collect-only -q  # → 3 tests collected"
    - "cd interfaces/discord && python -m pytest tests/test_subcommands.py -k 'harvest' --collect-only -q  # → 7 tests collected"
    - "cd modules/pathfinder && python -m pytest tests/test_harvest.py -q  # → 21 failed (RED, not collection errors)"
---

<plan_objective>
Wave 0 RED scaffolding for Phase 32. Create the 31 test stubs (21 module unit + 3 module integration + 7 bot unit, includes 1 recognition-check) enumerated in 32-VALIDATION.md so downstream waves implement against an explicit test contract. Stubs MUST fail (not error on collection) — they reference symbols that will land in Waves 1-3 and are import-protected so collection succeeds. This plan ships ZERO production code.
</plan_objective>

<threat_model>
## STRIDE Register (Wave 0 — test scaffolding only)

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-32-01-S01 | Spoofing | test fixtures using fake user_id | accept | Test-only; fixtures never touch production auth path. |
| T-32-01-T01 | Tampering | test fixtures embedding prompt-injection-shaped monster names (`"Goblin. Ignore prior instructions."`) | accept | Strings are inert in test context (canned, not LLM-evaluated). Documents the shape Wave 1 must defend against. |

**Block level:** none — Wave 0 ships test scaffolding only; production code lands in Waves 1-3. ASVS L1 enforcement begins at Plan 32-03 (helpers with input sanitisation) and Plan 32-04 (route handler + Pydantic validators).

**Threats this scaffolding ANTICIPATES (not introduces):**
- T-32-SEC-01 (malicious monster name / path traversal / control chars) — covered by `test_harvest_invalid_name_control_char` and `test_harvest_batch_cap_enforced`
- T-32-SEC-02 (fuzzy-match false positive) — covered by `test_fuzzy_wolf_lord_falls_through` and `test_fuzzy_hobgoblin_falls_through`
- T-32-SEC-03 (LLM prompt injection via monster name) — covered by `test_harvest_llm_fallback_marks_generated` (asserts `verified: False` so a manipulated response still lands behind the verify gate)
- T-32-SEC-04 (Obsidian file-name collision) — covered by `test_harvest_cache_write_on_miss` (asserts path starts with the namespaced prefix)
- T-32-LLM-01 (low-confidence LLM output silently canonicalised) — covered by `test_harvest_llm_fallback_marks_generated` and integration `test_first_query_writes_cache_second_reads_cache`
</threat_model>

<tasks>

<task id="32-01-01" type="execute" autonomous="true">
  <name>Task 32-01-01: Create modules/pathfinder/tests/test_harvest.py with 21 unit stubs</name>
  <read_first>
    - modules/pathfinder/tests/test_npc.py (lines 1-12 for env-bootstrap pattern; lines 20-39 for happy-path test analog; line 243 for AsyncMock side_effect pattern)
    - .planning/phases/32-monster-harvesting/32-PATTERNS.md §7 (20-test table + gotchas + analog A)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md lines 993-1020 (Phase Requirements → Test Map)
    - .planning/phases/32-monster-harvesting/32-VALIDATION.md (per-task verification map once filled by this planning pass)
    - .planning/phases/31-dialogue-engine/31-01-red-test-stubs-PLAN.md (exemplar Wave-0 plan — scaffolding contract + import-protection rule)
  </read_first>
  <action>
CREATE `modules/pathfinder/tests/test_harvest.py`. Top of file — verbatim env-bootstrap from test_npc.py lines 1-12 (per PATTERNS.md §7 Analog A):

```python
"""Tests for pf2e-module harvest endpoints (HRV-01..06, D-02 fuzzy, D-03b cache)."""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
```

**Import-protection rule (so collection succeeds despite missing modules):**
Do NOT use `try/except ImportError` to skip — tests must run and FAIL so the RED→GREEN signal is honest. Where a test needs to import a not-yet-existing symbol (e.g. `from app.harvest import format_price`), put the import INSIDE the test function body so collection succeeds but the test fails at runtime.

**Module-scope fixture helpers** (place after imports, before tests):

```python
# Wave 0 RED scaffolding — implementation lands in Waves 1-3.
# Stubs reference app.harvest (Plan 32-03) and app.routes.harvest (Plan 32-04)
# which do not yet exist. Tests are expected to FAIL on run (RED) but MUST collect cleanly.

# A minimal stub harvest table usable by tests — structural shape from 32-RESEARCH.md §YAML Loader.
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
```

**The 21 tests** — implement EXACTLY these names (matches 32-VALIDATION.md verbatim):

1. `test_rapidfuzz_importable` — smoke test per PATTERNS.md §6 verifier: `import rapidfuzz; assert rapidfuzz.__version__ >= "3.14.0"`. Will FAIL until Plan 32-02 adds `rapidfuzz>=3.14.0` to pyproject.toml AND `uv sync` runs.

2. `test_harvest_single_seed_hit` — HRV-01, HRV-04. Stub harvest_tables with STUB_HARVEST_TABLE_DATA; `get_note` → None (cache miss); patch `app.routes.harvest.generate_harvest_fallback` (unused — seed hits first). POST `/harvest` `{"names": ["Boar"], "user_id": "u1"}`. Assert 200, `monsters[0]["source"] == "seed"`, `monsters[0]["level"] == 2`, `len(monsters[0]["components"]) >= 1`, every component has integer `medicine_dc`.

3. `test_harvest_components_have_craftable` — HRV-02, HRV-05. Same setup as test 2. Assert every component in `monsters[0]["components"]` has a `craftable` list; each craftable entry has keys `name`, `crafting_dc` (int), `value` (str).

4. `test_harvest_medicine_dc_present` — HRV-04. Same setup. Assert every component has integer `medicine_dc`, and for Boar (level 2) the first component's `medicine_dc == 16` (per DC-by-level table).

5. `test_harvest_batch_aggregated` — HRV-06, D-04. Stub tables with Boar+Wolf. `get_note = AsyncMock(side_effect=[None, None, ...])` (misses for both monsters and their cache writes). POST `{"names": ["Boar", "Wolf"], "user_id": "u1"}`. Assert `len(monsters) == 2`; `aggregated` has one "Hide" field with `monsters` containing BOTH "Boar" and "Wolf"; `aggregated[*][type]` contains all unique component types across the two monsters.

6. `test_harvest_fuzzy_match_returns_note` — D-02. Stub tables contain "Wolf"; POST `{"names": ["Alpha Wolf"], "user_id": "u1"}`; `get_note` → None. Assert 200, `monsters[0]["source"] == "seed-fuzzy"`, `monsters[0]["note"]` is non-empty AND contains the substring "Matched to closest".

7. `test_harvest_fuzzy_below_threshold_falls_to_llm` — D-02 (Pitfall 2). Stub tables contain "Wolf"; POST `{"names": ["Wolf Lord"], "user_id": "u1"}`. Patch `app.routes.harvest.generate_harvest_fallback` with AsyncMock returning a minimal valid dict: `{"monster": "Wolf Lord", "level": 3, "components": [{"type": "Hide", "medicine_dc": 18, "craftable": []}], "source": "llm-generated", "verified": False}`. Assert the mock was called once; `monsters[0]["source"] == "llm-generated"`; `monsters[0]["verified"] is False`.

8. `test_harvest_llm_fallback_marks_generated` — D-02, T-32-LLM-01. No seed match. Patch `generate_harvest_fallback` → dict with `verified: False, source: "llm-generated"`. Assert `monsters[0]["verified"] is False`; footer contains "generated".

9. `test_harvest_cache_hit_skips_llm` — D-03b. `get_note` → CACHED_HARVEST_MD (cache hit). Patch `generate_harvest_fallback` with a spy. POST `{"names": ["Boar"], "user_id": "u1"}`. Assert 200; `generate_harvest_fallback.await_count == 0` (no LLM call); `monsters[0]["source"]` is either `"cache"` or preserves the frontmatter source (planner accepts either per PATTERNS.md §8 Gotcha 2 — assert it is one of `{"cache", "seed"}`); `put_note.await_count == 0` (cache hits do NOT re-write).

10. `test_harvest_cache_write_on_miss` — D-03b. Seed hit (Boar); `put_note` spy. Assert `put_note.await_count == 1`; the call's first positional arg (path) starts with `"mnemosyne/pf2e/harvest/"` AND ends with `"boar.md"`.

11. `test_harvest_cache_write_failure_degrades` — D-03b graceful degrade. Seed hit; `put_note` raises `Exception("obsidian down")`. Assert 200 returned (NOT 500); `monsters[0]` present; WARNING logged (use `caplog` at `logging.WARNING` level; assert any record has `"cache"` or `"harvest"` in the message).

12. `test_harvest_empty_names_422` — validator. POST `{"names": [], "user_id": "u1"}`. Assert 422 (Pydantic validator rejects empty list per PATTERNS.md §3 Analog A — exercises the `field_validator` code path with an explicitly empty list).

13. `test_harvest_missing_names_key_422` — required-field guard. POST `{}` (missing `names` key entirely). Assert 422. This exercises a DIFFERENT code path from test 12: FastAPI/Pydantic's built-in required-field handling (triggered because `names: list[str]` has no default) runs BEFORE any `field_validator` is invoked. The test locks in that the endpoint is not only rejecting empty lists but also missing keys.

14. `test_harvest_invalid_name_control_char` — T-32-SEC-01. POST `{"names": ["Boar\x00"], "user_id": "u1"}`. Assert 422 (per _validate_monster_name mirror of _validate_npc_name).

15. `test_harvest_batch_cap_enforced` — T-32-SEC DoS. POST with `names=["M"] * 21` (21 entries; MAX_BATCH_NAMES=20 per RESEARCH.md §Security Domain). Assert 422.

16. `test_format_price_single_denom` — HRV-03, Pitfall 3. Inside the test body: `from app.harvest import format_price`. Assert `format_price({"gp": 2}) == "2 gp"`.

17. `test_format_price_mixed_currency` — HRV-03, Pitfall 3. Inside: `from app.harvest import format_price`. Assert `format_price({"gp": 2, "sp": 5}) == "2 gp 5 sp"`.

18. `test_format_price_empty_dict` — HRV-03 defensive. Inside: `from app.harvest import format_price`. Assert `format_price({}) == "0 cp"`.

19. `test_fuzzy_subset_matches` — D-02 unit. Inside: `from app.harvest import lookup_seed`; build `tables = _make_stub_tables()`. `entry, note = lookup_seed("alpha wolf", tables)`. Assert `entry is not None`, `entry.name == "Wolf"`, `note is not None` and contains "Matched to closest".

20. `test_fuzzy_wolf_lord_falls_through` — Pitfall 2 boundary. `entry, note = lookup_seed("wolf lord", tables)`. Assert `entry is None` AND `note is None` (score below cutoff 85).

21. `test_invalid_yaml_raises` — YAML schema validator (§YAML Loader). Inside: `from app.harvest import load_harvest_tables`. Write a malformed YAML to a tmp file (use `tmp_path` fixture) — e.g. `monsters:\n  - name: "Broken"\n    # missing level and components fields (required by MonsterEntry)\n`. Wrap the outer shape so `yaml.safe_load` parses successfully but Pydantic rejects. Assert `pytest.raises(Exception)` (ValidationError or equivalent) when `load_harvest_tables(tmp_file)` runs.

**Scaffolding contract** (inherits from 31-01-01 patterns per PATTERNS.md §7 Gotcha 1):
- Use `mock_obs = MagicMock(); mock_obs.get_note = AsyncMock(...); mock_obs.put_note = AsyncMock(return_value=None)`.
- Always patch `app.main._register_with_retry` AND `app.routes.harvest.obsidian` AND `app.routes.harvest.harvest_tables` inside the same `with` block; `from app.main import app` MUST be inside that `with` block.
- For LLM mocks, target `app.routes.harvest.generate_harvest_fallback` (the route's import), not `app.llm.generate_harvest_fallback` (the source).
- Use `AsyncMock(side_effect=[...])` for multiple sequential calls in batch tests.
- `async def test_*` — no `@pytest.mark.asyncio` decorator (pyproject.toml has `asyncio_mode = "auto"` per PATTERNS.md §7 Gotcha 2).

DO NOT add any production code. DO NOT skip stubs because a symbol doesn't exist — write the stub assuming Waves 1-3 will land the symbol.
  </action>
  <acceptance_criteria>
    - `test -f modules/pathfinder/tests/test_harvest.py` exits 0
    - `grep -cE '^(async )?def test_' modules/pathfinder/tests/test_harvest.py` → exactly 21
    - `grep -c '^STUB_HARVEST_TABLE_DATA = ' modules/pathfinder/tests/test_harvest.py` → 1
    - `grep -c '^CACHED_HARVEST_MD = ' modules/pathfinder/tests/test_harvest.py` → 1
    - `grep -c '^def _make_stub_tables' modules/pathfinder/tests/test_harvest.py` → 1
    - All 21 test names present: `grep -cE '^(async )?def test_(rapidfuzz_importable|harvest_single_seed_hit|harvest_components_have_craftable|harvest_medicine_dc_present|harvest_batch_aggregated|harvest_fuzzy_match_returns_note|harvest_fuzzy_below_threshold_falls_to_llm|harvest_llm_fallback_marks_generated|harvest_cache_hit_skips_llm|harvest_cache_write_on_miss|harvest_cache_write_failure_degrades|harvest_empty_names_422|harvest_missing_names_key_422|harvest_invalid_name_control_char|harvest_batch_cap_enforced|format_price_single_denom|format_price_mixed_currency|format_price_empty_dict|fuzzy_subset_matches|fuzzy_wolf_lord_falls_through|invalid_yaml_raises)' modules/pathfinder/tests/test_harvest.py` → 21
    - `cd modules/pathfinder && python -m pytest tests/test_harvest.py --collect-only -q` outputs "21 tests collected" (no collection errors)
    - `cd modules/pathfinder && python -m pytest tests/test_harvest.py -q` exit code != 0 (RED — failures expected)
    - File begins with the env-bootstrap stanza identical to test_npc.py lines 3-9: `head -11 modules/pathfinder/tests/test_harvest.py | grep -c "os.environ.setdefault"` → 6
  </acceptance_criteria>
  <automated>cd modules/pathfinder && python -m pytest tests/test_harvest.py --collect-only -q</automated>
</task>

<task id="32-01-02" type="execute" autonomous="true">
  <name>Task 32-01-02: Create modules/pathfinder/tests/test_harvest_integration.py with 3 round-trip stubs</name>
  <read_first>
    - modules/pathfinder/tests/test_npc_say_integration.py (full file — lines 45-62 for StatefulMockVault pattern to copy verbatim; lines 1-19 for env-bootstrap + imports)
    - .planning/phases/32-monster-harvesting/32-PATTERNS.md §8 (3-test table + StatefulMockVault analog + Gotchas 1-2)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md §Architecture Patterns (cache-aside flow)
    - .planning/phases/31-dialogue-engine/31-01-red-test-stubs-PLAN.md (Task 31-01-02 integration-test exemplar)
  </read_first>
  <action>
CREATE `modules/pathfinder/tests/test_harvest_integration.py`.

**Top of file** — verbatim env-bootstrap from test_npc_say_integration.py lines 1-19:

```python
"""Integration tests for /harvest — full vault round-trip with mocked LLM (HRV-01..06, D-03b)."""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
```

**Module-level constants**:

```python
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
    from app.harvest import HarvestTable
    return HarvestTable.model_validate(STUB_HARVEST_TABLE_DATA)
```

**StatefulMockVault helper — copy verbatim from test_npc_say_integration.py lines 45-62** (per PATTERNS.md §8 analog), renaming nothing:

```python
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
```

**The 3 tests** (names match 32-VALIDATION.md verbatim):

1. `test_first_query_writes_cache_second_reads_cache` — D-03b write-through round trip.
   Steps:
   1. `vault = StatefulMockVault({})` (empty).
   2. Build LLM mock: `mock_llm = AsyncMock(return_value={"monster": "Unicorn", "level": 3, "components": [{"type": "Horn", "medicine_dc": 18, "craftable": [{"name": "Horn dust", "crafting_dc": 18, "value": "10 gp"}]}], "source": "llm-generated", "verified": False})`.
   3. Stub tables are empty-monsters (or omit Unicorn). Use `patch("app.routes.harvest.harvest_tables", _make_stub_tables())`.
   4. With patches active (`app.main._register_with_retry`, `app.routes.harvest.obsidian=vault`, `app.routes.harvest.harvest_tables`, `app.routes.harvest.generate_harvest_fallback=mock_llm`), POST `/harvest` `{"names": ["Unicorn"], "user_id": "u1"}` via AsyncClient.
   5. Assert call 1: 200; `vault.put_note.await_count == 1`; `mock_llm.await_count == 1`; `monsters[0]["source"] == "llm-generated"`; vault store contains `mnemosyne/pf2e/harvest/unicorn.md` with frontmatter containing `source: llm-generated` AND `verified: false`.
   6. POST again with identical payload (second call — cache hit expected).
   7. Assert call 2: 200; `mock_llm.await_count == 1` (NOT 2 — cache hit skipped LLM); `vault.put_note.await_count == 1` (NOT 2 — no re-write on hit); response `monsters[0]` reflects cached data (horn component present, `verified: False` preserved).

2. `test_seed_hit_writes_cache_with_source_seed` — D-03b seed→cache.
   Steps:
   1. `vault = StatefulMockVault({})`.
   2. `patch("app.routes.harvest.harvest_tables", _make_stub_tables())` — contains Wolf.
   3. `mock_llm = AsyncMock(side_effect=AssertionError("LLM should not be called for seed hit"))`.
   4. POST `/harvest` `{"names": ["Wolf"], "user_id": "u1"}`.
   5. Assert 200; `mock_llm.await_count == 0`; `vault.put_note.await_count == 1`; the stored path is `mnemosyne/pf2e/harvest/wolf.md`; the stored content includes `source: seed` in frontmatter AND `verified:` value is present (seed matches default to True OR False per planner's choice in Plan 32-03 — accept whichever the stub markdown reflects; assert `"source: seed"` literal).
   6. Response `monsters[0]["source"] == "seed"`.

3. `test_batch_mixed_sources_footer` — D-04.
   Steps:
   1. `vault = StatefulMockVault({})`.
   2. Stub tables contain Wolf; Unicorn is NOT in tables.
   3. `mock_llm = AsyncMock(return_value={"monster": "Unicorn", "level": 3, "components": [{"type": "Horn", "medicine_dc": 18, "craftable": []}], "source": "llm-generated", "verified": False})`.
   4. POST `{"names": ["Wolf", "Unicorn"], "user_id": "u1"}`.
   5. Assert 200; `mock_llm.await_count == 1` (only for Unicorn — Wolf hits seed); `vault.put_note.await_count == 2` (both cached).
   6. Response `footer` contains the substring `"1 seed"` AND `"1 generated"` (exact phrasing — e.g. `"Mixed sources — 1 seed / 1 generated"` per D-04 / CONTEXT.md).
   7. Response `aggregated` lists both monsters' components (`Wolf` under "Hide", `Unicorn` under "Horn").

**Mock pattern** — wrap each test body:
```python
async def test_first_query_writes_cache_second_reads_cache():
    vault = StatefulMockVault({})
    mock_llm = AsyncMock(return_value={...})
    stub_tables = _make_stub_tables()
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.harvest.obsidian", vault), \
         patch("app.routes.harvest.harvest_tables", stub_tables), \
         patch("app.routes.harvest.generate_harvest_fallback", new=mock_llm):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp1 = await client.post("/harvest", json={"names": ["Unicorn"], "user_id": "u1"})
            ...
```

Both tests are async (no `@pytest.mark.asyncio` — `asyncio_mode = "auto"`).
  </action>
  <acceptance_criteria>
    - `test -f modules/pathfinder/tests/test_harvest_integration.py` exits 0
    - `grep -cE '^async def test_' modules/pathfinder/tests/test_harvest_integration.py` → exactly 3
    - `grep -F 'test_first_query_writes_cache_second_reads_cache' modules/pathfinder/tests/test_harvest_integration.py` matches
    - `grep -F 'test_seed_hit_writes_cache_with_source_seed' modules/pathfinder/tests/test_harvest_integration.py` matches
    - `grep -F 'test_batch_mixed_sources_footer' modules/pathfinder/tests/test_harvest_integration.py` matches
    - `grep -c 'class StatefulMockVault' modules/pathfinder/tests/test_harvest_integration.py` → 1
    - `cd modules/pathfinder && python -m pytest tests/test_harvest_integration.py --collect-only -q` → "3 tests collected"
    - `cd modules/pathfinder && python -m pytest tests/test_harvest_integration.py -q` → exit code != 0 (RED)
    - `head -11 modules/pathfinder/tests/test_harvest_integration.py | grep -c "os.environ.setdefault"` → 6
  </acceptance_criteria>
  <automated>cd modules/pathfinder && python -m pytest tests/test_harvest_integration.py --collect-only -q</automated>
</task>

<task id="32-01-03" type="execute" autonomous="true">
  <name>Task 32-01-03: Append 7 test_pf_harvest_* stubs to interfaces/discord/tests/test_subcommands.py</name>
  <read_first>
    - interfaces/discord/tests/test_subcommands.py (full file — lines 13-50 for discord stub pattern; lines 301-355 for `test_pf_say_*` block to mirror; lines 206-225 for `test_pf_dispatch_create` analog)
    - .planning/phases/32-monster-harvesting/32-PATTERNS.md §10 (6-test table + Gotchas 1-3)
    - .planning/phases/32-monster-harvesting/32-VALIDATION.md (bot-layer tests section once filled by this planning pass)
    - .planning/phases/31-dialogue-engine/31-01-red-test-stubs-PLAN.md (Task 31-01-03 exemplar — 8-test append to the same file)
  </read_first>
  <action>
APPEND 7 test stubs to interfaces/discord/tests/test_subcommands.py. Patch target for ALL bot-side LLM dispatch tests is `bot._sentinel_client.post_to_module` (module-level client instantiated at import — per PATTERNS.md §10 Gotcha 1).

**The 7 tests** (names match 32-VALIDATION.md verbatim — numbered 1-7 linearly):

1. `test_pf_harvest_solo_dispatch` — HRV-01.
   ```python
   async def test_pf_harvest_solo_dispatch():
       mock_result = {
           "monsters": [{"monster": "Boar", "level": 2, "source": "seed", "verified": True, "components": [], "note": None}],
           "aggregated": [{"type": "Hide", "medicine_dc": 16, "craftable": [], "monsters": ["Boar"]}],
           "footer": "Source — FoundryVTT pf2e",
       }
       with patch.object(bot._sentinel_client, "post_to_module", new=AsyncMock(return_value=mock_result)) as mock_ptm:
           result = await bot._pf_dispatch("harvest Boar", "user123")
       mock_ptm.assert_called_once()
       assert mock_ptm.call_args[0][0] == "modules/pathfinder/harvest"
       payload = mock_ptm.call_args[0][1]
       assert payload["names"] == ["Boar"]
       assert payload["user_id"] == "user123"
   ```

2. `test_pf_harvest_batch_dispatch` — HRV-06. Input: `"harvest Boar,Wolf,Orc"`. Assert `payload["names"] == ["Boar", "Wolf", "Orc"]`.

3. `test_pf_harvest_multi_word_monster` — Pitfall 5. Input: `"harvest Giant Rat"`. Assert `payload["names"] == ["Giant Rat"]` (single name, space preserved — the comma-separated rule keeps the whole string as one name because no comma is present).

4. `test_pf_harvest_batch_trimmed_commas` — HRV-06, Pitfall 5. Input: `"harvest Boar , Wolf , Orc"` (whitespace around commas). Assert `payload["names"] == ["Boar", "Wolf", "Orc"]` (each trimmed).

5. `test_pf_harvest_empty_returns_usage` — HRV-01 usage. Input: `"harvest"` (no names). No `post_to_module` patch needed (it MUST NOT be called). Build the patch stub that would raise if called: `with patch.object(bot._sentinel_client, "post_to_module", new=AsyncMock(side_effect=AssertionError("should not call module")))`. Call `await bot._pf_dispatch("harvest", "user123")`. Assert the returned value is a string (not a dict) AND contains `"Usage"` AND contains `"harvest"`.

6. `test_pf_harvest_returns_embed_dict` — HRV-01/D-03a. mock_result as in test 1. Assert `result` is a dict with `result["type"] == "embed"`, `result["content"] == ""`, and `"embed" in result`. Do NOT introspect the embed value (per PATTERNS.md §10 Gotcha 2 — the discord stub makes `discord.Embed` unusable in tests).

7. `test_pf_harvest_noun_recognised` — noun widen regression guard. Input: `"harvest Boar"`. mock_result as test 1. Assert the returned value is NOT a string starting with `"Unknown pf category"` (per PATTERNS.md §10 Gotcha 3 — locks in the noun-widening).

**Stub contract**:
- Follow `test_pf_say_*` block style exactly.
- Use `patch.object(bot._sentinel_client, "post_to_module", new=AsyncMock(...))` not `patch("bot._sentinel_client...")` (per PATTERNS.md §10 Gotcha 1 — the module-level client attribute must be patched directly).
- `async def test_*` — no `@pytest.mark.asyncio`.
- `build_harvest_embed` will be referenced inside bot.py's dispatch return value; the test MUST NOT try to introspect the embed object because Phase 30/31 tests already demonstrate that the discord stub makes Embed unusable.

DO NOT add any production code to bot.py. Tests reference `bot._pf_dispatch` handling the `harvest` noun + `build_harvest_embed` which Wave 3 (Plan 32-05) will land — failures expected.
  </action>
  <acceptance_criteria>
    - `grep -cE '^async def test_pf_harvest_' interfaces/discord/tests/test_subcommands.py` → exactly 7
    - All 7 test names present (grep each): `test_pf_harvest_solo_dispatch`, `test_pf_harvest_batch_dispatch`, `test_pf_harvest_multi_word_monster`, `test_pf_harvest_batch_trimmed_commas`, `test_pf_harvest_empty_returns_usage`, `test_pf_harvest_returns_embed_dict`, `test_pf_harvest_noun_recognised`
    - `cd interfaces/discord && python -m pytest tests/test_subcommands.py -k 'harvest' --collect-only -q` → "7 tests collected"
    - `cd interfaces/discord && python -m pytest tests/test_subcommands.py -k 'harvest' -q` → exit code != 0 (RED)
    - Existing tests unchanged: `grep -c '^async def test_pf_say_solo_dispatch' interfaces/discord/tests/test_subcommands.py` → 1 (pre-Phase-31 test count preserved)
    - `grep -F "modules/pathfinder/harvest" interfaces/discord/tests/test_subcommands.py` matches at least once (in the solo dispatch assertion)
  </acceptance_criteria>
  <automated>cd interfaces/discord && python -m pytest tests/test_subcommands.py -k 'harvest' --collect-only -q</automated>
</task>

</tasks>

<verification>
Run the three collect-only commands and confirm 21 + 3 + 7 = 31 stubs collected:

```bash
cd modules/pathfinder && python -m pytest tests/test_harvest.py --collect-only -q
# Expected: "21 tests collected"

cd modules/pathfinder && python -m pytest tests/test_harvest_integration.py --collect-only -q
# Expected: "3 tests collected"

cd interfaces/discord && python -m pytest tests/test_subcommands.py -k 'harvest' --collect-only -q
# Expected: "7 tests collected"
```

RED proof — run each suite and confirm failures (NOT collection errors):
```bash
cd modules/pathfinder && python -m pytest tests/test_harvest.py -q
# Expected: 21 failed, 0 errors during collection. Exit code != 0.
```

After execution, update 32-VALIDATION.md frontmatter `wave_0_complete: true` (executor responsibility after Wave 0 merge-back).
</verification>

<success_criteria>
- 21 + 3 + 7 = 31 RED test stubs exist and collect cleanly across the 3 test files.
- Stubs reference symbols (`app.harvest.*`, `app.routes.harvest.*`, `app.llm.generate_harvest_fallback`, `bot.build_harvest_embed`) that Waves 1-3 will land.
- No production code modified in this plan.
- Each test has a clear assertion target — no `pass` stubs, no `assert True`.
- `STUB_HARVEST_TABLE_DATA`, `CACHED_HARVEST_MD`, `_make_stub_tables` fixtures present in test_harvest.py for use by downstream assertions.
- `StatefulMockVault` present verbatim in test_harvest_integration.py for round-trip observation.
- AI Deferral Ban: zero TODO/FIXME/NotImplementedError/pass-as-body introduced in any test stub.
</success_criteria>

<output>
Create `.planning/phases/32-monster-harvesting/32-01-SUMMARY.md` documenting:
- Test file paths + test count per file (21 / 3 / 7)
- Verification commands run + their output
- Confirmation that all 31 tests are RED (failing for the expected reason: missing implementation symbols + rapidfuzz not yet installed)
- Note: Wave 0 complete; Waves 1-3 implement against this contract. The `test_rapidfuzz_importable` smoke test flips GREEN as soon as Plan 32-02 adds the dep + uv sync runs.
- Worktree reminder: if executed in a parallel worktree, commit with `--no-verify` per CLAUDE.md + Phase 31 31-01-SUMMARY convention; orchestrator merge-back runs the formatter once.
</output>
</output>
