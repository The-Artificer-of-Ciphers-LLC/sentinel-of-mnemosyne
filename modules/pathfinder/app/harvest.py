"""Harvest helpers for pathfinder module — YAML schema, fuzzy match, price formatter,
markdown builder, component aggregator, cache parser.

Pure-transform module: no LLM calls (those live in app.llm.generate_harvest_fallback),
no Obsidian I/O (those live in app.routes.harvest), no FastAPI dependencies.
Only stdlib + yaml + pydantic + rapidfuzz + logging.

Owns:
- Pydantic schema models (CraftableItem / HarvestComponent / MonsterEntry / HarvestTable)
- Module constants (FUZZY_SCORE_CUTOFF, HARVEST_CACHE_PATH_PREFIX, DC_BY_LEVEL, MAX_BATCH_NAMES)
- load_harvest_tables: YAML -> Pydantic-validated HarvestTable (fail-fast)
- normalize_name / lookup_seed: fuzzy match input -> seed entry
- format_price: {gp|sp|cp} dict -> display string
- build_harvest_markdown: result dict -> Obsidian cache note with ORC attribution footer
- _aggregate_by_component: per-monster -> grouped-by-component-type (D-04)
- _parse_harvest_cache: cached note markdown -> result dict

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

# slugify is re-exported from this module as part of the harvest layer's public
# surface (build_harvest_markdown call-sites in Plan 32-04 slugify monster names
# for the cache path); keep the import alive even if this file is the only caller
# in the refactor window.
__all__ = [
    "CraftableItem",
    "DC_BY_LEVEL",
    "FUZZY_SCORE_CUTOFF",
    "HARVEST_CACHE_PATH_PREFIX",
    "HarvestComponent",
    "HarvestTable",
    "MAX_BATCH_NAMES",
    "MonsterEntry",
    "_aggregate_by_component",
    "_parse_harvest_cache",
    "build_harvest_markdown",
    "format_price",
    "load_harvest_tables",
    "lookup_seed",
    "normalize_name",
    "slugify",
]


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
    all-zeros/None returns "0 cp". Falsy denominations skipped.
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

    Two-tier strategy (Rule 1 deviation from RESEARCH.md — `token_set_ratio` actually
    returns 100 for "wolf lord" vs "wolf" because "wolf" is a token subset, which
    fails the "wolf lord" -> None test and RESEARCH Pitfall 2 intent):
      1) Exact match on normalized query -> (entry, None).
      2) Head-noun anchor: if the last token of the query exactly matches a seed
         name (as a whole token), return that seed with a "Matched to closest"
         note. This catches "alpha wolf" -> Wolf while rejecting "wolf lord" and
         "hobgoblin" (latter is a single token that doesn't equal "goblin").
      3) Typo fallback: `fuzz.ratio` on the whole normalized query against each
         seed; accept only if >= threshold (conservative — "wolfe" -> Wolf at 88.9,
         but "wolf lord" -> Wolf at 61.5 below cutoff).
    """
    normalized_query = normalize_name(query)

    # Build normalized -> entry map
    choices: dict[str, MonsterEntry] = {
        normalize_name(m.name): m for m in tables.monsters
    }

    # Tier 1: exact match — no note
    if normalized_query in choices:
        return choices[normalized_query], None

    # Tier 2: head-noun anchor — last whitespace-separated token is an exact seed match.
    tokens = normalized_query.split()
    if len(tokens) >= 2:
        head = tokens[-1]
        if head in choices:
            entry = choices[head]
            note = f"Matched to closest entry: {entry.name}. Confirm if this wasn't intended."
            return entry, note

    # Tier 3: typo-tolerant whole-string match via fuzz.ratio (Levenshtein-derived;
    # does NOT reward subset overlap, so multi-word compounds like "wolf lord"
    # correctly score below the cutoff).
    best = process.extractOne(
        normalized_query,
        list(choices.keys()),
        scorer=fuzz.ratio,
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
    # CR-03: persist fuzzy-match note across cache round-trips. lookup_seed
    # returns a "Matched to closest entry: <Wolf>..." warning on head-noun
    # and fuzz.ratio hits; this note MUST survive the cache hit so the DM
    # sees the same "did you mean" warning on every repeat query. Only write
    # when non-empty to keep exact-hit notes clean.
    note_val = result.get("note")
    if note_val:
        frontmatter["note"] = note_val
    fm_yaml = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
    body_lines: list[str] = [f"# {result['monster']}"]
    for c in result.get("components", []) or []:
        ctype = c.get("type") or c.get("name") or "?"
        body_lines.append(f"\n## {ctype}")
        # CR-02: defensive lookups — DM-hand-edited cache notes or a malformed
        # cached shape degrade to "?" rather than crashing the markdown build.
        body_lines.append(f"- Medicine DC: **{c.get('medicine_dc', '?')}**")
        if c.get("craftable"):
            body_lines.append("- Craftable:")
            for craft in c.get("craftable", []) or []:
                if not isinstance(craft, dict):
                    continue
                body_lines.append(
                    f"  - {craft.get('name', '?')} — "
                    f"Crafting DC {craft.get('crafting_dc', '?')}, "
                    f"{craft.get('value', '?')}"
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
                # CR-02: defensive get() on medicine_dc — a DM-hand-edited
                # cached note or malformed component no longer crashes here.
                "medicine_dc": c.get("medicine_dc", 0),
                "monsters": [],
                "craftable": [],
                "_seen_craftables": set(),
            })
            entry["monsters"].append(m["monster"])
            for craft in c.get("craftable", []) or []:
                if not isinstance(craft, dict):
                    continue
                # CR-02: skip craftables missing a name rather than crashing.
                craft_name = craft.get("name")
                if not isinstance(craft_name, str) or not craft_name:
                    continue
                craft_key = craft_name.lower()
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
            # CR-03: read `note` back out of the cache frontmatter so the
            # fuzzy-match "did you mean" warning survives a cache hit. Falls
            # back to None for exact-match notes written before CR-03 (and
            # for any cache file whose frontmatter legitimately has no note).
            "note": fm.get("note"),
        }
    except Exception as exc:
        logger.warning("Harvest cache parse failed for %s: %s", name, exc)
        return None
