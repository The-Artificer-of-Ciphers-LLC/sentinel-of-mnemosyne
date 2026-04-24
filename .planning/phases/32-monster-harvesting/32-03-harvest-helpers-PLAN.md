---
plan_id: 32-03
phase: 32
wave: 2
depends_on: [32-01, 32-02]
files_modified:
  - modules/pathfinder/app/harvest.py
  - modules/pathfinder/app/llm.py
autonomous: true
requirements: [HRV-01, HRV-02, HRV-03, HRV-04, HRV-05, HRV-06]
must_haves:
  truths:
    - "modules/pathfinder/app/harvest.py exposes Pydantic models: HarvestTable, MonsterEntry, HarvestComponent, CraftableItem"
    - "modules/pathfinder/app/harvest.py exposes module constants: FUZZY_SCORE_CUTOFF=85.0, HARVEST_CACHE_PATH_PREFIX='mnemosyne/pf2e/harvest', DC_BY_LEVEL (keys 0-25), MAX_BATCH_NAMES=20"
    - "app/harvest.py exposes helpers: load_harvest_tables, normalize_name, lookup_seed, format_price, build_harvest_markdown, _aggregate_by_component, _parse_harvest_cache"
    - "lookup_seed enforces cutoff 85: Wolf Lord→None, Alpha Wolf→Wolf with note, Hobgoblin→None when only Goblin seeded"
    - "format_price handles {gp:2}, {gp:2,sp:5}, {cp:0}, {} correctly (Pitfall 3)"
    - "build_harvest_markdown emits YAML frontmatter (monster, level, verified, source, harvested_at ISO-8601 Z-suffix) + body with H2 per component + ORC attribution footer"
    - "_aggregate_by_component deduplicates craftables per-type across monsters while preserving monster attribution"
    - "app/llm.py exposes generate_harvest_fallback(monster_name, model, api_base=None) that calls litellm.acompletion with timeout=60.0 and embeds DC-by-level table (0-25) verbatim in system prompt"
    - "generate_harvest_fallback post-parse stamps source='llm-generated' and verified=False (T-32-LLM-01 mitigation)"
    - "generate_harvest_fallback applies DC sanity clamp: parsed medicine_dc overwritten to DC_BY_LEVEL[level] if off (Pitfall 4)"
    - "No LLM call or Obsidian I/O in app/harvest.py (pure transform); litellm only in app/llm.py"
    - "app/harvest.py imports slugify from app.routes.npc (reuse per Don't Hand-Roll)"
  tests:
    - "cd modules/pathfinder && uv run python -c 'from app.harvest import HarvestTable, MonsterEntry, HarvestComponent, CraftableItem, load_harvest_tables, normalize_name, lookup_seed, format_price, build_harvest_markdown, _aggregate_by_component, _parse_harvest_cache, FUZZY_SCORE_CUTOFF, HARVEST_CACHE_PATH_PREFIX, DC_BY_LEVEL, MAX_BATCH_NAMES; print(\"all symbols OK\")'"
    - "cd modules/pathfinder && uv run python -c 'from app.llm import generate_harvest_fallback; print(\"OK\")'"
    - "cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py -k 'format_price or fuzzy_subset or fuzzy_wolf_lord or invalid_yaml' -q  # 6 unit tests flip GREEN"
---

<plan_objective>
Ship the pure-transform helper layer + LLM fallback for Phase 32. Creates `modules/pathfinder/app/harvest.py` (Pydantic YAML schema + fuzzy match + price formatter + markdown builder + component aggregator + cache parser), and extends `modules/pathfinder/app/llm.py` with `generate_harvest_fallback`. ZERO route code and ZERO Obsidian I/O — those live in Plan 32-04. After this plan, 6 RED unit tests in test_harvest.py flip GREEN (format_price ×3, fuzzy_subset_matches, fuzzy_wolf_lord_falls_through, invalid_yaml_raises); the remaining tests await Plan 32-04's route wiring.

**Wave 2 placement (Warning 5 fix):** this plan imports `rapidfuzz` which Plan 32-02 installs via `uv sync`. Declaring `depends_on: [32-01, 32-02]` keeps this plan at wave 2 — strictly serialized after the rapidfuzz wheel lands. Executing in parallel with 32-02 would crash on `ModuleNotFoundError: rapidfuzz`.
</plan_objective>

<threat_model>
## STRIDE Register

| Threat ID | Category | Component | Disposition | Mitigation | Test Reference |
|-----------|----------|-----------|-------------|------------|----------------|
| T-32-03-T01 | Tampering | YAML injection via `!!python/object` | mitigate | `load_harvest_tables` uses `yaml.safe_load` only. Pydantic `model_validate` rejects bad types. | test_invalid_yaml_raises (32-01) |
| T-32-03-T02 | Tampering | Fuzzy-match false positive (T-32-SEC-02) | mitigate | `score_cutoff=FUZZY_SCORE_CUTOFF=85.0`; fuzzy hits return `(entry, note)` surfaced as user-visible warning by the route. | test_fuzzy_subset_matches, test_fuzzy_wolf_lord_falls_through (32-01) |
| T-32-03-T03 | Tampering | LLM prompt injection via monster name (T-32-SEC-03) | mitigate | System prompt is a fixed template; user input passed ONLY as user-role message `f"Monster: {monster_name}"`. `json.loads` rejects prose. | test_harvest_llm_fallback_marks_generated (32-01) |
| T-32-03-T04 | Tampering | LLM hallucinated DC (Pitfall 4, T-32-LLM-01) | mitigate | Post-parse DC sanity clamp: compare `parsed["medicine_dc"]` against `DC_BY_LEVEL[parsed["level"]]`; on mismatch, log WARNING and overwrite. | Task 32-03-02 smoke test |
| T-32-03-T05 | Tampering | Path traversal via monster slug | mitigate (delegated) | `slugify` from app.routes.npc already strips non-alphanum. Plan 32-04 is the call-site. | — |
| T-32-03-I01 | Information Disclosure | LLM response leaking system-prompt content | accept | Returned JSON is structured; LLM failure raises in Plan 32-04 (no silent cache). | — |
| T-32-03-D01 | DoS | Huge fuzzy-match search | accept | v1 seed is 20-40 entries; rapidfuzz is O(N) on a tiny list. | — |
| T-32-03-D02 | DoS | Unbounded LLM tokens | accept (delegated) | `timeout=60.0` matches S2 convention; LiteLLM enforces model-side limits. | — |

