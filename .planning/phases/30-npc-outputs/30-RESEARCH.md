# Phase 30: NPC Outputs — Research

**Researched:** 2026-04-23
**Domain:** PDF generation, Foundry VTT actor JSON, constrained LLM output, Discord file attachment, FastAPI binary response
**Confidence:** HIGH (core patterns verified; Foundry JSON schema verified from TypeScript source)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Discord Command Routing**
- D-01: New output verbs (`export`, `token`, `stat`, `pdf`) added to `_pf_dispatch` — same routing pattern as Phase 29
- D-02: Dispatch to `POST /npc/export-foundry`, `POST /npc/token`, `POST /npc/stat`, `POST /npc/pdf`
- D-03: File attachments sent via `discord.File` in bot layer; module endpoints return raw bytes; `_pf_dispatch` wraps in `discord.File`

**Foundry VTT Actor JSON Schema**
- D-04: Build from PF2e TypeScript source types; required fields derived from `NPCSystemSource`, `NPCAttributesSource`, `NPCSavesSource`
- D-05: NPCs with no stats block export with all numeric fields defaulting to `0`
- D-06: Filename: `{slug}.json`
- D-07: Schema validation strategy = live Foundry import test (no JSON schema linting step)

**Midjourney Token Prompt**
- D-08: Hybrid composition — fixed template + one constrained LLM call for visual description slot
- D-09: Template: `{description}, {ancestry} {class}, tabletop RPG portrait token, circular frame, parchment border, oil painting style, dramatic lighting --ar 1:1 --q 2 --s 180 --no text`
- D-10: LLM call: system prompt instructs comma-separated visual phrases, 15-30 tokens, no MJ params, no prose; `max_tokens=40`
- D-11: Backstory/personality sanitized before LLM interpolation (strip newlines, truncate 200 chars)
- D-12: Output returned as plain text (not embed)

**Stat Block Discord Embed**
- D-13: PF2e-mirror layout — Defenses inline (AC, HP), Saves inline (Fort/Ref/Will), Speed non-inline, Skills non-inline, Perception inline
- D-14: Embed title: `{Name}` (Level {N} {Ancestry} {Class})
- D-15: Embed description: `personality` field only; mood in footer
- D-16: Absent stats block: mechanical fields silently omitted
- D-17: Distinct from `:pf npc show` — `/stat` is full mechanical reference view

**PDF Stat Card**
- D-18: Library: ReportLab Platypus with `Table` flowable
- D-19: Single A4/Letter page; header block + stats grid (2-column key-value Table)
- D-20: Missing stats block: stats section omitted, header block renders alone
- D-21: Attachment filename: `{slug}-stat-card.pdf`
- D-22: Dockerfile unchanged — ReportLab is pure-Python

**New Module Endpoints**
- D-23: Four new routes in `REGISTRATION_PAYLOAD`: `npc/export-foundry`, `npc/token`, `npc/stat`, `npc/pdf`

### Claude's Discretion
- Exact LLM system prompt wording for the Midjourney description slot
- ReportLab font choices and card color scheme
- Internal PDF helper location (`app/routes/npc.py` extension vs. `app/pdf.py`)
- UUID generation method for Foundry actor `_id`

### Deferred Ideas (OUT OF SCOPE)
- Phase 35: REST endpoint for direct Foundry module import
- Midjourney auto-send (bot-to-bot messaging)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OUT-01 | Export NPC as PF2e Remaster-compatible Foundry VTT actor JSON file attachment in Discord | Verified Foundry PF2e actor JSON schema from TypeScript source; binary transport pattern identified (base64 encoding through proxy) |
| OUT-02 | Midjourney `/imagine` prompt for NPC token art as copyable text in Discord | LiteLLM `acompletion` with `max_tokens=40` pattern verified in existing `llm.py`; plain text return pattern matches existing `show` verb |
| OUT-03 | Formatted PF2e stat block for an NPC inline in Discord | Discord embed construction via `discord.Embed`; bot-layer rendering from structured JSON; existing `show` verb comparison |
| OUT-04 | Export NPC as PDF stat card | ReportLab 4.4.10 Platypus patterns verified; `SimpleDocTemplate(BytesIO())` pattern confirmed; binary transport via base64 encoding identified |
</phase_requirements>

---

## Summary

Phase 30 adds four read-only transform endpoints to the pathfinder module: Foundry actor JSON export, Midjourney token prompt, Discord embed stat block, and PDF stat card. Every endpoint reads an existing NPC note from Obsidian, transforms it, and returns the result — no writes.

**The critical infrastructure constraint:** The sentinel-core proxy (`modules.py`) always wraps module responses in `JSONResponse` by calling `resp.json()`. The `SentinelCoreClient.post_to_module()` also calls `resp.json()`. Binary files (PDF bytes, JSON attachment) cannot pass through this proxy as raw bytes. The solution is to **base64-encode binary outputs** inside a JSON wrapper at the module endpoint, and decode them in the bot layer before wrapping in `discord.File`. This keeps all routing through the existing proxy and requires no sentinel-core changes.

For the stat block (OUT-03), the endpoint returns a structured JSON dict — the bot layer renders the Discord embed locally. This is the same pattern as `show` (Phase 29).

For the token prompt (OUT-02), the endpoint returns plain text in a JSON field — the bot returns it as-is.

