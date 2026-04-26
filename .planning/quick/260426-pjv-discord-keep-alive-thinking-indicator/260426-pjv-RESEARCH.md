# Discord Keep-Alive / Thinking Indicator — Research

**Researched:** 2026-04-26
**Domain:** discord.py interaction model, typing indicators, deferred responses
**Confidence:** HIGH

---

## Summary

The bot already implements the correct pattern for the `/sen` slash command — `defer(thinking=True)` is called before any LLM work. Thread replies (`on_message`) also correctly use `async with message.channel.typing()`, which auto-renews every 10 seconds while the async event loop is responsive. There is no timeout problem in the current code, and no changes are needed to either path.

The actual user-facing concern ("do they see a thinking indicator?") is already answered: yes for both paths. The research below documents why, and identifies the one real gap: **error responses after defer must always use `followup.send()`, never `response.send_message()`** — the code already does this correctly too.

**Primary recommendation:** No changes needed. The implementation is already correct for both interaction paths.

---

## Discord Interaction Timeout Model

[VERIFIED: discord.com/developers/docs]

| Constraint | Value | Notes |
|------------|-------|-------|
| Initial response window | 3 seconds | Must call `response.defer()` or `response.send_message()` within this window or Discord invalidates the interaction |
| Deferred followup window | 15 minutes | After defer, `interaction.followup` is valid for up to 15 minutes |
| Typing indicator duration | 10 seconds per burst | `channel.typing()` auto-renews while async event loop is active |

The 15-minute window is a hard Discord API ceiling. It cannot be extended. For LLM calls that might theoretically exceed it, the only option is a timeout error message sent via `followup.send()`. In practice, LM Studio on local hardware responds in seconds to minutes — not 15+ minutes.

---

## How the Current Bot Handles Each Path

### Path 1: `/sen` slash command

```python
# bot.py line 1512
await interaction.response.defer(thinking=True)   # <-- shows "Bot is thinking..."
# ... thread creation, _route_message (LLM call) ...
await interaction.followup.send(f"Response ready in {thread.mention}", ephemeral=True)
```

[VERIFIED: bot.py lines 1511-1559]

Status: **Correct and complete.** `defer(thinking=True)` acknowledges within 3s, user sees "Bot is thinking...", followup resolves it after LLM returns. No changes needed.

### Path 2: Thread replies (`on_message`)

```python
# bot.py line 1455
async with message.channel.typing():
    ai_response = await _route_message(...)
await message.channel.send(ai_response)
```

[VERIFIED: bot.py lines 1455-1464]

Status: **Correct and complete.** `channel.typing()` as an async context manager auto-renews the typing indicator every 10 seconds as long as the `await` inside completes normally (i.e., the event loop remains responsive). Since `_route_message` uses `await` throughout (httpx async calls), the event loop is never blocked. [VERIFIED: github.com/Rapptz/discord.py/discussions/5969]

---

## The defer() / followup Pattern (Reference)

```python
# Slash command — must defer within 3s, then use followup for everything after
@bot.tree.command(name="sen", ...)
async def sen(interaction: discord.Interaction, message: str) -> None:
    await interaction.response.defer(thinking=True)   # shows "Bot is thinking..."
    result = await do_slow_work()
    await interaction.followup.send(result)           # resolves the thinking state

# Thread reply — typing() auto-renews during await
async def on_message(self, message: discord.Message) -> None:
    async with message.channel.typing():
        result = await do_slow_work()                 # typing indicator stays active
    await message.channel.send(result)
```

`thinking=True` specifically triggers Discord's built-in "Bot is thinking..." UI element (animated ellipsis). Without it, `defer()` still delays the response but shows no visible indicator.

---

## Rules After defer()

[VERIFIED: discord.com/developers/docs]

Once `interaction.response.defer()` is called:

1. `interaction.response` is consumed — calling `response.send_message()` again raises `InteractionResponded`
2. All subsequent responses (including errors) MUST go through `interaction.followup.send()`
3. The followup token expires after 15 minutes from the original interaction

The current bot does this correctly — all response branches after the defer use `followup.send()` (lines 1559-1577).

---

## Edge Cases

| Scenario | What Happens | Current Handling |
|----------|-------------|-----------------|
| LLM call errors (HTTP 4xx/5xx) | `_sentinel_client.send_message()` catches and returns error string | Error string reaches `followup.send()` via `_route_message` — correct |
| LLM call times out (200s) | `SentinelCoreClient` returns "The Sentinel took too long..." string | Same path — correct |
| LLM takes > 15 minutes | `followup.send()` raises `discord.errors.NotFound` (token expired) | Not caught — would log an unhandled exception; extremely unlikely in practice |
| Thread creation fails (Forbidden) | `thread = None`, falls through to `followup.send(ai_response)` | Handled — lines 1561-1577 |

The only unhandled case is the >15min LLM scenario, which is not a realistic concern for local LM Studio responses.

---

## Files in Scope

| File | Status | Notes |
|------|--------|-------|
| `interfaces/discord/bot.py` | No changes needed | Both paths correctly implemented |
| `shared/sentinel_client.py` | No changes needed | 200s httpx timeout well within 15min Discord window |

---

## Pitfalls (for future reference)

- **Never call `response.send_message()` after `defer()`** — raises `InteractionResponded`. Always use `followup.send()` for everything after the defer.
- **`thinking=True` requires a followup** — if the bot crashes after `defer(thinking=True)` without sending a followup, the "Bot is thinking..." indicator spins indefinitely. The only mitigation is wrapping `_route_message` in a `try/except` that calls `followup.send(error_message)` in the finally block.
- **`channel.typing()` requires async** — must be `async with`, not `with`. Using the sync form or a blocking sleep inside will stop renewal.
- **Thread replies have no 15-minute constraint** — `on_message` is not an interaction, so the only concern is the typing indicator, which `channel.typing()` handles.

---

## Sources

- [VERIFIED: discord.com/developers/docs — Receiving and Responding to Interactions](https://discord.com/developers/docs/interactions/receiving-and-responding) — 3s initial window, 15min followup window
- [VERIFIED: github.com/Rapptz/discord.py/discussions/5969](https://github.com/Rapptz/discord.py/discussions/5969) — `channel.typing()` auto-renews every 10s, requires responsive event loop
- [VERIFIED: bot.py lines 1511-1577] — `/sen` defer + followup implementation
- [VERIFIED: bot.py lines 1455-1479] — `on_message` typing context manager implementation
