---
phase: 27-architecture-pivot
plan: "09"
subsystem: discord-interface
status: partial
tags: [discord, slash-commands, setup-hook, gap-closure]
dependency_graph:
  requires: [27-04]
  provides: [discord-sync-evidence]
  affects: [interfaces/discord/bot.py]
tech_stack:
  added: []
  patterns: [tree.sync-return-capture, startup-logging]
key_files:
  modified:
    - interfaces/discord/bot.py
decisions:
  - "Capture tree.sync() return value to get command count — discord.py tree.sync() returns list[app_commands.AppCommand]"
  - "Zero-command warning added to catch missing applications.commands OAuth scope at startup rather than requiring manual Discord UI inspection"
metrics:
  duration: "5m"
  completed_date: "2026-04-20"
  tasks_completed: 1
  tasks_total: 2
---

# Phase 27 Plan 09: Discord Slash Command Sync Evidence — Summary

setup_hook now captures tree.sync() return value and logs registered command count to provide runtime evidence of Discord API registration.

## Task Completion

| Task | Name | Status | Commit |
|------|------|--------|--------|
| 1 | Add sync result logging to setup_hook | complete | 56208b7 |
| 2 | Verify /sen registered with Discord API and audit subcommands | pending human verification | — |

## What Was Built

**Task 1 (complete):** Modified `setup_hook` in `interfaces/discord/bot.py` to:

1. Capture the return value of `await self.tree.sync()` into `synced_commands`
2. Compute `synced_count = len(synced_commands) if synced_commands else 0`
3. Log: `Slash commands synced to Discord API: {N} command(s) registered (global sync — up to 1hr propagation to all servers).`
4. Log a warning if `synced_count == 0`: advises checking `applications.commands` OAuth scope
5. Removed redundant `logger.info("Slash commands synced globally (up to 1hr propagation).")`

**Task 2 (pending human verification):** Discord bot must be started and the operator must confirm:
- Docker logs show "Slash commands synced to Discord API: 1 command(s) registered" (not 0)
- `/sen` appears in Discord slash command autocomplete picker
- `/sentask` does NOT appear in Discord slash command autocomplete picker
- `:help` subcommand produces a response listing available subcommands
- At least one standard subcommand (e.g., `:goals`) produces a non-empty AI response

## Human Verification Steps

```bash
./sentinel.sh up -d
docker compose logs discord --follow --since 10s
```

Wait for "Sentinel bot ready:" log line. Expected output includes:
```
Slash commands synced to Discord API: 1 command(s) registered (global sync — up to 1hr propagation to all servers).
```

Then open Discord, type `/`, confirm `/sen` appears and `/sentask` does not.

## Subcommand Audit

From SUBCOMMAND_HELP vs `_SUBCOMMAND_PROMPTS` / explicit handlers in `handle_sentask_subcommand`:

| Subcommand | Status | Location |
|-----------|--------|----------|
| `:help` | Implemented | `handle_sentask_subcommand` — returns `SUBCOMMAND_HELP` string |
| `:capture <text>` | Implemented | `handle_sentask_subcommand` — arg-taking handler |
| `:seed <text>` | Implemented | `handle_sentask_subcommand` — arg-taking handler |
| `:ralph` | Implemented | `_SUBCOMMAND_PROMPTS` dict |
| `:pipeline` | Implemented | `_SUBCOMMAND_PROMPTS` dict |
| `:connect <note>` | Implemented | `handle_sentask_subcommand` — arg-taking handler |
| `:reweave` | Implemented | `_SUBCOMMAND_PROMPTS` dict |
| `:review <note>` | Implemented | `handle_sentask_subcommand` — arg-taking handler |
| `:check` | Implemented | `_SUBCOMMAND_PROMPTS` dict |
| `:rethink` | Implemented | `_SUBCOMMAND_PROMPTS` dict |
| `:refactor` | Implemented | `_SUBCOMMAND_PROMPTS` dict |
| `:tasks` | Implemented | `_SUBCOMMAND_PROMPTS` dict |
| `:stats` | Implemented | `_SUBCOMMAND_PROMPTS` dict |
| `:graph [query]` | Implemented | `handle_sentask_subcommand` — optional arg handler |
| `:next` | Implemented | `_SUBCOMMAND_PROMPTS` dict |
| `:learn <topic>` | Implemented | `handle_sentask_subcommand` — arg-taking handler |
| `:remember <obs>` | Implemented | `handle_sentask_subcommand` — arg-taking handler |
| `:revisit <note>` | Implemented | `handle_sentask_subcommand` — arg-taking handler |
| `:plugin:help` | Implemented | `_PLUGIN_PROMPTS` dict |
| `:plugin:health` | Implemented | `_PLUGIN_PROMPTS` dict |
| `:plugin:ask <q>` | Implemented | `handle_sentask_subcommand` — arg-taking handler |
| `:plugin:architect` | Implemented | `_PLUGIN_PROMPTS` dict |
| `:plugin:setup` | Implemented | `_PLUGIN_PROMPTS` dict |
| `:plugin:tutorial` | Implemented | `_PLUGIN_PROMPTS` dict |
| `:plugin:upgrade` | Implemented | `_PLUGIN_PROMPTS` dict |
| `:plugin:reseed` | Implemented | `_PLUGIN_PROMPTS` dict |
| `:plugin:add-domain` | Implemented | `handle_sentask_subcommand` — arg-taking handler |
| `:plugin:recommend` | Implemented | `_PLUGIN_PROMPTS` dict |

All subcommands listed in SUBCOMMAND_HELP have implementations. No deferred stubs found.

Note: `:health`, `:goals`, `:reminders` appear in the module docstring (lines 14-17) but are in `_SUBCOMMAND_PROMPTS` — implemented correctly.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None. The sync result logging adds evidence for T-27-09-01 (Repudiation threat — no log evidence that tree.sync() completed). No new trust boundaries introduced.

## Self-Check: PASSED

- `interfaces/discord/bot.py` exists and contains all required patterns
- Commit `56208b7` exists in git log
- Task 2 correctly documented as pending human verification per task_notes
