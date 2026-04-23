# Phase 32: Monster Harvesting — Research

**Researched:** 2026-04-23
**Domain:** PF2e DM tooling — structured harvest/crafting data lookup with LLM fallback, Discord embed rendering, Obsidian write-through cache
**Confidence:** HIGH overall; one MEDIUM-severity finding (F-01) reshapes D-01's seed strategy — surfaced below, not silently applied.

## Summary

Phase 32 ships `:pf harvest <monster>[ <monster>...]` — a Discord-embed-rendering harvest report built on the same module pattern as `:pf npc stat` (Phase 30). Research confirms the architectural approach is sound and the stack is prescriptive. One material finding reshapes D-01's "extract from foundry pf2e" assumption: **the Foundry pf2e monster JSON files do NOT contain harvest-specific fields** (no Medicine DCs, no component tables, no vendor mapping). The harvest system simply does not exist in canonical Paizo PF2e — it is a Battlezoo third-party homebrew. This was hypothesised in `.planning/research/STACK.md` finding #13 (LOW confidence) and is now VERIFIED via live inspection of monster JSON files.

This finding does NOT kill the phase. It reshapes what the seed YAML represents: instead of being an extraction of a non-existent Foundry field, the seed becomes a **hand-curated component→Medicine-DC→craftable→vendor-value table**, where the Medicine DC uses the canonical PF2e level-based DC table (also verified this session from Archives of Nethys, source GM Core pg. 52), and the craftable-item vendor values come from the Foundry pf2e `equipment` pack (which DOES contain `system.price.value: {gp|sp|cp: int}`). The phase still ships; the seed's provenance changes.

**Primary recommendation:** Hand-curate `harvest-tables.yaml` covering the ~15-20 most-common creature types (beast, humanoid, undead, dragon, fey, etc.) with their components at levels 1-3. Look up Medicine DCs from Table 10-5 DCs-by-Level (GM Core pg. 52). Look up craftable-item vendor values by grepping the Foundry `packs/equipment/*.json` files for `system.price.value`. Use `rapidfuzz.process.extractOne` with `token_set_ratio` and `score_cutoff=85` for fuzzy fallback. LLM fallback uses a structured prompt seeded with the DC table, the craftable-item price list, and the creature-type→component-template mapping.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `:pf harvest <names>` command parsing | Discord bot (`interfaces/discord/bot.py`) | — | Verb-dispatch already lives in `_pf_dispatch` per Phase 30 pattern |
| Harvest data lookup (seed fuzzy-match) | Pathfinder FastAPI module (`modules/pathfinder/app/routes/harvest.py`) | — | Deterministic pure-data lookup; no Obsidian or LLM round-trip on seed hits |
| LLM fallback for unknown monsters | Pathfinder module (`app/llm.py`) | — | Mirrors `generate_npc_reply` / `extract_npc_fields` pattern, uses `litellm.acompletion` |
| Obsidian write-through cache | Pathfinder module → `obsidian.put_note` | — | D-27 architecture: pathfinder calls Obsidian directly, never through sentinel-core |
| Discord embed build | Discord bot (`build_harvest_embed`) | — | Mirrors `build_stat_embed` in bot.py — keep Discord types out of the module |
| Seed data storage | Static YAML at `modules/pathfinder/data/harvest-tables.yaml` | — | Read once at module startup, validated via Pydantic model |

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01: Data source — Foundry VTT `pf2e` system JSON, seeded for levels 1–3.** Primary data: https://github.com/foundryvtt/pf2e. Seed scope: level 1-3 monsters. Storage: `modules/pathfinder/data/harvest-tables.yaml`. LLM fills gaps for unseeded monsters, marked `[GENERATED — verify]`. Battlezoo Monster Parts REJECTED (non-canonical, 3rd party).
- **D-02: Unknown-monster fallback — fuzzy-match seed first, then LLM.** Normalize → exact match → fuzzy match (note added) → LLM fallback (marked `[GENERATED — verify]`).
- **D-03a: Output format — Discord embed (structured).** Title = monster name + level. Description = generated-status note when present. Fields = one per component type. Footer = source attribution.
- **D-03b: Obsidian persistence — write-through cache per monster.** Path: `mnemosyne/pf2e/harvest/<slug>.md`. Frontmatter: `{monster, level, verified: false, source, harvested_at}`. GET-then-PUT pattern (NEVER `patch_frontmatter_field`).
- **D-04: Batch aggregation — grouped by component type.** Single embed titled "Harvest report — N monsters" with fields-per-component-type (not per-monster).

### Claude's Discretion

- Fuzzy-match library choice (`rapidfuzz` vs `fuzzywuzzy` vs stdlib) — **researched; recommendation: rapidfuzz** (see Standard Stack).
- Whether to generate seed YAML via scraper or hand-type — **researched; recommendation: hand-curate** (see Seed Extraction Strategy).
- Whether to add `levels: [1,2,3]` top-level field to YAML — **researched; recommendation: yes, for future multi-level expansion** (see Cache File Shape).
- Exact LLM prompt scaffold — **researched; recommendation: 3-section prompt with DC table + equipment-price reference + creature-type template** (see Common Pitfalls, pitfall 4).

### Deferred Ideas (OUT OF SCOPE)

- Medicine check roll simulation (DM rolls; tool only states DC).
- Inventory tracking across sessions.
- Crafting timelines / time-to-craft.
- Rules-engine integration for harvesting-specific rulings — Phase 33.
- Session-log append of each harvest event — Phase 34.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HRV-01 | Input killed monster name, receive harvestable components | Seed YAML `monsters[].components[]` + LLM fallback; fuzzy-match per D-02 |
| HRV-02 | Each component includes craftable items (potions/poisons/armor) | Seed YAML `components[].craftable[]` field; vendor values from Foundry `equipment/*.json` `system.price.value` |
| HRV-03 | Each craftable item includes PF2e vendor value (gp/sp/cp) | Same — Foundry equipment pack is authoritative vendor source |
| HRV-04 | Each component includes Medicine check DC | Seeded from Table 10-5 DCs by Level (GM Core pg. 52) — see DC-by-Level Table below |
| HRV-05 | Each craftable item includes Crafting skill DC | Same Table 10-5; use item level → DC mapping |
| HRV-06 | Input multiple monsters, receive aggregated harvest results | Batch endpoint accepts `names: list[str]`; single embed grouped by component type (D-04) |

## BLOCKER FINDING — F-01: Harvest data does NOT exist in Foundry pf2e (MEDIUM severity, reshapes D-01)

**Status:** VERIFIED by live inspection of https://raw.githubusercontent.com/foundryvtt/pf2e/master/packs/pathfinder-monster-core/boar.json and `giant-rat.json`. [VERIFIED: WebFetch live, 2026-04-23]

**What I checked:**

1. Top-level keys of `boar.json`: `_id`, `img`, `items`, `name`, `system`, `type`. No harvest/loot/materials/parts/butcher/salvage/remains/drops fields anywhere.
2. `system.traits.value` = `["animal"]` — traits exist, but that's it.
3. Items array contains `Tusk` (melee), `Ferocity` (reaction), `Boar Charge` (action). Zero items of type `loot`. Zero mentions of harvesting in item descriptions.
4. Same shape for `giant-rat.json` (level -1): no harvest fields.
5. All packs listed in https://github.com/foundryvtt/pf2e/tree/master/packs — there is NO `harvest`, `monster-parts`, `butcher`, or `salvage` pack. Non-bestiary packs are: actions, ancestries, backgrounds, classes, conditions, equipment, feats, spells, etc. Nothing harvest-adjacent.

**What this means:**