**Block level:** none HIGH unmitigated. T-32-03-T01/T02/T03/T04 MITIGATED. ASVS L1 satisfied.
</threat_model>

<tasks>

<task id="32-03-01" type="tdd" autonomous="true" tdd="true">
  <name>Task 32-03-01: Create the full modules/pathfinder/app/harvest.py in a single Write (all constants, models, and helpers)</name>
  <read_first>
    - modules/pathfinder/app/dialogue.py (lines 1-22 for module-docstring pattern; lines 56-62 for module-scope constant hoist)
    - modules/pathfinder/app/routes/npc.py (lines 210-217 for slugify; lines 220-237 for _parse_frontmatter log-and-degrade style; lines 256-269 for build_npc_markdown analog)
    - .planning/phases/32-monster-harvesting/32-PATTERNS.md §2 Analog A (module shape), Analog B (constants), Analog C lines 220-237 (`_parse_frontmatter` log-and-degrade style), Analog D (slugify reuse), Gotcha 2 (format_price mixed-denomination rule), Gotcha 3 (lookup_seed tuple return discipline)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md §YAML Loader (HarvestTable reference impl)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md §Common Pitfalls Pitfall 3 (format_price)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md lines 136-170 (DC-by-Level Table verbatim 0-25)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md §Code Examples Example 2 (_aggregate_by_component), Example 3 (build_harvest_markdown), Example 4 (lookup_seed)
  </read_first>
  <behavior>
    - FUZZY_SCORE_CUTOFF == 85.0; HARVEST_CACHE_PATH_PREFIX == "mnemosyne/pf2e/harvest"; MAX_BATCH_NAMES == 20
    - DC_BY_LEVEL[0]==14, [1]==15, [2]==16, [3]==18, [10]==27, [25]==50 (full 0-25 table)
    - HarvestTable.model_validate({...complete...}) returns typed object
    - HarvestTable.model_validate({monsters: []}) missing version/source/levels raises ValidationError
    - load_harvest_tables(nonexistent path) raises FileNotFoundError (no silent catch)
    - format_price({gp:2})=="2 gp"; ({sp:5})=="5 sp"; ({cp:3})=="3 cp"
    - format_price({gp:2, sp:5})=="2 gp 5 sp" (Pitfall 3)
    - format_price({gp:2, sp:5, cp:1})=="2 gp 5 sp 1 cp"
    - format_price({})=="0 cp"; ({cp:0})=="0 cp"; (None)=="0 cp"
    - normalize_name("  The Wolf ") == "wolf" (strip articles + whitespace + lowercase)
    - normalize_name("An Alpha Wolf") == "alpha wolf"
    - normalize_name("A Goblin") == "goblin"
    - lookup_seed("Wolf", tables_with_wolf) == (wolf_entry, None) — exact match, no note
    - lookup_seed("Alpha Wolf", tables_with_wolf) == (wolf_entry, non-None note) — fuzzy, note contains "Matched to closest"
    - lookup_seed("Wolf Lord", tables_with_wolf) == (None, None) — below cutoff 85
    - lookup_seed("Hobgoblin", tables_with_goblin_only) == (None, None) — below cutoff (Pitfall 2)
    - build_harvest_markdown({"monster": "Boar", "level": 2, "verified": False, "source": "llm-generated", "components": [...]}) returns a string with "---\nmonster: Boar\n..." frontmatter + "# Boar" H1 + "## Hide" H2 + "- Medicine DC: **16**" line + "> **⚠ Generated..." quote (because verified=False)
    - build_harvest_markdown with verified=True omits the ⚠ Generated warning block
    - build_harvest_markdown always emits `harvested_at` frontmatter with ISO-8601 UTC Z-suffix
    - build_harvest_markdown always emits an ORC attribution footer (Info 1): "*Source: PF2e (Paizo, ORC license) via FoundryVTT pf2e system — verified: {verified}*"
    - _aggregate_by_component groups by `type` (case-insensitive key); "Hide" from Boar AND Wolf → one field with monsters=["Boar", "Wolf"]; internal _seen_craftables set is stripped before return
    - _parse_harvest_cache(valid_cached_md, name) returns a dict with monster, level, verified, source, components fields
    - _parse_harvest_cache(malformed_text, name) returns None AND logs WARNING (does NOT raise)
  </behavior>
  <action>
CREATE `modules/pathfinder/app/harvest.py` in a **single Write** operation. The file is shipped complete — every import is used by code in the same file at its first use-site (no intermediate unused-import state; no `# noqa: F401` anywhere). Per Blocker 1 fix option A: the whole module lands atomically, mirroring PATTERNS.md §9 "REPEAT OFFENDER" rule applied to worktree-safe large writes.

