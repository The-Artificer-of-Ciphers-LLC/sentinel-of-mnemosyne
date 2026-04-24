# Phase 32: Monster Harvesting — Pattern Map

**Mapped:** 2026-04-23
**Files analyzed:** 8 (7 NEW, 1 EXTEND — plus 4 touches for registration/deps)
**Analogs found:** 8 / 8 — every new/extended file has a strong in-repo analog. One file (`data/harvest-tables.yaml`) is greenfield for **file type** but its loader pattern is prescribed.

All excerpts below are verbatim from the cited files. Line ranges checked in full. Paste them into the implementation files and rename identifiers; do NOT reinvent the shape.

---

## File Classification

| File | New/Extend | Role | Data Flow | Closest Analog | Match Quality |
|------|-----------|------|-----------|----------------|---------------|
| `modules/pathfinder/data/harvest-tables.yaml` | NEW (greenfield type) | data / config | batch read-at-startup | pyproject.toml / RESEARCH.md Example 1 (no in-repo YAML data file) | greenfield — shape prescribed by RESEARCH.md YAML Loader section |
| `modules/pathfinder/app/harvest.py` | NEW | helper module (YAML loader + fuzzy match + pure transforms) | transform | `modules/pathfinder/app/dialogue.py` (module shape) + `_parse_frontmatter` style | exact (module shape) + role-match (helpers) |
| `modules/pathfinder/app/routes/harvest.py` (or `say_npc` siblings in npc.py) | NEW | controller (route + Pydantic models + build_harvest_markdown + LLM fallback dispatch) | request-response + cache-aside | `say_npc` in `routes/npc.py:858-983` + NPC Pydantic models `routes/npc.py:110-205` | exact |
| `modules/pathfinder/app/llm.py` | EXTEND | LLM wrapper (add `generate_harvest_fallback`) | request-response | `extract_npc_fields` (SAME FILE, lines 33-73) — JSON-contract shape | exact |
| `modules/pathfinder/app/main.py` | EXTEND | registration config (13th route) + lifespan hook for harvest_tables | config | `REGISTRATION_PAYLOAD` (SAME FILE, lines 48-65) + lifespan assigns `_npc_module.obsidian` (lines 93-113) | exact |
| `modules/pathfinder/pyproject.toml` | EXTEND | deps (add `rapidfuzz>=3.14.0`) | config | `dependencies = [...]` (SAME FILE, lines 5-13) | exact |
| `modules/pathfinder/tests/test_harvest.py` | NEW | unit tests (request mocks; fuzzy unit tests; format_price unit tests) | request-response | `test_npc.py` lines 1-39 (env + mock-obsidian) + lines 333-345 (happy path) | exact |
| `modules/pathfinder/tests/test_harvest_integration.py` | NEW | integration tests (stateful vault mock; cache hit/miss round-trip) | request-response | `test_npc_say_integration.py` (whole file) — especially `StatefulMockVault` lines 45-62 | exact |
| `interfaces/discord/tests/test_subcommands.py` | EXTEND | unit tests (append `test_pf_harvest_*`) | request-response | `test_pf_say_*` block (SAME FILE, lines 301-355) | exact |
| `interfaces/discord/bot.py` | EXTEND | controller (add `harvest` noun + `build_harvest_embed` + `_render_harvest_response` helpers) | request-response | `stat` branch lines 516-528 + `build_stat_embed` lines 272-314 + `say` branch lines 545-587 | exact |
| `modules/pathfinder/scripts/scaffold_harvest_seed.py` (optional) | NEW (optional) | one-shot scrape-and-print script | batch | No in-repo precedent; recommend stdlib `urllib.request` or `httpx.Client` sync | no-analog — see §7 |

---

## Pattern Assignments

### 1. `modules/pathfinder/data/harvest-tables.yaml` (NEW — greenfield data file)

**No in-repo analog for file type.** There is no existing YAML data file in the repo — `pyproject.toml` is TOML, tests use inline triple-string YAML fixtures.

**Prescribed shape** — RESEARCH.md §Code Examples Example 1, §YAML Loader, §DC-by-Level Table.

**Reuse:**
- Header comment block mirroring Python module docstrings at `app/llm.py:1-5` (ORC-license attribution required by D-01 reshape: `# Derived from Foundry VTT pf2e system — ORC license, see github.com/foundryvtt/pf2e`).
- Top-level keys from RESEARCH.md YAML Loader: `version: str`, `source: str`, `levels: list[int]`, `monsters: list[MonsterEntry]`.
- Per-monster shape: `name`, `level`, `traits: list[str]`, `components: list[HarvestComponent]` where each has `name`, `medicine_dc`, `craftable: list[CraftableItem]`.
- DC values come from RESEARCH.md §DC-by-Level Table (level 1 → 15, level 2 → 16, level 3 → 18). Crafting DC uses **item level** not monster level.

**Diverge:**
- No existing file to diverge from. Planner must pick realistic craftable items per component; use the "Sample craftable vendor values" list in RESEARCH.md §LLM fallback prompt (Pattern 2) as canonical pricing source.
- The optional `scaffold_harvest_seed.py` script (see §7) scrapes Foundry pf2e pack to pre-populate `name` + `level`. DM hand-fills `components`.

**Gotcha:** The YAML is read once at lifespan startup (§5). Malformed YAML MUST fail-fast (ValidationError surfaces to logs; Docker restart policy applies). Do NOT catch `yaml.YAMLError` at startup — let it propagate.

---

### 2. `modules/pathfinder/app/harvest.py` (NEW — helper module)

**Analog A — module shape / imports:** `modules/pathfinder/app/dialogue.py:1-22`

```python
"""Dialogue helpers for pathfinder module — prompt construction + mood math.

Pure-transform module: no LLM calls (those live in app.llm.generate_npc_reply),
no Obsidian I/O (those live in app.routes.npc), no FastAPI dependencies.
Only stdlib + tiktoken (already transitive via litellm) + logging.

Owns:
- MOOD_ORDER: 5-state ordered spectrum (D-06)
- MOOD_TONE_GUIDANCE: per-mood system-prompt fragments (D-08, RESEARCH Finding 5)
- normalize_mood / apply_mood_delta: state-machine math (D-07)
- build_system_prompt / build_user_prompt: per-NPC prompt assembly (D-21, D-22, RESEARCH Finding 4)
- cap_history_turns: history budget enforcement (D-14, RESEARCH Finding 3)

Per CLAUDE.md AI Deferral Ban: every helper completes its job; no deferral markers.
"""

import logging

import tiktoken

logger = logging.getLogger(__name__)
```

