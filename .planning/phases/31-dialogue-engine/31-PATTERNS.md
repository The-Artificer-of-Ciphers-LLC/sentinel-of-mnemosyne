# Phase 31: Dialogue Engine — Pattern Map

**Mapped:** 2026-04-23
**Files analyzed:** 8 (2 NEW, 6 EXTEND)
**Analogs found:** 8 / 8 — every new/extended file has a strong in-repo analog.

All excerpts below are verbatim copies from the cited files. Line ranges were read in full and checked; paste them into the implementation files and rename identifiers, do NOT reinvent the shape.

---

## File Classification

| File | New/Extend | Role | Data Flow | Closest Analog | Match Quality |
|------|-----------|------|-----------|----------------|---------------|
| `modules/pathfinder/app/dialogue.py` | NEW | helper module (prompt + mood math) | transform | `modules/pathfinder/app/llm.py` (module shape) + `_parse_frontmatter` (helper style) | exact (module shape) + role-match (helpers) |
| `modules/pathfinder/tests/test_npc_say_integration.py` | NEW | integration test | request-response (ASGI mock) | `modules/pathfinder/tests/test_npc.py` (all tests) | exact |
| `modules/pathfinder/app/llm.py` | EXTEND | LLM wrapper (add `generate_npc_reply`) | request-response | `extract_npc_fields` (SAME FILE, lines 29-69); `update_npc_fields` (SAME FILE, lines 134-170) | exact |
| `modules/pathfinder/app/routes/npc.py` | EXTEND | controller (add `/npc/say`, 4 models) | request-response + CRUD | `update_npc` (SAME FILE, lines 331-379) — GET-then-PUT flow; `NPCOutputRequest` (lines 114-121) — name validator; `extract_npc` / `relate_npc` — pydantic+validator patterns | exact |
| `modules/pathfinder/app/main.py` | EXTEND | registration config (12th route) | config | `REGISTRATION_PAYLOAD` entries (SAME FILE, lines 47-63) | exact |
| `modules/pathfinder/tests/test_npc.py` | EXTEND | unit tests (16 say tests) | request-response | `test_npc_token_*` / `test_npc_pdf_*` / `test_npc_token_image_*` blocks (SAME FILE, lines 333-536) | exact |
| `interfaces/discord/bot.py` | EXTEND | controller (add `say` verb + helpers) | request-response | `token-image` branch in `_pf_dispatch` (SAME FILE, lines 383-416); `on_message` thread access (lines 654-687) | exact |
| `interfaces/discord/tests/test_subcommands.py` | EXTEND | unit tests (8 say tests) | request-response | `test_pf_dispatch_*` block (SAME FILE, lines 206-290) | exact |

---

## Pattern Assignments

### 1. `modules/pathfinder/app/dialogue.py` (NEW — helper module)

**Analog A — module shape / imports:** `modules/pathfinder/app/llm.py` lines 1-15

```python
"""LLM helpers for pathfinder module — NPC field extraction via LiteLLM.

Calls litellm.acompletion() directly (no wrapper class).
Uses the project's configured LITELLM_MODEL + LITELLM_API_BASE from settings.
"""
import json
import logging

import litellm

logger = logging.getLogger(__name__)

# Suppress litellm's verbose startup logs
litellm.suppress_debug_info = True
```

**Copy for dialogue.py:** use the same module-docstring style; use `logger = logging.getLogger(__name__)`; do NOT import litellm here (dialogue.py is pure transform — no LLM calls, those live in `llm.generate_npc_reply`).

**Analog B — helper-function style (pure string transforms with exception-to-log fallback):** `modules/pathfinder/app/routes/npc.py` lines 143-187

```python
def slugify(name: str) -> str:
    """Convert NPC name to a stable lowercase filename slug (D-18).

    Examples: 'Baron Aldric' -> 'baron-aldric', 'Varek' -> 'varek'.
    Uses stdlib re — no external dependency (RESEARCH.md Don't Hand-Roll).
    Strips path traversal chars — '../' becomes '' (T-29-01 mitigation).
    """
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _parse_frontmatter(note_text: str) -> dict:
    """Parse YAML frontmatter from a note string delimited by '---'.

    Returns empty dict if frontmatter cannot be parsed.
    Safe to call on machine-generated notes (Sentinel always writes valid YAML).
    """
    try:
        if not note_text.startswith("---"):
            return {}
        # Find the closing --- delimiter (use find to avoid ValueError on malformed notes)
        end = note_text.find("---", 3)
        if end == -1:
            return {}
        frontmatter_text = note_text[3:end].strip()
        return yaml.safe_load(frontmatter_text) or {}
    except Exception as exc:
        logger.warning("Frontmatter parse failed: %s", exc)
        return {}
```