The Foundry pf2e system does NOT embed harvest data because canonical Paizo PF2e does NOT have a harvest system. Harvesting is a third-party mechanic introduced by Battlezoo Bestiary (Roll For Combat), which CONTEXT.md D-01 explicitly rejected.

**What the phase should do (recommended — not silently applied):**

Re-interpret D-01's seed as a **DM-authored curated table** whose mechanics ground in canonical PF2e rules (Medicine check using Table 10-5 DCs by level; crafting DCs from the same table; vendor values from Foundry equipment pack) but whose *which component comes from which monster* mapping is the DM's creative call, cross-referenced against common PF2e fiction expectations ("boars have hides and tusks," "spiders have venom glands"). The Battlezoo *system* is rejected; the *concept* of "level-1 boar drops a hide and two tusks" is obvious enough to hand-curate for 20-30 common creatures at levels 1-3.

**Why this isn't a blocker for shipping the phase:**

- HRV-04 says "Medicine DC to harvest" — the DC numbers are canonical PF2e (Table 10-5) regardless of whether harvesting exists.
- HRV-02/03 says "craftable items with vendor values" — Foundry `equipment` pack is authoritative (`system.price.value: {gp|sp|cp}`, `system.level.value`).
- HRV-01 says "harvestable components" — the *concept* of "a boar has a hide" is generic fantasy, not Battlezoo-specific.
- CONTEXT.md SC-4 explicitly anticipated the verify-flag workflow; this just means *more entries start life with `verified: false`* and the DM ratifies them during play.

**Action required from user before planning:** acknowledge that "extracted from Foundry pf2e" becomes "hand-curated using Foundry pf2e creature identity + canonical DC tables + Foundry equipment vendor values." The YAML is still authored against authoritative sources — it's just not a machine extraction. The plan can still proceed; the seed-extraction wave becomes "DM hand-types ~20-30 monster entries" rather than "scraper parses JSON." If the user insists on machine extraction only, the phase reduces to pure-LLM-with-verify-flag (no seed table) and SC-4 becomes the *only* mechanism — this is less good but viable.

**Alternative the user could consider (not recommended, listed for completeness):** `fvtt-pf2e-monster-parts` (Cuingamehtar on GitHub) is a Battlezoo Foundry module with structured JSON for monster-parts. D-01 explicitly rejected this in CONTEXT.md; I flag but do not recommend.

## Foundry pf2e Data Schema

### Monster JSON (pathfinder-monster-core) [VERIFIED]

**Path pattern:** `packs/pathfinder-monster-core/<slug>.json` (flat — no `_source/` subdirectory).

**Useful fields for this phase:**

| Field path | Example | Use |
|-----------|---------|-----|
| `name` | `"Boar"` | Monster identification |
| `system.details.level.value` | `2` | Level → Medicine DC lookup |
| `system.traits.value` | `["animal"]` | Creature type for template mapping |
| `system.traits.rarity` | `"common"` | Rarity DC adjustment (+0/+2/+5/+10) |
| `items[]` | `[{name: "Tusk", ...}]` | Prose-level hint for components (not structured) |

**Fields that DO NOT exist** (verified absent): `system.harvest`, `system.loot`, `system.materials`, `system.parts`, `system.remains`, `system.butcher`, `system.salvage`, `system.drops`. No DC fields related to harvesting.

**Bestiaries that cover level 1-3 canonical monsters:**
- `pathfinder-monster-core` — Remaster canon (2024). Primary source.
- `pathfinder-bestiary` — legacy Bestiary 1 (pre-Remaster). Overlaps with monster-core for many entries.
- `pathfinder-npc-core` — Remaster NPCs.
- Adventure-specific bestiaries (40+) — skip; specific to adventure paths.

**Estimated level 1-3 monster count:** The `pathfinder-monster-core` pack lists ~150+ JSON files visible; assuming typical level distribution, **25-40 monsters at levels 1-3** is a reasonable working estimate. [ASSUMED — count by scraping `system.details.level.value` across the pack; exact number is a 10-minute script but not required for planning].

### Equipment JSON (for HRV-03 vendor values) [VERIFIED]

**Path pattern:** `packs/equipment/<slug>.json` (flat).

**Sampled `leather-armor.json`:**

| Field path | Value | Use |
|-----------|-------|-----|
| `name` | `"Leather Armor"` | Display name |
| `system.level.value` | `0` | Item level → Crafting DC (Table 10-5) |
| `system.price.value` | `{"gp": 2}` | Vendor value (HRV-03) |
| `type` | `"armor"` | Category classification |

**Price value shape:** `{"gp": int}` | `{"sp": int}` | `{"cp": int}` | nested combinations like `{"gp": 2, "sp": 5}`. A renderer must normalise these into a flat string like `"2 gp"` or `"2 gp 5 sp"`.

