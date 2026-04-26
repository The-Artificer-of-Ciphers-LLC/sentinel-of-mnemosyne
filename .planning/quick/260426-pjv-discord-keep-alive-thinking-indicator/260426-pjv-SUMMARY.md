---
status: complete
quick_id: 260426-pjv
slug: discord-keep-alive-thinking-indicator
date: 2026-04-26
commit: f258ebb
---

# Quick Task 260426-pjv: Discord Keep-Alive / Thinking Indicator

## What Was Done

**Research finding:** The Discord bot already implements the correct keep-alive patterns on both interaction paths:

- `/sen` slash command: `defer(thinking=True)` + `interaction.followup.send()` — users see "Bot is thinking..." immediately, followup resolves it
- Thread replies: `async with message.channel.typing():` — auto-renews the typing indicator every 10s while the async event loop is responsive

**Gap fixed:** If `_route_message` (or any code after the defer) raised an unhandled exception, the "Bot is thinking..." indicator would spin indefinitely because no `followup.send()` was ever called.

## Changes Made

### `interfaces/discord/bot.py`

1. **Lines 1515–1586** — Wrapped the entire post-`defer(thinking=True)` body in `sen()` with a `try/except Exception` block. The except clause logs via `logger.exception()` and calls `await interaction.followup.send("Something went wrong — the Sentinel encountered an error.", ephemeral=True)`. The "Bot is thinking..." indicator now always resolves regardless of what raises.

2. **Line 1455** — Added comment above `async with message.channel.typing():` in `on_message`:
   ```python
   # typing() auto-renews the typing indicator every 10s while the event loop is responsive.
   ```

## Verification

- `python -c "import ast; ast.parse(open('interfaces/discord/bot.py').read())"` → syntax OK
- `grep -c "followup.send" interfaces/discord/bot.py` → 6 (all existing followup calls preserved)
- `grep -n "except Exception" interfaces/discord/bot.py` → confirms guard is in place at line 1581