**Copy for dialogue.py helpers:**
- Pure functions: `normalize_mood(value: str) -> str`, `apply_mood_delta(current: str, delta: int) -> str`, `cap_history_turns(turns: list[dict]) -> list[dict]`, `build_system_prompt(...)`, `build_user_prompt(...)` — all follow this shape (docstring, single well-defined job, log-and-fall-back on unexpected input, no exception propagation unless caller must know).
- Pattern for invalid-enum handling mirrors `_parse_frontmatter`: `logger.warning("NPC mood %r invalid; treating as 'neutral'", value)` then return the safe default (see RESEARCH.md lines 805-810).

**Module-level constants:** mirror `VALID_RELATIONS` in `routes/npc.py` line 57:
```python
VALID_RELATIONS = frozenset({"knows", "trusts", "hostile-to", "allied-with", "fears", "owes-debt"})
```
Use the same style for `MOOD_ORDER = ["hostile", "wary", "neutral", "friendly", "allied"]` and `MOOD_TONE_GUIDANCE = {...}` (see RESEARCH.md lines 794-802 for the full sketch).

**Gotcha:** `dialogue.py` must NOT import from `app.routes.npc` (that would create a circular-import risk once `routes/npc.py` imports `dialogue`). Keep dialogue.py dependency-free of the routes layer — it should only import stdlib + `logging`.

---

### 2. `modules/pathfinder/tests/test_npc_say_integration.py` (NEW — integration test)

**Analog:** `modules/pathfinder/tests/test_npc.py` lines 1-83 (env setup + mock-obsidian pattern) and lines 445-485 (full round-trip verification).

**Env bootstrap (lines 1-12)** — copy verbatim at the top of the new file:

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

**Integration test skeleton (lines 20-39, mirror exactly):**

```python
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
```

**For `/npc/say` integration tests, clone this pattern and replace:**
- `patch("app.routes.npc.extract_npc_fields", ...)` → `patch("app.routes.npc.generate_npc_reply", new=AsyncMock(return_value={"reply": "...", "mood_delta": 0}))`
- `mock_obs.get_note.return_value = NOTE_WITH_STATS` (re-use the module constant from `test_npc.py` lines 261-268 OR import via a shared fixture — NOT recommended; copy the literal).
- Assert on `resp.json()["replies"][0]["new_mood"]` and `mock_obs.put_note.await_count`.

**Gotcha:** `pyproject.toml` sets `asyncio_mode = "auto"` (line 23) — do NOT decorate tests with `@pytest.mark.asyncio`. `async def test_*` is enough.

**Gotcha:** The `from app.main import app` line MUST be inside the `with patch(...)` block so the obsidian patch is active when the lifespan runs. Reproduce this ordering exactly.

---

### 3. `modules/pathfinder/app/llm.py` — ADD `generate_npc_reply()`

**Analog (SAME FILE):** `extract_npc_fields` lines 29-69.

```python
async def extract_npc_fields(
    name: str,
    description: str,
    model: str,
    api_base: str | None = None,
) -> dict:
    """Call LLM to extract NPC frontmatter fields from a freeform description.

    Returns a dict with keys: name, level (int), ancestry, class, traits (list),
    personality, backstory, mood. Raises json.JSONDecodeError on LLM parse failure.

    Per D-06 and D-07: unspecified fields are randomly filled from PF2e Remaster options.
    Valid ancestries: Human, Elf, Dwarf, Gnome, Halfling, Goblin, Leshy, Ratfolk, Tengu.
    """
    system_prompt = (
        "You are a Pathfinder 2e Remaster NPC generator. "
        ...
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

**Shape rules for `generate_npc_reply`** (all enforced):
1. Signature: `async def generate_npc_reply(system_prompt: str, user_prompt: str, model: str, api_base: str | None = None) -> dict:` — follows RESEARCH.md lines 746-782 which explicitly matches this pattern.
2. **`kwargs: dict = {...}`** then conditional `if api_base: kwargs["api_base"] = api_base` — do NOT pass `api_base=api_base` unconditionally; LM Studio will error on `api_base=None`.
3. **`"timeout": 60.0`** — same as `extract_npc_fields`. Dialogue is chat-tier but still calls LM Studio; 60s covers slow cold starts.
4. **Use `_strip_code_fences`** (SAME FILE, lines 17-26) — the salvage primitive. Call `.strip()` after. Do NOT write a new fence-stripper.
5. **Graceful JSON fallback** (distinguishes this from `extract_npc_fields` which raises): wrap `json.loads(...)` in `try/except json.JSONDecodeError`, salvage the reply, return `{"reply": <best-effort>, "mood_delta": 0}`. Log a warning with `raw[:200]` for diagnosis. See RESEARCH.md lines 769-782 for the exact shape.
6. **Clamp `mood_delta`** to `{-1, 0, 1}` — anything else coerces to 0. Model compliance is not guaranteed with chat-tier; trust no value.

**Gotcha:** `_strip_code_fences` (SAME FILE, lines 17-26) only handles ` ```json ` and bare ` ``` ` prefixes — not ` ```python ` or `~~~`. This is already a known limitation (RESEARCH.md Pitfall: "`_strip_code_fences` doesn't strip ` ```python ` or alternate languages"). Do not extend it as part of this phase — the salvage path catches the JSONDecodeError and returns the raw text as reply.