**Absolute prohibition (CLAUDE.md AI Deferral Ban):** no `# noqa: F401`, no `# type: ignore`, no `# noqa` anywhere in this file. If ruff flags anything, fix the root cause.

```python
"""Harvest helpers for pathfinder module — YAML schema, fuzzy match, price formatter,
markdown builder, component aggregator, cache parser.

Pure-transform module: no LLM calls (those live in app.llm.generate_harvest_fallback),
no Obsidian I/O (those live in app.routes.harvest), no FastAPI dependencies.
Only stdlib + yaml + pydantic + rapidfuzz + logging.

Owns:
- Pydantic schema models (CraftableItem / HarvestComponent / MonsterEntry / HarvestTable)
- Module constants (FUZZY_SCORE_CUTOFF, HARVEST_CACHE_PATH_PREFIX, DC_BY_LEVEL, MAX_BATCH_NAMES)
- load_harvest_tables: YAML → Pydantic-validated HarvestTable (fail-fast)
- normalize_name / lookup_seed: fuzzy match input → seed entry
- format_price: {gp|sp|cp} dict → display string
- build_harvest_markdown: result dict → Obsidian cache note with ORC attribution footer
- _aggregate_by_component: per-monster → grouped-by-component-type (D-04)
- _parse_harvest_cache: cached note markdown → result dict

Per CLAUDE.md AI Deferral Ban: every helper completes its job; no TODO/pass/NotImplementedError.
"""

from __future__ import annotations

import datetime
import logging
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from rapidfuzz import fuzz, process

from app.routes.npc import slugify  # reuse — Don't Hand-Roll (PATTERNS.md §2 Analog D)

logger = logging.getLogger(__name__)


# --- Module constants ---

FUZZY_SCORE_CUTOFF: float = 85.0  # RESEARCH §Fuzzy-Match Recommendation
HARVEST_CACHE_PATH_PREFIX: str = "mnemosyne/pf2e/harvest"  # D-03b
MAX_BATCH_NAMES: int = 20  # RESEARCH §Security Domain — DoS cap

# DC-by-Level table verbatim from GM Core pg. 52 (RESEARCH lines 136-170).
DC_BY_LEVEL: dict[int, int] = {
    0: 14, 1: 15, 2: 16, 3: 18, 4: 19, 5: 20, 6: 22, 7: 23, 8: 24, 9: 26,
    10: 27, 11: 28, 12: 30, 13: 31, 14: 32, 15: 34, 16: 35, 17: 36, 18: 38,
    19: 39, 20: 40, 21: 42, 22: 44, 23: 46, 24: 48, 25: 50,
}


# --- Pydantic schema models ---

class CraftableItem(BaseModel):
    name: str
    crafting_dc: int
    value: str


class HarvestComponent(BaseModel):
    name: str
    medicine_dc: int
    craftable: list[CraftableItem] = Field(default_factory=list)


class MonsterEntry(BaseModel):
    name: str
    level: int
    traits: list[str] = Field(default_factory=list)
    components: list[HarvestComponent] = Field(default_factory=list)


class HarvestTable(BaseModel):
    version: str
    source: str
    levels: list[int]
    monsters: list[MonsterEntry]


# --- YAML loader (fail-fast at lifespan startup) ---

def load_harvest_tables(path: Path) -> HarvestTable:
    """Load and validate harvest YAML. Raises on missing file OR invalid schema.

    Called once at FastAPI lifespan startup (Plan 32-04). Do NOT catch here —
    let exceptions propagate so Docker restart-loop surfaces the problem.
    """
    raw = yaml.safe_load(path.read_text())
    return HarvestTable.model_validate(raw)


# --- Price formatter (HRV-03, Pitfall 3) ---

def format_price(value: dict | None) -> str:
    """Normalise a Foundry-shaped price dict to a display string.

    Accepts {"gp": N}, {"sp": N}, {"cp": N}, or mixed combinations. Empty dict or
    all-zeros/None → "0 cp". Falsy denominations skipped.
    """
    if not value:
        return "0 cp"
    parts: list[str] = []
    for denom in ("gp", "sp", "cp"):
        n = value.get(denom)
        if n:  # skips 0 and None
            parts.append(f"{n} {denom}")
    return " ".join(parts) if parts else "0 cp"


# --- Input normalisation ---

def normalize_name(raw: str) -> str:
    """Lowercase, strip articles, trim. Used before fuzzy match (RESEARCH §Fuzzy-Match)."""
    s = raw.strip().lower()
    for article in ("the ", "a ", "an "):
        if s.startswith(article):
            s = s[len(article):]
    return s.strip()


# --- Fuzzy seed lookup (D-02) ---

def lookup_seed(
    query: str,
    tables: HarvestTable,
    threshold: float = FUZZY_SCORE_CUTOFF,
) -> tuple[MonsterEntry | None, str | None]:
    """Return (entry, note). `note` is None on exact match, non-None on fuzzy match.

    Tuple return contract: callers check `entry is not None`, not truthiness of `note`.
    Never returns a sentinel empty entry (PATTERNS.md §2 Gotcha 3).
    """
    normalized_query = normalize_name(query)

    # Build normalized → entry map
    choices: dict[str, MonsterEntry] = {
        normalize_name(m.name): m for m in tables.monsters
    }

    # Exact match first — no note
    if normalized_query in choices:
        return choices[normalized_query], None

    # Fuzzy match with cutoff
    best = process.extractOne(
        normalized_query,
        list(choices.keys()),
        scorer=fuzz.token_set_ratio,
        score_cutoff=threshold,
    )
    if best is None:
        return None, None

    matched_name, _score, _idx = best
    entry = choices[matched_name]
    note = f"Matched to closest entry: {entry.name}. Confirm if this wasn't intended."
    return entry, note


# --- Obsidian cache markdown builder (D-03b) ---

def build_harvest_markdown(result: dict) -> str:
    """Build the write-through cache markdown for mnemosyne/pf2e/harvest/<slug>.md.

    Mirrors build_npc_markdown (routes/npc.py lines 256-269) — YAML frontmatter +
    human-readable body. DM can edit the note in Obsidian; set verified: true after
    confirming. Uses datetime.UTC per Python 3.12+ convention (avoids utcnow
    deprecation).

    The footer always carries the ORC attribution (Info 1): the DM's cached note
    remains traceable to Paizo + Foundry pf2e upstream even after further edits.
    """
    verified_flag = bool(result.get("verified", False))
    frontmatter = {
        "monster": result["monster"],
        "level": result["level"],
        "verified": verified_flag,
        "source": result.get("source", "llm-generated"),
        "harvested_at": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
    }
    fm_yaml = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
    body_lines: list[str] = [f"# {result['monster']}"]
    for c in result.get("components", []) or []:
        ctype = c.get("type") or c.get("name") or "?"
        body_lines.append(f"\n## {ctype}")
        body_lines.append(f"- Medicine DC: **{c['medicine_dc']}**")
        if c.get("craftable"):
            body_lines.append("- Craftable:")
            for craft in c["craftable"]:
                body_lines.append(
                    f"  - {craft['name']} — Crafting DC {craft['crafting_dc']}, {craft['value']}"
                )
    if not verified_flag:
        body_lines.append("\n> **⚠ Generated — verify against sourcebook before finalising.**")
    # ORC attribution footer (Info 1) — always present regardless of source.
    body_lines.append(
        f"\n*Source: PF2e (Paizo, ORC license) via FoundryVTT pf2e system — verified: {str(verified_flag).lower()}*"
    )
    return f"---\n{fm_yaml}---\n\n" + "\n".join(body_lines) + "\n"


# --- Component aggregation (D-04) ---

def _aggregate_by_component(per_monster: list[dict]) -> list[dict]:
    """Group components across all monsters by component type.

    Input: list of per-monster result dicts. Output: list of aggregated component
    dicts with {type, medicine_dc, craftable, monsters}. Craftables deduplicated
    per-type (case-insensitive name key).
    """
    agg: dict[str, dict] = {}
    for m in per_monster:
        for c in m.get("components", []) or []:
            ctype = c.get("type") or c.get("name") or "?"
            key = ctype.lower()
            entry = agg.setdefault(key, {
                "type": ctype,
                "medicine_dc": c["medicine_dc"],
                "monsters": [],
                "craftable": [],
                "_seen_craftables": set(),
            })
            entry["monsters"].append(m["monster"])
            for craft in c.get("craftable", []) or []:
                craft_key = craft["name"].lower()
                if craft_key not in entry["_seen_craftables"]:
                    entry["craftable"].append(craft)
                    entry["_seen_craftables"].add(craft_key)
    # Strip internal bookkeeping key before return
    for entry in agg.values():
        entry.pop("_seen_craftables", None)
    return list(agg.values())


# --- Cache note parser (D-03b read path) ---

def _parse_harvest_cache(note_text: str, name: str) -> dict | None:
    """Parse a cached harvest note back into a result dict. Returns None on malformed.

    Log-and-degrade shape matches `_parse_frontmatter` in routes/npc.py lines 220-237
    (PATTERNS.md §2 Analog C). Route handler treats None identically to 'no cache file'.
    """
    try:
        if not note_text.startswith("---"):
            return None
        end = note_text.find("---", 3)
        if end == -1:
            return None
        frontmatter_text = note_text[3:end].strip()
        fm = yaml.safe_load(frontmatter_text) or {}
        if not isinstance(fm, dict) or "monster" not in fm:
            return None
        # Body parse — lightweight H2 scan for component types and Medicine DC / Craftable lines.
        body = note_text[end + 3:]
        components: list[dict] = []
        current: dict | None = None
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                if current is not None:
                    components.append(current)
                current = {"type": stripped[3:].strip(), "medicine_dc": 0, "craftable": []}
            elif current is not None and stripped.startswith("- Medicine DC:"):
                m = re.search(r"\*\*(\d+)\*\*", stripped)
                if m:
                    current["medicine_dc"] = int(m.group(1))
            elif current is not None and stripped.startswith("- ") and "Crafting DC" in stripped:
                m = re.match(r"-\s+(.+?)\s+—\s+Crafting DC\s+(\d+),\s+(.+)$", stripped)
                if m:
                    current["craftable"].append({
                        "name": m.group(1).strip(),
                        "crafting_dc": int(m.group(2)),
                        "value": m.group(3).strip(),
                    })
        if current is not None:
            components.append(current)
        return {
            "monster": fm.get("monster", name),
            "level": fm.get("level", 1),
            "verified": bool(fm.get("verified", False)),
            "source": fm.get("source", "cache"),
            "components": components,
            "note": None,
        }
    except Exception as exc:
        logger.warning("Harvest cache parse failed for %s: %s", name, exc)
        return None
```

