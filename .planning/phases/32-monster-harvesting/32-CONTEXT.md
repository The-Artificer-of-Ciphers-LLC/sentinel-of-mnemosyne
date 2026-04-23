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

### D-01: Data source — Foundry VTT `pf2e` system JSON, seeded for levels 1–3

- **Primary data:** https://github.com/foundryvtt/pf2e — the official Foundry VTT Pathfinder 2e system repo, containing canonical Paizo-licensed monster JSON under `packs/pathfinder-bestiary*/_source/` (and equivalent for Bestiary 2/3).
- **Seed scope (v1):** Extract harvest/crafting data for **level 1–3 monsters only**. These cover the vast majority of early-play encounters; keeps the initial curation pass bounded.
- **Storage location:** `modules/pathfinder/data/harvest-tables.yaml` (hand-typed from the Foundry JSON source, or a small scraper/normalizer — TBD in research).
- **LLM role:** Fills gaps for monsters outside the seed (higher-level or variant creatures). All LLM-generated entries are marked `[GENERATED — verify]` (SC-4 contract).

**Why:** The Foundry pf2e system is actively maintained, is canonical Paizo data under license, and already has structured JSON. Battlezoo "Monster Parts" was considered but rejected — non-canonical (3rd-party Roll For Combat) and per-monster data is prose-in-source-book, not table-shaped.

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
- Discord side: `:pf harvest <name>[ <name>...]` dispatch branch in `_pf_dispatch` (`interfaces/discord/bot.py`). Follows the Phase 31 pipe/comma-parse pattern where applicable.
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

## Open Questions for Research Phase

- Exact path and schema inside `foundryvtt/pf2e` where harvest-relevant fields live (may require a short spike).
- Fuzzy-match library choice (`rapidfuzz` vs `fuzzywuzzy` vs simple SequenceMatcher).
- Whether to generate the seed YAML via a one-time scraper script or hand-type from the JSON (research picks based on field shape).
- Whether to add a `levels: [1,2,3]` top-level field to the YAML for future multi-level expansion.
- Exact LLM prompt scaffold — likely 1-shot with the PF2e DC-by-level table as context.

## Downstream Agent Briefing

**For `gsd-phase-researcher`:**
- Priority research: Foundry pf2e repo layout — confirm harvest-field schema, list level 1–3 monsters, estimate YAML entry count.
- Secondary: PF2e Remaster DC-by-level chart for the LLM fallback prompt.
- Tertiary: fuzzy-match library selection.
- Do NOT research Battlezoo Monster Parts JSON — that data source is rejected (D-01).

**For `gsd-planner`:**
- Seed-extraction plan is likely its own wave-0 task (may be data-only, no tests).
- Module route + Pydantic models + harvest logic mirror Phase 31's 31-04 structure (route + registration + 4 Pydantic models).
- Discord dispatch branch mirrors Phase 31's 31-05 structure.
- Obsidian cache write uses Phase 29's NPC write pattern (GET-then-PUT via `build_npc_markdown`-style helper — but write the equivalent for harvest entries).
- Test stubs first (TDD, like Phase 31 Wave 0 RED).

## Next Steps

```
/gsd-plan-phase 32 ${GSD_WS}     # Research + plan in one pass
```

or if research-first:

```
/gsd-research-phase 32 ${GSD_WS}
/gsd-plan-phase 32 ${GSD_WS}
```