---

### 4. `modules/pathfinder/app/routes/npc.py` — ADD models + `/say` handler

**Analog A — Pydantic model with `_validate_npc_name` wrapper:** `NPCOutputRequest` lines 114-121 (SAME FILE).

```python
class NPCOutputRequest(BaseModel):
    """Request model for /npc/{export-foundry,token,stat,pdf} (OUT-01..OUT-04)."""
    name: str

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        return _validate_npc_name(v)
```

**Copy for `TurnHistory`, `NPCReply`, `NPCSayRequest`, `NPCSayResponse`:**

- `TurnHistory(BaseModel)`: fields `party_line: str`, `replies: list[dict]`. No name validator (history is bot-sourced, already sanitised upstream when originally issued).
- `NPCReply(BaseModel)`: fields `npc: str`, `reply: str`, `mood_delta: int`, `new_mood: str`.
- `NPCSayRequest(BaseModel)`: fields `names: list[str]`, `party_line: str = ""`, `history: list[TurnHistory] = []`, `user_id: str`. Apply `@field_validator("names")` that loops through and calls `_validate_npc_name(n)` for each — see RESEARCH.md lines 924-929 for the exact shape. Apply `@field_validator("party_line")` that enforces `len(v) > 2000` raises `ValueError("party_line too long (max 2000 chars)")` — see D-28 in CONTEXT.md and RESEARCH.md lines 931-936.
- `NPCSayResponse(BaseModel)`: fields `replies: list[NPCReply]`, `warning: str | None = None`. (Optional — the route currently returns via `JSONResponse({...})` matching other routes. Pydantic response model is optional; all sibling routes use `JSONResponse` and no `response_model=` kwarg. Follow sibling pattern: skip the response model.)

**Analog B — GET-then-PUT handler flow:** `update_npc` lines 331-379 (SAME FILE).

```python
@router.post("/update")
async def update_npc(req: NPCUpdateRequest) -> JSONResponse:
    """Update NPC fields via GET-then-PUT (NPC-02, D-10).

    Reads the existing note, sends to LLM with correction to extract changed fields,
    merges changes into frontmatter, rebuilds full markdown, and PUTs back.
    Stats block preserved if present; replaced only if correction mentions stats.
    """
    slug = slugify(req.name)
    path = f"{_NPC_PATH_PREFIX}/{slug}.md"

    # Read existing note — must exist
    note_text = await obsidian.get_note(path)
    if note_text is None:
        raise HTTPException(status_code=404, detail={"error": "NPC not found", "slug": slug})

    # LLM extracts changed fields from correction string (D-10)
    # Task kind "structured" — same JSON-extraction profile as /create
    try:
        changed = await update_npc_fields(
            current_note=note_text,
            correction=req.correction,
            model=await resolve_model("structured"),
            api_base=settings.litellm_api_base or None,
        )
    except Exception as exc:
        logger.error("LLM update extraction failed for NPC %s: %s", req.name, exc)
        raise HTTPException(status_code=500, detail={"error": "LLM update failed", "detail": str(exc)})

    # Merge changed fields into existing frontmatter
    current_fields = _parse_frontmatter(note_text)
    current_stats = _parse_stats_block(note_text)
    current_fields.update(changed)

    # Rebuild and PUT full note
    content = build_npc_markdown(current_fields, stats=current_stats if current_stats else None)
    try:
        await obsidian.put_note(path, content)
    except Exception as exc:
        logger.error("Obsidian write failed for NPC %s: %s", req.name, exc)
        raise HTTPException(status_code=503, detail={"error": "Obsidian write failed", "detail": str(exc)})

    logger.info("NPC updated: %s, changed: %s", req.name, list(changed.keys()))
    return JSONResponse({...})
```