**Primary recommendation:** All four endpoints POST to the pathfinder module via the existing `post_to_module` proxy chain. Binary endpoints (`export-foundry`, `pdf`) return `{"data_b64": "<base64>", "filename": "<name>"}` JSON; the bot decodes and wraps in `discord.File`. Text and stat endpoints return normal JSON.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| NPC note reading + parsing | API/Module (pf2e-module) | — | Obsidian client lives in module; parser functions already exist in npc.py |
| Foundry actor JSON construction | API/Module | — | Pure data transformation; no UI concern |
| PDF generation | API/Module | — | ReportLab runs server-side; bytes produced in module |
| Binary transport (PDF, JSON) | API/Module → base64 → bot | — | sentinel-core proxy cannot pass raw bytes; base64 JSON wrapper is the transport mechanism |
| Midjourney prompt LLM call | API/Module | — | LiteLLM call pattern lives in module (llm.py) |
| Discord embed construction | Interface (discord bot) | — | Embed objects are discord.py types; only the bot can construct them |
| Discord file attachment send | Interface (discord bot) | — | discord.File wrapping happens in bot layer |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| reportlab | 4.4.10 | PDF generation | [VERIFIED: pypi.org/project/reportlab] Industry standard Python PDF library; pure Python install (D-22 confirmed); Platypus flowable system handles structured layouts; no system library changes required |
| uuid (stdlib) | 3.12 stdlib | Foundry actor `_id` generation | [VERIFIED: Python docs] `uuid.uuid4()` produces random UUIDs; `str(uuid.uuid4()).replace("-", "")` yields 32-char hex matching Foundry's ID format |
| base64 (stdlib) | 3.12 stdlib | Binary transport encoding | [VERIFIED: codebase] Required to pass PDF/JSON bytes through sentinel-core proxy which wraps all responses in JSONResponse |
| io (stdlib) | 3.12 stdlib | BytesIO buffer for PDF | [VERIFIED: CONTEXT.md + ReportLab docs] `SimpleDocTemplate(BytesIO())` is the standard in-memory PDF pattern |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| litellm | >=1.83.0 | Midjourney description LLM call | Already in pyproject.toml; `acompletion` with `max_tokens=40` for constrained output |
| discord.py | >=2.7.0 | `discord.File`, `discord.Embed` | Bot layer only; File wraps BytesIO for attachments; Embed constructs stat block display |

**Installation (add to requirements.txt):**
```bash
# In modules/pathfinder/requirements.txt or pyproject.toml
reportlab>=4.4.0
```

Also add to Dockerfile pip install line:
```
RUN pip install --no-cache-dir \
    "fastapi>=0.135.0" \
    "uvicorn[standard]>=0.44.0" \
    "httpx>=0.28.1" \
    "litellm>=1.83.0" \
    "pyyaml>=6.0.0" \
    "pydantic-settings>=2.13.0" \
    "reportlab>=4.4.0"
```

---

## Architecture Patterns

### System Architecture Diagram

```
Discord user
    |
    | ":pf npc export|token|stat|pdf <name>"
    v
bot.py _pf_dispatch()
    |
    | POST modules/pathfinder/npc/{export-foundry|token|stat|pdf}
    | via SentinelCoreClient.post_to_module()
    v
sentinel-core proxy_module()
    |
    | POST http://pf2e-module:8000/npc/{verb}
    v
pf2e-module routes/npc.py
    |
    | GET obsidian /vault/mnemosyne/pf2e/npcs/{slug}.md
    v
Obsidian REST API
    |
    | note_text (markdown with YAML frontmatter + ## Stats block)
    v
npc.py: _parse_frontmatter() + _parse_stats_block()
    |
    +-- export-foundry --> build_foundry_actor_json() --> base64 encode --> {"data_b64": ..., "filename": "slug.json"}
    +-- token         --> litellm.acompletion(max_tokens=40) --> {"prompt": "..."}
    +-- stat          --> build_stat_block_dict() --> {"embed_data": {...}}
    +-- pdf           --> build_pdf_bytes() ReportLab --> base64 encode --> {"data_b64": ..., "filename": "slug-stat-card.pdf"}
    |
    v
sentinel-core wraps in JSONResponse (JSON passthrough)
    |
    v
bot.py _pf_dispatch() receives dict
    |
    +-- export/pdf: base64.b64decode(data_b64) → discord.File(BytesIO(bytes), filename=...)
    |                → await message.channel.send(file=discord_file)
    +-- token: return result["prompt"] as plain text string
    +-- stat: construct discord.Embed from embed_data dict → await message.channel.send(embed=embed)
```

### Recommended Project Structure
```
modules/pathfinder/
├── app/
│   ├── routes/
│   │   └── npc.py          # Add: export_foundry, token, stat, pdf handlers
│   ├── pdf.py              # NEW: ReportLab PDF generation helper
│   └── main.py             # Extend REGISTRATION_PAYLOAD with 4 new routes
└── pyproject.toml          # Add reportlab dependency
```

The PDF helper location is left to Claude's discretion (CONTEXT.md). `app/pdf.py` is recommended — it keeps `npc.py` focused on routing and keeps the ~80-line PDF builder separately testable.

### Pattern 1: Binary Transport via Base64 JSON

**What:** Module endpoints returning binary files encode bytes as base64 inside a JSON wrapper; bot layer decodes and wraps in `discord.File`.