**Smoke test after implementing** — one pass, covers every helper:
```bash
cd modules/pathfinder && uv run python -c "
from app.harvest import (
    HarvestTable, format_price, normalize_name, lookup_seed,
    build_harvest_markdown, _aggregate_by_component, _parse_harvest_cache,
    FUZZY_SCORE_CUTOFF, HARVEST_CACHE_PATH_PREFIX, DC_BY_LEVEL, MAX_BATCH_NAMES,
)

# Constants
assert FUZZY_SCORE_CUTOFF == 85.0
assert HARVEST_CACHE_PATH_PREFIX == 'mnemosyne/pf2e/harvest'
assert MAX_BATCH_NAMES == 20
# Full DC table 0-25 (Warning 2 fix — no truncation)
assert DC_BY_LEVEL[0] == 14 and DC_BY_LEVEL[1] == 15 and DC_BY_LEVEL[2] == 16
assert DC_BY_LEVEL[3] == 18 and DC_BY_LEVEL[10] == 27 and DC_BY_LEVEL[25] == 50
assert len(DC_BY_LEVEL) == 26

# format_price
assert format_price({'gp': 2}) == '2 gp'
assert format_price({'gp': 2, 'sp': 5}) == '2 gp 5 sp'
assert format_price({}) == '0 cp'
assert format_price({'cp': 0}) == '0 cp'
assert format_price(None) == '0 cp'

# normalize_name
assert normalize_name('  The Wolf ') == 'wolf'
assert normalize_name('An Alpha Wolf') == 'alpha wolf'
assert normalize_name('A Goblin') == 'goblin'

# Build a stub HarvestTable
t = HarvestTable.model_validate({
    'version': '1.0', 'source': 'foundryvtt-pf2e', 'levels': [1],
    'monsters': [
        {'name': 'Wolf', 'level': 1, 'traits': ['animal'], 'components': [
            {'name': 'Hide', 'medicine_dc': 15, 'craftable': [{'name': 'Leather armor', 'crafting_dc': 14, 'value': '2 gp'}]},
        ]},
    ],
})

entry, note = lookup_seed('Wolf', t)
assert entry is not None and entry.name == 'Wolf' and note is None

entry, note = lookup_seed('Alpha Wolf', t)
assert entry is not None and entry.name == 'Wolf' and 'Matched to closest' in note

entry, note = lookup_seed('Wolf Lord', t)
assert entry is None and note is None

# hobgoblin vs goblin (Pitfall 2 boundary — use a separate tables instance)
t2 = HarvestTable.model_validate({'version':'1.0','source':'x','levels':[1],'monsters':[{'name':'Goblin','level':1,'traits':[],'components':[]}]})
entry, note = lookup_seed('Hobgoblin', t2)
assert entry is None and note is None, (entry, note)

# build_harvest_markdown — unverified (footer + warning)
md = build_harvest_markdown({
    'monster': 'Boar', 'level': 2, 'verified': False, 'source': 'llm-generated',
    'components': [{'type': 'Hide', 'medicine_dc': 16, 'craftable': [{'name': 'Leather armor', 'crafting_dc': 14, 'value': '2 gp'}]}],
})
assert md.startswith('---\n')
assert 'monster: Boar' in md
assert 'level: 2' in md
assert 'verified: false' in md
assert 'source: llm-generated' in md
assert 'harvested_at:' in md
assert '# Boar' in md
assert '## Hide' in md
assert '- Medicine DC: **16**' in md
assert '⚠ Generated' in md
# Info 1: ORC attribution footer always present
assert 'ORC license' in md
assert 'FoundryVTT pf2e system' in md
assert 'verified: false' in md  # in footer too (duplicated; frontmatter already has it)

# build_harvest_markdown — verified (no ⚠, footer still present)
md2 = build_harvest_markdown({'monster': 'X', 'level': 1, 'verified': True, 'source': 'seed', 'components': []})
assert '⚠ Generated' not in md2
assert 'ORC license' in md2  # Info 1: footer still present even when verified

# _aggregate_by_component
agg = _aggregate_by_component([
    {'monster': 'Boar', 'components': [{'type': 'Hide', 'medicine_dc': 16, 'craftable': [{'name': 'Leather armor', 'crafting_dc': 14, 'value': '2 gp'}]}]},
    {'monster': 'Wolf', 'components': [{'type': 'Hide', 'medicine_dc': 15, 'craftable': [{'name': 'Leather armor', 'crafting_dc': 14, 'value': '2 gp'}]}]},
])
assert len(agg) == 1
hide = agg[0]
assert hide['type'] == 'Hide'
assert set(hide['monsters']) == {'Boar', 'Wolf'}
assert len(hide['craftable']) == 1  # Leather armor deduplicated
assert '_seen_craftables' not in hide  # internal key stripped

# _parse_harvest_cache round-trip
parsed = _parse_harvest_cache(md, 'Boar')
assert parsed is not None
assert parsed['monster'] == 'Boar' and parsed['level'] == 2 and parsed['verified'] is False
assert parsed['source'] == 'llm-generated'
assert len(parsed['components']) == 1
assert parsed['components'][0]['medicine_dc'] == 16
assert parsed['components'][0]['craftable'][0]['name'] == 'Leather armor'
assert parsed['components'][0]['craftable'][0]['crafting_dc'] == 14

# Malformed cache returns None
assert _parse_harvest_cache('not a cache file', 'X') is None
assert _parse_harvest_cache('', 'X') is None
assert _parse_harvest_cache('---\nnot: frontmatter\n---', 'X') is None  # no 'monster' key

print('OK')
"
```
  </action>
  <acceptance_criteria>
    - test -f modules/pathfinder/app/harvest.py
    - grep -E '^class HarvestTable\(BaseModel\)' modules/pathfinder/app/harvest.py matches
    - grep -E '^class (MonsterEntry|HarvestComponent|CraftableItem)\(BaseModel\)' modules/pathfinder/app/harvest.py matches 3 times (one for each class name across lines)
    - grep -F 'FUZZY_SCORE_CUTOFF: float = 85.0' modules/pathfinder/app/harvest.py matches
    - grep -F 'HARVEST_CACHE_PATH_PREFIX: str = "mnemosyne/pf2e/harvest"' modules/pathfinder/app/harvest.py matches
    - grep -F 'MAX_BATCH_NAMES: int = 20' modules/pathfinder/app/harvest.py matches
    - grep -F 'from app.routes.npc import slugify' modules/pathfinder/app/harvest.py matches
    - grep -F 'yaml.safe_load' modules/pathfinder/app/harvest.py matches; grep -c 'yaml\.load(' modules/pathfinder/app/harvest.py returns 1 (safe_load only — the `yaml.load(` count matches `yaml.safe_load` substring)
    - grep -E '^def normalize_name\(' modules/pathfinder/app/harvest.py matches
    - grep -E '^def lookup_seed\(' modules/pathfinder/app/harvest.py matches
    - grep -E '^def build_harvest_markdown\(' modules/pathfinder/app/harvest.py matches
    - grep -E '^def _aggregate_by_component\(' modules/pathfinder/app/harvest.py matches
    - grep -E '^def _parse_harvest_cache\(' modules/pathfinder/app/harvest.py matches
    - grep -F 'process.extractOne' modules/pathfinder/app/harvest.py matches (rapidfuzz used)
    - grep -F 'fuzz.token_set_ratio' modules/pathfinder/app/harvest.py matches
    - grep -F 'score_cutoff=threshold' modules/pathfinder/app/harvest.py matches
    - grep -F 'datetime.datetime.now(datetime.UTC)' modules/pathfinder/app/harvest.py matches (not deprecated utcnow)
    - grep -F '⚠ Generated' modules/pathfinder/app/harvest.py matches
    - grep -F 'Matched to closest entry:' modules/pathfinder/app/harvest.py matches
    - Info 1: ORC attribution footer is emitted: grep -F 'ORC license' modules/pathfinder/app/harvest.py matches AND grep -F 'FoundryVTT pf2e system' modules/pathfinder/app/harvest.py matches
    - No `# noqa` or `# type: ignore` anywhere: grep -cE '# (noqa|type: ignore)' modules/pathfinder/app/harvest.py returns 0 (Blocker 1 — no F401 workarounds)
    - No litellm, httpx, FastAPI imports: grep -cE '^(from|import) (litellm|httpx|fastapi)' modules/pathfinder/app/harvest.py returns 0 (pure-transform discipline)
    - DC_BY_LEVEL has 26 entries (keys 0-25): the smoke test asserts `len(DC_BY_LEVEL) == 26`
    - 3 format_price tests GREEN: cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py -k 'format_price' -q exits 0
    - 2 fuzzy Wave-0 tests GREEN: cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py -k 'fuzzy_subset or fuzzy_wolf_lord' -q exits 0 (2 passed)
    - 1 YAML validation test GREEN: cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py::test_invalid_yaml_raises -q exits 0
    - Smoke test exits 0 with OK
    - grep -v '^#' modules/pathfinder/app/harvest.py | grep -E '(TODO|FIXME|NotImplementedError|raise NotImplementedError)' returns 0 matches
  </acceptance_criteria>
  <automated>cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py -k 'format_price or fuzzy_subset or fuzzy_wolf_lord or invalid_yaml' -q</automated>
