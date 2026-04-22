# Phase 29: NPC CRUD + Obsidian Persistence — Research

**Researched:** 2026-04-22
**Domain:** FastAPI module endpoint design, Obsidian REST API PATCH semantics, LiteLLM structured extraction, Discord bot dispatch routing
**Confidence:** HIGH (architecture is locked and consistent with verified API docs; one critical PATCH semantics finding requires implementation adjustment)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Discord Command Routing**
- D-01: NPC commands use the existing `:prefix` pattern inside `/sen` — NOT new app_commands. Form: `:pf npc <verb> <args>`.
- D-02: `bot.py` gets `_pf_dispatch(verb, args, user_id)` helper matching `:pf <noun> <verb>` → calls `SentinelCoreClient` at `POST /modules/pathfinder/npc/create` etc.
- D-03: CRUD routes directly to pathfinder module endpoints — NOT through `POST /message` AI pipeline.
- D-04: `_pf_dispatch` called from `handle_sentask_subcommand` when prefix is `pf`.

**NPC Create**
- D-05: `:pf npc create <name> | <description>` — pipe separator splits name from optional description.
- D-06: Pathfinder module sends name + description to LLM → structured JSON of all frontmatter fields.
- D-07: LLM random-fills unspecified fields from PF2e Remaster valid options (ancestry, class, level=1 default, traits).
- D-08: Name always first positional arg before pipe.

**NPC Update**
- D-09: `:pf npc update <name> | <freeform correction>` — same pipe pattern.
- D-10: LLM extracts changed fields. Identity/roleplay fields surgically PATCHed. Stats block is read-modify-write PUT (entire block replaced).
- D-11: No explicit key=value syntax required.

**NPC Relate**
- D-12: `:pf npc relate <npc-name> <relation> <target-npc-name>`
- D-13: Valid relation enum: `knows | trusts | hostile-to | allied-with | fears | owes-debt`. Invalid → error embed.
- D-14: Stored as `relationships: [{target: "Baron Aldric", relation: "trusts"}]` in frontmatter.

**Obsidian Note Schema**
- D-15: Split schema — identity fields in YAML frontmatter, PF2e stats in fenced `yaml` block in body.
- D-16: Frontmatter fields: name, level, ancestry, class, traits, personality, backstory, mood, relationships, imported_from.
- D-17: Stats block under `## Stats` heading as fenced yaml: ac, hp, fortitude, reflex, will, speed, skills.
- D-18: File slug: `slugify(name)` only (e.g., `varek.md`, `baron-aldric.md`). Stable regardless of level changes.
- D-19: Collision check: `GET /vault/mnemosyne/pf2e/npcs/{slug}.md` before every create. 200 → return 409 with existing path.
- D-20: Initial mood: `neutral` at creation.

**NPC Show Embed**
- D-21: Embed: Title with name/level/ancestry/class; description = personality + first 200 chars backstory; fields = AC, HP, Perception, Fort/Ref/Will, relationships; footer = mood + path.
- D-22: Stats fields omitted from embed if stats block absent.

**Foundry Bulk Import**
- D-23: `:pf npc import` expects JSON file attachment.
- D-24: Identity fields only — name, level, ancestry, class, traits. Stats block left empty.
- D-25: Parser defensively ignores unknown JSON keys.
- D-26: Summary embed: "Imported N NPC(s)" with collision-skipped names listed.

**Pathfinder Module Obsidian Integration**
- D-27: Pathfinder module calls Obsidian REST API directly — NOT through sentinel-core.
- D-28: Two new env vars: `OBSIDIAN_BASE_URL` and `OBSIDIAN_API_KEY` in pydantic-settings config + `.env.example`.
- D-29: Obsidian PATCH uses `Content-Type: application/json` with `Target-Type: frontmatter` header per plugin spec.

### Claude's Discretion

- LLM model: use project's configured LITELLM_MODEL
- Exact LLM prompt templates for create extraction and update diff parsing
- Internal pathfinder router file structure (`app/routes/npc.py` or equivalent)
- Pydantic models for NPC creation/update request/response shapes
- Stats block section heading (locked to `## Stats` in SPECIFICS)

### Deferred Ideas (OUT OF SCOPE)

- Full Foundry stat block extraction from bulk import JSON (Phase 30)
- NPC combat tracker integration (future milestone)
- Mood state transitions driven by dialogue history (Phase 31)
- `/pf` as a true Discord app_commands slash command group
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NPC-01 | User can create an NPC via Discord command; stored in Obsidian under `mnemosyne/pf2e/npcs/` | Obsidian PUT `/vault/{path}` confirmed. Slugify via stdlib regex. LiteLLM structured extraction pattern verified. |
| NPC-02 | User can update any field of an existing NPC by name via Discord command | Obsidian PATCH per-field confirmed (one PATCH per field). Stats block requires GET-then-PUT. See critical finding below. |
| NPC-03 | User can query an NPC by name and receive a summary in Discord | Obsidian GET `/vault/{path}` returns full note; parse YAML frontmatter; discord.Embed pattern verified in codebase. |
| NPC-04 | User can define NPC relationships stored in the NPC's Obsidian note | Relationships stored in frontmatter list; PATCH `relationships` field or GET-then-PUT. |
| NPC-05 | User can bulk-import NPCs from a Foundry VTT actor list JSON export | Discord file attachment via `interaction.data` / `message.attachments`; httpx to fetch attachment URL; defensive JSON parsing. |
</phase_requirements>