**Copy for `harvest.py`:**
- Same module-docstring style. Enumerate what the module owns: `Pydantic schema models (HarvestTable/MonsterEntry/HarvestComponent/CraftableItem)`, `normalize_name`, `lookup_seed` (fuzzy), `format_price`, `build_harvest_markdown`, `_aggregate_by_component`, `load_harvest_tables`.
- Imports: `import logging`, `from pathlib import Path`, `import yaml`, `from pydantic import BaseModel`, `from rapidfuzz import process, fuzz`, `import datetime`.
- Do NOT import `litellm`, `httpx`, or anything from `app.routes.*` — keep the layer pure (dialogue.py's discipline). LLM fallback lives in `app.llm`; Obsidian I/O in the route handler.

**Analog B — module-scope constant hoist (idiomatic for call-path frequent use):** `modules/pathfinder/app/dialogue.py:56-62`

```python
HISTORY_MAX_TURNS: int = 10
HISTORY_MAX_TOKENS: int = 2000

# Module-scope tiktoken encoder (IN-01): get_encoding is internally cached by
# tiktoken but hoisting matches the idiomatic pattern used in
# sentinel-core/app/services/token_guard.py and avoids a lookup on every call.
_ENC = tiktoken.get_encoding("cl100k_base")
```

**Copy for `harvest.py`:**
```python
FUZZY_SCORE_CUTOFF: float = 85.0          # RESEARCH.md §Fuzzy-Match Recommendation
HARVEST_CACHE_PATH_PREFIX: str = "mnemosyne/pf2e/harvest"  # D-03b
DC_BY_LEVEL: dict[int, int] = {0: 14, 1: 15, 2: 16, 3: 18, 4: 19, ...}  # RESEARCH.md §DC-by-Level Table
MAX_BATCH_NAMES: int = 20                  # RESEARCH.md §Security Domain (DoS cap)
```

**Analog C — helper function style (pure, log-and-fall-back on bad input):** `routes/npc.py:220-237`

```python
def _parse_frontmatter(note_text: str) -> dict:
    """Parse YAML frontmatter from a note string delimited by '---'.

    Returns empty dict if frontmatter cannot be parsed.
    Safe to call on machine-generated notes (Sentinel always writes valid YAML).
    """
    try:
        if not note_text.startswith("---"):
            return {}
        end = note_text.find("---", 3)
        if end == -1:
            return {}
        frontmatter_text = note_text[3:end].strip()
        return yaml.safe_load(frontmatter_text) or {}
    except Exception as exc:
        logger.warning("Frontmatter parse failed: %s", exc)
        return {}
```

**Copy for `harvest.py` — `_parse_harvest_cache(note_text, name)`:** same log-and-degrade shape. On malformed cache note, return `None` (cache miss), do NOT raise. The route handler treats `None` identically to "no cache file".

**Analog D — slugify (REUSE, do not reimplement):** `routes/npc.py:210-217`

```python
def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
```

**Reuse:** `from app.routes.npc import slugify` in `harvest.py`. Do NOT reimplement. This is documented in RESEARCH.md §Don't Hand-Roll.

**Gotcha 1 — circular import:** `harvest.py` importing `slugify` from `app.routes.npc` is fine because `routes/npc.py` does not import `harvest.py`. But `routes/harvest.py` MUST NOT have `app.harvest` or `app.routes.npc` both importing from each other. Keep all pure helpers in `app.harvest`; keep route-only code (HTTPException, obsidian, resolve_model) in `app.routes.harvest`.

**Gotcha 2 — format_price mixed currency:** RESEARCH.md Pitfall 3. The helper MUST handle `{"gp": 2, "sp": 5}` (concatenated: "2 gp 5 sp") and `{}` (empty → "0 cp"). Unit-test every branch.

**Gotcha 3 — lookup_seed tuple return:** RESEARCH.md Example 4 — return `(entry, note) | (None, None)`. The route handler checks `seed_hit is not None`, not `seed_hit == {}`. Never return a sentinel empty dict.

---

### 3. `modules/pathfinder/app/routes/harvest.py` (NEW — route + models)

**Analog A — Pydantic request model with per-element name validator:** `routes/npc.py:162-185`

```python
class NPCSayRequest(BaseModel):
    """Request shape for POST /npc/say (D-24).

    party_line == "" is the SCENE ADVANCE signal (D-02).
    history is bot-assembled from Discord thread (D-11..D-14); empty when first turn.
    """
    names: list[str]
    party_line: str = ""
    history: list[TurnHistory] = Field(default_factory=list)
    user_id: str

    @field_validator("names")
    @classmethod
    def sanitize_names(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("at least one NPC name required")
        return [_validate_npc_name(n) for n in v]

    @field_validator("party_line")
    @classmethod
    def check_party_length(cls, v: str) -> str:
        if len(v) > 2000:
            raise ValueError("party_line too long (max 2000 chars)")
        return v
```

**Copy for Phase 32 — 4 Pydantic models** (shape in RESEARCH.md §Pattern 1):

```python
class HarvestRequest(BaseModel):
    names: list[str]
    user_id: str = ""

    @field_validator("names")
    @classmethod
    def sanitize_names(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("at least one monster name required")
        if len(v) > MAX_BATCH_NAMES:
            raise ValueError(f"too many monsters (max {MAX_BATCH_NAMES})")
        return [_validate_monster_name(n) for n in v]


class CraftableOut(BaseModel):
    name: str
    crafting_dc: int
    value: str                    # "2 gp" | "5 sp" | "3 cp" | "2 gp 5 sp"


class ComponentOut(BaseModel):
    type: str                     # "Hide", "Claws", "Venom gland"
    medicine_dc: int
    craftable: list[CraftableOut]
    monsters: list[str]           # D-04 aggregation: which monsters produced this


class MonsterHarvestOut(BaseModel):
    monster: str
    level: int
    source: str                   # "seed" | "seed-fuzzy" | "llm-generated" | "cache"
    verified: bool
    components: list[dict]
    note: str | None = None       # fuzzy-match note or generated warning
```

Reuse `_validate_npc_name` pattern but rename to `_validate_monster_name` (same body). The `names`-list validator pattern is identical to Phase 31 NPCSayRequest.

**Analog B — route handler shape (module-level `obsidian` singleton + fail-fast + cache-aside + put_note degrade):** `routes/npc.py:858-983` (the `say_npc` handler — read the full 125-line body once; do not reinvent).

Key sub-patterns to mirror line-by-line:

| Phase 31 `say_npc` line | Phase 32 `harvest` equivalent |
|-------------------------|-------------------------------|
| `for name in req.names: … path = f"{_NPC_PATH_PREFIX}/{slug}.md"` (871-887) | `for name in req.names: … cache_path = f"{HARVEST_CACHE_PATH_PREFIX}/{slug}.md"` |
| `note_text = await obsidian.get_note(path)` (873) | `cached_text = await obsidian.get_note(cache_path)` — cache-hit returns immediately |
| `if note_text is None: raise HTTPException(404, …)` (874-878) | NO 404 — cache miss triggers seed lookup + LLM fallback |
| `await generate_npc_reply(system_prompt=..., model=model, api_base=api_base)` (927-932) | `await generate_harvest_fallback(monster_name=name, model=..., api_base=...)` |
| `await obsidian.put_note(npc["path"], new_content)` (954) | `await obsidian.put_note(cache_path, build_harvest_markdown(result))` |
| `except Exception as exc: logger.error(...); new_mood = current_mood` (965-968) — degrade pattern | Same degrade: log WARNING, skip cache write, still return result (D-03b graceful degradation) |

**Analog C — route handler with 404 fail-fast + LLM exception wrap + Obsidian put_note with 503 on raise:** `create_npc` `routes/npc.py:344-395`

```python
@router.post("/create")
async def create_npc(req: NPCCreateRequest) -> JSONResponse:
    slug = slugify(req.name)
    path = f"{_NPC_PATH_PREFIX}/{slug}.md"

    # Collision check — D-19: return 409 with existing path, never silently overwrite
    existing = await obsidian.get_note(path)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": "NPC already exists", "path": path},
        )

    # LLM field extraction — D-06, D-07
    try:
        fields = await extract_npc_fields(
            name=req.name,
            description=req.description,
            model=await resolve_model("structured"),
            api_base=settings.litellm_api_base or None,
        )
    except Exception as exc:
        logger.error("LLM extraction failed for NPC %s: %s", req.name, exc)
        raise HTTPException(status_code=500, detail={"error": "LLM extraction failed", "detail": str(exc)})
    ...
```

**Copy for `harvest` handler:**
- Wrap `generate_harvest_fallback` in `try/except` → `HTTPException(500, detail={"error": "LLM fallback failed", "detail": str(exc)})`. Per RESEARCH.md §Anti-Patterns: "Writing the cache on LLM failure" — if LLM raises, return 500 WITHOUT writing the cache. Next call retries.
- `await resolve_model("chat")` — RESEARCH.md §Pattern 2 does not specify, but chat tier is the right fit (freeform generation, not structured JSON-extraction). Planner may choose `"structured"` if LLM reliability is shaky; justify in the plan.
- Use `JSONResponse({...})` return shape — no `response_model=`, consistent with every sibling route.

**Analog D — module-level singletons assigned by lifespan:** `routes/npc.py:48-50`

```python
# Module-level ObsidianClient instance — set by main.py lifespan, patchable in tests.
obsidian = None
```

**Copy for `routes/harvest.py`:**
```python
obsidian = None                    # type: ObsidianClient | None  — set by lifespan
harvest_tables = None              # type: HarvestTable | None   — set by lifespan
```

Both are patched in tests via `patch("app.routes.harvest.obsidian", mock_obs)` and `patch("app.routes.harvest.harvest_tables", stub_tables)`.

**Gotcha 1 — slugify reuse:** import from `app.routes.npc` rather than redefining. `from app.routes.npc import slugify`.

**Gotcha 2 — aggregator lives in the route handler OR in `harvest.py`:** RESEARCH.md §Code Examples Example 2 shows `_aggregate_by_component` as a pure function. Recommend placing it in `app.harvest` (pure transform; unit-testable without FastAPI). The route calls it between the cache-resolve loop and the `JSONResponse` return. Phase 31 equivalent: `_render_say_response` lives in `bot.py` (not in the route) because it's bot-layer presentation; for harvest, aggregation is server-layer data shape because the bot layer renders the embed from the aggregated structure.

**Gotcha 3 — build_harvest_markdown placement:** Put it in `app.harvest` (pure transform of dict → string). The route calls it just before `put_note`. Phase 31's `build_npc_markdown` (at `routes/npc.py:256-269`) is in the route file but only because Phase 29 started that way — for Phase 32, place it in `app.harvest` for test isolation (Phase 31 SUMMARY notes the test seam quality of pure helpers).

---

### 4. `modules/pathfinder/app/llm.py` — ADD `generate_harvest_fallback()`

**Analog (SAME FILE):** `extract_npc_fields` lines 33-73.

```python
async def extract_npc_fields(
    name: str,
    description: str,
    model: str,
    api_base: str | None = None,
) -> dict:
    system_prompt = (
        "You are a Pathfinder 2e Remaster NPC generator. "
        "Extract or infer NPC fields from the user description. "
        "Return ONLY a JSON object — no markdown, no explanation — with these exact keys: "
        "name (string), level (integer, default 1 if unspecified), ..."
        "Return nothing except the JSON object."
    )
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Name: {name}\nDescription: {description}"},
        ],
        "timeout": 60.0,
    }
    if api_base:
        kwargs["api_base"] = api_base

    response = await litellm.acompletion(**kwargs)
    content = response.choices[0].message.content
    return json.loads(_strip_code_fences(content))
```

**Copy for `generate_harvest_fallback` — shape rules (all enforced):**
1. Signature: `async def generate_harvest_fallback(monster_name: str, model: str, api_base: str | None = None) -> dict:`.
2. `kwargs: dict = {...}` + conditional `if api_base: kwargs["api_base"] = api_base` — same as every sibling in `llm.py` (Pattern S2, below).
3. `"timeout": 60.0` — matches `extract_npc_fields` and `update_npc_fields`. No `max_tokens` (default is generous).
4. `_strip_code_fences(content)` before `json.loads` — SAME FILE lines 21-30.
5. **System prompt scaffold:** verbatim text from RESEARCH.md §Pattern 2 (lines 519-571 of 32-RESEARCH.md). Embed the DC-by-level table (level 0 → DC 14 through level 10 → DC 27) and the sample craftable vendor values. JSON-object contract must list every required key.
6. **After parse, stamp `parsed["source"] = "llm-generated"` and `parsed["verified"] = False`** before returning. RESEARCH.md Pattern 2 lines 568-570.
7. **DC sanity clamp:** RESEARCH.md Pitfall 4. After LLM returns, for each component, recompute expected DC = `DC_BY_LEVEL[parsed["level"]]`. If the LLM's `medicine_dc` differs, log WARNING, overwrite with `DC_BY_LEVEL[level]`. Trust the table, not the LLM. (Plan this as a post-parse coercion step, not in the prompt.)

**Do NOT copy `generate_npc_reply`'s salvage path.** For `generate_harvest_fallback`, a JSON parse failure is a hard 500 — the route handler must not cache a partial result. This matches `extract_npc_fields` (raises) not `generate_npc_reply` (salvages). Rationale: dialogue tolerates prose fallback; harvest data tolerates none.

**Gotcha:** `_strip_code_fences` (lines 21-30) strips ` ```json ` and bare ` ``` ` only. Known limitation from Phase 31. If the LLM wraps in ` ```yaml ` (possible for DC tables), the JSON parse fails → the route returns 500. Acceptable for v1; document in the plan.

---

### 5. `modules/pathfinder/app/main.py` — EXTEND lifespan + registry

**Analog A — REGISTRATION_PAYLOAD (SAME FILE):** lines 48-65.

```python
REGISTRATION_PAYLOAD = {
    "name": "pathfinder",
    "base_url": "http://pf2e-module:8000",
    "routes": [
        {"path": "healthz", "description": "pf2e module health check"},
        {"path": "npc/create", "description": "Create NPC in Obsidian (NPC-01)"},
        ...
        {"path": "npc/say", "description": "In-character NPC dialogue with mood tracking (DLG-01..03)"},
    ],
}
```

**Copy for Phase 32 — append one line after the `npc/say` entry:**

```python
{"path": "harvest", "description": "Monster harvest report with Medicine/Crafting DCs and vendor values (HRV-01..06)"},
```

Description wording cites HRV IDs. If the planner prefers the proxy path `modules/pathfinder/harvest` to route bot-side, the `path` here must stay as `harvest` (sentinel-core's module proxy prepends `modules/{name}/`).

**Also update the module docstring at lines 4-17** — append one line after the `/npc/say` entry on line 16:

```
  POST /harvest            — monster harvest report with DC + vendor values (HRV-01..06)
```

**Analog B — lifespan assigns module-level singletons (SAME FILE):** lines 93-113.

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: register with Sentinel Core + create persistent ObsidianClient."""
    async with httpx.AsyncClient() as client:
        await _register_with_retry(client)

    async with httpx.AsyncClient() as obsidian_http_client:
        obsidian_client = ObsidianClient(
            http_client=obsidian_http_client,
            base_url=settings.obsidian_base_url,
            api_key=settings.obsidian_api_key,
        )
        app.state.obsidian_client = obsidian_client
        _npc_module.obsidian = obsidian_client
        yield
    _npc_module.obsidian = None
```

**Copy for Phase 32:**
- `import app.routes.harvest as _harvest_module` at top of main.py (alongside `import app.routes.npc as _npc_module` line 39).
- In lifespan, before `yield`:
  ```python
  _harvest_module.obsidian = obsidian_client
  _harvest_module.harvest_tables = load_harvest_tables(
      Path(__file__).parent.parent / "data" / "harvest-tables.yaml"
  )
  ```
- After `yield`: `_harvest_module.obsidian = None` and `_harvest_module.harvest_tables = None`.
- `app.include_router(harvest_router)` after the existing `app.include_router(npc_router)` line 123.

**Gotcha 1 (Pitfall 7 from Phase 28, reinforced in Phase 31 31-04-SUMMARY):** All routes MUST appear in `REGISTRATION_PAYLOAD` at module import time. Missing the registry entry means sentinel-core's `/modules/pathfinder/harvest` proxy returns 404. The plan's "done" checklist MUST verify this line.

**Gotcha 2 — path resolution:** `Path(__file__).parent.parent / "data" / ...` resolves relative to `modules/pathfinder/app/main.py` (so → `modules/pathfinder/data/harvest-tables.yaml`). Verify with `assert (path).exists()` at startup; SystemExit(1) if missing.

**Gotcha 3 — test patching target:** Tests patch `app.routes.harvest.harvest_tables` directly (module-level var) rather than `app.state.harvest_tables`. Mirror the `_npc_module.obsidian` pattern exactly — the route handler dereferences the module-level name, not `app.state`.

---

### 6. `modules/pathfinder/pyproject.toml` — ADD `rapidfuzz>=3.14.0`

**Analog (SAME FILE):** `dependencies = [...]` lines 5-13.

```toml
[project]
name = "pf2e-module"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.135.0",
    "uvicorn[standard]>=0.44.0",
    "httpx>=0.28.1",
    "litellm>=1.83.0",
    "pydantic-settings>=2.13.0",
    "pyyaml>=6.0.0",
    "reportlab>=4.4.0",
]
```

**Copy:** insert `"rapidfuzz>=3.14.0",` keeping alphabetical ordering (between `pyyaml` and `reportlab`):

```toml
    "pyyaml>=6.0.0",
    "rapidfuzz>=3.14.0",
    "reportlab>=4.4.0",
```

**Post-edit step:** run `cd modules/pathfinder && uv lock && uv sync` (RESEARCH.md §Standard Stack installation step). Rebuild the pf2e-module Docker container so the new wheel is installed.

**Verifier:** `python -c "import rapidfuzz; print(rapidfuzz.__version__)"` must succeed inside the container. Recommend adding this as a smoke test at the top of `test_harvest.py`:

```python
def test_rapidfuzz_importable():
    """Smoke test — rapidfuzz wheel installed in the container."""
    import rapidfuzz
    assert rapidfuzz.__version__ >= "3.14.0"
```

---

### 7. `modules/pathfinder/tests/test_harvest.py` (NEW — unit tests)

**Analog A — env bootstrap + imports:** `test_npc.py:1-12` (reproduced via `test_npc_say_integration.py:1-19`).

```python
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
```

**Copy verbatim** at the top of `test_harvest.py`. Env defaults MUST come before any `from app.*` import.

**Analog B — happy-path route test:** `test_npc.py:20-39` (`test_npc_create_success`).

```python
async def test_npc_create_success():
    """POST /npc/create returns 200 + slug when NPC does not exist (NPC-01)."""
    mock_obs = MagicMock()
    mock_obs.get_note = AsyncMock(return_value=None)
    mock_obs.put_note = AsyncMock(return_value=None)
    extracted = {...}
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", mock_obs), \
         patch("app.routes.npc.extract_npc_fields", new=AsyncMock(return_value=extracted)):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/create", json={...})
    assert resp.status_code == 200
    assert resp.json()["slug"] == "varek"
```

**Copy for Phase 32 — 12+ tests** (from RESEARCH.md §Validation Architecture — Phase Requirements → Test Map):

| # | Test name | Setup | Assert |
|---|-----------|-------|--------|
| 1 | `test_harvest_single_seed_hit` | Stub `harvest_tables` with Boar entry; `get_note` → None (cache miss) | 200; `monsters[0]["source"] == "seed"`; ≥1 component with `medicine_dc` |
| 2 | `test_harvest_components_have_craftable` | same | each component has `craftable` list with `name`, `crafting_dc`, `value` (HRV-02, HRV-05) |
| 3 | `test_harvest_medicine_dc_present` | same | every component has integer `medicine_dc` (HRV-04) |
| 4 | `test_harvest_batch_aggregated` | stub with Boar + Wolf (both have "Hide" component); `get_note` → None × 2 | `aggregated` has one "Hide" field with `monsters == ["Boar","Wolf"]` (HRV-06, D-04) |
| 5 | `test_harvest_fuzzy_match_returns_note` | stub with "Wolf" seed; query "Alpha Wolf" | 200; `monsters[0]["source"] == "seed-fuzzy"`, `note` contains "Matched to closest" |
| 6 | `test_harvest_fuzzy_below_threshold_falls_to_llm` | stub with "Wolf"; query "Wolf Lord" | `generate_harvest_fallback` called; `source == "llm-generated"` |
| 7 | `test_harvest_llm_fallback_marks_generated` | no seed match; patch `generate_harvest_fallback` → `{monster: ..., verified: false}` | `monsters[0]["verified"] is False`; footer contains "generated" |
| 8 | `test_harvest_cache_hit_skips_llm` | `get_note` → cached markdown with frontmatter `verified: true`; LLM mock | 200; `generate_harvest_fallback` NOT called; `monsters[0]["source"] == "cache"` |
| 9 | `test_harvest_cache_write_on_miss` | seed hit; `put_note` spy | `put_note.await_count == 1`; path starts with `mnemosyne/pf2e/harvest/` |
| 10 | `test_harvest_cache_write_failure_degrades` | seed hit; `put_note` raises | 200 returned; result present; WARNING logged (inspect `caplog`) |
| 11 | `test_harvest_empty_names_422` | POST `{"names": []}` | 422 (Pydantic validator) |
| 12 | `test_harvest_invalid_name_control_char` | POST with `\x00` in name | 422 |
| 13 | `test_harvest_batch_cap_enforced` | POST with 21 names | 422 (MAX_BATCH_NAMES DoS cap) |
| 14 | `test_format_price_single_denom` | `format_price({"gp": 2})` | `"2 gp"` |
| 15 | `test_format_price_mixed_currency` | `format_price({"gp": 2, "sp": 5})` | `"2 gp 5 sp"` (Pitfall 3) |
| 16 | `test_format_price_empty_dict` | `format_price({})` | `"0 cp"` |
| 17 | `test_fuzzy_subset_matches` | `lookup_seed("alpha wolf", tables)` | returns Wolf + non-None note |
| 18 | `test_fuzzy_wolf_lord_falls_through` | `lookup_seed("wolf lord", tables)` | returns `(None, None)` |
| 19 | `test_fuzzy_hobgoblin_falls_through` | `lookup_seed("hobgoblin", tables_with_goblin)` | returns `(None, None)` (Pitfall 2) |
| 20 | `test_invalid_yaml_raises` | `load_harvest_tables(Path(tmp_yaml_bad))` | raises `pydantic.ValidationError` (RESEARCH.md §YAML Loader) |

**Analog C — `side_effect` for sequential calls** (needed for batch tests): `test_npc.py:243` (`test_npc_import_collision_skipped`):

```python
mock_obs.get_note = AsyncMock(side_effect=[note1, note2, ...])
```

**Gotcha 1 — lifespan-safe import ordering (Phase 31 Pattern S6):**
The `from app.main import app` line MUST be inside the `with patch(...)` block. `_register_with_retry` MUST be patched so the real registration POST to sentinel-core does not hang.

**Gotcha 2 — pytest-asyncio mode:** `pyproject.toml` has `asyncio_mode = "auto"` (line 23). Do NOT decorate tests with `@pytest.mark.asyncio`. `async def test_*` is enough.

**Gotcha 3 — `harvest_tables` patch target:** stub a minimal `HarvestTable` via `HarvestTable.model_validate({...})` or a fixture object. Patch `"app.routes.harvest.harvest_tables"` (the module-level name), never `app.state.harvest_tables`.

---

### 8. `modules/pathfinder/tests/test_harvest_integration.py` (NEW — round-trip tests)

**Analog:** `test_npc_say_integration.py` — the whole file, especially `StatefulMockVault` lines 45-62.

```python
class StatefulMockVault:
    """In-memory vault mock — get_note returns the last put_note content for each path.

    Allows integration tests to observe the full round-trip: POST → mood write →
    subsequent POST reads the updated state.
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

**Copy verbatim** — rename the fixture constants but the class stays identical. Harvest integration tests care about the same round-trip: first POST writes the cache; second POST reads the cache and skips the LLM.

**Required integration tests (at least 3):**

| # | Test name | Flow | Assert |
|---|-----------|------|--------|
| 1 | `test_first_query_writes_cache_second_reads_cache` | Vault empty; `generate_harvest_fallback` mocked. POST twice with same name. | Turn 1: `put_note` called once, `source == "llm-generated"`. Turn 2: `put_note` NOT called, LLM NOT called, response identical, `source == "cache"`. |
| 2 | `test_seed_hit_writes_cache_with_source_seed` | Vault empty; seed table has Boar entry. POST once. | `put_note` called with markdown containing `source: seed` in frontmatter; response `source == "seed"`. |
| 3 | `test_batch_mixed_sources_footer` | Vault empty; seed has Wolf; query `["Wolf", "Unicorn"]` (Unicorn → LLM). | Footer contains "Mixed sources — 1 seed / 1 generated" (D-04); `aggregated` has both monsters' components. |

**Gotcha 1 — stateful mock paths:** Harvest cache paths are `mnemosyne/pf2e/harvest/<slug>.md`, NOT `mnemosyne/pf2e/npcs/<slug>.md`. Fixture path strings must reflect this.

**Gotcha 2 — source field parsing:** Turn 2 reads the cache markdown, parses frontmatter, and the `source` field in the response should reflect the cache origin (`"cache"`) rather than the original `"seed"`/`"llm-generated"`. The DM distinguishes "this was a cache hit" from "this was a fresh seed lookup". Or alternatively, preserve the original source from frontmatter — planner decides. Recommend: return the original source from frontmatter; distinguish cache-hit via a separate `cached: bool` field. Document the choice in the plan.

---

### 9. `interfaces/discord/bot.py` — ADD `harvest` noun + `build_harvest_embed` + `_render_harvest_response`

**Analog A — verb branch (single-argument with embed return):** `stat` branch lines 516-528 (SAME FILE).

```python
elif verb == "stat":
    npc_name = rest.strip()
    if not npc_name:
        return "Usage: `:pf npc stat <name>`"
    result = await _sentinel_client.post_to_module(
        "modules/pathfinder/npc/stat", {"name": npc_name}, http_client
    )
    embed = build_stat_embed(result)
    return {
        "type": "embed",
        "content": "",
        "embed": embed,
    }
```

**Analog B — batch/pipe parsing:** `say` branch lines 545-587 (SAME FILE).

```python
elif verb == "say":
    if "|" not in rest:
        return "Usage: `:pf npc say <Name>[,<Name>...] | <party line>`"
    names_raw, _, party_line = rest.partition("|")
    names = [n.strip() for n in names_raw.split(",") if n.strip()]
    if not names:
        return "Usage: `:pf npc say <Name>[,<Name>...] | <party line>`"
    ...
    payload = {
        "names": names,
        "party_line": party_line.strip(),
        "user_id": user_id,
        "history": history,
    }
    result = await _sentinel_client.post_to_module(
        "modules/pathfinder/npc/say", payload, http_client
    )
    return _render_say_response(result)
```

**Copy for `harvest` verb** — harvest is simpler than `say` (no pipe; no history walk):

```python
# Noun dispatcher widens at line 344-345 — change from:
if noun != "npc":
    return f"Unknown pf category `{noun}`. Currently supported: `npc`."
# to:
if noun not in {"npc", "harvest"}:
    return f"Unknown pf category `{noun}`. Currently supported: `npc`, `harvest`."

# Then at the top-level dispatch (after the `if noun == "npc":` block), add:
if noun == "harvest":
    # Format: `:pf harvest <Name>[,<Name>...]` — comma-separated batch (D-04, Pitfall 5).
    # verb slot holds the FIRST monster name when `noun = "harvest"`; reassemble.
    raw = (verb + " " + rest).strip() if rest else verb
    names = [n.strip() for n in raw.split(",") if n.strip()]
    if not names:
        return "Usage: `:pf harvest <Name>[,<Name>...]`"
    result = await _sentinel_client.post_to_module(
        "modules/pathfinder/harvest",
        {"names": names, "user_id": user_id},
        http_client,
    )
    return {
        "type": "embed",
        "content": "",
        "embed": build_harvest_embed(result),
    }
```

**Note on noun/verb parsing:** The existing `_pf_dispatch` at line 338 splits args into `parts[0]=noun`, `parts[1]=verb`, `parts[2]=rest`. For `:pf harvest Goblin`, `noun="harvest"`, `verb="Goblin"`, `rest=""`. For `:pf harvest Goblin,Wolf`, `noun="harvest"`, `verb="Goblin,Wolf"`, `rest=""`. For `:pf harvest Giant Rat`, `noun="harvest"`, `verb="Giant"`, `rest="Rat"`. Reassemble as shown above (`raw = verb + " " + rest`).

**Consider alternative parsing:** the planner may prefer to bypass the noun/verb split when `noun="harvest"` by re-parsing from `args`:
```python
if noun == "harvest":
    # Skip the noun/verb model; harvest has no verbs, just monster names.
    harvest_args = args[len("harvest"):].strip()
    names = [n.strip() for n in harvest_args.split(",") if n.strip()]
```
This is cleaner but requires storing `args` as a local before the strip/split. Planner picks.

**Analog C — embed builder:** `build_stat_embed` lines 272-314 (SAME FILE).

```python
def build_stat_embed(data: dict) -> "discord.Embed":
    fields = data.get("fields", {})
    stats = data.get("stats") or {}
    embed = discord.Embed(
        title=(
            f"{fields.get('name', '?')} "
            f"(Level {fields.get('level', '?')} "
            f"{fields.get('ancestry', '')} {fields.get('class', '')})"
        ),
        description=fields.get("personality", ""),
        color=discord.Color.dark_gold(),
    )
    if stats:
        embed.add_field(name="AC", value=str(stats.get("ac", "—")), inline=True)
        ...
    embed.set_footer(text=f"Mood: {fields.get('mood', 'neutral')}")
    return embed
```

**Copy for `build_harvest_embed`** — full shape in RESEARCH.md §Pattern 3 lines 579-628. Key structural rules to preserve:
- Pure function, dict → `discord.Embed`, no I/O.
- Fallback for absent optional fields (`data.get("monsters", [])`).
- Single-monster: title = `"{monster} (Level {level})"`; description = note/warning if present.
- Batch: title = `"Harvest report — N monsters"`; description = aggregate warning.
- Loop over `aggregated`, add one field per component type with Medicine DC + monsters tally + craftable bullets. Value truncated to 1024 chars (Discord field cap).
- `embed.set_footer(text=footer_text)` — source attribution.

**Analog D — `_render_say_response` fallback helper for text-only clients:** `bot.py:194-208`.

```python
def _render_say_response(result: dict) -> str:
    replies = result.get("replies") or []
    warning = result.get("warning")
    lines: list[str] = []
    if warning:
        lines.append(warning)
        lines.append("")
    for r in replies:
        lines.append(f"> {r.get('reply', '')}")
    return "\n".join(lines) if lines else "_(no reply generated)_"
```

**Decide whether to build `_render_harvest_response` as a text-only fallback:** RESEARCH.md §Pattern 3 recommends embed-only (D-03a). There is no text fallback for `stat` either (it returns `{"type": "embed", ...}`). Recommend: embed-only, no text fallback. The on_message/sen dispatcher (which converts `{"type": "embed"}` to `discord.Embed`) is already in place per Phase 30's `stat` work.

**Analog E — help text update:** `bot.py:340` + `bot.py:589-593`.

```python
# line 340 — top-level usage:
return "Usage: `:pf npc <create|update|show|relate|import|say> ...`"

# lines 589-593 — unknown-verb help inside the npc branch:
return (
    f"Unknown npc command `{verb}`. "
    "Available: `create`, `update`, `show`, `relate`, `import`, `export`, `token`, `token-image`, `stat`, `pdf`, `say`."
)
```

**Update for Phase 32:**
- Line 340: `Usage: \`:pf <npc|harvest> ...\`` — the dispatcher now accepts two nouns.
- If `noun=="harvest"` but the input is empty (`:pf harvest`), return `"Usage: \`:pf harvest <Name>[,<Name>...]\`"`.
- Keep the npc help text unchanged (npc verbs are orthogonal to harvest).

**Gotcha 1 — discord stub in tests:** `test_subcommands.py:34` stubs `_discord_stub.Thread = object`. For harvest (no thread walk), this is irrelevant, but the `discord.Embed` creation in `build_harvest_embed` needs a stub. The existing tests (Phase 30 `stat`, Phase 31 `say`) already handle this via the on_message dispatch; the unit tests for `_pf_dispatch` just assert the returned dict shape `{"type": "embed", ...}` — they never instantiate a real `discord.Embed`. See `test_pf_say_*` analog block (§10) for the pattern.

**Gotcha 2 — error handling reuse:** the existing `except httpx.HTTPStatusError/ConnectError/TimeoutException` block (lines 595-615) covers all module exceptions. No new branches needed. 404 currently maps to `"NPC not found."` — but harvest has no 404 cases (cache miss goes to LLM fallback; LLM failure is 500). Leave the 404 arm unchanged.

**Gotcha 3 — Phase 31 SUMMARY ruff-formatter quirk (REPEAT OFFENDER):** The project's PostToolUse hook runs `ruff check --fix` on every Python edit; the F401 rule strips unused imports. If the `harvest` branch imports `build_harvest_embed` BEFORE the branch that uses it is written (task split across commits), ruff auto-deletes the import. **Mandatory countermeasure:** use a single `Edit` that adds BOTH the import AND the first use-site in the same edit. Phase 31's 31-04 SUMMARY describes the `git add --patch` workaround for split-commits. Plan 32's wave ordering MUST avoid this split (recommend: one task that touches bot.py adds import + branch + help text updates together; then a second task adds tests).

---

### 10. `interfaces/discord/tests/test_subcommands.py` — APPEND `test_pf_harvest_*` tests

**Analog:** `test_pf_say_solo_dispatch` lines 301-318 (SAME FILE).

```python
async def test_pf_say_solo_dispatch():
    """_pf_dispatch('npc say Varek | hello there') calls post_to_module with say payload (DLG-01)."""
    mock_result = {
        "replies": [
            {"npc": "Varek", "reply": "> *nods.* \"Aye.\"", "mood_delta": 0, "new_mood": "neutral"}
        ],
        "warning": None,
    }
    with patch.object(bot._sentinel_client, "post_to_module", new=AsyncMock(return_value=mock_result)) as mock_ptm:
        result = await bot._pf_dispatch("npc say Varek | hello there", "user123")

    mock_ptm.assert_called_once()
    assert mock_ptm.call_args[0][0] == "modules/pathfinder/npc/say"
    payload = mock_ptm.call_args[0][1]
    assert payload["names"] == ["Varek"]
    assert payload["party_line"] == "hello there"
    assert payload["user_id"] == "user123"
    assert payload["history"] == []
```

**Copy for Phase 32 — 6 harvest dispatch tests:**

| # | Test name | Input | Assert |
|---|-----------|-------|--------|
| 1 | `test_pf_harvest_solo_dispatch` | `"harvest Boar"` | post_to_module called with `"modules/pathfinder/harvest"`, payload `names==["Boar"]` |
| 2 | `test_pf_harvest_batch_dispatch` | `"harvest Boar,Wolf,Orc"` | payload `names==["Boar","Wolf","Orc"]` |
| 3 | `test_pf_harvest_multi_word_monster` | `"harvest Giant Rat"` | payload `names==["Giant Rat"]` (single name, space preserved) |
| 4 | `test_pf_harvest_batch_trimmed_commas` | `"harvest Boar , Wolf , Orc"` | payload `names==["Boar","Wolf","Orc"]` |
| 5 | `test_pf_harvest_empty_returns_usage` | `"harvest"` (no names) | post_to_module NOT called; result contains "Usage" |
| 6 | `test_pf_harvest_returns_embed_dict` | mock returns `{monsters:[...], aggregated:[...], footer:...}` | result is dict, `result["type"]=="embed"`, `result["embed"]` is the stub Embed object |

**Gotcha 1 — `post_to_module` patch target:** use `patch.object(bot._sentinel_client, "post_to_module", new=AsyncMock(...))`. The module-level client is instantiated at import time (bot.py:95), so attribute patching is the only working route. Precedent: `test_pf_dispatch_create` line 216, `test_pf_say_solo_dispatch` line 309.

**Gotcha 2 — build_harvest_embed in tests:** the unit test asserts `result["type"] == "embed"` and that `build_harvest_embed` was invoked. Since the discord stub at line 30 sets `_discord_stub` without a real `Embed`, the test must either (a) stub `bot.discord.Embed = MagicMock()` before `_pf_dispatch` runs, or (b) assert only on the dict shape and skip introspecting the `embed` value. Recommend option (b) — mirror `test_pf_dispatch_stat` if it exists (Phase 30), else assert `"embed" in result` and `result["type"] == "embed"`.

**Gotcha 3 — widened noun check:** `test_pf_dispatch_unknown_noun` currently expects `"monster create Goblin"` to return an Unknown-noun error. After the widening `if noun not in {"npc", "harvest"}`, this test still passes because `monster` is still unknown. No regression. Add a new test `test_pf_harvest_noun_recognised` to lock in the new behaviour.

---

## Shared Patterns (Global Rules This Phase MUST Maintain)

### S1. Logging — project-standard formatter

**Source:** `routes/npc.py:44`; `app/llm.py:11`; `app/dialogue.py:21`; `app/obsidian.py:11`; `app/main.py:42`.

```python
logger = logging.getLogger(__name__)
```

Use `%s` substitution in log calls (`logger.info("NPC updated: %s, changed: %s", req.name, list(changed.keys()))`), NOT f-strings. Consistent across the entire pathfinder module.

### S2. LLM call kwargs pattern (ALL LLM call sites)

**Source:** `app/llm.py:60-69` (`extract_npc_fields`) and all other functions in that file (lines 91-100, 144-163, 207-216).

```python
kwargs: dict = {
    "model": model,
    "messages": [{"role": "system", "content": ...}, {"role": "user", "content": ...}],
    "timeout": 60.0,
}
if api_base:
    kwargs["api_base"] = api_base
response = await litellm.acompletion(**kwargs)
```

**Rules (all enforced):**
- ALWAYS conditionally set `api_base` — never pass `None` (LM Studio errors).
- `timeout=60.0` for structured/chat; `timeout=30.0` for short-output (`generate_mj_description`). Harvest fallback uses 60.0.
- Call `_strip_code_fences(content)` before `json.loads` — known limitation: only strips ` ```json ` and bare ` ``` `.

### S3. Obsidian interaction — ALWAYS GET-then-PUT for new or mutating writes

**Source:** `routes/npc.py:409-446` (`update_npc`); `obsidian.py:37-64` (`get_note` / `put_note`).

Call `await obsidian.get_note(path)` → check `is None` → parse → mutate → `await obsidian.put_note(path, build_<kind>_markdown(...))`. **NEVER** use `patch_frontmatter_field` for fields that may be missing (memory: `project_obsidian_patch_constraint.md`).

For harvest, the cache file does not exist on first query → PATCH would return 400. Always GET-then-PUT. The frontmatter-field constraint applies here: `verified:`, `source:`, `harvested_at:` are NEW fields on first write → they cannot use PATCH.

### S4. Input sanitization — validator on every `name` field

**Source:** `routes/npc.py:72-81` (`_validate_npc_name`).

```python
def _validate_npc_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("name cannot be empty")
    if len(v) > 100:
        raise ValueError("name too long (max 100 chars)")
    if re.search(r"[\x00-\x1f\x7f]", v):
        raise ValueError("name contains invalid control characters")
    return v
```

**Copy for `_validate_monster_name`** — same body. Every Pydantic model whose `name` field flows to `slugify()` MUST apply `@field_validator` + per-element call.

### S5. Error response shape — `{"error": ..., "detail": ...}`

**Source:** `routes/npc.py:358-360`, `373`, `412`, `425`, `438`.

```python
raise HTTPException(status_code=500, detail={"error": "LLM extraction failed", "detail": str(exc)})
```

Two-key shape: `error` (summary) + `detail` (caught exception str). 404s differ: `{"error": "NPC not found", "slug": slug, "name": name}`. Harvest errors use `{"error": "...", "detail": str(exc)}`.

### S6. Test ASGI boot — lifespan-safe import ordering

**Source:** `test_npc.py:30-38` and every test thereafter; `test_npc_say_integration.py:81-107`.

```python
with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
     patch("app.routes.npc.obsidian", mock_obs):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ...
```

- `from app.main import app` MUST be inside the patch block.
- `_register_with_retry` MUST be patched (real one hangs or errors).
- Obsidian patch targets the route-layer module (`app.routes.harvest.obsidian`), NOT `app.main._harvest_module.obsidian`. The handlers dereference the module-level name at call time.

### S7. HTTP client — httpx ONLY, never requests or aiohttp

**Source:** `app/obsidian.py` uses `httpx.AsyncClient`; `app/main.py` uses `httpx.AsyncClient`; `bot.py:348` uses `async with httpx.AsyncClient() as http_client`.

**Rule (project-wide):** No `requests`, no `aiohttp`, no `urllib3`. httpx is the ONLY HTTP client. If a scaffold script needs to fetch Foundry JSON, use `httpx.Client` (sync) or stdlib `urllib.request` (no dep). Recommend `httpx.Client` for consistency.

### S8. Pydantic v2 `model_validate` for YAML / external data

**Source:** RESEARCH.md §YAML Loader; no in-repo precedent yet (harvest is the first YAML-loaded Pydantic case).

```python
raw = yaml.safe_load(path.read_text())
return HarvestTable.model_validate(raw)
```

**Rule:** Never `.parse_obj()` (Pydantic v1). Never `HarvestTable(**raw)` (bypasses validators). Always `.model_validate(raw)`. Matches how FastAPI internally validates request bodies.

### S9. `--no-verify` in parallel worktrees (Phase 31 31-01-SUMMARY line 74)

**Source:** Phase 31 worktree commits used `git commit --no-verify` to bypass the global pre-commit hook which ran formatter on files outside the worktree. This is documented in every 31-*-SUMMARY.md.

**Rule for Phase 32:** If wave plans run in parallel worktrees (recommended per Phase 31's proven pattern), each task commits with `--no-verify`. The orchestrator's final merge-back to main runs the formatter once on the merged state, which either produces a clean no-op or a single formatting commit on main.

**Do not skip hooks on main.** Worktree commits with `--no-verify` are the ONLY acceptable use. The global CLAUDE.md prohibits `--no-verify` on main commits.

### S10. Ruff formatter single-Edit rule (Phase 31 31-02 + 31-04 SUMMARIES)

**Source:** Phase 31 31-02-SUMMARY line 108-111 and 31-04-SUMMARY line 108-116.

> The project's PostToolUse formatter (ruff, likely with F401 fix) strips unused imports on every Python edit.

**Rule:** When adding an import + its first use-site, both changes MUST land in a SINGLE `Edit` or `Write` operation. If the plan splits "add imports" (task A) and "use imports" (task B) across commits, ruff deletes the imports between task A and task B. Phase 31's 31-04 used `git add --patch` to split a single edit session into two logical commits AFTER the code was written — the plan-task split existed in git history but not in the edit sequence.

**Apply to Phase 32:**
- `modules/pathfinder/app/routes/harvest.py` — write the full file in a single `Write` operation (new file, so this is trivial).
- `modules/pathfinder/app/main.py` — add `import app.routes.harvest as _harvest_module` in the SAME Edit that adds the lifespan assignment `_harvest_module.obsidian = obsidian_client` (the first use).
- `interfaces/discord/bot.py` — add `build_harvest_embed` function + the `harvest` branch that calls it + the noun widen + the help-text update in a SINGLE Edit session. If the plan splits this across tasks, `git add --patch` AFTER the edit lands, don't split the Edit itself.
- `modules/pathfinder/app/llm.py` — adding `generate_harvest_fallback` is additive; no pre-existing import needs to be paired. Safe to do as a standalone Edit.

### S11. TDD Red-Green per Phase 31 Wave 0 (optional but recommended)

**Source:** Phase 31 Wave 0 created `test_npc_say_integration.py` with failing `patch("app.routes.npc.generate_npc_reply", ...)` that raised `AttributeError` at runtime — the "honest RED signal" (31-01-SUMMARY line 3-7).

**Apply to Phase 32 (recommended per RESEARCH.md Plan Skeleton):**
- Wave 0: create `test_harvest.py` and `test_harvest_integration.py` with failing stubs that reference `app.routes.harvest.harvest_tables`, `app.routes.harvest.generate_harvest_fallback` (module attribute indirection), `app.harvest.lookup_seed`. Collection succeeds; runtime `AttributeError`. Commit as RED.
- Wave 1-3: GREEN by implementing the referenced symbols.

---

## No-Analog Findings

All primary files have strong in-repo analogs. Two sub-features warrant explicit "no precedent, follow RESEARCH.md" guidance:

| Sub-feature | Reason no analog | Planner guidance |
|-------------|------------------|------------------|
| YAML data file at `modules/pathfinder/data/harvest-tables.yaml` | First YAML data file in the module (previous YAML is inline strings in tests or Docker compose config) | Follow RESEARCH.md §Code Examples Example 1 for shape. Header comment cites ORC license. Load once at lifespan startup. Fail-fast on malformed content. |
| `rapidfuzz` integration | No existing fuzzy library in the project. `difflib` is stdlib but rejected in RESEARCH.md §Fuzzy-Match Recommendation. | RESEARCH.md §Fuzzy-Match Recommendation (verbatim imports + scorer + cutoff). Add to pyproject.toml per §6 above. |
| Scaffold script `modules/pathfinder/scripts/scaffold_harvest_seed.py` (OPTIONAL) | No `scripts/` dir exists in the module yet. Closest precedent: `modules/pathfinder/app/pdf.py` shows synchronous stdlib-ish helper style. | One-shot script — sync is fine. Use `httpx.Client` (consistent with S7) over `urllib.request` to keep one HTTP client library in the project. Output: print-to-stdout a scaffolded YAML that the DM hand-fills. Not a registered route; not imported from app.main. Planner may skip entirely if the DM prefers to hand-list L1-3 monsters from memory. |

---

## Metadata

**Analog search scope:**
- `/Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder/app/*.py`
- `/Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder/app/routes/*.py`
- `/Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder/tests/*.py`
- `/Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder/pyproject.toml`
- `/Users/trekkie/projects/sentinel-of-mnemosyne/interfaces/discord/bot.py`
- `/Users/trekkie/projects/sentinel-of-mnemosyne/interfaces/discord/tests/test_subcommands.py`
- `/Users/trekkie/projects/sentinel-of-mnemosyne/.planning/phases/31-dialogue-engine/31-*-SUMMARY.md` (ruff + worktree notes)
- `/Users/trekkie/projects/sentinel-of-mnemosyne/.planning/phases/31-dialogue-engine/31-PATTERNS.md` (format template)

**Files read in full:** 9 (all under 1,000 lines — single-pass; targeted offsets for npc.py sections).
**Pattern extraction date:** 2026-04-23