</task>

<task id="32-03-02" type="tdd" autonomous="true" tdd="true">
  <name>Task 32-03-02: Add generate_harvest_fallback to app/llm.py with full DC table 0-25</name>
  <read_first>
    - modules/pathfinder/app/llm.py (full file — especially lines 33-73 for extract_npc_fields analog to mirror; lines 21-30 for _strip_code_fences; lines 60-69 for kwargs+api_base pattern S2)
    - .planning/phases/32-monster-harvesting/32-PATTERNS.md §4 (shape rules 1-7, DC sanity clamp)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md §Code Examples Pattern 2 (full reference impl + verbatim prompt)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md lines 136-170 (DC-by-Level Table verbatim 0-25 — ALL 26 levels land in the prompt, no truncation)
  </read_first>
  <behavior>
    - Signature: async def generate_harvest_fallback(monster_name: str, model: str, api_base: str | None = None) -> dict
    - Calls litellm.acompletion once with messages=[system, user(f"Monster: {monster_name}")], timeout=60.0
    - System prompt contains VERBATIM the full 0-25 DC table — every level appears as "Level N: DC X" (Warning 2 fix — no truncation at level 10)
    - System prompt instructs JSON-only output with exact keys: monster, level, components (with type, medicine_dc, craftable[])
    - Uses kwargs pattern with conditional api_base (S2): kwargs.setdefault won't work; use `if api_base: kwargs["api_base"] = api_base` block
    - Calls _strip_code_fences(content) before json.loads (S2)
    - Post-parse: stamps source="llm-generated" AND verified=False
    - Post-parse: DC sanity clamp — if parsed level L is in DC_BY_LEVEL AND parsed medicine_dc != DC_BY_LEVEL[L], log WARNING and overwrite medicine_dc to DC_BY_LEVEL[L] (for each component)
    - JSON parse failure raises (route layer catches and returns 500 per Plan 32-04) — DO NOT salvage
  </behavior>
  <action>