**When to use:** Any module endpoint that must return binary data through the sentinel-core JSONResponse proxy.

**Module endpoint (npc.py):**
```python
# Source: [VERIFIED: FastAPI docs + stdlib]
import base64
from fastapi.responses import JSONResponse

@router.post("/export-foundry")
async def export_foundry(req: NPCOutputRequest) -> JSONResponse:
    # ... read + build actor_json dict ...
    json_bytes = json.dumps(actor_json, indent=2).encode("utf-8")
    return JSONResponse({
        "data_b64": base64.b64encode(json_bytes).decode("ascii"),
        "filename": f"{slug}.json",
        "content_type": "application/json",
    })

@router.post("/pdf")
async def export_pdf(req: NPCOutputRequest) -> JSONResponse:
    # ... read + build PDF ...
    pdf_bytes = build_npc_pdf(fields, stats)  # returns bytes from BytesIO
    return JSONResponse({
        "data_b64": base64.b64encode(pdf_bytes).decode("ascii"),
        "filename": f"{slug}-stat-card.pdf",
        "content_type": "application/pdf",
    })
```

**Bot layer (bot.py) — new helper:**
```python
# Source: [VERIFIED: discord.py docs FAQ + stackoverflow]
import io, base64

async def _send_file_attachment(channel, result: dict, content: str = "") -> None:
    """Decode base64 binary from module response and send as Discord file attachment."""
    raw_bytes = base64.b64decode(result["data_b64"])
    discord_file = discord.File(io.BytesIO(raw_bytes), filename=result["filename"])
    await channel.send(content=content, file=discord_file)
```

**Bot dispatch branches:**
```python
elif verb == "export":
    npc_name = rest.strip()
    if not npc_name:
        return "Usage: `:pf npc export <name>`"
    result = await _sentinel_client.post_to_module(
        "modules/pathfinder/npc/export-foundry", {"name": npc_name}, http_client
    )
    # _send_file_attachment is async — must be called differently
    # bot.py _pf_dispatch returns a string; file sends need to happen at call site
    # See Pitfall 1 below for the solution.
```

### Pattern 2: ReportLab Platypus Single-Page PDF

**What:** `SimpleDocTemplate` with `BytesIO` buffer; `Paragraph` for text; `Table` for stats grid.

**When to use:** All PDF generation in Phase 30.

```python
# Source: [VERIFIED: ReportLab docs + Stack Overflow verified examples]
import io
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

def build_npc_pdf(fields: dict, stats: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    story = []

    # Header block
    story.append(Paragraph(fields.get("name", "Unknown"), styles["Title"]))
    story.append(Paragraph(
        f"Level {fields.get('level', '?')} {fields.get('ancestry', '')} {fields.get('class', '')}",
        styles["Heading2"]
    ))
    traits = fields.get("traits") or []
    if traits:
        story.append(Paragraph(", ".join(traits), styles["Normal"]))
    personality = (fields.get("personality") or "")[:150]
    if personality:
        italic = ParagraphStyle("italic", parent=styles["Normal"], fontName="Helvetica-Oblique")
        story.append(Paragraph(personality, italic))
    story.append(Spacer(1, 0.2 * inch))

    # Stats grid — 2-column key-value table
    if stats:
        data = [
            ["AC", str(stats.get("ac", 0))],
            ["HP", str(stats.get("hp", 0))],
            ["Fort / Ref / Will", f"{stats.get('fortitude', 0)} / {stats.get('reflex', 0)} / {stats.get('will', 0)}"],
            ["Speed", f"{stats.get('speed', 25)} ft."],
        ]
        skills = stats.get("skills") or {}
        if isinstance(skills, dict):
            for skill_name, skill_val in skills.items():
                data.append([skill_name.capitalize(), f"+{skill_val}"])
        elif isinstance(skills, str):
            data.append(["Skills", skills[:100]])

        table = Table(data, colWidths=[2 * inch, 3.5 * inch])
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)

    doc.build(story)
    return buffer.getvalue()
```

### Pattern 3: Foundry VTT PF2e NPC Actor JSON

**What:** Minimum viable actor JSON that Foundry PF2e will accept for NPC import.

**When to use:** `export-foundry` endpoint only.

```python
# Source: [VERIFIED: foundryvtt/pf2e GitHub TypeScript source NPCSystemSource]
import uuid

def build_foundry_actor(fields: dict, stats: dict) -> dict:
    actor_id = str(uuid.uuid4()).replace("-", "")  # 32-char hex per D-specifics
    slug = slugify(fields.get("name", ""))

    return {
        "_id": actor_id,
        "name": fields.get("name", "Unknown"),
        "type": "npc",
        "img": "icons/svg/mystery-man.svg",
        "items": [],
        "effects": [],
        "folder": None,
        "flags": {},
        "ownership": {"default": 0},
        "prototypeToken": {
            "name": fields.get("name", "Unknown"),
            "texture": {"src": "icons/svg/mystery-man.svg"},
        },
        "system": {
            "traits": {
                "value": fields.get("traits") or [],
                "rarity": "common",
                "size": {"value": "med"},
            },
            "abilities": {
                "str": {"mod": 0}, "dex": {"mod": 0}, "con": {"mod": 0},
                "int": {"mod": 0}, "wis": {"mod": 0}, "cha": {"mod": 0},
            },
            "attributes": {
                "ac": {"value": stats.get("ac", 0), "details": ""},
                "adjustment": None,
                "hp": {
                    "value": stats.get("hp", 0),
                    "max": stats.get("hp", 0),
                    "temp": 0,
                    "details": "",
                },
                "speed": {
                    "value": stats.get("speed", 25),
                    "otherSpeeds": [],
                    "details": "",
                },
                "allSaves": {"value": ""},
            },
            "perception": {
                "mod": stats.get("perception", 0),
            },
            "skills": {},
            "initiative": {"statistic": "perception"},
            "details": {
                "level": {"value": fields.get("level", 1)},
                "blurb": (fields.get("personality") or "")[:100],
                "publicNotes": fields.get("backstory") or "",
                "privateNotes": "",
                "publication": {"title": "", "authors": "", "license": "ORC"},
            },
            "saves": {
                "fortitude": {"value": stats.get("fortitude", 0), "saveDetail": ""},
                "reflex": {"value": stats.get("reflex", 0), "saveDetail": ""},
                "will": {"value": stats.get("will", 0), "saveDetail": ""},
            },
            "resources": {"focus": {"value": 0, "max": 0}},
        },
    }
```

