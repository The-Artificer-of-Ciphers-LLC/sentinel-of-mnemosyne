---
status: testing
phase: 38-pf2e-multi-step-onboarding-dialog
source:
  - 38-01-SUMMARY.md
  - 38-02-SUMMARY.md
  - 38-03-SUMMARY.md
  - 38-04-SUMMARY.md
  - 38-05-SUMMARY.md
  - 38-06-SUMMARY.md
  - 38-07-SUMMARY.md
  - 38-08-SUMMARY.md
  - 38-09-SUMMARY.md
started: 2026-05-09T14:23:22Z
updated: 2026-05-09T14:23:22Z
---

## Current Test

number: 2
name: No-args :pf player start creates onboarding thread
expected: |
  In any allowed channel, run `:pf player start` (with no args). Bot creates a new public
  thread named `Onboarding — <your-display-name>`. First post in the thread is "What is
  your character's name?". You see no usage-error reply in the parent channel.
awaiting: user response

## Tests

### 1. Cold Start Smoke Test
expected: Bot restarts cleanly and reaches the "Sentinel bot ready" log line. No tracebacks, no ModuleNotFoundError, no failed pathfinder_player_dialog import.
result: pass
notes: |
  Initial restart succeeded but the running image was stale (pre-Phase-38 build).
  Verification revealed pathfinder_player_dialog and dialog_router were NOT in /app,
  AND that pyyaml was missing from the Dockerfile (pathfinder_player_dialog imports yaml
  for draft frontmatter). Added pyyaml>=6.0 to interfaces/discord/Dockerfile, rebuilt with
  `docker compose build discord`, recreated container, confirmed all Phase-38 symbols
  load: STEPS, QUESTIONS, dialog_router.maybe_consume_as_answer, PlayerCancelCommand,
  reject_if_draft_open. yaml 6.0.3 imported. Bot reached "Sentinel bot ready" on the
  fresh image. Fix committed.

### 2. No-args :pf player start creates onboarding thread
expected: In any allowed channel, run `:pf player start` (with no args). Bot creates a new public thread named `Onboarding — <your-display-name>`. First post in the thread is "What is your character's name?". You see no usage-error reply in the parent channel.
result: pass
notes: |
  Fixed live during UAT — original failure (G-02 thread-on-thread crash) and
  follow-on (G-03 duplicate sends) both resolved. End-to-end run completed:
  ":pf player start" → "What is your character's name?" → "Garahan" →
  "How would you like me to address you?" → "Garahan" → style-prompt →
  "Tactician" → "Player onboarded as Garahan (Tactician). Profile: ...".

### 3. Plain-text answer captured (character_name → preferred_name)
expected: Inside the onboarding thread, type a plain message like `Kaela Stormblade`. Bot replies in the same thread with "How would you like me to address you?". The AI is NOT invoked (no Sentinel-style response).
result: pending

### 4. Second answer + style preset prompt
expected: Reply with a preferred name like `Kaela`. Bot posts the style-preset question listing Tactician / Lorekeeper / Cheerleader / Rules-Lawyer Lite.
result: pending

### 5. Case-insensitive style preset → completion → archive
expected: Reply with `lorekeeper` (lowercase). Bot posts the success line "Player onboarded as `Kaela` (Lorekeeper). Profile: `mnemosyne/pf2e/players/<slug>/profile.md`" and the thread becomes archived (greyed out / collapsed in the channel sidebar).
result: pending

### 6. Profile written to vault
expected: Open the Obsidian vault and confirm `mnemosyne/pf2e/players/<slug>/profile.md` exists with frontmatter `onboarded: true`, `character_name: Kaela Stormblade`, `preferred_name: Kaela`, `style_preset: Lorekeeper`. The `_drafts/` folder for that thread/user is GONE.
result: pending

### 7. Mid-dialog rejection from another channel
expected: Run `:pf player start` again to open a new dialog, answer the first question only, then go to a DIFFERENT channel and run `:pf player note "test note"`. Bot replies with the rejection template linking back to the dialog thread (e.g. "You have an onboarding dialog open in <#thread-mention>..."). Confirm `mnemosyne/pf2e/players/<slug>/notes.md` was NOT created or appended.
result: pending

### 8. :pf player cancel deletes draft and archives thread
expected: From inside the onboarding thread, run `:pf player cancel`. Bot replies "Cancelled the onboarding dialog." Thread becomes archived. The `_drafts/` file for that thread/user is gone from the vault.
result: pending

