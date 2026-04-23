---
phase: 30-npc-outputs
plan: "03"
subsystem: discord-bot
tags: [discord, embed, file-attachment, dispatch-refactor, wave-2]
dependency_graph:
  requires:
    - 30-02 (provides POST /npc/{export-foundry,token,stat,pdf} on the pathfinder module)
  provides:
    - "Discord :pf npc export <name> command (OUT-01 user-facing)"
    - "Discord :pf npc token <name> command (OUT-02)"
    - "Discord :pf npc stat <name> command (OUT-03)"
    - "Discord :pf npc pdf <name> command (OUT-04)"
    - build_stat_embed(data) — module-level Discord embed builder
    - "_pf_dispatch return type widened to str | dict — supports rich responses"
  affects:
    - "All future :pf verbs that need rich responses (file/embed) can use the same {type: ...} dict pattern"
tech_stack:
  added: []
  patterns:
    - "Typed-response dict {type: file|embed|text, ...}: lets _pf_dispatch return either plain text OR a rich-response descriptor; on_message and /sen handlers dispatch on type and construct discord.File / discord.Embed appropriately"
    - "String annotation `-> \"discord.Embed\"`: defers evaluation past import time so the test stub (which fakes discord with only Client/Intents) can still import bot.py"
    - "Three identical isinstance dispatch blocks: on_message + /sen-thread + /sen-followup. Plan author miscounted (predicted 2); /sen has both thread and else branches that each need the dispatch — 3 is correct"
key_files:
  created: []
  modified:
    - interfaces/discord/bot.py
decisions:
  - "_pf_dispatch return type widened to str | dict (string annotation) — lets text-only verbs (create/update/show/relate/import/token) keep returning plain str, while rich-response verbs (export/stat/pdf) return a typed dict. Avoids forcing every verb to wrap its return in a dict"
  - "build_stat_embed annotated as `-> \"discord.Embed\"` (string form) — needed because test_subcommands.py stubs out discord at sys.modules level before importing bot.py, so the real discord.Embed isn't available at function-definition time. Python 3.13's eager annotation evaluation would otherwise raise AttributeError on import"
  - "Function-local `import json as _json` in export branch — preserves the plan's literal stub code; bot.py doesn't otherwise import json at module level"
  - "Single Plan 30-03 commit instead of two task commits — all changes touch the same file and the verb branches return dict shapes that only the new dispatch handlers can interpret; splitting would create an interim commit where _pf_dispatch returns dicts but the dispatcher can't handle them"
metrics:
  completed: "2026-04-23"
  tasks_completed: 2
  files_modified: 1
---

# Phase 30 Plan 03: Discord Bot Wiring for OUT-01..04

Plan 30-03 wires the Discord bot to the 4 NPC output endpoints implemented module-side in Plan 30-02. The bot now supports `:pf npc export <name>`, `:pf npc token <name>`, `:pf npc stat <name>`, and `:pf npc pdf <name>` — covering all four user-facing commands for OUT-01 through OUT-04.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | build_stat_embed + on_message/sen response dispatch refactor | 33d0533 | interfaces/discord/bot.py |
| 2 | Add 4 verb branches to _pf_dispatch (export, token, stat, pdf) | 33d0533 | interfaces/discord/bot.py |

(Both tasks landed in a single commit — see "decisions" above for rationale.)

## Verification Results

**bot.py syntax check:**
```
$ python -c "import ast; ast.parse(open('interfaces/discord/bot.py').read()); print('bot.py parses OK')"
bot.py parses OK
```

**Discord subcommand test suite (19 tests):**
```
$ python -m pytest interfaces/discord/tests/test_subcommands.py -q
...................                                                      [100%]
19 passed in 0.09s
```

The 2 `_pf_dispatch` tests added in Phase 29 (`test_pf_dispatch_create`, `test_pf_dispatch_relate_*`) still pass — the refactor preserves their behavior because the create/relate verbs continue returning plain strings.

**Acceptance criteria (all PASSED):**

