---
slug: pf-verb-routing-stale-image
status: resolved
trigger: ":pf npc create Jareth a halfing dwarf who is a fish" returned "Unknown command :pf. Try :help for available commands" in Discord; :help text silently became an emoji
created: 2026-04-23
updated: 2026-04-23
resolution_type: operational (not a code bug)
---

# Debug Session — :pf verbs unreachable + :help becomes emoji

## Symptoms

1. User typed `:pf npc create Jareth a halfing dwarf who is a fisherman...` in a Discord thread. Bot replied `Unknown command :pf. Try :help for available commands.`
2. User typed `:help`. Discord client converted it to an emoji (pointing-person) before sending; bot received only the emoji and fell through to the AI route, replying `Hello! How can I assist you today?`
3. Observed while running the default `./sentinel.sh up` stack.

## Root Cause

**Primary: running Discord container image is two days stale.**

Evidence:

| Check | Value |
|-------|-------|
| `docker inspect sentinel-of-mnemosyne-discord-1 → .Created` | `2026-04-21T14:33:57Z` |
| `git log -1 --format="%ci" main` | `2026-04-23 12:19 -0400` |
| `docker exec sentinel-of-mnemosyne-discord-1 grep -c "_pf_dispatch" /app/bot.py` | `0` |
| `grep -c "_pf_dispatch" interfaces/discord/bot.py` (on disk) | `≥2` |
| Phase 29-03 commit that added `_pf_dispatch` (`6f4ec80`) | Landed 2026-04-22 |
| Phase 30 commits wiring `export/token/stat/pdf` verbs | Landed 2026-04-23 |

The running container was built on 2026-04-21 — **before** Phase 29-03 introduced `_pf_dispatch` and the `:pf` routing in `handle_sentask_subcommand`. So the live bot has none of the `:pf npc` verbs (`create`, `update`, `show`, `relate`, `import`, `export`, `token`, `stat`, `pdf`). Its subcommand dispatcher hits the default case and returns the generic "Unknown command" string.

The container was *started* at 2026-04-23T14:53 UTC (a few hours ago), but `docker compose up` reuses the existing image unless `--build` is passed. Starting ≠ rebuilding.

**Secondary: `pf2e-module` service is not running.**

Evidence:

| Check | Value |
|-------|-------|
| `docker ps` matching `pf` | No rows |
| `docker compose config --profiles` | Lists `pf2e` as an **opt-in** profile |
| Existing command (from `sentinel.sh:12`) | `--pf2e` flag required to activate |

The pathfinder FastAPI service is gated behind the `pf2e` profile (designed this way per Phase 28 D-10). Default `./sentinel.sh up` doesn't include it. Even if the Discord bot had the current code, `_pf_dispatch` would fail on the first `post_to_module("modules/pathfinder/npc/...")` call because the target service isn't bound.

**Tertiary: `:help` became an emoji — Discord client behaviour, not a bot bug.**

Evidence:

- The user's 12:10 PM message in the screenshot renders as a single emoji (👉 pointing person), not the text `:help`.
- Discord's desktop client autocompletes `:word` sequences to emoji when a matching emoji exists. `:help` is NOT a standard Unicode emoji shortcode, but Discord's guild/nitro-emoji picker offers auto-replace suggestions — and with certain accessibility/tab-complete settings the text is converted before send.
- The bot receives the emoji character/shortcode, not the text `:help`. That falls through `_route_message`'s subcommand branch (doesn't start with `:`), doesn't match `_HELP_KEYWORDS`, and goes to the AI router — which cheerfully replied "Hello! How can I assist you today?"

## Fix

### 1. Rebuild and redeploy with the pf2e profile active

```bash
cd /Users/trekkie/projects/sentinel-of-mnemosyne
# Stop current stack cleanly
./sentinel.sh down

# Rebuild ALL services (picks up Phase 29–30 code) AND start with pf2e profile
./sentinel.sh --pf2e up -d --build
```