EDIT `modules/pathfinder/app/llm.py`:

**Step 1 — Add import for DC_BY_LEVEL at the top of the file.** Find the existing imports. Add:

```python
from app.harvest import DC_BY_LEVEL
```

(Do this in the SAME Edit as the function body below, per S10 ruff rule — if the import lands alone, ruff strips it.)

**Step 2 — Append `generate_harvest_fallback` function at the end of llm.py.** Keep the shape identical to `extract_npc_fields` (lines 33-73):

```python
async def generate_harvest_fallback(
    monster_name: str,
    model: str,
    api_base: str | None = None,
) -> dict:
    """Generate a harvest table for an unseeded monster (D-02 LLM fallback).

    Grounds the LLM in the canonical DC-by-level table (GM Core pg. 52, levels 0-25)
    embedded verbatim in the system prompt, plus a sampled equipment-price reference
    so DCs and vendor values land in plausible ranges.

    Returns a dict stamped with source='llm-generated' AND verified=False (SC-4).
    Post-parse DC sanity clamp overwrites any component medicine_dc that doesn't
    match DC_BY_LEVEL for the stated monster level (Pitfall 4 mitigation).

    Raises on malformed JSON — the route layer (Plan 32-04) catches and returns 500.
    Do NOT salvage a partial result; a half-result cached would poison the DM's data.
    """
    system_prompt = (
        "You are a Pathfinder 2e Remaster DM assistant. "
        "Given a monster name, return a JSON object describing harvestable components "
        "and craftable items. Ground your DCs in the PF2e DC-by-level table (GM Core pg. 52):\n"
        "Level 0: DC 14, Level 1: DC 15, Level 2: DC 16, Level 3: DC 18, "
        "Level 4: DC 19, Level 5: DC 20, Level 6: DC 22, Level 7: DC 23, "
        "Level 8: DC 24, Level 9: DC 26, Level 10: DC 27, Level 11: DC 28, "
        "Level 12: DC 30, Level 13: DC 31, Level 14: DC 32, Level 15: DC 34, "
        "Level 16: DC 35, Level 17: DC 36, Level 18: DC 38, Level 19: DC 39, "
        "Level 20: DC 40, Level 21: DC 42, Level 22: DC 44, Level 23: DC 46, "
        "Level 24: DC 48, Level 25: DC 50. "
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

    # Stamp source + verified per SC-4 / T-32-LLM-01.
    parsed["source"] = "llm-generated"
    parsed["verified"] = False

    # DC sanity clamp (Pitfall 4) — trust the table, not the LLM.
    level = parsed.get("level")
    if isinstance(level, int) and level in DC_BY_LEVEL:
        expected_dc = DC_BY_LEVEL[level]
        for comp in parsed.get("components", []) or []:
            if isinstance(comp, dict):
                observed = comp.get("medicine_dc")
                if isinstance(observed, int) and observed != expected_dc:
                    logger.warning(
                        "LLM harvest DC mismatch for %s: level=%d observed_dc=%d expected=%d (overwriting)",
                        monster_name, level, observed, expected_dc,
                    )
                    comp["medicine_dc"] = expected_dc
    return parsed
```

