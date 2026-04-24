---
phase: 32
name: monster-harvesting
milestone: v0.5
requirements: [HRV-01, HRV-02, HRV-03, HRV-04, HRV-05, HRV-06]
depends_on: [28]
discussed: 2026-04-23
---

# Phase 32: Monster Harvesting — Context

## Goal

Given a killed monster, produce a complete harvest report: harvestable components (with Medicine DCs), craftable items derived from each component (with Crafting DCs and PF2e vendor values), and batch support for multi-monster encounters. Covers HRV-01..06.

## Locked Decisions

### D-01 (reshaped 2026-04-23 after research F-01): Hand-curated seed YAML

**Research finding F-01 reshaped this decision.** Live inspection of `foundryvtt/pf2e` confirmed the repo contains NO harvest-specific fields (no `harvest`, `loot`, `materials`, `parts`, `butcher`, `salvage` in any monster JSON or pack). PF2e harvesting is a Battlezoo 3rd-party mechanic, not canonical Paizo. Since Battlezoo was rejected, there is no machine-extractable canonical harvest data to pull.

**Reshaped decision:**
- **Seed format:** Hand-curated `modules/pathfinder/data/harvest-tables.yaml` — one YAML entry per monster.
- **Seed scope (v1):** Level 1–3 monsters from the PF2e Remaster Monster Core. Researcher estimates 25–40 entries; confirm via a ~10-min scraper before curation begins.
- **Data the DM authors per entry:**
  - Harvestable components (thematic; the DM's call for each monster — e.g. boar → hide, tusks, meat)
  - What each component can be crafted into (potion / poison / armor / etc.)
- **Data pulled from canonical sources (not re-authored):**
  - **Monster identity** (name, level, traits) → Foundry pf2e monster JSON
  - **Medicine DC to harvest** → canonical PF2e DC-by-level table (GM Core p.52, captured in 32-RESEARCH.md)
  - **Crafting DC** → same DC-by-level table
  - **Vendor values** → Foundry pf2e equipment pack (`system.price.value: {gp|sp|cp: int}`) — verified real data via research on `leather-armor.json`
- **LLM role:** Unchanged. For monsters outside the level-1–3 seed, the LLM generates harvest data grounded in the captured DC-by-level table. All LLM entries marked `[GENERATED — verify]` (SC-4 contract).
- **License:** PF2e Monster Core is ORC-licensed → redistribution permitted with attribution. Add attribution line to `harvest-tables.yaml` header and to the Discord embed footer.

**Why:** Battlezoo and Foundry harvest-fields-in-JSON both turned out to be dead ends. Hand-curation is unavoidable for the "components per monster" dimension, but the research limits it to a bounded list (25–40 entries) and pulls the numeric DCs + vendor values from canonical sources so the DM doesn't re-author those. Starts small, grows organically as the DM plays.

### D-02: Unknown-monster fallback — fuzzy-match seed first, then LLM

On `/pf harvest <name>`:
1. **Normalize input** (lowercase, strip articles, singularize if obvious).
2. **Exact match** against seed table → return canonical harvest data. No verify flag.
3. **Fuzzy match** against seed (e.g. `alpha wolf` → `wolf` with high score) → return seed data + response-level note: `Matched to closest entry: <seed monster>. Confirm if this wasn't intended.`
4. **No fuzzy match** → LLM fallback. Response marked `[GENERATED — verify]` at both the monster level and per-component level. Response embed visibly signals the generated status.

**Rationale:** DMs commonly throw "Goblin Archer" / "Veteran Wolf" variants at the party. Fuzzy-match preserves the seed's canonical data for the base creature without forcing manual YAML updates for every variant. LLM fills the genuinely unknown tail.

### D-03a: Output format — Discord embed (structured)

Single-monster query renders as a `discord.Embed`, mirroring the Phase 30 `:pf npc stat` / OUT-03 pattern:
- **Title:** Monster name + level
- **Description:** One-line generated-status note when present (`⚠ Generated — verify against sourcebook`)
- **Fields:** One field per component type ("Hide", "Claws", "Venom gland", etc.) with:
  - Medicine DC to harvest
  - Craftable items (nested, bullets): name, Crafting DC, vendor value (gp/sp/cp)
- **Footer:** Source — `FoundryVTT pf2e@<version>` for seed matches; `LLM generated` for fallbacks.

**Rationale:** Embed is readable at a glance, visually distinct from plain-text responses, and reuses the existing `build_stat_embed`-style helper pattern. Consistent with the NPC output family.

### D-03b: Obsidian persistence — write-through cache per monster

- On **first** successful harvest query for a monster, the full report is written to `mnemosyne/pf2e/harvest/<slug>.md` with YAML frontmatter:
  ```yaml
  monster: "Goblin Warrior"
  level: 1
  verified: false     # true when DM confirms; LLM-generated defaults to false
  source: "foundryvtt-pf2e" | "llm-generated"
  harvested_at: <timestamp>
  ```
- On **subsequent** queries, the cache file is read and returned (no LLM call, no re-lookup). The DM may edit the note in Obsidian to promote `verified: true` after checking against Battlezoo or Bestiary prose.
- Uses **GET-then-PUT** via `build_npc_markdown`-style helper (D-09 pattern inherited from Phase 31) — never `patch_frontmatter_field`, per the memory constraint.

**Rationale:** SC-4 wants verifiability; a persistent note with a `verified` flag + human-editable body is the cheapest DM-in-the-loop check. Also gives HRV-04..05 data a durable audit trail.

### D-04: Batch aggregation — grouped by component type

For `/pf harvest Goblin Wolf Orc`:
- **Single embed** titled `Harvest report — 3 monsters`
- **Fields grouped by component type** (not by monster). Example:
  - **Hide** (3 total): Goblin (Medicine DC 12), Wolf ×2 (Medicine DC 14), Orc (Medicine DC 15) → craftable: `Leather Armor` (Crafting DC 15, 2 gp), `Waterskin` (Crafting DC 10, 5 sp)
  - **Claws** (1): Wolf (Medicine DC 14) → craftable: `Improvised Dagger` (Crafting DC 12, 8 cp)
  - **Teeth** (2): Wolf ×2 (Medicine DC 14) → craftable: `Bone Charm` (Crafting DC 14, 3 sp)
- **Footer:** `Mixed sources — 2 seed / 1 generated` (when applicable).

**Rationale:** The DM cares about the craft-outcome side ("what can the party make from this fight?") more than per-monster attribution. Aggregating-by-component puts crafting decisions directly in hand; per-monster detail stays available via the persisted per-monster notes from D-03b.

## Technical Constraints (inherited from Phase 28–31)

- FastAPI sub-service under `modules/pathfinder/` — new route `POST /modules/pathfinder/harvest` (or similar; exact shape for research).
- Pydantic v2 request/response models. Mirror 31-04's `NPCSayRequest`/`NPCSayResponse` structure.
- Obsidian writes via `obsidian.put_note` (GET-then-PUT). Never `patch_frontmatter_field` for new fields.
- Discord side: `:pf harvest <Name>[,<Name>...]` dispatch branch in `_pf_dispatch` (`interfaces/discord/bot.py`). Comma-separated batch (consistent with Phase 31's `:pf npc say Name1,Name2 | ...` — trim whitespace per name to allow multi-word names).
- Unknown-verb help and top-level usage in `_pf_dispatch` updated to include `harvest`.
- All LLM calls go through the existing `litellm.acompletion` pattern with `timeout=60.0`. Reuse `_strip_code_fences` and other existing helpers in `llm.py`.

## Scope Guardrails

**In scope:**
- Harvest tables + lookup
- Medicine DC + Crafting DC + vendor values
- Single and batch queries
- Per-monster cache in Obsidian
- LLM fallback with verify flag

**Out of scope (deferred ideas):**
- Medicine check roll simulation (DM rolls physically or in Foundry — this tool just states the DC)
- Inventory tracking across sessions ("how many hides does the party have?")
- Crafting timelines / time-to-craft
- Rules-engine integration for harvesting-specific rulings — belongs to Phase 33 (`:pf rules`)
- Session-log append of each harvest event — belongs to Phase 34 (`:pf session log`)

## Known Pitfalls

1. **Foundry pf2e repo license:** Verify the harvest-relevant fields are under Paizo's Community Use policy vs. OGL/ORC. Research step must confirm redistribution terms before committing curated YAML to the repo.
2. **Level-range coverage gap:** v1 seeds only levels 1–3. Document this clearly in responses and help text so DMs don't assume missing coverage is a bug.
3. **Fuzzy-match false positives:** "Wolf Lord" fuzzy-matching to "Wolf" would be a wrong result. Research must pick a fuzzy-match library / threshold that errs on the side of LLM-fallback rather than silent mismatches.
4. **LLM hallucinated DCs:** LLM often invents plausible-but-wrong DCs. Prompt must ground with the PF2e DC-by-level table (Core Rulebook / GM Core). Seed the prompt with the level-to-DC chart.
5. **Cache invalidation:** If the Foundry pf2e data updates (monsters rebalanced), seed YAML goes stale. Out of scope for v1; document as a future maintenance task.

## Open Questions for Research Phase — RESOLVED

Research round 1 (32-RESEARCH.md) resolved all five open questions:

- ~~Exact path and schema inside `foundryvtt/pf2e` where harvest-relevant fields live~~ → **F-01**: no such fields exist. D-01 reshaped to hand-curated seed (see above).
- ~~Fuzzy-match library choice~~ → **rapidfuzz >=3.14.0** with `fuzz.token_set_ratio` and `score_cutoff=85.0` (MIT, Python-3.12 wheels).
- ~~Whether to generate the seed YAML via scraper or hand-type~~ → Hand-type the components/craftables dimension; script-extract the level+name list from Foundry pf2e for curation scaffolding.
- ~~Whether to add a `levels` top-level field~~ → Yes — include `level: <int>` per entry in YAML so the DC-by-level table can be consulted at lookup time.
- ~~Exact LLM prompt scaffold~~ → **1-shot with the verbatim DC-by-level table embedded** (captured in 32-RESEARCH.md "DC-by-Level Table" section). Planner embeds this into the prompt template.

## Resolved in discuss-phase round 1

- **Batch separator:** comma (not whitespace). Matches Phase 31 `:pf npc say Name1,Name2 | ...` — enables multi-word monster names via `"Giant Rat, Boar"` splitting. Parse rule: `[n.strip() for n in rest.split(",") if n.strip()]`.
- **Cache refresh verb:** None in v1. Document in help text: "To re-query an LLM-generated entry, delete `mnemosyne/pf2e/harvest/<slug>.md` in Obsidian." Revisit if DMs request an explicit `:pf harvest --refresh` later.

## Downstream Agent Briefing

**Research is done** (see 32-RESEARCH.md). The planner reads it directly.

**For `gsd-planner`:**
- Research is in `32-RESEARCH.md`. All key sections the planner expects (`## Standard Stack`, `## Architecture Patterns`, `## Don't Hand-Roll`, `## Common Pitfalls`, `## Code Examples`) are populated.
- **Hand-curated seed scope caveat (D-01 reshape):** The Wave-1 seed task is hand-curation of the YAML, not JSON extraction. Planner should allocate realistic effort and include a lightweight pre-curation script (pull level + name for L1-3 creatures from Foundry pf2e packs) as a distinct sub-task so the DM has a scaffolded list to fill in.
- Module route + Pydantic models + harvest logic mirror Phase 31's 31-04 structure (route + registration + 4 Pydantic models).
- Discord dispatch branch mirrors Phase 31's 31-05 structure; `_extract_thread_history` does NOT apply here (harvest is stateless lookup, not conversational).
- Obsidian cache write uses Phase 29's NPC write pattern (GET-then-PUT via a new `build_harvest_markdown` helper — cache file shape suggested in RESEARCH.md).
- Test stubs first (TDD, like Phase 31 Wave 0 RED). Suggested wave ordering in RESEARCH.md "Plan Skeleton Suggestion" section.

## Next Steps

```
/gsd-plan-phase 32     # CONTEXT.md + RESEARCH.md both ready → plan is cheap
```