**Apply to `/npc/say` handler:** full reference shape is RESEARCH.md lines 939-1026 (already matches this codebase style). Key invariants to preserve:
- **404-on-first-missing** per D-29: `raise HTTPException(status_code=404, detail={"error": "NPC not found", "slug": slug, "name": name})` inside the `for name in req.names` loop BEFORE any LLM calls. Pattern mirrors `update_npc` line 344-345.
- **Mood write ONLY when `new_mood != current_mood`** (D-07 + D-09): use the same `build_npc_markdown(updated_fields, stats=current_stats if current_stats else None)` + `await obsidian.put_note(path, content)` shape as `update_npc` lines 365-371. Log `logger.error(...)` + **degrade the response** (set `new_mood = current_mood`) on put_note failure — do NOT raise. See RESEARCH.md lines 1007-1012.
- **Obsidian 503 on write failure** for `put_note` (line 371) — but dialogue wants graceful degradation instead; follow the RESEARCH.md guidance.
- **Model selection**: `await resolve_model("chat")` (D-27) — NOT `"structured"`. This is the only existing call site that will use "chat" kind; `resolve_model("chat")` already exists in `app/resolve_model.py`.

**Analog C — the name-validator pattern at class level:** `NPCCreateRequest` lines 76-84 (SAME FILE).

```python
class NPCCreateRequest(BaseModel):
    name: str
    description: str = ""
    user_id: str

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        return _validate_npc_name(v)
```

**For `NPCSayRequest.names: list[str]`** — the validator shape changes: iterate and sanitise every element. RESEARCH.md lines 924-929:

```python
@field_validator("names")
@classmethod
def sanitize_names(cls, v: list[str]) -> list[str]:
    if not v:
        raise ValueError("at least one NPC name required")
    return [_validate_npc_name(n) for n in v]
```

**Gotcha 1:** `_validate_npc_name` (lines 64-73) is a module-level helper and MUST be applied to every string that flows to `slugify`. Never bypass. Unit test pattern: send a name with `\x00` in it, assert 422 (per Phase 29 CR-02 mitigation).

**Gotcha 2:** `build_npc_markdown` (lines 189-202) takes `(fields: dict, stats: dict | None)` — stats MUST be `None` (not `{}`) when omitted, otherwise the `## Stats` block is written with empty content. Line 366 in `update_npc` uses `stats=current_stats if current_stats else None` — copy this ternary exactly.

**Gotcha 3:** The mood-write path MUST use `build_npc_markdown` + `put_note`, NOT `patch_frontmatter_field`. This is D-09 and the hard-won memory `project_obsidian_patch_constraint.md`. The existing `relate_npc` (line 449) still uses PATCH because `relationships:` always exists in frontmatter (set at create time); `mood:` also always exists (set `mood: neutral` at create per Phase 29 D-20), but using PUT keeps the pattern consistent with `update_npc` and `upload_token_image` (which handle both PATCH-safe and PATCH-unsafe cases uniformly). See `upload_token_image` lines 756-774 comment block for the authoritative rationale.

---

### 5. `modules/pathfinder/app/main.py` — ADD 12th route to `REGISTRATION_PAYLOAD`

**Analog (SAME FILE):** `REGISTRATION_PAYLOAD` lines 47-63.

```python
REGISTRATION_PAYLOAD = {
    "name": "pathfinder",
    "base_url": "http://pf2e-module:8000",
    "routes": [
        {"path": "healthz", "description": "pf2e module health check"},
        {"path": "npc/create", "description": "Create NPC in Obsidian (NPC-01)"},
        {"path": "npc/update", "description": "Update NPC fields (NPC-02)"},
        {"path": "npc/show", "description": "Show NPC summary (NPC-03)"},
        {"path": "npc/relate", "description": "Add NPC relationship (NPC-04)"},
        {"path": "npc/import", "description": "Bulk import NPCs from Foundry JSON (NPC-05)"},
        {"path": "npc/export-foundry", "description": "Export NPC as Foundry VTT actor JSON (OUT-01)"},
        {"path": "npc/token", "description": "Generate Midjourney token prompt (OUT-02)"},
        {"path": "npc/token-image", "description": "Upload NPC token image to vault (OUT-02 extension)"},
        {"path": "npc/stat", "description": "Return structured stat block data (OUT-03)"},
        {"path": "npc/pdf", "description": "Generate PDF stat card (OUT-04)"},
    ],
}
```

**Copy for Phase 31** — append exactly one line after the `pdf` entry:

```python
{"path": "npc/say", "description": "In-character NPC dialogue with mood tracking (DLG-01..03)"},
```

Per D-26. Description wording is verbatim from CONTEXT.md D-26 — paste as-is.

**Also update:** the module docstring at lines 4-16 (list of endpoints). Append one line after the `/npc/pdf` entry on line 15:
```
  POST /npc/say            — in-character NPC dialogue with mood tracking (DLG-01..03)
```