Smoke test (does NOT call the LLM — mocks it):
```bash
cd modules/pathfinder && uv run python -c "
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import json
import app.llm as llm

# Fake LLM response: mismatched DC that clamp MUST fix (Level 15 → DC 34; LLM returned 33)
fake_reply = json.dumps({
    'monster': 'Balor',
    'level': 15,
    'components': [{'type': 'Hide', 'medicine_dc': 33, 'craftable': [{'name': 'X', 'crafting_dc': 33, 'value': '1 gp'}]}],
})
fake = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=fake_reply))])

async def run():
    with patch.object(llm, 'litellm') as mock_llm:
        mock_llm.acompletion = AsyncMock(return_value=fake)
        out = await llm.generate_harvest_fallback('Balor', model='openai/local-model')
    return out

out = asyncio.run(run())
assert out['source'] == 'llm-generated'
assert out['verified'] is False
# Level 15 → DC 34 per full DC table. LLM returned 33 → clamp must overwrite to 34.
assert out['components'][0]['medicine_dc'] == 34, out['components'][0]
print('OK')
"
```
  </action>
  <acceptance_criteria>
    - grep -E '^async def generate_harvest_fallback\(' modules/pathfinder/app/llm.py matches
    - grep -F 'from app.harvest import DC_BY_LEVEL' modules/pathfinder/app/llm.py matches
    - grep -F 'timeout": 60.0' modules/pathfinder/app/llm.py matches (occurs in multiple functions — verify non-zero)
    - grep -F 'kwargs["api_base"] = api_base' modules/pathfinder/app/llm.py matches (S2 conditional pattern)
    - grep -F '_strip_code_fences' modules/pathfinder/app/llm.py matches (reused per S2)
    - Warning 2: full DC table 0-25 verbatim in system prompt — every level appears:
      - grep -F 'Level 0: DC 14' modules/pathfinder/app/llm.py matches
      - grep -F 'Level 10: DC 27' modules/pathfinder/app/llm.py matches
      - grep -F 'Level 15: DC 34' modules/pathfinder/app/llm.py matches
      - grep -F 'Level 20: DC 40' modules/pathfinder/app/llm.py matches
      - grep -F 'Level 25: DC 50' modules/pathfinder/app/llm.py matches
      - No truncation marker ("..." between level 10 and 11): grep -F 'Level 10: DC 27, Level 11: DC 28' modules/pathfinder/app/llm.py matches (adjacency proves the 0-25 chain is continuous)
    - grep -F 'parsed["source"] = "llm-generated"' modules/pathfinder/app/llm.py matches
    - grep -F 'parsed["verified"] = False' modules/pathfinder/app/llm.py matches
    - grep -F 'DC_BY_LEVEL[level]' modules/pathfinder/app/llm.py matches (clamp present)
    - Smoke test exits 0 with OK (mocks litellm, verifies level-15 clamp using upper-table DCs)
    - cd modules/pathfinder && uv run python -c 'from app.llm import generate_harvest_fallback; print("OK")' exits 0
    - No Phase 29/30/31 regressions: cd modules/pathfinder && uv run python -m pytest tests/ -q -k 'not harvest' exits 0
    - grep -v '^#' modules/pathfinder/app/llm.py | grep -E '(TODO|FIXME|NotImplementedError|raise NotImplementedError)' returns 0 matches in lines added by this task
  </acceptance_criteria>
  <automated>cd modules/pathfinder && uv run python -c "