---

## Summary

Phase 29 adds five NPC CRUD operations to the pathfinder module established in Phase 28. The architecture is straightforward: `bot.py` adds a `_pf_dispatch()` helper that pattern-matches `:pf <noun> <verb>` subcommands and routes them via `SentinelCoreClient` to `POST /modules/pathfinder/npc/{verb}`. The pathfinder module handles Obsidian persistence directly (not through sentinel-core) using an `httpx.AsyncClient` that mirrors the `ObsidianClient` pattern from `sentinel-core/app/clients/obsidian.py`.

The most important research finding is a **critical PATCH semantics discrepancy**: the Obsidian REST API v3 PATCH endpoint targets **one frontmatter field at a time** via the `Target` header — it does not accept a JSON object with multiple fields in a single request. CONTEXT.md D-29 describes the body as `{"mood": "hostile"}` (a JSON object), which is technically the right content-type, but the API routes that to a single field named by the `Target` header. For NPC create (writing a full new note) and stats block updates (full block replacement), `PUT /vault/{path}` with the complete markdown content is the correct and simpler operation. For surgical identity-field updates (NPC-02), the implementation must issue one `PATCH` per changed field, or alternatively issue a `GET`-then-`PUT` for the full note with modified frontmatter. The GET-then-PUT approach is simpler to implement correctly and avoids multiple round-trips for multi-field updates.

LiteLLM is already installed (`1.83.10`) and used by sentinel-core; the pathfinder module must add `litellm` to its `pyproject.toml` dependencies and call it directly (same pattern as `LiteLLMProvider` in sentinel-core). The pathfinder module does not call sentinel-core for LLM operations — it calls LiteLLM directly.

