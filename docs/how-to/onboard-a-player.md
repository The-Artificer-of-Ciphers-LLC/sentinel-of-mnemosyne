# How to onboard a Pathfinder player

This guide walks through getting a new player set up with their own isolated vault namespace via `:pf player start`. For the full command reference, see [Discord Command Reference](../reference/discord-commands.md).

---

## Before you begin

- The `pf2e` module must be running: `./sentinel.sh --discord --pf2e up -d`
- The player must have access to a Discord channel where the Sentinel bot is present.
- Decide which style preset the player will use. Run `:pf player style list` first if you want to preview options — this command is exempt from the onboarding gate and works before any account exists.

**Valid style presets** (case-sensitive):

- `Tactician` — concise, mechanics-first
- `Lorekeeper` — setting-rich, context-heavy
- `Cheerleader` — encouraging, positive framing
- `Rules-Lawyer Lite` — RAW citations with brief reasoning

---

## Steps

### Option A: Multi-step onboarding dialog (default)

This is the standard path. The bot guides the player through three questions in a private-feeling thread.

1. In any `/sen` thread, run:

   ```
   :pf player start
   ```

   The bot creates a thread named "Onboarding — \<your display name\>" and asks the first question.

2. When the bot asks **"What is your character's name?"**, reply with the character name in plain text inside the thread.

   ```
   Kael Stormblade
   ```

3. When the bot asks **"How would you like me to address you?"**, reply with your preferred name.

   ```
   Kael
   ```

4. When the bot asks **"Pick a style: Tactician, Lorekeeper, Cheerleader, Rules-Lawyer Lite"**, reply with one of the four presets exactly as shown (case-sensitive).

   ```
   Tactician
   ```

5. The bot confirms onboarding and archives the thread:

   ```
   → Player onboarded as `Kael` (Tactician). Profile: `mnemosyne/pf2e/players/<slug>/profile.md`
   ```

**If the bot restarts mid-dialog:** your prior answers are preserved in the vault at `mnemosyne/pf2e/players/_drafts/{thread_id}-{user_id}.md`. Simply reply in the thread again and the dialog continues from where it left off.

**If you need to abandon onboarding:** run `:pf player cancel` from inside the dialog thread or from any other channel. This deletes the draft and archives the thread.

**While the dialog is open:** other `:pf player` commands (`note`, `ask`, `npc`, `recall`, `todo`, `style`, `canonize`) are blocked. The bot replies with a link back to your open thread. Complete or cancel the dialog first.

---

### Option B: One-shot pipe syntax

If you prefer a single command — for example when setting up multiple players as an operator, or scripting onboarding — use the pipe-separated form:

```
:pf player start <character_name> | <preferred_name> | <style_preset>
```

Example:

```
:pf player start Kael Stormblade | Kael | Tactician
→ Player onboarded as `Kael` (Tactician). Profile: `mnemosyne/pf2e/players/p-<hash>/profile.md`
```

This path does not create a thread and does not write a draft. It calls `/player/onboard` directly with the four-field payload and is supported indefinitely.

---

## After onboarding

Once onboarding is complete, the player can use:

- `:pf player note <text>` — capture notes to their inbox
- `:pf player npc <npc_name> <note>` — record personal NPC knowledge
- `:pf player ask <question>` — queue a rules or lore question
- `:pf player recall [query]` — retrieve past notes
- `:pf player todo <text>` — append a todo
- `:pf player style set <preset>` — change style preset without re-onboarding

**Re-running `:pf player start`** is idempotent — it overwrites `profile.md` with the latest values. Use this to change a character name or preferred name. Use `:pf player style set <preset>` to change just the style preset without re-typing the other fields.

The operator (GM) can periodically run `:pf player canonize <outcome> <question_id> <rule_text>` to lock pending questions into per-player canon.

For the complete command reference, see [Discord Command Reference](../reference/discord-commands.md).
