# How to troubleshoot the Discord interface

Problem/solution pairs for common issues with the Sentinel Discord interface. For the full command reference, see [Discord Command Reference](../reference/discord-commands.md).

---

### `:pf player start` says "Usage:..."

You called it with no arguments. Provide all three pipe-separated fields:

```
:pf player start <character_name> | <preferred_name> | <style_preset>
```

---

### `:pf player start` says "Invalid style preset"

The preset is case-sensitive and must be one of: `Tactician`, `Lorekeeper`, `Cheerleader`, `Rules-Lawyer Lite`. Note the hyphen in "Rules-Lawyer Lite".

---

### `:pf player note` (or any verb) says "onboard first"

The onboarding gate is closed. Run `:pf player start ...` to write your profile. The orchestrator checks `players/{slug}/profile.md` for `onboarded: true` before any non-`start`/non-`style-list` verb.

---

### `:pf rule what is sneak attack?` says "Unknown sub-command"

`:pf rule` requires an explicit verb. Use `:pf rule query <question>` (or `list`/`show`/`history`). Bare-noun lookup is not supported.

---

### `:pf <noun> <verb>` returns "Cannot reach the Sentinel"

sentinel-core isn't running. Check `docker ps` for `sentinel-of-mnemosyne-sentinel-core-1`. If absent, bring the stack up:

```
./sentinel.sh --discord --pf2e up -d
```

---

### Admin-only command says "Admin only..."

Verbs like `:pf foundry import-messages`, `:pf ingest`, `:pf cartosia`, and `:vault-sweep` require your Discord user id to be in the `SENTINEL_ADMIN_USER_IDS` env var (comma-separated). Add it to `.env` and restart the discord container.

---

### Recall returns nothing

`:pf player recall` only searches **your** namespace at `players/{slug}/*`, never the global vault. If you have never written a note, ask, npc record, or todo, recall has nothing to find. Empty query returns most-recent items; a query filters by keyword.

---

### Two players seem to share an NPC note

They don't. Each `:pf player npc <name> <note>` writes to `players/{slug}/npcs/{npc_slug}.md` — a per-player file. The global NPC note at `mnemosyne/pf2e/npcs/{npc_slug}.md` is owned by the GM (`:npc create` / `:npc update`) and is never written by `:pf player` verbs.

---

## See Also

- [Discord Command Reference](../reference/discord-commands.md) — complete verb catalogue
- [Foundry VTT First Setup](../tutorial/foundry-first-setup.md) — Foundry VTT module installation
- `.planning/REQUIREMENTS.md` — full PVL-* / FCM-* requirement IDs