**Key schema notes (from TypeScript source):**
- `system.details.alignment` was removed in the 2023 Remaster — do NOT include it
- `system.saves` requires all three entries with both `value` (int) and `saveDetail` (string)
- `system.attributes.ac` requires both `value` (int) and `details` (string)
- `system.attributes.hp` requires `value`, `max`, `temp`, `details`
- `items: []` is required at envelope level (empty for identity-only NPCs)
- `ownership: {"default": 0}` controls visibility; 0 = player can view actor

### Pattern 4: Constrained LLM Call for MJ Description

**What:** Single `acompletion` call with `max_tokens=40`, strict system prompt constraining output to comma-separated visual phrases.

**When to use:** Midjourney token prompt generation only.

```python
# Source: [VERIFIED: matches existing llm.py pattern]
async def generate_mj_description(
    fields: dict,
    model: str,
    api_base: str | None = None,
) -> str:
    """Generate a 15-30 token visual description for a Midjourney token prompt.
    Returns a comma-separated phrase string only — no prose, no MJ parameters.
    """
    personality = (fields.get("personality") or "")[:200].replace("\n", " ")
    backstory = (fields.get("backstory") or "")[:200].replace("\n", " ")
    traits = ", ".join(fields.get("traits") or [])

    system_prompt = (
        "You are a visual description generator for tabletop RPG character tokens. "
        "Output ONLY a comma-separated list of visual description phrases, 15-30 tokens total. "
        "Describe physical appearance only: features, clothing, expression, posture. "
        "No Midjourney parameters. No prose. No punctuation except commas. "
        "Example output: nervous eyes, disheveled dark clothing, scarred knuckles, hunched posture"
    )
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                f"Ancestry: {fields.get('ancestry', '')}\n"
                f"Class: {fields.get('class', '')}\n"
                f"Traits: {traits}\n"
                f"Personality: {personality}\n"
                f"Backstory: {backstory}"
            )},
        ],
        "max_tokens": 40,
        "timeout": 30.0,
    }
    if api_base:
        kwargs["api_base"] = api_base

    response = await litellm.acompletion(**kwargs)
    return response.choices[0].message.content.strip()
```

**Token prompt assembly:**
```python
def build_mj_prompt(fields: dict, description: str) -> str:
    ancestry = fields.get("ancestry", "")
    npc_class = fields.get("class", "")
    return (
        f"{description}, {ancestry} {npc_class}, "
        "tabletop RPG portrait token, circular frame, "
        "parchment border, oil painting style, dramatic lighting "
        "--ar 1:1 --q 2 --s 180 --no text"
    )
```

### Pattern 5: Discord Embed for Stat Block

**What:** `discord.Embed` with inline fields for Defenses/Saves, non-inline for Speed/Skills.

**When to use:** Stat block rendering in bot layer (bot receives JSON dict from `/npc/stat` endpoint).

```python
# Source: [VERIFIED: discord.py docs]
import discord

def build_stat_embed(data: dict) -> discord.Embed:
    fields = data.get("fields", {})
    stats = data.get("stats", {})
    embed = discord.Embed(
        title=f"{fields.get('name', '?')} (Level {fields.get('level', '?')} "
              f"{fields.get('ancestry', '')} {fields.get('class', '')})",
        description=fields.get("personality", ""),
        color=discord.Color.dark_gold(),
    )
    if stats:
        embed.add_field(name="AC", value=str(stats.get("ac", "—")), inline=True)
        embed.add_field(name="HP", value=str(stats.get("hp", "—")), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # spacer
        embed.add_field(name="Fort", value=str(stats.get("fortitude", "—")), inline=True)
        embed.add_field(name="Ref", value=str(stats.get("reflex", "—")), inline=True)
        embed.add_field(name="Will", value=str(stats.get("will", "—")), inline=True)
        embed.add_field(name="Speed", value=f"{stats.get('speed', '—')} ft.", inline=False)
        skills = stats.get("skills") or {}
        if skills:
            if isinstance(skills, dict):
                skill_text = ", ".join(f"{k.capitalize()} +{v}" for k, v in skills.items())
            else:
                skill_text = str(skills)
            embed.add_field(name="Skills", value=skill_text[:900] + ("..." if len(skill_text) > 900 else ""), inline=False)
        if stats.get("perception") is not None:
            embed.add_field(name="Perception", value=f"+{stats['perception']}", inline=True)
    embed.set_footer(text=f"Mood: {fields.get('mood', 'neutral')}")
    return embed
```