**Gotcha (Pitfall 7 from Phase 28):** All routes MUST appear in `REGISTRATION_PAYLOAD` at module import time. If the planner adds `npc/say` to the router but forgets this registry entry, sentinel-core's `/modules/pathfinder/npc/say` proxy will return 404 (the route is not advertised). Every Phase 30/29 plan failed to make this explicit — verify it in the plan's "done" checklist.

---

### 6. `modules/pathfinder/tests/test_npc.py` — APPEND 16 `test_npc_say_*` tests

**Analog block 1 — module-scope NOTE constants:** lines 261-276 (SAME FILE).

```python
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
```

**Add new constants** for say tests: `NOTE_HOSTILE_VAREK`, `NOTE_FRIENDLY_BARON`, `NOTE_WITH_RELATIONSHIPS` (Varek fears Baron). Follow the same triple-string YAML shape — do NOT use `yaml.dump(...)` in test setup.

**Analog block 2 — happy-path route test:** lines 333-345 (SAME FILE, `test_npc_token_success`).

```python
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
```

**Copy for Phase 31 tests** — one per required case:

| # | Test name | Setup | Assert |
|---|-----------|-------|--------|
| 1 | `test_npc_say_solo_happy_path` | mock get_note → NOTE_NO_STATS; patch `generate_npc_reply` → `{"reply": "...", "mood_delta": 0}` | 200, `replies[0]["npc"] == "Varek"`, NO put_note called |
| 2 | `test_npc_say_scene_order_preserved` | 2 NPCs, two side_effect get_notes, two side_effect LLM replies | `replies[0]["npc"] == "Varek"`, `replies[1]["npc"] == "Baron"` |
| 3 | `test_npc_say_mood_delta_plus_one_writes` | NOTE_NO_STATS (mood neutral), LLM returns mood_delta=+1 | 200; put_note called once; content contains `mood: friendly` |
| 4 | `test_npc_say_mood_delta_minus_one_writes` | NOTE_NO_STATS, LLM returns mood_delta=-1 | put_note content contains `mood: wary` |
| 5 | `test_npc_say_mood_delta_zero_no_write` | LLM returns mood_delta=0 | put_note NOT called; `replies[0]["new_mood"] == "neutral"` |
| 6 | `test_npc_say_mood_clamp_at_hostile` | mood:hostile + delta=-1 | `new_mood == "hostile"`; put_note NOT called (no-op clamp) |
| 7 | `test_npc_say_mood_clamp_at_allied` | mood:allied + delta=+1 | `new_mood == "allied"`; put_note NOT called |
| 8 | `test_npc_say_unknown_npc_404` | get_note → None | 404; error detail names the missing NPC |
| 9 | `test_npc_say_scene_advance_empty_payload` | party_line="" | 200; LLM called with scene-advance user prompt (inspect call args) |
| 10 | `test_npc_say_five_plus_warning` | 5 NPCs | `warning` field non-null and contains "5 NPCs" |
| 11 | `test_npc_say_invalid_name_control_char` | POST with name containing `\x00` | 422 (pydantic) |
| 12 | `test_npc_say_empty_names_422` | POST with `names: []` | 422 |
| 13 | `test_npc_say_party_line_too_long_422` | party_line with 2001 chars | 422 |
| 14 | `test_npc_say_invalid_mood_frontmatter_normalized` | NOTE with `mood: grumpy` | no crash; normalize→neutral; LLM called with neutral tone |
| 15 | `test_npc_say_scene_relationships_filtered` | 2 NPCs with cross-scene relationships + 1 out-of-scene target | verify system prompt (inspect LLM call args) includes only the in-scene rel |
| 16 | `test_npc_say_obsidian_write_fail_degrades` | put_note raises; delta=+1 | 200; `new_mood == current_mood` (degrade); reply still present |

**Inspect LLM call args pattern:** use `mock.call_args.kwargs["system_prompt"]` / `["user_prompt"]` to assert on prompt contents. Pattern example from `test_npc_token_image_saves_binary_and_frontmatter` (lines 471-474):

```python
assert mock_obs.put_binary.await_count == 1
args, kwargs = mock_obs.put_binary.call_args
path_arg, bytes_arg, ct_arg = args
```

**Gotcha:** When mocking multiple `get_note` calls (scene tests), use `AsyncMock(side_effect=[note1, note2, ...])` not `return_value`. Precedent: `test_npc_import_collision_skipped` line 243.

---

### 7. `interfaces/discord/bot.py` — ADD `say` branch + 2 helpers

**Analog A — verb branch style:** `token-image` branch lines 383-416 (SAME FILE).

