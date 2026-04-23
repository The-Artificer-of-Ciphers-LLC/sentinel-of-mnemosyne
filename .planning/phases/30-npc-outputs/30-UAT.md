---
status: testing
phase: 30-npc-outputs
source:
  - 30-01-SUMMARY.md
  - 30-02-SUMMARY.md
  - 30-03-SUMMARY.md
started: 2026-04-23T13:00:00Z
updated: 2026-04-23T13:00:00Z
---

## Current Test

number: 1
name: Prereq — `:pf npc create` round-trip after infrastructure fixes
expected: |
  `:pf npc create Jareth | halfling dwarf fisherman, twice as strong as men twice his size`
  in Discord returns a confirmation like "Created NPC: **Jareth** at
  mnemosyne/pf2e/npcs/jareth.md" and writes the note to Obsidian.
awaiting: user response

## Tests

### 1. Prereq — :pf npc create round-trip
expected: `:pf npc create Jareth | halfling dwarf fisherman, twice as strong as men twice his size` in Discord returns a "Created NPC: **Jareth**..." confirmation; Obsidian note exists at `mnemosyne/pf2e/npcs/jareth.md` with YAML frontmatter.
result: pending
note: |
  This is Phase 29 scope but required before OUT tests can run. After the 4 debug
  commits (4515c99 stale-image, eb83cb6 Dockerfile deps, c1d194f openai/ prefix,
  3964c47 OPENAI_API_KEY), create is the first end-to-end check that the stack
  routes a Discord message through Core → pf2e-module → Obsidian successfully.

### 2. OUT-01 — :pf npc export Jareth
expected: Bot replies "Foundry actor JSON for **Jareth**:" with an attached `jareth.json` file. Downloading and opening the JSON shows a valid PF2e actor dict with `type: "npc"`, `name: "Jareth"`, and `system.attributes` populated.
result: pending

### 3. OUT-02 — :pf npc token Jareth
expected: Bot replies with a plain-text Midjourney prompt string containing `--ar 1:1` and `--no text`. The prompt should describe Jareth's visual features (ancestry, class, traits, personality) in comma-separated phrases.
result: pending

### 4. OUT-03 — :pf npc stat Jareth
expected: Bot replies with a formatted Discord Embed showing title like "Jareth (Level 1 Halfling Rogue)", AC/HP inline, Fort/Ref/Will inline, Speed, and a "Mood: neutral" footer. Mechanical stat fields (AC/HP/saves) may be 0 or absent if the NPC has no `## Stats` block yet.
result: pending

### 5. OUT-04 — :pf npc pdf Jareth
expected: Bot attaches a `jareth-stat-card.pdf` file. Opening the PDF shows a one-page stat card with Jareth's name as title, level/ancestry/class subtitle, and (if stats are present) an AC/HP/saves table. If no stats block, header-only PDF is correct.
result: pending

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps

<!-- Populated when any test reports issue. YAML format for plan-phase --gaps consumption. -->