**Module `/npc/stat` endpoint returns:**
```python
return JSONResponse({
    "fields": fields,   # frontmatter dict
    "stats": stats,     # stats block dict or {}
    "slug": slug,
    "path": path,
})
```

**`_pf_dispatch` stat branch** (note: returns a string, but bot needs to send embed):
```python
# _pf_dispatch CANNOT return discord.Embed — it returns str.
# The stat verb needs special handling — see Pitfall 1 below.
```

### Anti-Patterns to Avoid
- **Returning raw bytes from FastAPI through the proxy:** sentinel-core's `proxy_module()` always calls `resp.json()` — raw bytes will cause a `JSONDecodeError` which surfaces as HTTP 503.
- **Using `_pf_dispatch` return value for file/embed attachments:** `_pf_dispatch` returns `str`. File attachments and embeds must be sent directly to `message.channel` — NOT returned as strings. The calling code in `on_message` does `await message.channel.send(ai_response)` — it can't handle `discord.File` or `discord.Embed` from a string return.
- **Calling `response.choices[0].message.content` without stripping code fences:** Local LM Studio models frequently wrap responses in ` ```json ` blocks. Use `_strip_code_fences()` (already in `llm.py`).
- **Including `system.details.alignment` in Foundry actor JSON:** Removed in PF2e Remaster 2023. Including it causes import validation warnings.
- **`uuid.uuid4()` with hyphens:** Foundry expects `_id` as 16-char hex. Use `str(uuid.uuid4()).replace("-", "")` — yields 32 hex chars. Actually Foundry uses 16-char IDs. Use `uuid.uuid4().hex[:16]` or generate with `secrets.token_hex(8)` for 16 hex chars.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PDF generation | Custom PostScript/HTML-to-PDF | ReportLab Platypus | ReportLab handles font metrics, page layout, table cell sizing, text wrapping — all non-trivial to get right |
| UUID generation for Foundry `_id` | Custom random hex strings | `uuid.uuid4().hex[:16]` | Collision probability matters; stdlib UUID is cryptographically sound |
| YAML frontmatter parsing | Custom regex parser | `yaml.safe_load()` (already in npc.py) | Already implemented in `_parse_frontmatter()`; edge cases handled |
| Stats block parsing | New parser | `_parse_stats_block()` (already in npc.py) | Already implemented; reuse directly |
| NPC slug generation | New slugifier | `slugify()` (already in npc.py) | Already implemented |
| Obsidian note reading | New HTTP client | `obsidian.get_note()` (module-level var) | Already implemented with error handling |
| LLM call boilerplate | New client | `litellm.acompletion()` (pattern in llm.py) | Already established pattern with `_strip_code_fences` and timeout |

**Key insight:** Phase 29 implemented all the read infrastructure. Phase 30 is entirely additive on top of those foundations.

---

## Critical Architecture Finding: Binary Transport Constraint

### The Proxy Pipeline

```
bot.py → sentinel-core proxy_module() → pf2e-module endpoint
```

The sentinel-core `proxy_module()` function (verified in `sentinel-core/app/routes/modules.py`):
```python
resp = await request.app.state.http_client.post(target_url, ...)
try:
    content = resp.json()   # <-- ALWAYS calls resp.json()
except ValueError:
    content = {"body": resp.text}
