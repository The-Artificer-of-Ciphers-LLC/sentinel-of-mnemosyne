---
phase: 03-interfaces
plan: "02"
subsystem: interfaces/discord
tags: [discord, bot, slash-command, docker, interface]
dependency_graph:
  requires: [03-01]
  provides: [IFACE-02, IFACE-03, IFACE-04]
  affects: [interfaces/discord/bot.py, interfaces/discord/Dockerfile, interfaces/discord/compose.yml, docker-compose.yml]
tech_stack:
  added: [discord.py>=2.7.1, httpx>=0.28.1 (discord container)]
  patterns: [channel.create_thread-after-defer, setup_hook-for-command-sync, snowflake-as-user_id, httpx-AsyncClient-to-Core]
key_files:
  created:
    - interfaces/discord/bot.py
    - interfaces/discord/Dockerfile
    - interfaces/discord/compose.yml
    - interfaces/discord/.env.example
  modified:
    - docker-compose.yml
decisions:
  - "No explicit Docker network config — all services on default Compose network; no sentinel_net named network defined in any existing compose, so no external network reference needed"
  - "channel.create_thread() used for thread creation — not interaction.followup.send().create_thread() (wrong pattern from 03-CONTEXT.md decision 2 was corrected against 03-RESEARCH.md)"
  - "DISCORD_BOT_TOKEN and SENTINEL_API_KEY use os.environ[] (not .get()) — KeyError at startup if missing, satisfying T-03-09 mitigate disposition"
metrics:
  duration_seconds: 420
  completed: "2026-04-10"
  tasks_completed: 2
  files_changed: 5
---

# Phase 03 Plan 02: Discord Bot Summary

**One-liner:** Discord bot container with /sentask slash command — defers within 3s, creates channel thread, calls Core with X-Sentinel-Key, sends AI response into thread.

## What Was Built

`interfaces/discord/bot.py` implements a `discord.py` v2.7.x bot with a single `/sentask <message>` slash command. The command follows the correct three-step interaction pattern: defer within 3 seconds (shows "Bot is thinking..."), create a public thread via `interaction.channel.create_thread()`, call Core POST `/message` with the user's Discord snowflake as `user_id`, send the AI response into the thread, and acknowledge the original interaction with an ephemeral thread mention.

`interfaces/discord/Dockerfile` builds a Python 3.12-slim image with `discord.py>=2.7.1` and `httpx>=0.28.1`. `interfaces/discord/compose.yml` defines the `discord` service with `restart: unless-stopped` and env_file from `.env`. `interfaces/discord/.env.example` documents the four required/optional env vars. Root `docker-compose.yml` include block now actively includes `interfaces/discord/compose.yml`.

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Discord bot container scaffold | e78530c | interfaces/discord/Dockerfile, compose.yml, .env.example, docker-compose.yml |
| 2 | Discord bot.py — /sentask slash command | d9580c4 | interfaces/discord/bot.py |

## Verification

Static checks passed:

```
python3 -c "import ast; ast.parse(...bot.py...)"  → syntax OK
grep "create_thread" bot.py                        → match (channel-level, correct)
grep "followup.send.*wait=True" bot.py             → no match (wrong pattern absent)
grep "X-Sentinel-Key" bot.py                       → match
grep "str(interaction.user.id)" bot.py             → match
grep "setup_hook" bot.py                           → match
grep "defer.*thinking.*True" bot.py                → match
grep "interfaces/discord/compose.yml" docker-compose.yml → match (not commented)
```

Integration test requires DISCORD_BOT_TOKEN (auth gate — not automated in this phase).

## Deviations from Plan

### Network Config

The plan instructed adding `sentinel_net` as an external network in `discord/compose.yml`. However, neither `sentinel-core/compose.yml` nor `pi-harness/compose.yml` define any named networks. All services communicate via Docker Compose's automatic default network (same compose project via root `include` directives). Adding `external: true` for a non-existent named network would cause `docker compose up` to fail. The discord service uses the same pattern as all other services: no explicit network configuration.

### 03-CONTEXT.md Decision 2 Conflict

`03-CONTEXT.md` section 2 contains an incorrect thread creation snippet using `interaction.followup.send(ai_response, wait=True)` — the wrong pattern. The plan's `<interfaces>` block and `03-RESEARCH.md` both document the correct `channel.create_thread()` pattern. The correct pattern was implemented per the plan's `<interfaces>` spec and RESEARCH.md, not the CONTEXT.md snippet.

## Known Stubs

None — all bot logic is fully wired. `SENTINEL_CORE_URL` defaults to `http://sentinel-core:8000` and is the correct internal Docker hostname. The bot makes real HTTP calls to Core.

## Threat Flags

None — all threat mitigations from the plan's threat_model are implemented:
- T-03-05: Token read from env var only; .env.example has placeholder
- T-03-08: Timeout handled with user-visible error message in thread (httpx timeout=200.0)
- T-03-09: `os.environ["DISCORD_BOT_TOKEN"]` and `os.environ["SENTINEL_API_KEY"]` raise KeyError at startup if missing

## Self-Check: PASSED

- interfaces/discord/bot.py: FOUND
- interfaces/discord/Dockerfile: FOUND
- interfaces/discord/compose.yml: FOUND
- interfaces/discord/.env.example: FOUND
- docker-compose.yml contains interfaces/discord/compose.yml (active): FOUND
- Commit e78530c: FOUND
- Commit d9580c4: FOUND