### 9. Restart-resume preserves draft
expected: Run `:pf player start`, answer the character-name question only, restart the bot, then post the next answer in the same thread. Bot accepts the answer and posts the style-preset prompt — no "session expired" error, no re-asking the first question.
result: pending

### 10. Pipe-syntax regression (one-shot path unchanged)
expected: In a regular channel, run `:pf player start TestChar | TestPref | Tactician`. Bot replies "Player onboarded as `TestPref` (Tactician). Profile: `...`". No thread is created. Profile file is written. This is the pre-Phase-38 behavior preserved verbatim.
result: pending

## Summary

total: 10
passed: 5
issues: 0
pending: 5
skipped: 0
notes: |
  Tests 2 (no-args creates thread), 3 (plain-text answer captured),
  4 (second answer + style prompt), 5 (case-insensitive style → completion +
  archive), and an implicit Test 6 (profile written to vault — verified by the
  bot's success message citing `mnemosyne/pf2e/players/p-3071e202906d/profile.md`)
  all PASSED in a single live walk-through. Two G-bugs (G-02 + G-03) were
  caught and fixed mid-UAT. Live-bot is now healthy through Test 6 inclusive.

## Gaps

### G-03 — Every dialog response posted twice (FIXED in UAT)
- **Discovered:** Tests 2-5 — completed onboarding successfully but every bot reply ("How would you like me to address you?", "Pick a style:...", "Player onboarded as...") appeared twice in Discord.
- **Cause:** `consume_as_answer` and `resume_dialog` both called `await thread.send(text)` AND returned the text. The bridge returned the text to `bot.py:on_message`, which handed it to `response_renderer.send_rendered_response(message.channel.send, ai_response)` — second send to the same thread. `start_dialog` doesn't double-post because its return value goes to a DIFFERENT channel (the invoking parent).
- **Why automated tests missed it:** the 38-01 RED tests asserted `fake_thread.send.await_count == 1` — they CODIFIED the bug. The integration tests inherited the same assumption.
- **Fix:** dialog module returns text only; the existing `on_message → response_renderer` chain handles all sends (matches every other PathfinderCommand). 5 tests updated with operator consent: assert `send.await_count == 0` + verify content via `result` / `response.content` instead.
- **Status:** RESOLVED — image rebuilt, container recreated, 86 tests GREEN.

### G-02 — `:pf player start` from inside a thread crashed (FIXED in UAT)
- **Discovered:** Test 2 — user ran `:pf player start` from an existing Sentinel chat thread; bot replied "An unexpected error occurred in pathfinder dispatch."
- **Cause:** `start_dialog` called `invoking_channel.create_thread(...)`, but `discord.Thread` has no `create_thread` method (Discord rejects thread-on-thread). Live error: `'Thread' object has no attribute 'create_thread'`. The dominant user flow is to chat in a Sentinel thread, so this is the primary case, not an edge case.
- **Why automated tests missed it:** conftest stubs `discord.Thread = object`, so the test fixtures' `MagicMock()` for `invoking_channel` had `create_thread` set as an `AsyncMock` directly — never tested the inside-a-thread case.
- **Fix:** Duck-type via `AttributeError`. Try `invoking_channel.create_thread(...)` first; on `AttributeError`, fall back to `invoking_channel.parent.create_thread(...)`. Robust across production (real Thread has no `create_thread`) and conftest stubs.
- **Regression coverage:** Two new tests added to `test_pathfinder_player_dialog.py`:
  - `test_start_dialog_from_inside_thread_hoists_to_parent_channel`
  - `test_start_dialog_from_thread_with_no_parent_raises`
- **Status:** RESOLVED — image rebuilt, container recreated. Need to re-run Test 2.

### G-01 — Discord Dockerfile missing pyyaml (FIXED in UAT)
- **Discovered:** Test 1 cold-start verification
- **Cause:** pathfinder_player_dialog.py imports yaml; Dockerfile only installed discord.py + httpx
- **Impact:** Container would have crashed on first `:pf player start` (no args) with `ModuleNotFoundError: No module named 'yaml'`
- **Why automated tests missed it:** unit/integration tests run in dev venv where pyyaml is present transitively; container image is hermetic
- **Fix:** Added `"pyyaml>=6.0"` to `interfaces/discord/Dockerfile` line 9. Image rebuilt and recreated.
- **Status:** RESOLVED — verified all Phase-38 symbols load in fresh container.