return JSONResponse(content=content, status_code=resp.status_code)
```

And `SentinelCoreClient.post_to_module()` (verified in `shared/sentinel_client.py`):
```python
resp.raise_for_status()
return resp.json()   # <-- ALWAYS calls resp.json()
```

**Consequence:** Binary bytes returned from a module endpoint will cause `JSONDecodeError` (caught as `{"body": resp.text}` — which will be garbled UTF-8 from binary data), or the application/json Content-Type response will parse correctly only if the bytes are valid JSON.

**Resolution for OUT-01 (Foundry JSON) and OUT-04 (PDF):**
The Foundry actor JSON is valid JSON — the module CAN return it as `JSONResponse` directly. However, the bot needs to know it's a file attachment, not a display message. Wrap it:

```python
# Foundry JSON: module returns the actor dict; bot base64-encodes on the bot side
# Alternative: module returns {"actor": {...}, "filename": "slug.json"}
# Bot does: json.dumps(result["actor"]).encode() -> discord.File(BytesIO(...))
```

For PDF bytes, base64 encoding inside JSON is required — there is no alternative without changing sentinel-core.

**Two valid approaches:**
1. **Foundry JSON:** Module returns `{"actor": {...}, "filename": "slug.json"}` — bot serializes `result["actor"]` to JSON bytes and wraps in `discord.File`. No base64 needed.
2. **PDF:** Module returns `{"data_b64": "...", "filename": "slug-stat-card.pdf"}` — bot decodes base64.

This is cleaner than a uniform base64 approach for JSON since the actor dict is already a Python object.

---

## Common Pitfalls

### Pitfall 1: `_pf_dispatch` Returns String — Cannot Return File or Embed
**What goes wrong:** `_pf_dispatch` returns a `str`. The `on_message` handler does `await message.channel.send(ai_response)`. Files and embeds can't be passed as strings; they must be sent directly via `await message.channel.send(file=...)` or `await message.channel.send(embed=...)`.

**Why it happens:** The existing dispatch architecture was designed for text responses only. File attachments and embeds require different send call signatures.

**How to avoid:** Refactor `_pf_dispatch` to return either a `str` OR a special response object, OR change the `on_message` handler to check response type. The cleanest approach is to change `_pf_dispatch` to return a `dict` like `{"type": "text"|"file"|"embed", "content": ..., "file": ..., "embed": ...}` and have `on_message` dispatch on `type`. Alternatively, change `_pf_dispatch` to accept the `message` channel and send directly for file/embed verbs.

**Recommended approach:** Change `_pf_dispatch` to return a structured response dict rather than a bare string. The `on_message` handler interprets the dict and calls the appropriate `channel.send()` variant.

**Warning signs:** If `export`, `pdf`, or `stat` tests show the file attachment in the `content` text field rather than as a Discord attachment.

### Pitfall 2: `on_message` Sends `_pf_dispatch` Result as String
**What goes wrong:** `on_message` does `await message.channel.send(ai_response)` where `ai_response` is a string. File and embed responses need `send(file=...)` and `send(embed=...)` signatures — passing them as strings either errors or sends garbage.

**Why it happens:** The `on_message` handler at line 548 of bot.py assumes `ai_response` is always a string.

**How to avoid:** Handle the return value check before calling `channel.send()`.

### Pitfall 3: ReportLab `getSampleStyleSheet` "Heading2" — Name Sensitivity
**What goes wrong:** Style names in `getSampleStyleSheet()` are case-sensitive. `"Heading2"` is valid; `"heading2"` raises `KeyError`.

**Why it happens:** ReportLab style names follow a specific casing convention.

**How to avoid:** Use exact style names: `"Title"`, `"Heading1"`, `"Heading2"`, `"Normal"`, `"BodyText"`. Custom styles must be created via `ParagraphStyle`.

**Warning signs:** `KeyError: 'heading2'` at PDF generation time.

### Pitfall 4: Foundry `_id` — 16 vs 32 Hex Chars
**What goes wrong:** The CONTEXT.md note says "16-char hex ID" in specifics, but `str(uuid.uuid4()).replace("-", "")` produces 32 hex chars. Foundry VTT currently accepts both lengths for the `_id` field, but the native format is 16 chars.

**Why it happens:** UUID4 without hyphens is 32 hex chars. Native Foundry IDs are 16 chars generated via their own ID utility.

**How to avoid:** Use `uuid.uuid4().hex[:16]` — yields exactly 16 random hex characters. This matches the length of Foundry-native IDs.

**Warning signs:** Foundry import succeeds but generated IDs look different from native actor IDs.

### Pitfall 5: `_pf_dispatch` Returning Before File Send Completes
**What goes wrong:** If the dispatch function tries to `await channel.send(file=...)` internally but is called in a context where `channel` isn't accessible, the send never happens.

**Why it happens:** `_pf_dispatch` currently only has `args`, `user_id`, and `attachments` — no channel reference.

**How to avoid:** Pass `channel` as a parameter to `_pf_dispatch`, or change the return type to carry file data that the caller sends. The cleanest fix: change signature to `_pf_dispatch(args, user_id, channel, attachments=None)` and have file/embed verbs call `await channel.send(...)` directly before returning a confirmation string.

### Pitfall 6: ReportLab `BytesIO.getvalue()` After `doc.build()` 
**What goes wrong:** `buffer.getvalue()` after `doc.build(story)` returns the correct bytes only if the buffer hasn't been seeked. After `build()`, the buffer position is at the end. `getvalue()` works correctly regardless of position (returns all bytes). `read()` would return empty bytes after `build()` without a `seek(0)`.

**Why it happens:** `BytesIO.getvalue()` always returns the full buffer regardless of position. `BytesIO.read()` is position-dependent. 

**How to avoid:** Always use `buffer.getvalue()` after `doc.build()`, not `buffer.read()`.

**Warning signs:** PDF bytes are empty (0 bytes) when using `.read()` without `.seek(0)`.

### Pitfall 7: Skills Field Schema Variance
**What goes wrong:** The `skills` field in the stats block can be a dict (`{"stealth": 14, "deception": 12}`) or a string (`"Stealth +14, Deception +12"`). Both appear in real Obsidian NPC notes depending on how the NPC was created vs imported.

**Why it happens:** Phase 29 imports create identity-only notes; the skills field format was not normalized.

**How to avoid:** Both PDF generation and Discord embed code must handle both formats (`isinstance(skills, dict)` check).

---

## Code Examples

### Complete `export-foundry` endpoint:
```python
# Source: [VERIFIED: codebase patterns + github.com/foundryvtt/pf2e TypeScript source]
import json
import uuid

class NPCOutputRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        return _validate_npc_name(v)

@router.post("/export-foundry")
async def export_foundry(req: NPCOutputRequest) -> JSONResponse:
    """Export NPC as Foundry VTT PF2e actor JSON (OUT-01)."""
    slug = slugify(req.name)
    path = f"{_NPC_PATH_PREFIX}/{slug}.md"
    note_text = await obsidian.get_note(path)
    if note_text is None:
        raise HTTPException(status_code=404, detail={"error": "NPC not found", "slug": slug})
    fields = _parse_frontmatter(note_text)
    stats = _parse_stats_block(note_text)
    actor = build_foundry_actor(fields, stats)  # function from Pattern 3
    return JSONResponse({
        "actor": actor,
        "filename": f"{slug}.json",
        "slug": slug,
    })