**Primary recommendation:** Use GET-then-PUT (full note rebuild) for all NPC updates. Reserve per-field PATCH only for the `relationships` append operation where it provides clear benefit (appending to a list without re-serializing the full note).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `:pf npc <verb>` command parsing | Discord bot (interfaces/discord) | — | bot.py owns all Discord routing; `_pf_dispatch` parses `:pf` prefix |
| HTTP proxy to pathfinder module | sentinel-core API gateway | — | `POST /modules/pathfinder/npc/{verb}` proxied via modules.py |
| NPC CRUD business logic | Pathfinder module (modules/pathfinder) | — | All NPC logic lives in `app/routes/npc.py`; no leakage into sentinel-core |
| LLM field extraction | Pathfinder module | LiteLLM / LM Studio | Pathfinder calls `litellm.acompletion()` directly with structured prompt |
| Obsidian persistence | Pathfinder module | Obsidian Local REST API | Direct httpx calls from pathfinder; sentinel-core not involved (D-27) |
| Discord embed formatting | Discord bot (interfaces/discord) | — | `discord.Embed` built by bot from structured API response; not by pathfinder |
| Foundry JSON parsing | Pathfinder module | — | File attachment content fetched and parsed server-side in pathfinder |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | >=0.135.0 | HTTP endpoints in pathfinder module | Already in pyproject.toml [VERIFIED: codebase] |
| httpx | >=0.28.1 | Obsidian REST API client in pathfinder | Already in pyproject.toml; same async pattern as sentinel-core [VERIFIED: codebase] |
| litellm | >=1.83.0 | LLM calls for field extraction | Installed (1.83.10); used by sentinel-core; supply chain note: >=1.83.0 required (1.82.7-1.82.8 were malicious) [VERIFIED: pip show] |
| pydantic | >=2.7.0 | Request/response models, settings | Already pulled in by FastAPI [VERIFIED: codebase] |
| pydantic-settings | >=2.13.0 | OBSIDIAN_BASE_URL, OBSIDIAN_API_KEY env vars | Existing pattern in sentinel-core/app/config.py [VERIFIED: codebase] |
| discord.py | >=2.7.0 | Discord embeds (`discord.Embed`) | Already in bot container; no new dependency needed [VERIFIED: codebase] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-asyncio | >=0.23 | Async test support | Already in pathfinder dev deps; `asyncio_mode = "auto"` already set [VERIFIED: pyproject.toml] |
| python-slugify | — | NPC name → filename slug | NOT INSTALLED; use stdlib regex instead (see Don't Hand-Roll) [VERIFIED: pip show] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| GET-then-PUT for multi-field update | Per-field PATCH | PATCH is one call per field; GET-then-PUT is one round-trip for all fields. GET-then-PUT wins for updates touching >1 field. |
| litellm directly in pathfinder | Call sentinel-core /message | /message goes through full AI pipeline with Obsidian context injection — wrong for structured extraction. Direct litellm is correct. |
| stdlib regex slugify | python-slugify | python-slugify handles Unicode; regex is sufficient for PF2e names (ASCII-dominant). Avoid new dependency. |

**Installation (pyproject.toml additions for pathfinder):**
```bash
# Add to modules/pathfinder/pyproject.toml dependencies:
# "litellm>=1.83.0",
# "pydantic-settings>=2.13.0",
```

**Version verification:**
- litellm: `1.83.10` [VERIFIED: pip show litellm 2026-04-22]
- fastapi, httpx, pydantic: already pinned in pathfinder pyproject.toml [VERIFIED: codebase]

---

## Architecture Patterns

### System Architecture Diagram

```
Discord User
    |
    | /sen :pf npc create Varek | young gnome rogue
    v
[interfaces/discord/bot.py]
    _route_message() → handle_sentask_subcommand("pf", "npc create Varek | ...", user_id)
    → _pf_dispatch("npc", "create", "Varek | ...", user_id)
    → SentinelCoreClient._post("/modules/pathfinder/npc/create", payload)
    |
    | POST /modules/pathfinder/npc/create (X-Sentinel-Key)
    v
[sentinel-core/app/routes/modules.py]
    proxy_module("pathfinder", "npc/create")
    → httpx.post("http://pf2e-module:8000/npc/create", body)
    |
    | POST /npc/create
    v
[modules/pathfinder/app/routes/npc.py]
    1. Parse name + description from request
    2. GET /vault/mnemosyne/pf2e/npcs/{slug}.md → 404 (no collision) or 409
    3. litellm.acompletion(extraction_prompt) → JSON with all NPC fields
    4. Build full markdown (frontmatter YAML + ## Stats block)
    5. PUT /vault/mnemosyne/pf2e/npcs/{slug}.md → 200
    → return {"status": "created", "slug": "varek", "path": "mnemosyne/pf2e/npcs/varek.md"}
    |
    v
[Obsidian Local REST API :27123]
    Note written at mnemosyne/pf2e/npcs/varek.md
    |
    v  (response bubbles back)
[bot.py]
    Formats discord.Embed from response data
    → thread.send(embed)
```

**NPC Update (GET-then-PUT pattern):**
```
bot.py → _pf_dispatch("npc", "update", "Varek | now level 7") 
→ POST /modules/pathfinder/npc/update
→ GET /vault/mnemosyne/pf2e/npcs/varek.md (read current note)
→ litellm.acompletion(diff_prompt, current_note + correction) → changed_fields dict
→ Merge changed_fields into parsed frontmatter
→ Rebuild full markdown with updated frontmatter + existing body
→ PUT /vault/mnemosyne/pf2e/npcs/varek.md
```

**NPC Relate (PATCH append — only operation where per-field PATCH is simpler):**
```
bot.py → _pf_dispatch("npc", "relate", "Varek trusts baron-aldric")
→ POST /modules/pathfinder/npc/relate
→ Validate relation type against enum
→ GET /vault/mnemosyne/pf2e/npcs/varek.md (read current relationships list)
→ Append new entry, rebuild relationships list
→ PATCH /vault/mnemosyne/pf2e/npcs/varek.md
    Headers: Target-Type: frontmatter, Target: relationships, Operation: replace, Content-Type: application/json
    Body: [{target: "Baron Aldric", relation: "trusts"}, ...]
```

### Recommended Project Structure
```
modules/pathfinder/
├── app/
│   ├── main.py              # FastAPI app + lifespan (exists) — add npc_router
│   ├── config.py            # NEW: pydantic-settings with OBSIDIAN_BASE_URL, OBSIDIAN_API_KEY, LITELLM_MODEL
│   ├── obsidian.py          # NEW: ObsidianClient (mirrors sentinel-core pattern)
│   ├── llm.py               # NEW: LLMClient wrapping litellm.acompletion()
│   └── routes/
│       └── npc.py           # NEW: NPC CRUD router
├── tests/
│   ├── test_healthz.py      # EXISTS
│   ├── test_registration.py # EXISTS
│   └── test_npc.py          # NEW: NPC endpoint tests
└── pyproject.toml           # MODIFY: add litellm, pydantic-settings deps
```

### Pattern 1: Obsidian GET-then-PUT for NPC Create and Update

**What:** Read existing note (404 = create, 200 = collision/update), build full markdown, PUT.
**When to use:** Creating a new NPC, or updating identity fields (which modifies frontmatter YAML).
**Example:**
```python
# Source: sentinel-core/app/clients/obsidian.py _safe_request pattern [VERIFIED: codebase]
async def create_npc_note(self, slug: str, content: str) -> int:
    """PUT /vault/mnemosyne/pf2e/npcs/{slug}.md — returns HTTP status code."""
    resp = await self._client.put(
        f"{self._base_url}/vault/mnemosyne/pf2e/npcs/{slug}.md",
        headers={**self._headers, "Content-Type": "text/markdown"},
        content=content.encode("utf-8"),
        timeout=10.0,
    )
    return resp.status_code  # 200 = created/replaced, check for collision first
```

### Pattern 2: Obsidian PATCH for Relationships Append

**What:** PATCH a single frontmatter field without fetching the whole note.
**When to use:** Only `relate` command — appending to `relationships` list where current list must be read and replaced atomically.
**Critical finding:** PATCH targets ONE field per request. The `Target` header names the field. [VERIFIED: github.com/coddingtonbear/obsidian-local-rest-api — March 2026]

```python
# Source: Obsidian REST API v3 PATCH spec [VERIFIED: WebFetch coddingtonbear/obsidian-local-rest-api]
# The body is the NEW VALUE for the targeted field, not a dict of fields.
# For relationships (a YAML list), body is the serialized JSON array.
await self._client.patch(
    f"{self._base_url}/vault/mnemosyne/pf2e/npcs/{slug}.md",
    headers={
        **self._headers,
        "Content-Type": "application/json",
        "Target-Type": "frontmatter",
        "Target": "relationships",
        "Operation": "replace",
    },
    content=json.dumps(updated_relationships).encode("utf-8"),
    timeout=10.0,
)
```

**Note on relate:** Even for PATCH-based relate, the current `relationships` list must be read first (GET the note, parse frontmatter) so the new entry can be appended to the existing list. PATCH Operation=replace with the full updated list is the correct approach.

### Pattern 3: NPC Slug Generation

**What:** Convert NPC name to a stable filename slug.
**When to use:** Every create, show, update, relate, import operation.
```python
# Source: stdlib — no external dependency needed [VERIFIED: python3 test 2026-04-22]
import re

def slugify(name: str) -> str:
    """'Baron Aldric' → 'baron-aldric', 'Varek' → 'varek'."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
```

### Pattern 4: LiteLLM Structured Extraction

**What:** Call LiteLLM with a system prompt enforcing JSON output for field extraction.
**When to use:** `npc create` (extract all fields from description) and `npc update` (extract changed fields from correction).
```python
# Source: sentinel-core/app/clients/litellm_provider.py [VERIFIED: codebase]
import json
import litellm

async def extract_npc_fields(name: str, description: str, model: str, api_base: str | None) -> dict:
    """Returns dict of NPC frontmatter fields. Raises on LLM failure."""
    system_prompt = (
        "You are a PF2e Remaster NPC generator. "
        "Extract or infer NPC fields from the description. "
        "Return ONLY a JSON object with these exact keys: "
        "name, level (int, default 1), ancestry, class, traits (list), "
        "personality, backstory, mood (default 'neutral'). "
        "For unspecified fields, randomly select a valid PF2e Remaster option. "
        "Valid ancestries: Human, Elf, Dwarf, Gnome, Halfling, Goblin, Leshy, Ratfolk, Tengu. "
        "Return nothing except the JSON object."
    )
    response = await litellm.acompletion(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Name: {name}\nDescription: {description}"},
        ],
        timeout=60.0,
        **({"api_base": api_base} if api_base else {}),
    )
    content = response.choices[0].message.content
    # Strip markdown code fences if present
    content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(content)
```

### Pattern 5: NPC Markdown Note Format

**What:** Full markdown template for an NPC note.
**When to use:** NPC create, NPC update (full note rebuild).
```markdown
---
name: Varek
level: 5
ancestry: Gnome
class: Rogue
traits:
  - sneaky
  - paranoid
personality: Nervous, evasive, loyal to old crew
backstory: Fled the Thornwood Thieves Guild after...
mood: neutral
relationships: []
imported_from: null
---

## Stats
```yaml
ac: 21
hp: 65
fortitude: +9
reflex: +13
will: +10
speed: 25
skills:
  stealth: +14
  deception: +12
```
```
*Note: The `## Stats` fenced yaml block is written as part of the PUT body. When the stats block is absent (identity-only create), the body ends after the frontmatter closing `---`.*

### Pattern 6: Discord File Attachment for Import

**What:** Discord passes attachment metadata in the message/interaction; httpx fetches the attachment content.
**When to use:** `:pf npc import` with JSON file attached.
**Note on routing:** The `:pf npc import` command arrives as a text prefix command inside `/sen`. Discord prefix commands (`on_message` handler) expose `message.attachments` as a list of `discord.Attachment` objects. However, the current `_route_message` flow strips `:` prefix from the message content only — attachments are not passed through to `handle_sentask_subcommand`. The `_pf_dispatch` handler in bot.py must receive attachments separately.

```python
# Source: discord.py docs — message.attachments[ASSUMED: discord.py v2.7 API]
# In on_message handler:
async def on_message(self, message: discord.Message) -> None:
    # ... existing checks ...
    attachments = list(message.attachments)  # pass to _route_message
    ai_response = await _route_message(user_id, message.content, attachments=attachments)

# In _pf_dispatch for "npc import":
async def _handle_npc_import(attachments: list, user_id: str) -> str:
    if not attachments:
        return "Usage: `:pf npc import` — attach a Foundry actor JSON file."
    attachment = attachments[0]
    async with httpx.AsyncClient() as client:
        resp = await client.get(attachment.url)
        actors = resp.json()
    # POST actors JSON to pathfinder module
    ...
```

**Important:** The current `_route_message` signature does not accept attachments. Adding attachment passthrough requires modifying the `_route_message` and `handle_sentask_subcommand` signatures. This is a non-trivial change to bot.py — plan must account for it.

### Pattern 7: Bot.py _pf_dispatch Integration

The `handle_sentask_subcommand` function has this structure:
```python
async def handle_sentask_subcommand(subcmd: str, args: str, user_id: str) -> str:
```

Adding `_pf_dispatch` requires:
1. A new `elif subcmd == "pf":` branch at the top of `handle_sentask_subcommand`
2. The branch calls `await _pf_dispatch(args, user_id)` (parses `<noun> <verb> <rest>` internally)
3. `_pf_dispatch` calls `SentinelCoreClient._post()` — but `SentinelCoreClient` currently only has `send_message()` method. A new `post_to_module(path, payload, http_client)` method is needed.

```python
# Needed addition to SentinelCoreClient in shared/sentinel_client.py
async def post_to_module(self, module_path: str, payload: dict, client: httpx.AsyncClient) -> dict:
    """POST to /modules/{name}/{path}. Returns parsed JSON dict."""
    resp = await client.post(
        f"{self._base_url}/{module_path.lstrip('/')}",
        json=payload,
        headers={"X-Sentinel-Key": self._api_key},
        timeout=self._timeout,
    )
    resp.raise_for_status()
    return resp.json()
```

### Anti-Patterns to Avoid

- **Routing NPC CRUD through `/message`:** The `/message` endpoint injects Obsidian context and calls LLM through the full conversation pipeline. NPC CRUD bypasses this (D-03). Never call `_call_core()` for NPC operations.
- **Sending a JSON object body to PATCH frontmatter:** The Obsidian PATCH API targets one field via the `Target` header. Sending `{"mood": "hostile", "level": 7}` as the body does NOT update both fields — only the field named in `Target` is updated, and the body is that field's new value. [VERIFIED: WebFetch coddingtonbear/obsidian-local-rest-api 2026-04-22]
- **Using python-slugify for slug generation:** Adds an unnecessary dependency. Stdlib regex handles PF2e names correctly.
- **Calling litellm without markdown code fence stripping:** LMs frequently wrap JSON responses in triple backticks. Always strip before `json.loads()`.
- **Silently overwriting on collision:** D-19 requires 409 + existing path instead of overwrite.
- **Hardcoding the Obsidian base URL:** Must come from `OBSIDIAN_BASE_URL` env var (D-28). In Docker, `http://host.docker.internal:27123` resolves to the Mac host.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async HTTP client | Custom httpx wrapper | httpx.AsyncClient in `_safe_request` pattern | Already proven in sentinel-core/app/clients/obsidian.py |
| LLM provider abstraction | Direct litellm.acompletion() call | litellm.acompletion() — already installed | No new code needed; same pattern as LiteLLMProvider |
| JSON parsing with error handling | Try/except json.loads() | Use `json.loads()` with `.strip()` + code fence stripping | LLM output is predictable with system prompt constraints |
| Slugify | Custom transliteration | stdlib `re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")` | One line, no dependency |
| YAML frontmatter parsing | Full YAML parser | Use `yaml` (stdlib in Python 3.12? No — use PyYAML) or string splitting | For GET-then-PUT pattern, parse frontmatter between `---` delimiters |

**Note on YAML parsing:** Python stdlib does not include PyYAML. For GET-then-PUT update pattern, frontmatter must be parsed. Options: (1) add `pyyaml` dependency, (2) use a simple string split on `---` and `json.loads()` if the frontmatter is machine-written (it always is for Sentinel NPCs). Since Sentinel writes the frontmatter (machine-generated, predictable structure), `pyyaml.safe_load()` is the safe choice. [ASSUMED — pyyaml not checked in pathfinder pyproject.toml]

---

## Runtime State Inventory

> Not a rename/refactor phase. No runtime state audit required.

---

## Common Pitfalls

### Pitfall 1: Obsidian PATCH Targets One Field at a Time

**What goes wrong:** Code sends `PATCH /vault/npc.md` with body `{"mood": "hostile", "level": 7}` expecting both to update. Only the field in the `Target` header is changed; the body is interpreted as the value for that one field.

**Why it happens:** CONTEXT.md D-29 described the body as a JSON object "with only the fields to update" — which reads like a multi-field merge, but the actual API contract uses `Target` header to name the single field.

**How to avoid:** Use GET-then-PUT for multi-field updates. Only use PATCH for single-field replace (e.g., `relationships` list). When in doubt, GET the full note, modify in memory, PUT it back.

**Warning signs:** Fields unchanged after update, no error returned (200 status but other fields not updated).

### Pitfall 2: LLM Returns JSON Wrapped in Markdown Code Fences

**What goes wrong:** `json.loads(response)` throws `JSONDecodeError` on `{"name": "Varek"}` wrapped in ` ```json\n...\n``` `.

**Why it happens:** Most LLMs (especially instruction-tuned models) wrap code in markdown even when told not to.

**How to avoid:** Always strip ` ```json`, ` ``` `, and leading/trailing whitespace before `json.loads()`.

**Warning signs:** `JSONDecodeError: Expecting value: line 1 column 1` on create/update commands.

### Pitfall 3: Discord Attachments Not Passed Through Subcommand Router

**What goes wrong:** `:pf npc import` command is received but `handle_sentask_subcommand` has no access to `message.attachments` because the current routing chain only passes `subcmd`, `args`, and `user_id`.

**Why it happens:** The existing subcommand design assumes text-only commands. Attachments are a new concept.

**How to avoid:** Plan must include signature extension for `_route_message`, `handle_sentask_subcommand`, and `_pf_dispatch` to accept an optional `attachments` parameter. See Pattern 6 above.

**Warning signs:** Import command says "no attachment found" even when user attached a file.

### Pitfall 4: SENTINEL_CORE_URL vs Host Network Confusion

**What goes wrong:** Pathfinder module tries to reach Obsidian at `http://sentinel-core:8000/...` instead of `http://host.docker.internal:27123`.

**Why it happens:** Developers confuse the two env vars. `SENTINEL_CORE_URL` points to sentinel-core (for registration). `OBSIDIAN_BASE_URL` (new in this phase) points to the Mac host running Obsidian.

**How to avoid:** Separate `Settings` fields with distinct names. Never reuse SENTINEL_CORE_URL for Obsidian calls.

### Pitfall 5: Pipe Character in Discord Message Content

**What goes wrong:** `:pf npc create Varek | young gnome | nervous` — splitting on `|` gives three parts, not two (name + description). If the description itself contains a pipe (e.g., for stat formatting), name parsing breaks.

**Why it happens:** Simple `split("|", 1)` avoids this. Splitting on maxsplit=1 handles it correctly.

**How to avoid:** Always use `content.split("|", 1)` — maxsplit=1 ensures only the first pipe separates name from description.

### Pitfall 6: NPC Note Path Case Sensitivity on macOS vs Linux

**What goes wrong:** `varek.md` and `Varek.md` are the same file on macOS (HFS+ case-insensitive) but different on Linux (ext4 case-sensitive). The slug must be normalized to lowercase.

**Why it happens:** Development on macOS masks this bug.

**How to avoid:** `slugify()` always lowercases. Vault path construction uses the slug, never the raw name.

### Pitfall 7: REGISTRATION_PAYLOAD Missing NPC Routes

**What goes wrong:** `GET /modules` lists the pathfinder module but not the NPC routes, so sentinel-core's module proxy doesn't know the routes exist.

**Why it happens:** The `routes` list in `REGISTRATION_PAYLOAD` in `main.py` was only populated with `healthz` in Phase 28.

**How to avoid:** The plan must update `REGISTRATION_PAYLOAD` to include all NPC route paths: `npc/create`, `npc/update`, `npc/show`, `npc/relate`, `npc/import`.

---

## Code Examples

### NPC Create Endpoint (pathfinder module)

```python
# Source: Follows FastAPI + httpx pattern from sentinel-core [VERIFIED: codebase]
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/npc")

class NPCCreateRequest(BaseModel):
    name: str
    description: str = ""
    user_id: str

@router.post("/create")
async def create_npc(req: NPCCreateRequest) -> JSONResponse:
    slug = slugify(req.name)
    # 1. Collision check
    existing = await obsidian_client.get_note(f"mnemosyne/pf2e/npcs/{slug}.md")
    if existing is not None:
        raise HTTPException(status_code=409, detail={
            "error": "NPC already exists",
            "path": f"mnemosyne/pf2e/npcs/{slug}.md"
        })
    # 2. LLM extraction
    fields = await extract_npc_fields(req.name, req.description)
    # 3. Build markdown + PUT
    content = build_npc_markdown(fields)
    await obsidian_client.put_note(f"mnemosyne/pf2e/npcs/{slug}.md", content)
    return JSONResponse({"status": "created", "slug": slug, "path": f"mnemosyne/pf2e/npcs/{slug}.md", **fields})
```

### NPC Show — Obsidian GET + Discord Embed

```python
# Source: sentinel-core ObsidianClient.get_user_context() pattern [VERIFIED: codebase]
# + discord.py Embed API [ASSUMED: discord.py v2.7]
async def build_npc_embed(npc_data: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"{npc_data['name']} (Level {npc_data.get('level', '?')} {npc_data.get('ancestry', '')} {npc_data.get('class', '')})",
        description=f"{npc_data.get('personality', '')}\n\n{npc_data.get('backstory', '')[:200]}...",
        color=discord.Color.dark_gold(),
    )
    stats = npc_data.get("stats", {})
    if stats:
        embed.add_field(name="AC", value=str(stats.get("ac", "—")), inline=True)
        embed.add_field(name="HP", value=str(stats.get("hp", "—")), inline=True)
        embed.add_field(name="Fort/Ref/Will", value=f"{stats.get('fortitude','—')}/{stats.get('reflex','—')}/{stats.get('will','—')}", inline=True)
    embed.set_footer(text=f"Mood: {npc_data.get('mood', 'neutral')} | mnemosyne/pf2e/npcs/{npc_data['slug']}.md")
    return embed
```

### SentinelCoreClient Extension

```python
# Source: shared/sentinel_client.py — new method following existing _post pattern [VERIFIED: codebase]
async def post_to_module(self, path: str, payload: dict, client: httpx.AsyncClient) -> dict:
    """POST to a module proxy path (e.g., 'modules/pathfinder/npc/create')."""
    resp = await client.post(
        f"{self._base_url}/{path.lstrip('/')}",
        json=payload,
        headers={"X-Sentinel-Key": self._api_key},
        timeout=self._timeout,
    )
    resp.raise_for_status()
    return resp.json()
```

### Foundry JSON Import — Defensive Parsing

```python
# Source: D-25 defensive parsing requirement [VERIFIED: CONTEXT.md]
def parse_foundry_actor(actor: dict) -> dict | None:
    """Extract identity fields from a Foundry actor dict. Returns None if name missing."""
    name = actor.get("name") or actor.get("data", {}).get("name")
    if not name:
        return None
    return {
        "name": name,
        "level": actor.get("system", {}).get("details", {}).get("level", {}).get("value", 1),
        "ancestry": actor.get("system", {}).get("details", {}).get("ancestry", {}).get("value", ""),
        "class": actor.get("system", {}).get("details", {}).get("class", {}).get("value", ""),
        "traits": actor.get("system", {}).get("traits", {}).get("value", []),
        "imported_from": "foundry",
    }
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Obsidian PATCH v2 (Heading header) | PATCH v3 (Target-Type + Target + Operation headers) | API v3.0 (Nov 2024) | New headers required; v2 still works if Target-Type omitted |
| PATCH body = JSON dict of all fields | PATCH body = single field value, Target header names field | v3.6.0 (2024) | Multi-field updates require GET-then-PUT or multiple PATCH calls |
| discord.py hiatus forks (py-cord) | discord.py v2.7.x (March 2026) | 2023 | discord.py is the canonical library again |

**Deprecated/outdated:**
- Obsidian PATCH v2 (`Heading` header, `Content-Insertion-Position` header): still works but undocumented. Don't use for new code.
- `Content-Insertion-Position: end` (v2 header): replaced by `Operation: append` in v3.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | pyyaml is not in pathfinder pyproject.toml and must be added | Don't Hand-Roll, Code Examples | Low — easy to add; fails at import time, not silently |
| A2 | discord.Embed API in v2.7 unchanged from v2.x pattern (color, add_field, set_footer) | Code Examples | Low — discord.py embed API is stable across v2.x |
| A3 | `_route_message` and `handle_sentask_subcommand` signatures must be extended with optional `attachments` parameter | Architecture Patterns (Pattern 6) | Medium — if `/sen` slash command doesn't surface attachments, import is impossible; needs verification |
| A4 | The existing `/sen` slash command interaction passes file attachments through `message.attachments` in the `on_message` handler | Common Pitfalls (Pitfall 3) | High if wrong — import command cannot work without this. Slash command interactions may handle attachments differently than message attachments. |
| A5 | Foundry actor JSON structure uses `system.details.level.value` / `system.details.ancestry.value` path | Code Examples (Foundry parsing) | Medium — PF2e Foundry schema evolves. Phase 30 derives canonical schema; Phase 29 import is identity-only, errors tolerated. Defensive parsing returns None on missing fields. |

**A4 expanded:** Discord slash commands (`/sen`) use `discord.Interaction` which does not inherently support file attachments in the `message` parameter of type `str`. For `:pf npc import` to work, the Discord message must be a regular message (thread reply or prefix command) not a slash command invocation. Since the `on_message` handler covers thread replies and the `_route_message` flow handles `:pf` prefix, import works correctly through thread replies with attachments. The `/sen` slash command's `message: str` parameter cannot carry attachments — this is a Discord API constraint. The import command works in thread reply context, not slash command context. **This does not require a separate slash command** — it works naturally through the thread reply flow.

---

## Open Questions

1. **Does pyyaml need to be added to pathfinder pyproject.toml?**
   - What we know: Python stdlib has no YAML parser. The GET-then-PUT update pattern requires parsing existing frontmatter. Sentinel writes frontmatter in a predictable format.
   - What's unclear: Whether a simpler string-split approach suffices vs. needing full YAML parsing.
   - Recommendation: Add `pyyaml>=6.0` to pathfinder dependencies. Frontmatter is machine-generated but may contain multiline strings (backstory) that string-split handles poorly.

2. **How does the `:pf` prefix interact with the existing subcommand parser?**
   - What we know: `handle_sentask_subcommand` receives `subcmd = "pf"` and `args = "npc create Varek | ..."`. The new `elif subcmd == "pf":` branch routes to `_pf_dispatch`.
   - What's unclear: None — the existing pattern is clear from reading bot.py.
   - Recommendation: Add `elif subcmd == "pf":` as the first branch in `handle_sentask_subcommand` (before the plugin: check) to keep PF routing fast.

3. **Does litellm need to be in the pathfinder container image?**
   - What we know: litellm is installed host-side (pip show confirms 1.83.10) but is NOT in pathfinder's `pyproject.toml` dependencies.
   - What's unclear: Nothing — it must be added to pyproject.toml for the container to have it.
   - Recommendation: Add `"litellm>=1.83.0"` to `modules/pathfinder/pyproject.toml` dependencies.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Obsidian Local REST API | All NPC persistence | User-operational | v3.6.x assumed | — (no fallback; Obsidian must be running) |
| litellm | NPC create, update LLM extraction | Host: ✓ | 1.83.10 | — (must add to pathfinder pyproject.toml) |
| LM Studio (or configured AI provider) | LLM calls | Operational dependency | User-configured | Claude fallback if ANTHROPIC_API_KEY set |
| pyyaml | Frontmatter parsing in GET-then-PUT | Not in pathfinder pyproject.toml | — | String split (fragile for multiline values) |
| discord.py | Discord embed building | ✓ (in bot container) | >=2.7.0 | — |

**Missing dependencies with no fallback:**
- `litellm` in pathfinder container (must add to pyproject.toml)
- `pyyaml` in pathfinder container (must add to pyproject.toml)

**Missing dependencies with fallback:**
- None

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `modules/pathfinder/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd modules/pathfinder && python -m pytest tests/ -x -q` |
| Full suite command | `cd modules/pathfinder && python -m pytest tests/ -v` |

`asyncio_mode = "auto"` is already set in pyproject.toml. [VERIFIED: codebase]

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NPC-01 | POST /npc/create returns 200 + slug; Obsidian PUT called with correct path | unit (mocked Obsidian + LLM) | `pytest tests/test_npc.py::test_npc_create_success -x` | ❌ Wave 0 |
| NPC-01 | POST /npc/create returns 409 when note already exists | unit (mocked Obsidian GET 200) | `pytest tests/test_npc.py::test_npc_create_collision -x` | ❌ Wave 0 |
| NPC-02 | POST /npc/update reads note, sends to LLM, PUTs updated note | unit (mocked Obsidian GET + PUT) | `pytest tests/test_npc.py::test_npc_update_identity_fields -x` | ❌ Wave 0 |
| NPC-03 | POST /npc/show returns parsed NPC dict with all expected keys | unit (mocked Obsidian GET 200) | `pytest tests/test_npc.py::test_npc_show_returns_fields -x` | ❌ Wave 0 |
| NPC-03 | POST /npc/show returns 404 when NPC not found | unit (mocked Obsidian GET 404) | `pytest tests/test_npc.py::test_npc_show_not_found -x` | ❌ Wave 0 |
| NPC-04 | POST /npc/relate appends to relationships; rejects invalid relation type | unit (mocked Obsidian) | `pytest tests/test_npc.py::test_npc_relate_valid -x` | ❌ Wave 0 |
| NPC-04 | POST /npc/relate returns 422 for invalid relation type | unit | `pytest tests/test_npc.py::test_npc_relate_invalid_type -x` | ❌ Wave 0 |
| NPC-05 | POST /npc/import creates notes for each actor; returns summary | unit (mocked Obsidian, sample Foundry JSON) | `pytest tests/test_npc.py::test_npc_import_basic -x` | ❌ Wave 0 |
| NPC-05 | Import skips and reports collision NPCs | unit | `pytest tests/test_npc.py::test_npc_import_collision_skipped -x` | ❌ Wave 0 |
| (bot) | _pf_dispatch routes `:pf npc create` to SentinelCoreClient | unit (mocked client) | `pytest interfaces/discord/tests/test_subcommands.py::test_pf_dispatch_create -x` | ❌ Wave 0 |
| (bot) | _pf_dispatch returns error embed for invalid relation type | unit | `pytest interfaces/discord/tests/test_subcommands.py::test_pf_dispatch_relate_invalid -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd modules/pathfinder && python -m pytest tests/ -x -q`
- **Per wave merge:** `cd modules/pathfinder && python -m pytest tests/ -v && cd interfaces/discord && python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `modules/pathfinder/tests/test_npc.py` — covers NPC-01 through NPC-05
- [ ] `interfaces/discord/tests/test_subcommands.py` — add `test_pf_dispatch_*` cases (file exists, extend it)
- [ ] Framework: already configured — no install needed

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | NPC commands inherit bot auth (X-Sentinel-Key on module proxy) |
| V3 Session Management | no | Stateless CRUD endpoints |
| V4 Access Control | yes | X-Sentinel-Key forwarded by sentinel-core to pathfinder; pathfinder must verify it |
| V5 Input Validation | yes | Pydantic models on all request bodies; relation type enum validation |
| V6 Cryptography | no | No new crypto operations |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Obsidian path traversal via NPC name | Tampering | slugify() strips all non-alphanum chars; `../` becomes empty or `-` |
| LLM prompt injection via NPC description | Tampering | System prompt clearly constrains output format; JSON parse failure = safe error |
| Foundry JSON bomb (deeply nested, huge file) | DoS | httpx attachment fetch with timeout (10s); parse with recursion limit |
| Unauthenticated access to NPC create/update | Spoofing | X-Sentinel-Key forwarded and verified; existing APIKeyMiddleware covers sentinel-core routes |

---

## Sources

### Primary (HIGH confidence)
- `sentinel-core/app/clients/obsidian.py` — existing ObsidianClient patterns (PUT, GET, PATCH in `_persist_thread_id`)
- `interfaces/discord/bot.py` — existing subcommand routing, `handle_sentask_subcommand`, discord.Embed absence (D-21 pattern)
- `modules/pathfinder/app/main.py` — existing FastAPI + lifespan + registration pattern
- `modules/pathfinder/pyproject.toml` — confirmed dependencies
- `shared/sentinel_client.py` — `SentinelCoreClient.send_message()` pattern for new `post_to_module`
- `sentinel-core/app/routes/modules.py` — proxy pattern; confirmed POST and GET proxy routes
- `sentinel-core/app/clients/litellm_provider.py` — LiteLLM call pattern
- `sentinel-core/app/config.py` — pydantic-settings pattern for new pathfinder config
- github.com/coddingtonbear/obsidian-local-rest-api [March 2026] — PATCH API v3 semantics, Target-Type/Target/Operation headers
- deepwiki.com/coddingtonbear/obsidian-local-rest-api/6.1-patch-operations [Dec 2025] — confirmed single-field PATCH behavior

### Secondary (MEDIUM confidence)
- deepwiki.com/MarkusPfundstein/mcp-obsidian — PATCH frontmatter Content-Type: application/json example
- pip show litellm [verified host 2026-04-22] — version 1.83.10

### Tertiary (LOW confidence)
- None — all critical claims verified from codebase or official docs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified in pathfinder pyproject.toml and codebase
- Architecture: HIGH — follows established Phase 27/28 patterns exactly
- Obsidian PATCH semantics: HIGH — verified via official GitHub repo and DeepWiki docs
- Discord attachment flow: MEDIUM — A4 assumption logged; bot.py read confirms `on_message` has `message.attachments`; slash command limitation is a Discord API constraint (ASSUMED for exact behavior)
- Foundry JSON schema: LOW — PF2e Foundry schema is not verified in this session; Phase 29 uses defensive parsing so low risk

**Research date:** 2026-04-22
**Valid until:** 2026-05-22 (stable APIs; Obsidian REST API PATCH semantics are stable since v3.0)