```python
elif verb == "token-image":
    # Close the Midjourney loop (PLAN.md token-image extension).
    # User replies in a thread with a PNG attached; bot fetches bytes,
    # base64-encodes, POSTs to /npc/token-image which stores under
    # mnemosyne/pf2e/tokens/<slug>.png and updates note frontmatter.
    npc_name = rest.strip()
    if not npc_name:
        return "Usage: `:pf npc token-image <name>` — attach a PNG as a reply in this thread."
    if not attachments:
        return (
            f"Usage: `:pf npc token-image {npc_name}` — attach the Midjourney-"
            "generated PNG as a reply in this thread."
        )
    attachment = attachments[0]
    content_type = getattr(attachment, "content_type", "") or ""
    if not content_type.startswith("image/"):
        return (
            f"Expected an image attachment (got `{content_type or 'unknown'}`). "
            "Midjourney exports PNG — re-attach the PNG and try again."
        )
    fetch_resp = await http_client.get(str(attachment.url), timeout=30.0)
    fetch_resp.raise_for_status()
    image_bytes = fetch_resp.content
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    result = await _sentinel_client.post_to_module(
        "modules/pathfinder/npc/token-image",
        {"name": npc_name, "image_b64": image_b64},
        http_client,
    )
    return (
        f"Token image saved for **{npc_name}** "
        f"({result.get('size_bytes', len(image_bytes))} bytes) → `{result.get('token_path', '?')}`.\n"
        f"Run `:pf npc pdf {npc_name}` to see it embedded in the stat card."
    )
```

**Copy for `say` branch:**
- Use `name_list_str, sep, payload = rest.partition("|")` — pipe parsing. If `not sep`, return usage string. Follow RESEARCH.md lines 630-643.
- `names = [n.strip() for n in name_list_str.split(",") if n.strip()]` — then check `if not names: return "Usage..."`. See RESEARCH.md lines 638-640.
- `party_line = payload.strip()` — empty-string is the SCENE ADVANCE signal (D-02). Do NOT strip away the empty case here.
- **POST shape:** `{"names": names, "party_line": party_line, "history": history, "user_id": user_id}` to `"modules/pathfinder/npc/say"` via `_sentinel_client.post_to_module`.
- Render via `_render_say_response(result)` helper (new).

**Analog B — pipe-separator + pipe-trailing-empty pattern:** `create` branch lines 251-268.

```python
elif verb == "create":
    # Split name | description on first pipe (D-05, Pitfall 5: maxsplit=1)
    name, _, description = rest.partition("|")
    if not name.strip():
        return "Usage: `:pf npc create <name> | <description>`"
```

**Copy:** Use `rest.partition("|")` for the `say` verb too — `rest.split("|", 1)` would also work but the partition pattern is established across 3 verbs (create/update/say) so stay consistent.

**Analog C — channel access for thread history:** `on_message` lines 664-687 (SAME FILE).

```python
# Only act on messages inside public threads
if not isinstance(message.channel, discord.Thread):
    return
...
thread = message.channel
is_sentinel_thread = (
    thread.id in SENTINEL_THREAD_IDS
    or thread.owner_id == self.user.id
)
...
async with message.channel.typing():
    ai_response = await _route_message(user_id, message.content, attachments=list(message.attachments))
```

**Signature-change required** per RESEARCH.md lines 666: the cleanest path is to **pre-walk history in `on_message` and `sen` BEFORE calling `_pf_dispatch`**, then pass the history array in through a new kwarg. But passing a `discord.Thread` object into `_pf_dispatch` breaks testability (test_subcommands.py stubs out discord entirely).

**Recommended signature:** extend `_pf_dispatch(args, user_id, attachments=None, channel=None)`. Inside the say branch, `if isinstance(channel, discord.Thread): history = await _extract_thread_history(...)`. Tests pass `channel=None` and assert history is empty. This keeps the signature backward-compatible for all existing verbs and lets tests stub `channel=None`.

**Thread history walker (new helper)** — follow RESEARCH.md lines 686-738 verbatim for the `_extract_thread_history` function. Key imports to add to bot.py: `import re`. Anchor the module-level patterns just after the existing `_VALID_RELATIONS = frozenset({...})` on line 181:

```python
_SAY_PATTERN = re.compile(r"^:pf\s+npc\s+say\s+(.+?)\s*\|(.*)$", re.IGNORECASE | re.DOTALL)
_QUOTE_PATTERN = re.compile(r"^>\s+(.+)$", re.MULTILINE)
```

**`_render_say_response` helper** — RESEARCH.md lines 671-683, verbatim. Place next to `build_stat_embed` (lines 184-226) as a sibling module-level helper.

**Unknown-verb help update** — line 450:

```python
return (
    f"Unknown npc command `{verb}`. "
    "Available: `create`, `update`, `show`, `relate`, `import`, `export`, `token`, `token-image`, `stat`, `pdf`."
)
```

**Add `say` to the list** — new value:
```python
"Available: `create`, `update`, `show`, `relate`, `import`, `export`, `token`, `token-image`, `stat`, `pdf`, `say`."
```

Also update the top-level Usage line 242:
```python
return "Usage: `:pf npc <create|update|show|relate|import> ...`"
```
→ add `|say` to the verb list in the usage message.

**Gotcha 1 — discord.Thread stub in tests:** `test_subcommands.py` lines 33-34 already stubs `_discord_stub.Thread = object`. Any `isinstance(channel, discord.Thread)` check in `_pf_dispatch` will ALWAYS be False under tests — which is correct behaviour (tests should not walk history). Do NOT patch this out; it's a feature.

**Gotcha 2 — error handling:** The existing `try/except httpx.HTTPStatusError/ConnectError/TimeoutException` block (lines 453-473) already maps 404 → `"NPC not found."` generically. For `say` verb, consider enhancing the 404 branch to include the NPC name from `detail` (the route already returns `{"name": name}` in the 404 detail per Gotcha in section 4). Otherwise the DM can't tell WHICH of 3 named NPCs in a scene was missing. Minimal change: update the `if status == 404` arm to extract `detail.get("name")` if detail is a dict.

**Gotcha 3 — slash-command (`/sen`) first-turn history:** Per CONTEXT.md integration point, the first `:pf npc say` in a brand-new thread has no prior history. `thread.history()` returns no messages. `_extract_thread_history` must handle empty input and return `[]` — already covered by the `while i < len(msgs) - 1` loop guard in RESEARCH.md line 707.

---

### 8. `interfaces/discord/tests/test_subcommands.py` — APPEND 8 `test_pf_say_*` tests

**Analog:** `test_pf_dispatch_create` lines 206-225 (SAME FILE).

```python
async def test_pf_dispatch_create():
    """_pf_dispatch('npc create Varek | gnome rogue', user_id) calls post_to_module create path."""
    mock_result = {
        "name": "Varek",
        "slug": "varek",
        "path": "mnemosyne/pf2e/npcs/varek.md",
        "ancestry": "Gnome",
        "class": "Rogue",
        "level": 1,
    }
    with patch.object(bot._sentinel_client, "post_to_module", new=AsyncMock(return_value=mock_result)) as mock_ptm:
        result = await bot._pf_dispatch("npc create Varek | gnome rogue", "user123")

    mock_ptm.assert_called_once()
    call_args = mock_ptm.call_args
    assert call_args[0][0] == "modules/pathfinder/npc/create"
    payload = call_args[0][1]
    assert payload["name"] == "Varek"
    assert "gnome rogue" in payload["description"]
    assert "Varek" in result
```

**Copy for 8 say tests:**

| # | Test name | Input | Assert |
|---|-----------|-------|--------|
| 1 | `test_pf_dispatch_say_solo` | `"npc say Varek | hello there"` | post_to_module called with `"modules/pathfinder/npc/say"`, payload `names==["Varek"]`, `party_line=="hello there"` |
| 2 | `test_pf_dispatch_say_scene` | `"npc say Varek,Baron | what do you want?"` | payload `names==["Varek","Baron"]` |
| 3 | `test_pf_dispatch_say_scene_trimmed_commas` | `"npc say Varek , Baron |hi"` | payload `names==["Varek","Baron"]` (spaces trimmed) |
| 4 | `test_pf_dispatch_say_scene_advance_empty_payload` | `"npc say Varek,Baron |"` | payload `party_line==""` |
| 5 | `test_pf_dispatch_say_no_pipe_returns_usage` | `"npc say Varek"` (no pipe) | post_to_module NOT called; result contains "Usage" |
| 6 | `test_pf_dispatch_say_no_names_returns_usage` | `"npc say | hi"` (empty names) | post_to_module NOT called; result contains "Usage" |
| 7 | `test_pf_dispatch_say_renders_replies` | mock `post_to_module` returns `{"replies": [{"npc":"Varek","reply":"*looks up.* \"Hi.\""}], "warning": None}` | result starts with `> *looks up.*` |
| 8 | `test_pf_dispatch_say_renders_warning` | mock returns warning + 5 replies | result contains `"5 NPCs in scene"` before the quote blocks |

**Gotcha 1 — discord stub:** tests run without `discord.py` installed (lines 13-50 stub the module). Do NOT pass real thread objects; pass `channel=None` or omit the kwarg. History walking is not testable in unit tests — add an integration test instead if coverage is needed (out of scope here; unit tests cover the dispatch layer only).