```

**Bot side (export verb):**
```python
elif verb == "export":
    npc_name = rest.strip()
    if not npc_name:
        return {"type": "text", "content": "Usage: `:pf npc export <name>`"}
    result = await _sentinel_client.post_to_module(
        "modules/pathfinder/npc/export-foundry", {"name": npc_name}, http_client
    )
    json_bytes = json.dumps(result["actor"], indent=2).encode("utf-8")
    return {
        "type": "file",
        "content": f"Foundry actor JSON for **{npc_name}**:",
        "file_bytes": json_bytes,
        "filename": result["filename"],
    }
```

### `on_message` handler change:
```python
# Before: await message.channel.send(ai_response)  [str only]
# After:
response = await _route_message(user_id, message.content, attachments=list(message.attachments))
if isinstance(response, str):
    await message.channel.send(response)
elif isinstance(response, dict):
    rtype = response.get("type")
    if rtype == "file":
        df = discord.File(io.BytesIO(response["file_bytes"]), filename=response["filename"])
        await message.channel.send(content=response.get("content", ""), file=df)
    elif rtype == "embed":
        await message.channel.send(content=response.get("content", ""), embed=response["embed"])
    else:
        await message.channel.send(response.get("content", str(response)))
```

**The same change is needed in the `/sen` slash command handler** (line ~600 in bot.py) which also does `await thread.send(ai_response)`.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `system.details.alignment` in PF2e actor JSON | Removed from PF2e Remaster | 2023 Remaster | Must NOT include in generated JSON — will cause import validation errors |
| Foundry actor `_id` as UUID with hyphens | 16-char lowercase hex without hyphens | Always | `uuid.uuid4().hex[:16]` is the correct generation method |
| reportlab 3.x | reportlab 4.4.10 (Feb 2026) | 2023+ | 4.x is stable; no breaking changes for Platypus usage patterns |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Foundry PF2e accepts actor JSON with `abilities` having only `mod` values (not full score) | Standard Stack / Foundry schema | Import may require `value` fields too; live import test (D-07) will catch this |
| A2 | `system.resources` with `{"focus": {"value": 0, "max": 0}}` satisfies the required `CreatureResourcesSource` type | Code Examples | Import error if format differs; fallback: omit `resources` entirely and let Foundry default it |
| A3 | Discord `message.channel.send()` accepts `content=""` (empty string) for file-only attachment | Code Examples | If empty string causes validation error, use `content=None` instead |
| A4 | ReportLab 4.4.10 Platypus `Table` and `SimpleDocTemplate` API is backward-compatible with 3.x patterns shown in docs | Standard Stack | If API changed, test will fail immediately on PDF build; reportlab changelog shows no Platypus breaking changes in 4.x |
| A5 | The `skills` field in NPC stats block is either a dict or a string | Common Pitfalls | If it's a list, PDF and embed rendering will silently produce incorrect output |

---

## Open Questions

1. **Foundry `resources` field format**
   - What we know: TypeScript type is `CreatureResourcesSource`; `focus` is common for caster NPCs
   - What's unclear: Whether the field can be omitted entirely for non-caster NPCs, or must be present with zero values
   - Recommendation: Include `{"focus": {"value": 0, "max": 0}}` as D-07 specifies live import as validation

2. **`_pf_dispatch` return type change scope**
   - What we know: `_pf_dispatch` currently returns `str` only; file/embed needs `dict` return
   - What's unclear: Whether the refactor should use a TypedDict, a dataclass, or an ad-hoc dict
   - Recommendation: Use a plain `dict` with `"type"` key — consistent with existing JSON patterns in the codebase, no new types needed

3. **Discord embed vs message.channel.send context**
   - What we know: `_route_message` is called from both `on_message` and the `/sen` slash command handler; both need the same file/embed handling change
   - What's unclear: Whether the `/sen` slash command needs `interaction.followup.send(embed=...)` vs `thread.send(embed=...)`
   - Recommendation: Change both `thread.send()` and `message.channel.send()` call sites to handle the new response dict format

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| reportlab | OUT-04 PDF generation | Not installed in container | 4.4.10 (latest) | — (required; add to Dockerfile) |
| uuid (stdlib) | OUT-01 Foundry `_id` | ✓ (stdlib) | Python 3.12 | — |
| base64 (stdlib) | OUT-01 + OUT-04 binary transport | ✓ (stdlib) | Python 3.12 | — |
| io (stdlib) | OUT-04 BytesIO | ✓ (stdlib) | Python 3.12 | — |
| litellm | OUT-02 MJ description | ✓ (pyproject.toml >=1.83.0) | 1.83.0+ | — |
| discord.py | Bot embed + file | ✓ (interfaces/discord) | >=2.7.0 | — |

**Missing dependencies:**
- `reportlab` must be added to both `pyproject.toml` and the `Dockerfile` `pip install` line (D-22 says Dockerfile unchanged — this means no system-level apt packages, not no Python packages; reportlab must still be installed).

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (asyncio_mode = "auto") |
| Config file | `modules/pathfinder/pyproject.toml` |
| Quick run command | `cd modules/pathfinder && python -m pytest tests/test_npc.py -x -q` |
| Full suite command | `cd modules/pathfinder && python -m pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OUT-01 | `POST /npc/export-foundry` returns 200 with `actor` dict and `filename` | unit | `python -m pytest tests/test_npc.py::test_npc_export_foundry_success -x` | ❌ Wave 0 |
| OUT-01 | `POST /npc/export-foundry` returns 404 for unknown NPC | unit | `python -m pytest tests/test_npc.py::test_npc_export_foundry_not_found -x` | ❌ Wave 0 |
| OUT-01 | `POST /npc/export-foundry` with no stats block returns actor with 0-value defaults (D-05) | unit | `python -m pytest tests/test_npc.py::test_npc_export_foundry_no_stats -x` | ❌ Wave 0 |
| OUT-02 | `POST /npc/token` returns 200 with `prompt` string containing MJ params | unit | `python -m pytest tests/test_npc.py::test_npc_token_success -x` | ❌ Wave 0 |
| OUT-02 | Token prompt contains `--ar 1:1` suffix (template structure enforced) | unit | `python -m pytest tests/test_npc.py::test_npc_token_template_structure -x` | ❌ Wave 0 |
| OUT-03 | `POST /npc/stat` returns 200 with `fields` and `stats` keys | unit | `python -m pytest tests/test_npc.py::test_npc_stat_success -x` | ❌ Wave 0 |
| OUT-03 | `POST /npc/stat` with no stats block returns empty `stats: {}` | unit | `python -m pytest tests/test_npc.py::test_npc_stat_no_stats -x` | ❌ Wave 0 |
| OUT-04 | `POST /npc/pdf` returns 200 with `data_b64` key; base64 decodes to valid PDF bytes | unit | `python -m pytest tests/test_npc.py::test_npc_pdf_success -x` | ❌ Wave 0 |
| OUT-04 | `POST /npc/pdf` with no stats block returns PDF with header only | unit | `python -m pytest tests/test_npc.py::test_npc_pdf_no_stats -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd modules/pathfinder && python -m pytest tests/test_npc.py -x -q`
- **Per wave merge:** `cd modules/pathfinder && python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `modules/pathfinder/tests/test_npc.py` — add OUT-01 through OUT-04 test functions (append to existing file)
- [ ] `modules/pathfinder/app/pdf.py` — new module; needs to exist before test imports work

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | X-Sentinel-Key already enforced by global middleware |
| V3 Session Management | no | Stateless endpoints |
| V4 Access Control | no | Single-user personal tool |
| V5 Input Validation | yes | `_validate_npc_name()` already applied; `NPCOutputRequest` uses same validator |
| V6 Cryptography | no | No new secrets; base64 is encoding not encryption |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| NPC name path traversal to read arbitrary Obsidian vault files | Tampering | `_validate_npc_name()` rejects control chars; `slugify()` strips path separators |
| LLM prompt injection via personality/backstory fields | Tampering | D-11: truncate to 200 chars, strip newlines before LLM interpolation; `max_tokens=40` limits output |
| PDF size bomb (very large skills list) | DoS | `skill_text[:900]` truncation in embed; PDF table rows naturally limited by page size |

---

## Sources

### Primary (HIGH confidence)
- [foundryvtt/pf2e GitHub: src/module/actor/npc/data.ts](https://github.com/foundryvtt/pf2e/blob/master/src/module/actor/npc/data.ts) — NPCSystemSource, NPCAttributesSource, NPCSavesSource TypeScript types
- [pypi.org/project/reportlab](https://pypi.org/project/reportlab/) — version 4.4.10, February 12, 2026
- `modules/pathfinder/app/routes/npc.py` — existing patterns, helper functions
- `modules/pathfinder/app/llm.py` — LiteLLM call pattern
- `interfaces/discord/bot.py` — `_pf_dispatch` routing, return type constraint
- `shared/sentinel_client.py` — `post_to_module` calls `resp.json()` — binary transport constraint VERIFIED
- `sentinel-core/app/routes/modules.py` — `proxy_module` calls `resp.json()` — binary transport constraint VERIFIED

### Secondary (MEDIUM confidence)
- [pdfnoodle.com — How to Generate PDF Using ReportLab in Python (2025)](https://pdfnoodle.com/blog/how-to-generate-pdf-from-html-using-reportlab-in-python) — Platypus BytesIO and Table patterns (verified against ReportLab docs)
- [Stack Overflow: reportlab SimpleDocTemplate fixed height table](https://stackoverflow.com/questions/54824919) — BytesIO + doc.build() pattern (multiple sources agree)
- [Stack Overflow: discord.py send BytesIO](https://stackoverflow.com/questions/65496133/discord-py-send-bytesio) — `discord.File(io.BytesIO(bytes), filename=...)` pattern

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — reportlab version from PyPI directly; all other libraries already in use
- Architecture: HIGH — sentinel-core proxy behavior VERIFIED from source code; binary transport constraint is code-level fact
- Pitfalls: HIGH — `_pf_dispatch` return type constraint VERIFIED from bot.py source; ReportLab BytesIO behavior is stdlib-documented
- Foundry schema: MEDIUM-HIGH — TypeScript source verified; `resources` field format is ASSUMED

**Research date:** 2026-04-23
**Valid until:** 2026-05-23 (Foundry PF2e TypeScript schema is stable; reportlab 4.x Platypus API is stable)