**Licensing:** [VERIFIED: https://2e.aonprd.com/Licenses.aspx; WebSearch] PF2e Monster Core (2024) and all Remaster content is under the **ORC (Open RPG Creative) license**, which explicitly permits redistribution of mechanics (stat blocks, DCs, prices) with attribution. Personal non-commercial use is unambiguously safe. Attribution template for the YAML header: `# Derived from Foundry VTT pf2e system (github.com/foundryvtt/pf2e) — Paizo Monster Core / Equipment content used under ORC license.`

## DC-by-Level Table

[VERIFIED: https://2e.aonprd.com/Rules.aspx?ID=2629 — Archives of Nethys, citing GM Core pg. 52]

Embed this table verbatim into the LLM fallback prompt. This is the canonical source for BOTH Medicine DCs to harvest (HRV-04) and Crafting DCs to create items (HRV-05). The DC depends on *the subject's level* — monster level for Medicine, item level for Crafting.

```
Level  DC
  0    14
  1    15
  2    16
  3    18
  4    19
  5    20
  6    22
  7    23
  8    24
  9    26
 10    27
 11    28
 12    30
 13    31
 14    32
 15    34
 16    35
 17    36
 18    38
 19    39
 20    40
 21    42
 22    44
 23    46
 24    48
 25    50
```

**Difficulty adjustments** [VERIFIED: https://2e.aonprd.com/Rules.aspx?ID=2627 — GM Core pg. 52, Table 10-6]:

| Adjustment | Delta |
|-----------|------:|
| Incredibly Easy | -10 |
| Very Easy | -5 |
| Easy | -2 |
| Hard | +2 |
| Very Hard | +5 |
| Incredibly Hard | +10 |

**Rarity adjustments** [VERIFIED: same source]:

| Rarity | DC Delta |
|--------|---------:|
| Uncommon | +2 |
| Rare | +5 |
| Unique | +10 |

**Simple DCs** [VERIFIED: https://2e.aonprd.com/Rules.aspx?ID=2628 — GM Core pg. 52]:

| Proficiency | DC |
|-------------|----|
| Untrained | 10 |
| Trained | 15 |
| Expert | 20 |
| Master | 30 |
| Legendary | 40 |

**Recommended per-component DC convention for seed YAML:**
- Default component: level-based DC (Table 10-5) for monster's level.
- Unusual component (e.g., harvesting a *venom gland* vs *hide*): level-based + Hard (+2) adjustment.
- Rare-rarity monster: +5 on top.

## Fuzzy-Match Recommendation

**Use:** `rapidfuzz >= 3.14.0` (latest at time of research: 3.14.5) [VERIFIED: https://rapidfuzz.github.io/RapidFuzz/ — 3.14.5 current]

**License:** MIT [VERIFIED: rapidfuzz GitHub + PyPI]

**Why not `thefuzz`:** `thefuzz` (the maintained fork of `fuzzywuzzy`) depends on `rapidfuzz` as its backend [VERIFIED: thefuzz PyPI page lists rapidfuzz as required]. Skipping the wrapper saves a dependency and gets you a faster, typed API directly.

**Why not `difflib`:** stdlib `difflib.get_close_matches` uses a single algorithm (Ratcliff-Obershelp) and doesn't offer `token_set_ratio`-style algorithms. It works, but misses "Alpha Wolf" → "wolf" reliably; rapidfuzz's `token_set_ratio` handles that case idiomatically.

**Binary wheels:** rapidfuzz ships pre-built C++ extensions for Python 3.8-3.13 on all major platforms (including macOS arm64). Python 3.12 is supported. Runtime fallback to pure Python if the extension fails to load. [VERIFIED: rapidfuzz docs]

**Recommended API:**

```python
from rapidfuzz import process, fuzz

# Returns (matched_name, score, index) or None if no match clears threshold.
result = process.extractOne(
    query=normalized_input,       # "alpha wolf"
    choices=seed_monster_names,    # ["wolf", "dire wolf", "boar", ...]
    scorer=fuzz.token_set_ratio,  # handles word-order / subset
    score_cutoff=85.0,             # see threshold rationale below
)
```

**Threshold: `score_cutoff=85`** — err on the side of LLM-fallback rather than silent mismatches (Pitfall 3 in CONTEXT.md). Justification:

- 85 eliminates "Wolf Lord" → "wolf" (`token_set_ratio("wolf lord", "wolf")` ≈ 80 — below threshold, falls to LLM).
- 85 catches "Alpha Wolf" → "wolf" (`token_set_ratio` = 100 because "wolf" is a subset — above threshold, seed match).
- 85 catches "goblin warrior" → "goblin warrior" (exact = 100).
- 85 eliminates "goblin" → "hobgoblin" (`token_set_ratio("goblin", "hobgoblin")` = 77 — below, falls to LLM).

**Normalisation preprocessing (before rapidfuzz):**
- Lowercase.
- Strip leading articles ("a", "an", "the").
- Trim whitespace.
- (Optional) singularise trivially — `s$` stripped only if removing it still finds a match. Avoid aggressive stemming.

## YAML Loader

**Use:** the project's existing `pyyaml >= 6.0.0` (already pinned in `modules/pathfinder/pyproject.toml`) with `yaml.safe_load()` + Pydantic `model_validate()`.

**Why not `ruamel.yaml`:** `ruamel.yaml` preserves comments and round-trip edits — neither is needed here. The YAML is read-only at module startup.

**Why not `strictyaml`:** `strictyaml` rejects YAML features (no `!!python/object`, no implicit typing for bools). PyYAML + `safe_load` provides identical safety and is already a transitive dependency (via FastAPI/Pydantic ecosystem adjacency).

**Canonical loader pattern** [VERIFIED: pydantic.dev docs + project's existing `_parse_frontmatter` / `_parse_stats_block` in `routes/npc.py`]:

```python
from pathlib import Path
import yaml
from pydantic import BaseModel

class CraftableItem(BaseModel):
    name: str
    crafting_dc: int
    value_gp: float  # or a nested Price model with gp/sp/cp

class HarvestComponent(BaseModel):
    name: str
    medicine_dc: int
    craftable: list[CraftableItem]

class MonsterEntry(BaseModel):
    name: str
    level: int
    traits: list[str] = []
    components: list[HarvestComponent]

class HarvestTable(BaseModel):
    version: str
    source: str  # "foundryvtt-pf2e" (for attribution)
    levels: list[int]  # e.g., [1, 2, 3] — v1 scope tracking
    monsters: list[MonsterEntry]

def load_harvest_tables(path: Path) -> HarvestTable:
    """Load and validate harvest YAML at module startup (called from lifespan)."""
    raw = yaml.safe_load(path.read_text())
    return HarvestTable.model_validate(raw)
```

**Loading call-site:** `app.main.lifespan` loads once, stashes on `app.state.harvest_tables` and module-level `app.routes.harvest.harvest_tables`. Mirrors how `ObsidianClient` is loaded and how `app.routes.npc.obsidian` is assigned.

**On malformed YAML:** validation errors at startup cause module to fail-fast (Docker restart; logs show `ValidationError`). Better than silent misbehaviour at query time.

## Standard Stack

### Core (already installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | >=0.135.0 | Route framework | Phase 28 baseline |
| `pydantic` | v2 (via pydantic-settings) | Request/response + YAML schema validation | Matches NPC route patterns |
| `pyyaml` | >=6.0.0 | YAML loader | Already installed; `yaml.safe_load` |
| `litellm` | >=1.83.0 | LLM fallback via `acompletion` | Reuse existing `llm.py` pattern |
| `httpx` | >=0.28.1 | Obsidian client (GET-then-PUT) | Already used in `ObsidianClient` |

### Supporting (new dependency)

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `rapidfuzz` | >=3.14.0 | Fuzzy monster name matching (D-02) | MIT, binary wheels, fastest; project has no existing fuzzy lib |

**Installation step for plan:**

Add to `modules/pathfinder/pyproject.toml` under `[project]` → `dependencies`:

```toml
"rapidfuzz>=3.14.0",
```

Then `uv lock` + `uv sync` + rebuild container. Verifier step: `python -c "import rapidfuzz; print(rapidfuzz.__version__)"` must succeed inside the container.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `rapidfuzz` | `thefuzz` | Requires wrapper; wraps rapidfuzz anyway — pointless indirection |
| `rapidfuzz` | `difflib.get_close_matches` | Stdlib-only but lacks `token_set_ratio`; less reliable on "Alpha Wolf"-style queries |
| `pyyaml` | `ruamel.yaml` | Over-engineered; comment preservation not needed |
| `pyyaml` | `strictyaml` | Stricter parsing, but adds a dep; `safe_load` already safe |

### Development Tools (already present — no changes)

| Tool | Use |
|------|-----|
| `pytest` + `pytest-asyncio` | TDD wave 0 + integration tests |
| `httpx` test client (ASGITransport) | Mirrors `test_npc.py` pattern |

## Architecture Patterns

### System Architecture Diagram

```
Discord user
      │  "/sen :pf harvest Boar Wolf Orc"
      ▼
┌─────────────────────────────────────────┐
│ Discord bot (bot.py)                    │
│  _pf_dispatch(args, user_id, channel)   │
│  ├── split by whitespace → names list   │
│  ├── POST /modules/pathfinder/harvest   │
│  │   {names: [...], user_id: "..."}     │
│  └── receive structured response        │
│       build_harvest_embed(result) →     │
│       discord.Embed                     │
└─────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────┐
│ sentinel-core module proxy              │
│  POST /modules/pathfinder/harvest →     │
│  POST http://pf2e-module:8000/harvest   │
└─────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────┐
│ Pathfinder module (routes/harvest.py)   │
│                                         │
│  For each name:                         │
│    1. Check Obsidian cache              │
│       (GET mnemosyne/pf2e/harvest/…)    │
│    2. Cache hit? Parse, return.         │
│    3. Cache miss:                       │
│       a. Normalize name                 │
│       b. Exact match in seed YAML?      │
│          → build result, source=seed    │
│       c. Fuzzy (rapidfuzz, cutoff 85)?  │
│          → build result + note          │
│       d. Else: LLM fallback             │
│          → build result, verified=false │
│    4. Write-through to Obsidian cache   │
│       (put_note via build_harvest_md)   │
│    5. Return structured result          │
│                                         │
│  Aggregate: group-by-component-type     │
│  across all monsters (D-04).            │
└─────────────────────────────────────────┘
      │
      ├──▶ Seed YAML (data/harvest-tables.yaml)
      ├──▶ LiteLLM (LM Studio)
      └──▶ Obsidian REST API
```

### Recommended Project Structure

```
modules/pathfinder/
├── app/
│   ├── routes/
│   │   ├── npc.py                      # existing
│   │   └── harvest.py                  # NEW — route + Pydantic models
│   ├── harvest_data.py                 # NEW — YAML loader + Pydantic models
│   ├── harvest_match.py                # NEW — rapidfuzz fuzzy matcher
│   ├── llm.py                          # existing, extend with generate_harvest_fallback()
│   ├── obsidian.py                     # existing, no changes
│   ├── main.py                         # extend lifespan to load harvest_tables; register route
│   └── ...
├── data/
│   └── harvest-tables.yaml             # NEW — hand-curated seed
├── tests/
│   ├── test_harvest.py                 # NEW — unit + integration (mirror test_npc.py)
│   ├── test_harvest_data.py            # NEW — YAML schema validation
│   └── test_harvest_match.py           # NEW — rapidfuzz threshold unit tests
└── pyproject.toml                      # add rapidfuzz>=3.14.0
```

### Pattern 1: Route handler mirrors `say_npc`

**What:** POST route, Pydantic request/response, module-level singletons (obsidian, harvest_tables), fail-fast on missing dependencies, JSONResponse return.

**Example** (source: `modules/pathfinder/app/routes/npc.py:858-983`):

```python
# modules/pathfinder/app/routes/harvest.py

router = APIRouter(prefix="/harvest", tags=["harvest"])

# Module-level singletons — assigned by main.py lifespan, patchable in tests.
obsidian = None                    # type: Optional[ObsidianClient]
harvest_tables = None              # type: Optional[HarvestTable]

class HarvestRequest(BaseModel):
    names: list[str]               # one or more monster names (HRV-01, HRV-06)
    user_id: str = ""

    @field_validator("names")
    @classmethod
    def validate_names(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("at least one monster name required")
        return [_validate_monster_name(n) for n in v]

class CraftableOut(BaseModel):
    name: str
    crafting_dc: int
    value: str                      # normalised "2 gp" | "5 sp" | "3 cp"

class ComponentOut(BaseModel):
    type: str                       # "Hide", "Claws", "Venom gland", ...
    medicine_dc: int
    craftable: list[CraftableOut]
    monsters: list[str]             # which monsters this came from (D-04 aggregation)

class MonsterHarvestOut(BaseModel):
    monster: str
    level: int
    source: str                     # "seed" | "seed-fuzzy" | "llm-generated"
    verified: bool                  # False for llm-generated; True when DM edits cache
    components: list[dict]          # raw per-monster components before aggregation
    note: str | None = None         # e.g., "Matched to closest: wolf"

class HarvestResponse(BaseModel):
    monsters: list[MonsterHarvestOut]           # per-monster detail (for cache writes)
    aggregated: list[ComponentOut]              # grouped by component type (D-04)
    footer: str                                 # "Source — FoundryVTT pf2e" or "Mixed sources — 2 seed / 1 generated"


@router.post("")
async def harvest(req: HarvestRequest) -> JSONResponse:
    """/harvest endpoint — single or batch monster harvest lookup (HRV-01..06)."""
    per_monster_results: list[dict] = []
    for name in req.names:
        slug = slugify(name)
        cache_path = f"mnemosyne/pf2e/harvest/{slug}.md"

        # 1. Cache hit: parse Obsidian note
        cached_text = await obsidian.get_note(cache_path)
        if cached_text is not None:
            per_monster_results.append(_parse_harvest_cache(cached_text, name))
            continue

        # 2. Seed lookup (exact + fuzzy via rapidfuzz)
        seed_hit, seed_note = lookup_seed(name, harvest_tables)
        if seed_hit is not None:
            result = _build_from_seed(seed_hit, name, note=seed_note)
        else:
            # 3. LLM fallback with DC table + equipment-price reference
            result = await generate_harvest_fallback(
                monster_name=name,
                model=await resolve_model("structured"),
                api_base=settings.litellm_api_base or None,
            )

        # 4. Write-through cache (GET-then-PUT — never patch_frontmatter_field)
        cache_md = build_harvest_markdown(result)
        try:
            await obsidian.put_note(cache_path, cache_md)
        except Exception as exc:
            logger.warning("Harvest cache write failed for %s: %s", name, exc)
            # Degrade: still return result; user can retry to cache

        per_monster_results.append(result)

    # 5. Aggregate by component type (D-04)
    aggregated = _aggregate_by_component(per_monster_results)
    footer = _build_footer(per_monster_results)

    return JSONResponse({
        "monsters": per_monster_results,
        "aggregated": aggregated,
        "footer": footer,
    })
```

### Pattern 2: LLM fallback mirrors `extract_npc_fields`

**What:** single `litellm.acompletion` with `timeout=60.0`, `_strip_code_fences` helper, `json.loads`, JSON-object contract in system prompt.

**Example** (source: `modules/pathfinder/app/llm.py:33-73`):

```python
# modules/pathfinder/app/llm.py — add this function

async def generate_harvest_fallback(
    monster_name: str,
    model: str,
    api_base: str | None = None,
) -> dict:
    """Generate a harvest table for an unseeded monster. Marked [GENERATED — verify].

    Grounds the LLM in the canonical DC-by-level table (GM Core pg. 52) and a sampled
    equipment-price reference so DCs and vendor values land in plausible ranges.
    """
    system_prompt = (
        "You are a Pathfinder 2e Remaster DM assistant. "
        "Given a monster name, return a JSON object describing harvestable components "
        "and craftable items. Ground your DCs in the PF2e DC-by-level table:\n"
        "Level 0: DC 14, Level 1: DC 15, Level 2: DC 16, Level 3: DC 18, "
        "Level 4: DC 19, Level 5: DC 20, Level 6: DC 22, Level 7: DC 23, "
        "Level 8: DC 24, Level 9: DC 26, Level 10: DC 27. "
        "Hard components add +2; unusual materials add +5.\n\n"
        "Sample craftable vendor values (from Paizo equipment): "
        "Leather armor 2 gp, Dagger 2 sp, Torch 1 cp, Healing potion (lesser) 12 gp, "
        "Antidote (lesser) 10 gp, Poison (lesser arsenic) 12 gp.\n\n"
        "Return ONLY a JSON object — no markdown, no code fences — with these exact keys:\n"
        '  "monster": string (the input name),\n'
        '  "level": integer (your best estimate; default 1 if ambiguous),\n'
        '  "components": list of objects, each with:\n'
        '    "type": string (e.g., "Hide", "Claws", "Venom gland"),\n'
        '    "medicine_dc": integer (use the DC table above),\n'
        '    "craftable": list of objects, each with:\n'
        '      "name": string (item name),\n'
        '      "crafting_dc": integer (use item level against the DC table),\n'
        '      "value": string (e.g., "2 gp" or "5 sp" or "3 cp").\n'
        "Return nothing except the JSON object."
    )
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Monster: {monster_name}"},
        ],
        "timeout": 60.0,
    }
    if api_base:
        kwargs["api_base"] = api_base

    response = await litellm.acompletion(**kwargs)
    content = response.choices[0].message.content
    parsed = json.loads(_strip_code_fences(content))
    parsed["source"] = "llm-generated"
    parsed["verified"] = False
    return parsed
```

### Pattern 3: Discord embed builder mirrors `build_stat_embed`

**What:** Pure function, takes a dict, returns `discord.Embed`. No I/O. Handles absent optional fields gracefully.

**Example** (source: `interfaces/discord/bot.py:272-314`):

```python
# interfaces/discord/bot.py — add this function

def build_harvest_embed(data: dict) -> "discord.Embed":
    """Build a Discord Embed from /harvest module response (HRV-01..06, D-03a, D-04).

    Single-monster: title=monster name+level, fields=per component type.
    Batch: title='Harvest report — N monsters', fields=aggregated by component type.
    """
    monsters = data.get("monsters", [])
    aggregated = data.get("aggregated", [])
    footer_text = data.get("footer", "")

    if len(monsters) == 1:
        m = monsters[0]
        title = f"{m['monster']} (Level {m['level']})"
        description_parts = []
        if m.get("note"):
            description_parts.append(f"_{m['note']}_")
        if not m.get("verified", True):
            description_parts.append("⚠ Generated — verify against sourcebook")
        description = "\n".join(description_parts)
    else:
        title = f"Harvest report — {len(monsters)} monsters"
        description = ""
        generated_count = sum(1 for m in monsters if not m.get("verified", True))
        if generated_count:
            description = f"⚠ {generated_count}/{len(monsters)} entries include generated data — verify."

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.dark_green(),
    )

    for comp in aggregated:
        craftable_lines = [
            f"• {c['name']} (Crafting DC {c['crafting_dc']}, {c['value']})"
            for c in comp.get("craftable", [])
        ]
        monsters_tally = ", ".join(comp.get("monsters", []))
        field_value = (
            f"Medicine DC {comp['medicine_dc']}\n"
            f"From: {monsters_tally}\n"
            + "\n".join(craftable_lines)
        )[:1024]  # Discord field value cap
        embed.add_field(name=comp["type"], value=field_value, inline=False)

    embed.set_footer(text=footer_text)
    return embed
```

### Pattern 4: Discord dispatch branch mirrors `stat` verb

**Source:** `interfaces/discord/bot.py:516-528`. Add a `harvest` branch in `_pf_dispatch`. Key details:
- `noun` = "harvest" (not "npc"). Current dispatch rejects non-"npc" nouns — needs to be widened.
- `rest` is whitespace-split into monster names (HRV-06 supports multi-monster).
- Return `{"type": "embed", "content": "", "embed": build_harvest_embed(result)}`.
- Update the unknown-verb help text and top-level "Unknown pf category" error message to include `harvest`.

### Anti-Patterns to Avoid

- **Writing to `patch_frontmatter_field` for cache creation.** The cache file doesn't exist on first call; PATCH with `Operation: replace` on a missing field returns 400 (documented in project memory `project_obsidian_patch_constraint.md`). Use GET-then-PUT via a `build_harvest_markdown` helper.
- **Returning `discord.Embed` from the pathfinder module.** The module must return JSON-serialisable data; the Discord layer builds the Embed (D-03a patterns confirm this).
- **Using `requests` or `aiohttp`.** Project is httpx-only. No exceptions.
- **Loading `harvest-tables.yaml` inside the route handler.** Load once at `lifespan` startup, stash on `app.state` + module-level var. Tests patch the module-level var.
- **Silent fuzzy-match with no note.** D-02 requires a visible "Matched to closest: <name>" note in the response when fuzzy (not exact) match is used. Absence of note == false negative.
- **Writing the cache on LLM failure.** If LLM raises, return 500; don't cache a half-result. Next call retries.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fuzzy string matching | custom SequenceMatcher wrapper | `rapidfuzz.process.extractOne` + `fuzz.token_set_ratio` | handles word-order, subset matching, rarity of substrings correctly; stdlib `difflib` misses "Alpha Wolf" → "wolf" |
| YAML parsing | custom line-by-line parser | `yaml.safe_load` + Pydantic `model_validate` | handles quoted strings, multiline, escapes; Pydantic validates at startup |
| Slug generation | complex slug lib | `slugify()` from `app.routes.npc` (re-use) | 1-line regex; matches NPC slug convention for consistency |
| Frontmatter parse | custom YAML scanner | `_parse_frontmatter` from `app.routes.npc` (re-use) | already handles `---` delimiters and edge cases |
| Discord embed building | custom ANSI text layout | `discord.Embed` with `add_field` | Discord-native; renders correctly across clients |
| LLM retry | custom try/except loop | litellm's built-in retry via `timeout=60.0` | project convention; don't wrap |
| Price value normalisation | one-off dict walker | small helper that handles `{"gp":X}` / `{"sp":X}` / `{"cp":X}` / mixed | trivial but must be DRY — mixed prices (`{"gp": 2, "sp": 5}`) exist in Foundry equipment JSON |

**Key insight:** All the interesting bits of Phase 32 — route, LLM, Obsidian I/O, embed — already have clone-shaped precedents in Phase 29/30/31. Don't invent new patterns. The genuinely new work is: (a) the seed YAML itself, (b) the rapidfuzz integration (~10 LOC), (c) the D-04 component-aggregation function (pure transform, ~30 LOC).

## Runtime State Inventory

*Not applicable — greenfield phase, no rename/refactor/migration.*

## Common Pitfalls

### Pitfall 1: `patch_frontmatter_field` on missing cache files

**What goes wrong:** On first harvest query, the cache file doesn't exist. Calling `patch_frontmatter_field` with `Operation: replace` returns HTTP 400 (field doesn't exist yet). Silent data loss — cache never gets written.

**Why it happens:** Obsidian REST API v3 PATCH replace-on-missing semantics (documented in `project_obsidian_patch_constraint.md` memory).

**How to avoid:** For cache writes, always use `build_harvest_markdown(result)` + `obsidian.put_note(path, content)` (GET-then-PUT pattern). `patch_frontmatter_field` is ONLY for fields that already exist (Phase 29's `relationships` list is the only valid use case).

**Warning signs:** HTTP 400 from Obsidian on first-time harvest; cache file missing from vault.

### Pitfall 2: rapidfuzz silently matching dissimilar names

**What goes wrong:** "Wolf Lord" → "wolf" with a too-low threshold; DM gets wrong harvest data without realizing.

**Why it happens:** `token_set_ratio` is aggressive on subsets. Score 80 is plausible but wrong for distinct creatures.

**How to avoid:** `score_cutoff=85` as the hard gate. Unit-test boundary cases: `("wolf lord", "wolf")` → None; `("alpha wolf", "wolf")` → match; `("goblin", "hobgoblin")` → None. Include these exact cases in `test_harvest_match.py` Wave 0.

**Warning signs:** Missing "Matched to closest: X" note when the user expected an LLM fallback.

### Pitfall 3: Mixed-currency price values

**What goes wrong:** Foundry equipment uses `{"gp": 2, "sp": 5}` for "2 gp 5 sp" items. Naive rendering like `"2 gp"` drops the silver.

**Why it happens:** PF2e mixed-denomination prices are canonical.

**How to avoid:** Normalisation helper:

```python
def format_price(value: dict) -> str:
    parts = []
    for denom in ("gp", "sp", "cp"):
        n = value.get(denom)
        if n:
            parts.append(f"{n} {denom}")
    return " ".join(parts) if parts else "0 cp"
```

Unit-test `{"gp": 2}` → `"2 gp"`, `{"gp": 2, "sp": 5}` → `"2 gp 5 sp"`, `{"cp": 0}` → `"0 cp"`, `{}` → `"0 cp"`.

**Warning signs:** DMs report wrong totals at the table.

### Pitfall 4: LLM hallucinated DCs

**What goes wrong:** LLM invents plausible-but-wrong DCs (e.g., returns "Medicine DC 17 for a level 3 monster" — correct answer per Table 10-5 is DC 18).

**Why it happens:** Models don't perfectly memorise the DC table; off-by-one is common.

**How to avoid:** Embed the DC table verbatim in the system prompt (see Pattern 2 above). Add a post-LLM sanity check: for any seed-known monster level, assert `returned_dc == table_dc + rarity_adj + difficulty_adj`; if the LLM gives `medicine_dc: 17` for a level-3 monster, clamp to 18 and log a WARNING.

**Warning signs:** LLM-generated entries have DCs that don't match Table 10-5 for their stated level.

### Pitfall 5: Whitespace splitting vs pipe-separated names

**What goes wrong:** A monster name with spaces ("dire wolf") gets split into two names ("dire", "wolf") by a naive `rest.split()`.

**Why it happens:** CONTEXT.md says `:pf harvest <monster>[ <monster>...]` (whitespace-separated). This works ONLY if monster names are single-word. Multi-word names break.

**How to avoid:** One of:
- **Option A (recommended):** Use comma-separation like the Phase 31 `:pf npc say <Name>[,<Name>...]` pattern. Change the contract to `:pf harvest <name>[,<name>...]`. This also fits better with the `names: list[str]` Pydantic model.
- **Option B:** Keep whitespace separation but require hyphenated multi-word names ("dire-wolf").

Recommend Option A for consistency with Phase 31's pattern. Update help text accordingly. **This is a CONTEXT.md wording slip, not a design change** — the user decision was "batch support"; the parser format is Claude's discretion.

**Warning signs:** "dire wolf" query returns separate harvest tables for "dire" and "wolf".

### Pitfall 6: Cache hit ignores generated-status flag during batch

**What goes wrong:** Batch response mixes cached (verified=true) and newly-generated (verified=false) monsters. The aggregate-by-component-type view obscures which components came from which source. Footer `"Mixed sources — 2 seed / 1 generated"` (D-04) helps, but individual component entries don't track source.

**Why it happens:** D-04 aggregates by component type across all monsters; per-component generated-status gets flattened.

**How to avoid:** Include source in the component's `monsters` list: `"From: Goblin (seed), Wolf ×2 (seed), Orc (generated)"`. Keep the footer count too. Per CONTEXT.md F-03b, this is visually distinct signalling.

**Warning signs:** DM trusts a generated entry because the embed showed a mix and the verify-flag got lost.

### Pitfall 7: Seeded monster at level > 3 but seed only covers 1-3

**What goes wrong:** DM queries a level-5 goblin variant; fuzzy-match hits "goblin" (level 1); the response uses the level-1 DC (15) instead of level-5 DC (20). DC is too easy; harvesting always succeeds.

**Why it happens:** Fuzzy match preserves the seed entry's level blindly.

**How to avoid:** When a fuzzy match is used, include the input level heuristic (from user input if provided, else default to seed level + note). Recommend: for v1, take the seed level as-is and include the note `"Using seed level L; adjust Medicine DC if your monster is higher-level."` Better solution in v2: accept optional level arg `:pf harvest Wolf/7` (level override).

**Warning signs:** Party with level-5 PCs always succeeds on harvest; DM didn't realize the DC was for level 1.

## Code Examples

### Example 1: Seed YAML fragment [ASSUMED format; planner will finalize]

```yaml
# modules/pathfinder/data/harvest-tables.yaml
# Hand-curated harvest table for PF2e level 1-3 monsters.
# Medicine DCs from Table 10-5 DCs by Level (GM Core pg. 52).
# Craftable vendor values from Foundry VTT pf2e equipment pack (ORC license).
# Redistributed under ORC license with attribution: github.com/foundryvtt/pf2e.

version: "1.0"
source: "foundryvtt-pf2e"
levels: [1, 2, 3]
monsters:
  - name: "Boar"
    level: 2
    traits: [animal]
    components:
      - name: "Hide"
        medicine_dc: 16
        craftable:
          - name: "Leather armor"
            crafting_dc: 14       # item level 0 → DC 14
            value: "2 gp"
          - name: "Waterskin"
            crafting_dc: 14
            value: "5 sp"
      - name: "Tusks"
        medicine_dc: 16
        craftable:
          - name: "Carved scrimshaw"
            crafting_dc: 14
            value: "3 sp"

  - name: "Wolf"
    level: 1
    traits: [animal]
    components:
      - name: "Hide"
        medicine_dc: 15
        craftable:
          - name: "Leather armor"
            crafting_dc: 14
            value: "2 gp"
      - name: "Fangs"
        medicine_dc: 15
        craftable:
          - name: "Bone charm"
            crafting_dc: 14
            value: "5 sp"

  - name: "Goblin Warrior"
    level: 1
    traits: [humanoid, goblin]
    components: []                 # humanoid remains — no standard components
    # Intentionally empty; DM may ratify variants later.
```

### Example 2: Component aggregation (D-04)

```python
def _aggregate_by_component(per_monster: list[dict]) -> list[dict]:
    """Group components across all monsters by component type (D-04).

    Input: list of per-monster dicts, each with components: list[dict].
    Output: list of aggregated component dicts, one per unique component type.
    """
    agg: dict[str, dict] = {}
    for m in per_monster:
        for c in m.get("components", []):
            key = c["type"].lower()
            entry = agg.setdefault(key, {
                "type": c["type"],
                "medicine_dc": c["medicine_dc"],   # first occurrence wins; note if conflict
                "monsters": [],
                "craftable": [],
                "_seen_craftables": set(),
            })
            entry["monsters"].append(m["monster"])
            for craft in c.get("craftable", []):
                craft_key = craft["name"].lower()
                if craft_key not in entry["_seen_craftables"]:
                    entry["craftable"].append(craft)
                    entry["_seen_craftables"].add(craft_key)
    # Strip internal keys
    for entry in agg.values():
        entry.pop("_seen_craftables", None)
    return list(agg.values())
```

### Example 3: Obsidian cache markdown builder

```python
import datetime

def build_harvest_markdown(result: dict) -> str:
    """Build the write-through cache markdown for mnemosyne/pf2e/harvest/<slug>.md (D-03b).

    Mirrors build_npc_markdown() — YAML frontmatter + human-readable body.
    DM can edit the note in Obsidian; set verified: true after confirming.
    """
    frontmatter = {
        "monster": result["monster"],
        "level": result["level"],
        "verified": bool(result.get("verified", False)),
        "source": result.get("source", "llm-generated"),
        "harvested_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
    fm_yaml = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
    body_lines = [f"# {result['monster']}"]
    for c in result.get("components", []):
        body_lines.append(f"\n## {c['type']}")
        body_lines.append(f"- Medicine DC: **{c['medicine_dc']}**")
        if c.get("craftable"):
            body_lines.append("- Craftable:")
            for craft in c["craftable"]:
                body_lines.append(
                    f"  - {craft['name']} — Crafting DC {craft['crafting_dc']}, {craft['value']}"
                )
    if not result.get("verified", False):
        body_lines.append("\n> **⚠ Generated — verify against sourcebook before finalising.**")
    return f"---\n{fm_yaml}---\n\n" + "\n".join(body_lines) + "\n"
```

### Example 4: Fuzzy lookup

```python
# modules/pathfinder/app/harvest_match.py
from rapidfuzz import process, fuzz

def normalize_name(raw: str) -> str:
    """Lowercase, strip articles, trim."""
    s = raw.strip().lower()
    for article in ("the ", "a ", "an "):
        if s.startswith(article):
            s = s[len(article):]
    return s.strip()

def lookup_seed(
    query: str,
    tables,  # HarvestTable Pydantic model
    threshold: float = 85.0,
) -> tuple[object | None, str | None]:
    """Return (monster_entry, note) or (None, None). Note is non-None on fuzzy match."""
    normalized_query = normalize_name(query)

    # Build {normalized_name: entry} map
    choices: dict[str, object] = {
        normalize_name(m.name): m for m in tables.monsters
    }

    # Exact match first
    if normalized_query in choices:
        return choices[normalized_query], None

    # Fuzzy match with cutoff 85
    best = process.extractOne(
        normalized_query,
        list(choices.keys()),
        scorer=fuzz.token_set_ratio,
        score_cutoff=threshold,
    )
    if best is None:
        return None, None

    matched_name, score, _idx = best
    entry = choices[matched_name]
    note = f"Matched to closest entry: {entry.name}. Confirm if this wasn't intended."
    return entry, note
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `fuzzywuzzy` + `python-Levenshtein` | `rapidfuzz` | 2020+; `thefuzz` fork just wraps rapidfuzz | Faster, MIT license (vs fuzzywuzzy's GPL-via-Levenshtein issue), C++ backend |
| PF2e Core Rulebook (2019) DC table | PF2e Remaster GM Core (2024) | March 2024 | Table values unchanged in the Remaster; GM Core pg. 52 is current citation |
| OGL 1.0a for PF2e | ORC license (for Remaster) | 2024 Remaster | Explicitly permits mechanics redistribution; no ambiguity for personal projects |
| `yaml.load()` (unsafe) | `yaml.safe_load()` | long since standard | Prevents `!!python/object` injection |

**Deprecated/outdated:**

- `fuzzywuzzy` — superseded by `rapidfuzz`. Do not install.
- `python-Levenshtein` — legacy fuzzywuzzy dependency. Not needed with rapidfuzz.
- PF2e Core Rulebook (2019) page references — use GM Core pg. 52 for citations.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Level 1-3 monster count in `pathfinder-monster-core` ≈ 25-40 | Foundry pf2e Data Schema | If 100+: hand-curation is still tractable (2-3 hour task); if <10: may skip seed entirely and go pure-LLM. Does not change plan shape, only wave-1 data-entry estimate. |
| A2 | Seed YAML sample format in Example 1 | Code Examples | Pydantic model shape is prescriptive; exact field names can flex during planning. |
| A3 | Monster name parsing contract: comma vs whitespace | Pitfall 5 / CONTEXT.md | Research recommends comma (consistency with Phase 31 `say`); CONTEXT.md said whitespace. Planner or discuss-phase should reconcile before task creation. |
| A4 | Cache file body format (Example 3) | Code Examples | DM-facing; plain-english headings. Not load-bearing for mechanics. |
| A5 | `harvest_tables` is loaded eagerly at lifespan startup (not lazily on first query) | Standard Stack / YAML Loader | Lazy-load is simpler to test but fail-slow on invalid YAML; eager-load is fail-fast. Recommend eager. |

## Open Questions

1. **Does the user accept the reshaped D-01 (F-01 above)?** i.e., "seed is hand-curated using Foundry creature identity + canonical DC tables + Foundry equipment vendor values" rather than "machine-extracted from a non-existent Foundry harvest field."
   - What we know: Foundry pf2e does NOT contain harvest fields; the concept of harvest is third-party Battlezoo (rejected by D-01). Paizo Remaster did not add harvesting.
   - What's unclear: whether the user wants to (a) proceed with hand-curation, (b) defer the seed entirely and ship pure-LLM-with-verify-flag, (c) something else.
   - Recommendation: proceed with hand-curation path (25-40 entries is tractable; DM authority is consistent with SC-4's verify workflow); escalate to discuss-phase if unclear.

2. **Batch command separator — whitespace or comma?**
   - What we know: CONTEXT.md says `:pf harvest <monster>[ <monster>...]` (whitespace). Phase 31 `:pf npc say <Name>[,<Name>...]` uses commas.
   - What's unclear: is "whitespace" in CONTEXT.md a deliberate choice or shorthand?
   - Recommendation: use commas for consistency with Phase 31 and to permit multi-word names ("dire wolf").

3. **Obsidian cache invalidation policy.**
   - What we know: CONTEXT.md notes "Cache invalidation — out of scope for v1; document as future maintenance task."
   - What's unclear: do we need a `:pf harvest refresh <name>` verb to force re-query? Or will DMs just delete the Obsidian note by hand?
   - Recommendation: no refresh verb in v1; document "delete the Obsidian note to force re-query" in help text.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python 3.12 | pathfinder module | ✓ (3.14 local; 3.12 in container) | 3.14.4 / 3.12 | — |
| Docker | Running containerized pathfinder module | ✓ | 29.4.0 | — |
| `uv` | Adding rapidfuzz dep to pyproject.toml | ✓ | 0.11.6 | `pip` (works too) |
| Obsidian REST API | Write-through cache | Assumed running (project constraint) | — | Cache degrades gracefully (logged warning, response still returned) |
| LM Studio | LLM fallback | Assumed running | — | Cache-only path; LLM calls return 503 if unreachable |
| `rapidfuzz` | Fuzzy monster name match | ✗ | — | **No viable fallback**: stdlib `difflib` misses token_set_ratio cases. Must install. |
| Foundry pf2e GitHub access | Equipment price scrape (optional) | ✓ (HTTPS read) | — | Hand-type from Archives of Nethys if GitHub unreachable |

**Missing dependencies with no fallback:** rapidfuzz — install via `uv add rapidfuzz` or add to `pyproject.toml` directly.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.3.0 (asyncio_mode = "auto") |
| Config file | `modules/pathfinder/pyproject.toml` ([tool.pytest.ini_options]) |
| Quick run command | `cd modules/pathfinder && uv run pytest tests/test_harvest.py -x` |
| Full suite command | `cd modules/pathfinder && uv run pytest -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HRV-01 | `/harvest` with one name returns ≥1 component with medicine_dc | integration | `uv run pytest tests/test_harvest.py::test_harvest_single_seed_hit -x` | ❌ Wave 0 |
| HRV-02 | Each component lists craftable items (name+dc+value) | integration | `uv run pytest tests/test_harvest.py::test_harvest_components_have_craftable -x` | ❌ Wave 0 |
| HRV-03 | Each craftable includes vendor value string | unit | `uv run pytest tests/test_harvest.py::test_format_price_mixed_currency -x` | ❌ Wave 0 |
| HRV-04 | Each component has medicine_dc integer | integration | `uv run pytest tests/test_harvest.py::test_harvest_medicine_dc_present -x` | ❌ Wave 0 |
| HRV-05 | Each craftable has crafting_dc integer | integration | same test as HRV-02 | ❌ Wave 0 |
| HRV-06 | `/harvest` with N names returns aggregated component view | integration | `uv run pytest tests/test_harvest.py::test_harvest_batch_aggregated -x` | ❌ Wave 0 |
| D-02 fuzzy | "Alpha Wolf" → seed-match Wolf + note | unit | `uv run pytest tests/test_harvest_match.py::test_fuzzy_subset_matches -x` | ❌ Wave 0 |
| D-02 LLM fallback | Unknown monster returns `[GENERATED — verify]`, `verified: false` | integration | `uv run pytest tests/test_harvest.py::test_harvest_llm_fallback_marks_generated -x` | ❌ Wave 0 |
| D-03b cache | Second query reads from Obsidian, no LLM call | integration | `uv run pytest tests/test_harvest.py::test_harvest_cache_hit_skips_llm -x` | ❌ Wave 0 |
| YAML schema | Invalid harvest-tables.yaml fails lifespan startup | unit | `uv run pytest tests/test_harvest_data.py::test_invalid_yaml_raises -x` | ❌ Wave 0 |
| Embed | `build_harvest_embed` handles single + batch shapes | unit | `cd interfaces/discord && uv run pytest tests/test_bot.py::test_build_harvest_embed_single -x` | ❌ Wave 0 |
| Dispatch | `:pf harvest A,B` calls `/modules/pathfinder/harvest` | integration | `cd interfaces/discord && uv run pytest tests/test_bot.py::test_pf_harvest_dispatch -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_harvest.py -x` + `uv run pytest tests/test_harvest_match.py -x`
- **Per wave merge:** `uv run pytest -x` (full pathfinder suite) + discord `uv run pytest tests/test_bot.py -x`
- **Phase gate:** Full pathfinder + discord suites green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `modules/pathfinder/tests/test_harvest.py` — covers HRV-01..06, D-02 fallback, D-03b cache
- [ ] `modules/pathfinder/tests/test_harvest_match.py` — rapidfuzz threshold boundary cases
- [ ] `modules/pathfinder/tests/test_harvest_data.py` — Pydantic YAML schema validation
- [ ] `modules/pathfinder/data/harvest-tables.yaml` — hand-curated seed (Wave 1 data task)
- [ ] `interfaces/discord/tests/test_bot.py` — add harvest dispatch + embed tests (append to existing file)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `X-Sentinel-Key` header, already enforced by sentinel-core middleware |
| V3 Session Management | no | Stateless request/response |
| V4 Access Control | no | Single-user personal tool; no authorization |
| V5 Input Validation | yes | Pydantic v2 `field_validator` on `names` (same pattern as NPC `_validate_npc_name`); reject control chars, length cap at 100 |
| V6 Cryptography | no | No secrets generation or cryptographic operations |

### Known Threat Patterns for Python/FastAPI + LLM + YAML

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| YAML deserialization injection (`!!python/object`) | Tampering | `yaml.safe_load` (never `yaml.load`) |
| Prompt injection via monster name | Tampering / Information Disclosure | Strict name validator (ASCII printables, length cap); LLM system prompt uses explicit field-name constraints (see Pattern 2) |
| Unbounded name list DoS | Denial of Service | Cap `len(req.names) <= 20` (mirrors NPC say's soft cap at 5; harvest is lighter, 20 is generous) |
| Path traversal via slug | Tampering | Reuse `slugify()` from `app.routes.npc` (strips `../`, non-alphanum) |
| LLM JSON parse failure | Availability | `_strip_code_fences` + `json.JSONDecodeError` → HTTP 500 with message; NOT silent fallback (audit trail matters) |
| Obsidian write failure during cache | Availability | Log WARNING, return result (mirrors Phase 30 PDF-token-image degradation) — don't 500 the user over a cache miss |

## Sources

### Primary (HIGH confidence)

- https://github.com/foundryvtt/pf2e/tree/master/packs — pack directory listing (VERIFIED live)
- https://raw.githubusercontent.com/foundryvtt/pf2e/master/packs/pathfinder-monster-core/boar.json — confirmed no harvest fields (VERIFIED live)
- https://raw.githubusercontent.com/foundryvtt/pf2e/master/packs/pathfinder-monster-core/giant-rat.json — confirmed no harvest fields (VERIFIED live)
- https://raw.githubusercontent.com/foundryvtt/pf2e/master/packs/equipment/leather-armor.json — confirmed `system.price.value`, `system.level.value` (VERIFIED live)
- https://2e.aonprd.com/Rules.aspx?ID=2629 — DC by Level table (VERIFIED live; source GM Core pg. 52)
- https://2e.aonprd.com/Rules.aspx?ID=2627 — DC adjustments + rarity (VERIFIED live)
- https://2e.aonprd.com/Rules.aspx?ID=2628 — Simple DCs (VERIFIED live)
- `modules/pathfinder/app/routes/npc.py` — route pattern (VERIFIED local grep)
- `modules/pathfinder/app/llm.py` — LLM call pattern (VERIFIED local grep)
- `modules/pathfinder/app/obsidian.py` — GET-then-PUT pattern (VERIFIED local grep)
- `modules/pathfinder/app/main.py` — REGISTRATION_PAYLOAD structure (VERIFIED local grep)
- `interfaces/discord/bot.py` — `_pf_dispatch` + `build_stat_embed` patterns (VERIFIED local grep)
- https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html — ratio function docs (VERIFIED)
- https://rapidfuzz.github.io/RapidFuzz/Usage/process.html — `extractOne` signature (VERIFIED)

### Secondary (MEDIUM confidence)

- https://paizo.com/community/communityuse — Community Use Policy (VERIFIED; ambiguous on stat-block reformatting, hence reliance on ORC)
- https://2e.aonprd.com/Licenses.aspx — license summary page referenced via search; ORC confirmed for Remaster (CITED)
- `.planning/research/STACK.md` line 366-385 — prior-art finding #13 (LOW confidence in original) confirmed by live check this session

### Tertiary (LOW confidence / context only)

- Battlezoo Bestiary Monster Parts — noted only to confirm D-01 rejection; not a source for the seed.
- fvtt-pf2e-monster-parts (Cuingamehtar) — noted as alternative only; rejected by D-01.

## Metadata

**Confidence breakdown:**

- Foundry pf2e schema: **HIGH** — 2 monster files + equipment file spot-checked live.
- Absence of harvest fields in Foundry pf2e: **HIGH** — verified via 2 monster files and pack-directory scan; no harvest/loot/monster-parts pack exists.
- DC-by-Level table: **HIGH** — Archives of Nethys direct with GM Core pg. 52 citation.
- rapidfuzz recommendation: **HIGH** — official docs + PyPI + live version check; already the ecosystem standard.
- YAML loader: **HIGH** — PyYAML already in project, standard Pydantic pattern.
- Seed YAML format: **MEDIUM** — pattern is prescriptive but exact field names can flex during planning.
- Level 1-3 monster count in Remaster: **MEDIUM** — estimate only; script would nail it.
- ORC license redistribution safety for personal use: **HIGH** — Monster Core explicitly ORC-licensed, ORC permits mechanics redistribution.
- Architecture patterns (route / LLM / embed / cache): **HIGH** — all four have direct precedents in Phases 29-31 that can be mirrored line-by-line.

**Research date:** 2026-04-23
**Valid until:** 2026-05-23 (30 days — ecosystem is stable; Foundry pf2e schema is versioned and backward-compatible within a major version)

## Plan Skeleton Suggestion

Proposed wave ordering for the planner (subject to `gsd-planner` refinement):

- **Wave 0 (RED):** Write failing tests for HRV-01..06, fuzzy-match boundary cases, YAML schema validation, cache hit/miss, LLM fallback marking. Add `rapidfuzz>=3.14.0` to `pyproject.toml`.
- **Wave 1 (GREEN, data + helpers):**
  - `modules/pathfinder/data/harvest-tables.yaml` — hand-curated seed (20-30 monsters levels 1-3, all major creature types).
  - `modules/pathfinder/app/harvest_data.py` — Pydantic models (HarvestTable, MonsterEntry, HarvestComponent, CraftableItem) + `load_harvest_tables()`.
  - `modules/pathfinder/app/harvest_match.py` — `normalize_name`, `lookup_seed(query, tables, threshold=85)`.
  - `format_price(value: dict) -> str` helper (wherever appropriate — probably `harvest_data.py`).
  - `build_harvest_markdown(result)` in `app.routes.harvest` or a helper module.
  - Extend `llm.py` with `generate_harvest_fallback()`.
- **Wave 2 (GREEN, route + registration):**
  - `modules/pathfinder/app/routes/harvest.py` — Pydantic request/response models + `POST /harvest` handler.
  - `main.py` — extend lifespan to `load_harvest_tables`, register route in `REGISTRATION_PAYLOAD.routes`.
  - `_aggregate_by_component` helper + integration tests for full request flow (mocked Obsidian + LLM).
- **Wave 3 (GREEN, discord):**
  - `interfaces/discord/bot.py` — widen noun-dispatch for "harvest"; add `build_harvest_embed`; update top-level help text; integration test for full dispatch.

This ordering maximises parallelism within waves: Wave 1 can split into YAML-authoring, pydantic-modeling, rapidfuzz-integration, LLM-prompt-engineering tasks. Waves 0 and 3 are TDD-brackets around the data/module work.
