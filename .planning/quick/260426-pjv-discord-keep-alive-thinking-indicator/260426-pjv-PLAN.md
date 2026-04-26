---
phase: quick-260426-pjv
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - interfaces/discord/bot.py
autonomous: true
requirements:
  - QUICK-260426-PJV
must_haves:
  truths:
    - "If _route_message raises an exception inside /sen, the deferred interaction always receives a followup.send() call and the 'Bot is thinking...' indicator resolves"
    - "The followup error message is user-readable, not a raw traceback"
  artifacts:
    - path: interfaces/discord/bot.py
      provides: "try/except/finally guard around _route_message in the sen() handler"
      contains: "followup.send"
  key_links:
    - from: "sen() — after defer(thinking=True)"
      to: "interaction.followup.send()"
      via: "try/except block"
      pattern: "finally.*followup\\.send"
---

<objective>
Wrap the `_route_message` call inside the `/sen` slash command handler with a try/except block so that any unhandled exception terminates the "Bot is thinking..." indicator instead of leaving it spinning indefinitely.

Purpose: Discord's deferred interaction shows "Bot is thinking..." until `followup.send()` is called. If the code after `defer(thinking=True)` raises before reaching `followup.send()`, the indicator spins forever with no recovery path.

Output: Modified `interfaces/discord/bot.py` with a try/except guard around the post-defer work in `sen()`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/STATE.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Wrap post-defer body in try/except with guaranteed followup</name>
  <files>interfaces/discord/bot.py</files>
  <action>
In `sen()` (starts at line 1491), wrap everything after `await interaction.response.defer(thinking=True)` (line 1512) in a single try/except block. The except clause must catch `Exception as exc`, log the error with `logger.exception(...)`, and call `await interaction.followup.send("Something went wrong — the Sentinel encountered an error.", ephemeral=True)`. This ensures the "Bot is thinking..." indicator always resolves.

The try block covers:
- Thread creation (lines 1517-1529) — already has its own inner try/except for Forbidden/HTTPException, which is fine; those exceptions are already swallowed there, so the outer try only fires for unexpected raises
- `_route_message` call (lines 1536-1538) — currently bare, the main risk
- All `thread.send()` / `followup.send()` calls in step 4 (lines 1541-1577)

Structure after the change:

```python
# 1. Defer within 3 seconds — shows "Bot is thinking..." to user (IFACE-03)
await interaction.response.defer(thinking=True)

try:
    # 2. Create public thread from the channel (IFACE-04)
    thread_name = message[:50] if message else "Sentinel response"
    thread = None
    try:
        thread = await interaction.channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.public_thread,
            auto_archive_duration=60,
        )
        SENTINEL_THREAD_IDS.add(thread.id)
        await _persist_thread_id(thread.id)
        logger.info("Created thread %s '%s' for user %s", thread.id, thread_name, interaction.user.id)
    except discord.Forbidden as exc:
        logger.error("Missing permission to create thread (403): %s", exc)
    except discord.HTTPException as exc:
        logger.error("Failed to create thread (HTTP %s, code %s): %s", exc.status, exc.code, exc)

    # 3. Route message — subcommand, help-intent, or AI.
    user_id = str(interaction.user.id)
    ai_response = await _route_message(
        user_id, message, channel=thread if thread is not None else interaction.channel
    )

    # 4. Send AI response — into thread if created, fallback to channel
    if thread:
        ... (unchanged thread-send block) ...
        await interaction.followup.send(f"Response ready in {thread.mention}", ephemeral=True)
    else:
        ... (unchanged followup-send block) ...

except Exception as exc:
    logger.exception("Unhandled error in /sen after defer — sending error followup: %s", exc)
    await interaction.followup.send(
        "Something went wrong — the Sentinel encountered an error.",
        ephemeral=True,
    )
```

Do NOT change any logic inside the try block — only add the outer try/except wrapper. Do NOT add a finally block; the error path ends with followup.send() in the except clause, which is sufficient.

Also add a one-line comment above the `async with message.channel.typing():` block in `on_message` (around line 1455) documenting why typing() is used:
```python
# typing() auto-renews the typing indicator every 10s while the event loop is responsive.
```
  </action>
  <verify>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne && python -c "import ast, sys; ast.parse(open('interfaces/discord/bot.py').read()); print('syntax OK')" && grep -n "except Exception" interfaces/discord/bot.py | grep -A2 "except Exception" && grep -c "followup.send" interfaces/discord/bot.py</automated>
  </verify>
  <done>
    - `python -c "ast.parse(...)"` prints "syntax OK" with no errors
    - `grep -n "except Exception"` shows the new handler in the sen() function
    - `grep -c "followup.send"` returns a count >= the original (no followup.send calls removed)
    - The "Bot is thinking..." indicator will resolve to an error message instead of spinning forever if _route_message raises
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Discord user → bot | User-supplied message content reaches _route_message; already validated upstream |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-pjv-01 | Information Disclosure | except clause in sen() | mitigate | Error sent to user is a generic string — no traceback, no internal detail exposed. Raw exc is logged server-side only. |
</threat_model>

<verification>
- `python -c "import ast; ast.parse(open('interfaces/discord/bot.py').read())"` exits 0
- `grep -n "except Exception" interfaces/discord/bot.py` shows one match inside `sen()`
- Manual review: the except block calls `interaction.followup.send(...)` and nothing else (no re-raise that would swallow the followup)
</verification>

<success_criteria>
Any exception raised by `_route_message` or the thread-send block inside `/sen` results in a user-visible ephemeral error message and resolves the "Bot is thinking..." indicator. No code paths exist where `defer(thinking=True)` was called but no followup was sent.
</success_criteria>

<output>
After completion, create `.planning/quick/260426-pjv-discord-keep-alive-thinking-indicator/260426-pjv-01-SUMMARY.md`
</output>