import asyncio, json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import app.llm as llm
fake_reply = json.dumps({'monster': 'Balor', 'level': 15, 'components': [{'type': 'Hide', 'medicine_dc': 33, 'craftable': []}]})
fake = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=fake_reply))])
async def run():
    with patch.object(llm, 'litellm') as mock_llm:
        mock_llm.acompletion = AsyncMock(return_value=fake)
        return await llm.generate_harvest_fallback('Balor', model='openai/local-model')
out = asyncio.run(run())
assert out['source'] == 'llm-generated' and out['verified'] is False
assert out['components'][0]['medicine_dc'] == 34
print('OK')
"</automated>
</task>

</tasks>

<verification>
After both tasks complete:

```bash
# 1. All new symbols importable
cd modules/pathfinder && uv run python -c "
from app.harvest import (
    HarvestTable, MonsterEntry, HarvestComponent, CraftableItem,
    load_harvest_tables, normalize_name, lookup_seed, format_price,
    build_harvest_markdown, _aggregate_by_component, _parse_harvest_cache,
    FUZZY_SCORE_CUTOFF, HARVEST_CACHE_PATH_PREFIX, DC_BY_LEVEL, MAX_BATCH_NAMES,
)
from app.llm import generate_harvest_fallback
assert len(DC_BY_LEVEL) == 26
print('all symbols OK')
"

# 2. 6 Wave-0 unit tests flip GREEN (format_price ×3, fuzzy ×2, invalid_yaml ×1)
cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py -k 'format_price or fuzzy_subset or fuzzy_wolf_lord or invalid_yaml' -q
# Expected: 6 passed

# 3. Remaining RED tests (the ones that need the route handler in Plan 32-04) still fail
cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py -q
# Expected: 6 passed + test_rapidfuzz_importable (1) = 7; 14 still failed. Exit != 0.

# 4. AI Deferral Ban scan + no-suppression scan
grep -v '^#' modules/pathfinder/app/harvest.py | grep -E '(TODO|FIXME|NotImplementedError|raise NotImplementedError)' && echo FAIL || echo PASS
grep -cE '# (noqa|type: ignore)' modules/pathfinder/app/harvest.py
# Expected: 0 for the second grep (Blocker 1 — no suppressions)

# 5. Pure-transform discipline — no litellm/httpx/fastapi in harvest.py
grep -cE '^(from|import) (litellm|httpx|fastapi)' modules/pathfinder/app/harvest.py
# Expected: 0

# 6. No Phase 29/30/31 regressions
cd modules/pathfinder && uv run python -m pytest tests/ -q -k 'not harvest'
# Expected: all green
```
</verification>

<success_criteria>
- `modules/pathfinder/app/harvest.py` exists as a single-Write file with 4 Pydantic models, 4 constants, 7 helpers (load_harvest_tables, normalize_name, lookup_seed, format_price, build_harvest_markdown, _aggregate_by_component, _parse_harvest_cache) — all imports used at first use-site, no `# noqa`, no `# type: ignore`
- `modules/pathfinder/app/llm.py` extended with `generate_harvest_fallback` following S2 conventions + DC sanity clamp + full 0-25 DC table embedded verbatim in system prompt
- build_harvest_markdown always emits the ORC attribution footer (Info 1)
- 6 Wave-0 unit tests flip GREEN: 3 format_price, 2 fuzzy lookup, 1 invalid YAML
- `test_rapidfuzz_importable` remains GREEN from Plan 32-02
- Pure-transform discipline maintained — no litellm/httpx/fastapi imports in harvest.py
- AI Deferral Ban: zero TODO/FIXME/NotImplementedError/pass-as-body introduced; zero `# noqa` suppressions
- No Phase 29/30/31 regressions
</success_criteria>

<output>
Create `.planning/phases/32-monster-harvesting/32-03-SUMMARY.md` documenting:
- Files created/modified: app/harvest.py (new, ~250 lines, single Write — no `# noqa`), app/llm.py (+1 function + 1 import)
- Public symbols exported by app.harvest
- LLM fallback contract: DC-by-level 0-25 embedded verbatim in prompt + post-parse clamp + source/verified stamps
- Smoke test outputs (2× OK)
- Wave-0 unit tests that flipped GREEN (6 + the rapidfuzz smoke)
- Confirmation: no Phase 29/30/31 regressions
- Note: pure-transform layer complete; route + models + Obsidian I/O land in Plan 32-04.
- Worktree note per S9: commit with `--no-verify` in parallel worktrees.
</output>
</output>
