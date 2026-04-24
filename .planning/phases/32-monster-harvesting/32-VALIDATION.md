---
phase: 32
slug: monster-harvesting
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-23
---

# Phase 32 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Planner fills the body during plan creation.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (existing project stack) |
| **Config file** | `modules/pathfinder/pyproject.toml`, `interfaces/discord/pyproject.toml` |
| **Quick run command** | `cd modules/pathfinder && uv run python -m pytest tests/ -k harvest -q --tb=short` |
| **Full suite command** | `cd modules/pathfinder && uv run python -m pytest tests/ -q && cd interfaces/discord && uv run --no-sync python -m pytest tests/ -q` |
| **Estimated runtime** | ~5 seconds (quick), ~15 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run the quick command scoped to harvest
- **After every plan wave:** Run the full suite command
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

_To be filled by gsd-planner based on final plan breakdown._

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 32-01-01 | 01 | 0 | HRV-01..06 | — | N/A | unit (RED) | `cd modules/pathfinder && uv run python -m pytest tests/ -k harvest --collect-only -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `modules/pathfinder/tests/test_harvest.py` — unit stubs for HRV-01..05
- [ ] `modules/pathfinder/tests/test_harvest_integration.py` — round-trip stubs for HRV-06 batch
- [ ] `interfaces/discord/tests/test_subcommands.py` — add `test_pf_harvest_*` stubs
- [ ] Existing conftest.py patterns (from test_npc_*) cover Obsidian + LLM + httpx stubs

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| LLM-generated fallback quality (T-32-LLM-01) | HRV-01 SC-4 | LLM output correctness requires DM judgment vs. Battlezoo/Bestiary prose | Run `:pf harvest Barghest` (L4, out of seed), open `mnemosyne/pf2e/harvest/barghest.md`, verify components plausible against Paizo Bestiary 2 p.46 |
| Fuzzy-match false-positive behavior | HRV-01 | Edge cases require human judgment | Run `:pf harvest 'Wolf Lord'`, confirm LLM fallback triggers (not silent match to Wolf) |
| YAML seed edit → cache invalidation | D-03b | Requires local file edit + re-query | Edit `harvest-tables.yaml` goblin entry, delete `mnemosyne/pf2e/harvest/goblin.md`, re-run `:pf harvest Goblin`, confirm new data returned |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