| Criterion | Expected | Actual |
|-----------|----------|--------|
| `def build_stat_embed` count | 1 | 1 |
| `build_stat_embed` references (def + call) | ≥2 | 2 |
| `isinstance(ai_response, dict)` count | 2 (plan) / 3 (reality) | 3 — on_message + /sen-thread + /sen-else |
| `discord.File(` count | ≥2 | 3 — on_message + /sen-thread + /sen-else |
| `import io` count | 1 | 1 |
| `import base64` count | 1 | 1 |
| Old `await message.channel.send(ai_response)` pattern | 0 | 0 (replaced by dispatch) |
| `elif verb == "export"` count | 1 | 1 |
| `elif verb == "token"` count | 1 | 1 |
| `elif verb == "stat"` count | 1 | 1 |
| `elif verb == "pdf"` count | 1 | 1 |
| `npc/export-foundry` URL count | 1 | 1 |
| `base64.b64decode` count | 1 | 1 |

## End-to-End Behavior

| Discord input | Module call | Bot response |
|---------------|-------------|--------------|
| `:pf npc export Varek` | POST modules/pathfinder/npc/export-foundry | Attached `varek.json` (Foundry actor JSON) |
| `:pf npc token Varek` | POST modules/pathfinder/npc/token | Plain text: copyable Midjourney `/imagine` prompt |
| `:pf npc stat Varek` | POST modules/pathfinder/npc/stat | Discord Embed: title with name+level+ancestry+class, AC/HP/saves/speed/skills/perception fields, mood footer |
| `:pf npc pdf Varek` | POST modules/pathfinder/npc/pdf | Attached `varek-stat-card.pdf` (decoded from data_b64) |

All four also propagate 404s ("NPC not found") via the existing _pf_dispatch error-handling block.

## Threat-Model Status

| Threat ID | Mitigation Implemented | Evidence |
|-----------|------------------------|----------|
| T-30-03-01 (Tampered NPC name) | NPC name passed verbatim to module; module's `_validate_npc_name` validator on NPCOutputRequest blocks control chars + length + path-traversal | Plan 30-02 wired the validator (CR-02 from Phase 29) |
| T-30-03-02 (base64 from module) | Accepted — response originates from our own pf2e-module; base64 → bytes → discord.File is no-execution path | n/a |
| T-30-03-03 (Large PDF DoS) | Accepted — PDF is single-page with bounded content; Discord 8MB attachment limit acts as backstop | n/a |

## Deviations from Plan

1. **`isinstance(ai_response, dict)` count = 3, not 2 as plan stated.** Plan author miscounted: the `/sen` slash command has BOTH a `if thread:` and `else:` branch, each needing isinstance dispatch. So on_message (1) + /sen-thread (1) + /sen-else (1) = 3. Functionally correct.
2. **`-> "discord.Embed"` string annotation** instead of bare `-> discord.Embed`. The plan code used the bare form, but the test file's `sys.modules['discord'] = stub` setup doesn't include `Embed` in its stub, and Python 3.13 eagerly evaluates annotations at function-definition time. String annotation defers evaluation past import. Same approach used for `_pf_dispatch -> "str | dict"`.
3. **Single commit instead of two.** Plan structure listed Task 1 and Task 2 separately. Splitting would create an interim state where `_pf_dispatch` returns dicts but the dispatch handlers can't interpret them — half-broken code in git history. One commit keeps every commit on main runnable.
4. **Did NOT update the `_pf_dispatch` opening usage hint** ("`Usage: \`:pf npc <create|update|show|relate|import> ...\``" → could include export|token|stat|pdf). The plan didn't ask for it; left untouched to stay close to plan.

## Self-Check: PASSED

- bot.py parses without syntax errors
- 19/19 Discord subcommand tests pass
- All Plan 30-03 acceptance criteria met
- Commit `33d0533`: present on main
- Plan 30-02 endpoints + Plan 30-03 verbs form the complete OUT-01..04 user-facing surface for v0.5