Breakdown of what this does:
- `down` — stops the currently-running old-image containers cleanly.
- `--pf2e` — activates the `pf2e` compose profile, enabling `pf2e-module`.
- `up -d --build` — rebuilds all images before starting, ensuring the Discord container gets Phase 29 + Phase 30 bot.py and the pf2e-module gets Phase 30's four new route handlers.

Expected result after rebuild:
- `:pf npc create Jareth | halfling dwarf fisherman` → 200 OK, creates `mnemosyne/pf2e/npcs/jareth.md`, replies with `Created NPC: **Jareth** at \`mnemosyne/pf2e/npcs/jareth.md\`` or similar.
- `:pf npc show Jareth` → embed with NPC summary.
- `:pf npc export Jareth` → attached `jareth.json` (Foundry actor JSON).
- `:pf npc token Jareth` → `/imagine` prompt text.
- `:pf npc stat Jareth` → Discord embed.
- `:pf npc pdf Jareth` → attached PDF.

### 2. Usage note on `:pf npc create` syntax

Your test input was `:pf npc create Jareth a halfing dwarf who is a fisherman and is twice as strong as men twice his size`. The parser in `_pf_dispatch` (see `interfaces/discord/bot.py:198-204`) splits on `|` for `create`:

```python
name, _, description = rest.partition("|")
if not name.strip():
    return "Usage: `:pf npc create <name> | <description>`"
```

Without the `|` separator, the entire string becomes `name` and `description` is empty. The LLM will still try to extract fields but the separation signal is missing. After rebuild, use:

```
:pf npc create Jareth | a halfling dwarf who is a fisherman and is twice as strong as men twice his size
```

(Also: "halfling" — the original message had "halfing". Spelling is forgiven by the LLM extractor but worth catching on your side.)

### 3. `:help` → emoji workarounds (client-side, not a code fix)

Options, easiest first:
- **Type without the leading colon**: `help` alone (or phrases like `what can you do`) trigger `_HELP_KEYWORDS` in `_route_message` (see `bot.py:441`). This is the non-colon help path already in place.
- **Escape the colon**: `\:help` sends the literal characters, bypassing Discord's emoji autocomplete.
- **Use the slash command**: `/sen :help` routes via the slash-command path where Discord is less aggressive about emoji substitution.
- **Disable emoji autocomplete**: User Settings → Text & Images → "Convert emoticons to emoji" / "Automatic emoji substitution". Personal preference.

No bot-side fix — Discord transforms the text before it reaches the gateway. The bot literally cannot see that the user typed `:help`.

## Verification Plan

After running the fix command above:

```bash
# 1. Confirm new container ages
docker inspect sentinel-of-mnemosyne-discord-1 --format '{{.Created}}'      # Should show today
docker inspect sentinel-of-mnemosyne-pf2e-module-1 --format '{{.Created}}'  # Should exist now

# 2. Confirm running image has _pf_dispatch
docker exec sentinel-of-mnemosyne-discord-1 grep -c "_pf_dispatch" /app/bot.py
# Expected: 5+ (import, dispatch table, call site)

# 3. Confirm pf2e-module /healthz via sentinel-core proxy
docker exec sentinel-of-mnemosyne-sentinel-core-1 curl -sf http://pf2e-module:8000/healthz
# Expected: {"status":"ok","module":"pathfinder"}

# 4. Live Discord test (manual)
# Post in allowed channel or thread: :pf npc create Jareth | halfling dwarf fisherman
# Expected: "Created NPC: **Jareth** at mnemosyne/pf2e/npcs/jareth.md" (or similar)
```

## Files Changed

**None.** This is an operational fix — code on `main` is correct. The running Docker image was simply stale.

## Lessons

Treat "the container is up" as *orthogonal* to "the container has the latest code." Every `docker compose up` after a significant code merge should be `up -d --build` or preceded by an explicit `build`. An automation idea for later: a pre-flight check in `sentinel.sh up` that compares the container image's creation timestamp to `git log -1 --format="%ci" HEAD` and warns if the image is older than the HEAD commit.
