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

number: 5
name: OUT-04 — `:pf npc pdf Jareth`
expected: |
  Bot attaches jareth-stat-card.pdf. One-page card with Jareth's name
  as title, level/ancestry/class subtitle. If no ## Stats block,
  header-only PDF is correct per D-20.
awaiting: user response

## Tests

### 1. Prereq — :pf npc create round-trip
expected: `:pf npc create Jareth | halfling dwarf fisherman, twice as strong as men twice his size` in Discord returns a "Created NPC: **Jareth**..." confirmation; Obsidian note exists at `mnemosyne/pf2e/npcs/jareth.md` with YAML frontmatter.
result: pass
note: |
  Validates the full Discord → Core → pf2e-module → LiteLLM → Obsidian round-trip
  after the 4 infrastructure fixes (4515c99 stale-image, eb83cb6 Dockerfile deps,
  c1d194f openai/ prefix, 3964c47 OPENAI_API_KEY).

### 2. OUT-01 — :pf npc export Jareth
expected: Bot replies "Foundry actor JSON for **Jareth**:" with an attached `jareth.json` file. Downloading and opening the JSON shows a valid PF2e actor dict with `type: "npc"`, `name: "Jareth"`, and `system.attributes` populated.
result: pass

### 3. OUT-02 — :pf npc token Jareth
expected: Bot replies with a plain-text Midjourney prompt string containing `--ar 1:1` and `--no text`. The prompt should describe Jareth's visual features (ancestry, class, traits, personality) in comma-separated phrases.
result: pass

### 4. OUT-03 — :pf npc stat Jareth
expected: Bot replies with a formatted Discord Embed showing title like "Jareth (Level 1 Halfling Rogue)", AC/HP inline, Fort/Ref/Will inline, Speed, and a "Mood: neutral" footer. Mechanical stat fields (AC/HP/saves) may be 0 or absent if the NPC has no `## Stats` block yet.
result: pass
reported: "does not have any fields but everything else was there"
note: |
  Embed-without-mechanical-fields is correct per D-16: Jareth was created
  via :pf npc create which writes frontmatter only (no ## Stats block yet).
  build_stat_embed's `if stats:` guard (bot.py) intentionally omits AC/HP/
  Fort/Ref/Will/Speed/Skills/Perception when stats == {}. Title, description,
  and Mood footer render from frontmatter and appeared as expected.

### 5. OUT-04 — :pf npc pdf Jareth
expected: Bot attaches a `jareth-stat-card.pdf` file. Opening the PDF shows a one-page stat card with Jareth's name as title, level/ancestry/class subtitle, and (if stats are present) an AC/HP/saves table. If no stats block, header-only PDF is correct.
result: pending

## Summary

total: 5
passed: 4
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps

<!-- Populated when any test reports issue. YAML format for plan-phase --gaps consumption. -->