**Gotcha 2 — `post_to_module` patch target:** use `patch.object(bot._sentinel_client, "post_to_module", new=AsyncMock(...))`, NOT a string-path patch. The module-level client is instantiated at import time (bot.py line 95), so targeting the attribute is the only working route. Precedent: lines 216, 230, 241, 265.

---

## Shared Patterns (apply to all Phase 31 files)

### S1. Logging — project-standard formatter
**Source:** `modules/pathfinder/app/routes/npc.py` line 36; `app/llm.py` line 11.

```python
logger = logging.getLogger(__name__)
```

Use `%s` substitution (e.g. `logger.info("NPC updated: %s, changed: %s", req.name, list(changed.keys()))` line 373), NOT f-strings in log calls. Consistent across llm.py, routes/npc.py, main.py.

### S2. LLM call kwargs pattern (ALL LLM call sites)
**Source:** `extract_npc_fields` lines 56-66.

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

**Always** conditionally set `api_base` — never pass `None`. Timeout always explicit. Every call site in llm.py (lines 56, 94, 157) follows this. Phase 31's `generate_npc_reply` MUST follow it too.

### S3. Obsidian interaction — ALWAYS GET-then-write
**Source:** `update_npc` lines 342-368; `upload_token_image` lines 725-768 (auth rationale).

Call `await obsidian.get_note(path)` → check `is None` → 404 → parse → mutate → `await obsidian.put_note(path, build_npc_markdown(...))`. NEVER use `patch_frontmatter_field` for fields that may be missing (memory: `project_obsidian_patch_constraint.md`). Mood writes use this exact pattern per D-09.

### S4. Input sanitization — `_validate_npc_name` everywhere names appear
**Source:** `modules/pathfinder/app/routes/npc.py` lines 64-73.

Every Pydantic model whose `name` field feeds `slugify()` MUST apply `@field_validator("name") + _validate_npc_name`. NPCCreateRequest, NPCUpdateRequest, NPCOutputRequest, NPCTokenImageRequest all do this. NPCSayRequest must loop through the list.

### S5. Error response shape — `{"error": ..., "detail": ...}`
**Source:** `update_npc` lines 358, 371; `upload_token_image` lines 733-735, 741-743, 751-754, 771-774.

```python
raise HTTPException(status_code=500, detail={"error": "LLM extraction failed", "detail": str(exc)})
```

Every HTTPException raises with `detail=dict` (not string). Two-key shape: `error` (human-readable summary) + `detail` (the caught exception's str). 404s are different: `{"error": "NPC not found", "slug": slug}` (optionally `"name": name` for scenes).

### S6. Test ASGI boot — lifespan-safe import ordering
**Source:** `test_npc.py` lines 30-34 and every test thereafter.

```python
with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
     patch("app.routes.npc.obsidian", mock_obs):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ...
```

The `from app.main import app` MUST be inside the patch block. `_register_with_retry` MUST be patched (the real one tries to POST to sentinel-core and will hang or error). `obsidian` patch on `app.routes.npc.obsidian` — NOT `app.main._npc_module.obsidian` (tests use the routes-layer import path; the main-layer assignment is irrelevant inside ASGITransport because lifespan runs and overwrites it, but routes.npc.obsidian is what handlers dereference).

---

## No-Analog Findings

All 8 files have strong in-repo analogs. No file in this phase requires falling back to RESEARCH.md-only guidance.

One sub-feature has no direct precedent but extrapolates from existing primitives:

| Sub-feature | Reason no analog | Planner guidance |
|-------------|------------------|------------------|
| `tiktoken`-backed token-count guardrail in `cap_history_turns` | No existing use of `tiktoken` in pathfinder module; sibling (`sentinel-core/app/services/token_guard.py`) uses it but that module is not importable from pathfinder | Add `tiktoken` import in `dialogue.py`. Already in the transitive dep tree via litellm (RESEARCH.md lines 247-248 — HIGH confidence). Use `tiktoken.get_encoding("cl100k_base")`. No new pyproject dep needed — verify with `uv lock --dry-run` in execution. |

---

## Metadata

**Analog search scope:**
- `/Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder/app/*.py`
- `/Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder/app/routes/*.py`
- `/Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder/tests/*.py`
- `/Users/trekkie/projects/sentinel-of-mnemosyne/interfaces/discord/bot.py`
- `/Users/trekkie/projects/sentinel-of-mnemosyne/interfaces/discord/tests/test_subcommands.py`

**Files read in full:** 7 (all under 2,000 lines — single-pass).
**Files NOT re-read:** 0 (each file read once).
**Analogs located via direct file targets from CONTEXT.md §Files Being Modified.**

**Pattern extraction date:** 2026-04-23

---
