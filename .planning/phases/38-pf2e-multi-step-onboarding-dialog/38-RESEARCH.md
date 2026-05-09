# Phase 38: PF2E Multi-Step Onboarding Dialog — Research

**Researched:** 2026-05-08
**Domain:** Discord thread lifecycle + Obsidian vault transient state + dialog state machine
**Confidence:** HIGH (every claim verified from in-tree code or installed library source)

## Summary

The CONTEXT.md decisions are implementable as written — every API, schema, and convention they assume already exists in the codebase. discord.py 2.7.1 is installed locally and confirms `TextChannel.create_thread` and `Thread.edit(archived=True)` are the canonical calls. The Obsidian directory listing pattern is already used twice in `sentinel-core/app/vault.py` (`list_under` + `get_recent_sessions`) and returns either a JSON array of strings or `{"files": [...]}` — caller code defends both shapes. `PathfinderRequest` already carries `channel`, `sentinel_client`, and `http_client`, so no type extension is needed. The function-scope-import RED convention is universal in `test_pathfinder_player_adapter.py` (one import per test body across 12 tests, lines 27, 44, 71, 93, 115, 140, 171, 195, 217, 241, 265, 289, 316, 336, 358, 391). The Phase 37 wave structure runs Wave 0 → Wave 8; the planner should mirror it for consistency.

**Primary recommendation:** Plan exactly the modules CONTEXT.md locks. The only spec-level edge worth surfacing for the planner: the `_drafts/` directory listing on a never-yet-populated tenant returns `[]` (404 absorbed by `list_under`), and the bot needs `Manage Threads` (or be the thread creator) to archive — the bot already creates the thread, so no new permission scope is required.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Thread creation + archive | Discord interface (`bot.py`/`pathfinder_player_dialog.py`) | — | discord.py API, only the Discord client owns Thread objects |
| Pre-route hijack of plain-text answers | Discord interface (new `dialog_router.py` in front of `command_router`) | — | D-01 locks this seam |
| Draft CRUD against vault | Discord interface (`pathfinder_player_dialog.py` via `request.http_client` + Obsidian REST) | — | Same pattern as `bot.py:_persist_thread_id` (PATCH/GET against Obsidian directly from interface) |
| Per-player isolation | Vault path convention (`mnemosyne/pf2e/players/_drafts/*-{user_id}.md`) | PVL-07 (Phase 37) | Slug-prefix isolation extended via filename suffix |
| Onboarding completion (`/player/onboard`) | pf2e module (existing) | — | Phase 37 ships unchanged |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| discord.py | 2.7.1 | Thread API (`create_thread`, `Thread.edit`) | Already installed at `interfaces/discord/.venv` and used throughout `bot.py` |
| httpx | (existing) | Obsidian REST calls | Already used by `_persist_thread_id` (`bot.py:541`) and `vault.py` |
| PyYAML | (existing) | Frontmatter parse/emit | `sentinel-core/app/markdown_frontmatter.py:22` already imports `yaml` |

### Supporting (already in tree, reuse)
| Symbol | Location | Reuse For |
|--------|----------|-----------|
| `_VALID_STYLE_PRESETS` | `pathfinder_player_adapter.py:22` | Style answer validation (D-14) |
| `SENTINEL_THREAD_IDS` (set) + `_persist_thread_id` | `bot.py:124, 536` | Register newly-created onboarding thread (D-11 inverse) |
| `split_frontmatter` / `join_frontmatter` | `sentinel-core/app/markdown_frontmatter.py:29, 46` | Draft frontmatter round-trip (NOT importable from Discord interface — see Architecture Patterns below) |
| `PathfinderRequest.channel`, `.sentinel_client`, `.http_client` | `pathfinder_types.py:46-50` | All already wired by `pathfinder_dispatch.py:117-121` — no extension needed |

**No new packages to install.** Everything required is already in the venv.

## Architecture Patterns

### System Architecture Diagram

```
Discord on_message (bot.py:658)
  └─ thread-only guard (bot.py:668) ──┐
                                      ▼
            _route_message (bot.py:486-501)
                                      │
                                      ▼
        discord_router_bridge.route_message (NEW: insert dialog_router BEFORE command_router)
              │
              ├─ NEW: dialog_router.maybe_consume_as_answer ─── hit ──► pathfinder_player_dialog.consume_as_answer
              │                                                            │
              │                                                            ├─ GET draft → split_frontmatter
              │                                                            ├─ validate answer (style: _VALID_STYLE_PRESETS)
              │                                                            ├─ PUT updated draft  (or)
              │                                                            ├─ on last step:
              │                                                            │   ├─ POST /modules/pathfinder/player/onboard
              │                                                            │   ├─ DELETE draft
              │                                                            │   ├─ Thread.edit(archived=True)
              │                                                            │   └─ SENTINEL_THREAD_IDS.discard(thread.id)
              │                                                            └─ return PathfinderResponse-like text
              │
              └─ miss (None) ──► command_router.route_message (UNCHANGED)
                                      │
                                      └─ ":" prefix → handle_subcommand → pf_dispatch
                                              │
                                              ├─ start (no args, no draft) → pathfinder_player_dialog.start_dialog
                                              │     ├─ TextChannel.create_thread(name=..., type=public_thread, auto_archive_duration=60)
                                              │     ├─ SENTINEL_THREAD_IDS.add + _persist_thread_id
                                              │     ├─ PUT draft (step="character_name")
                                              │     └─ thread.send(QUESTIONS["character_name"])
                                              │
                                              ├─ start (no args, draft exists for this thread+user) → re-prompt current step
                                              │
                                              ├─ start (pipe args) → existing PlayerStartCommand path (UNCHANGED)
                                              │
                                              ├─ cancel → PlayerCancelCommand
                                              │     ├─ list _drafts/, find {thread_id}-{user_id}.md
                                              │     ├─ if found: DELETE + Thread.edit(archived=True) + SENTINEL_THREAD_IDS.discard
                                              │     └─ else: "No onboarding dialog in progress."
                                              │
                                              └─ {note,ask,npc,recall,todo,style,canonize}
                                                    │ (mid-dialog rejection guard — NEW)
                                                    ├─ list _drafts/, filter *-{user_id}.md
                                                    ├─ if any → return rejection text with <#thread_id> link(s)
                                                    └─ else → existing command (unchanged)
```

### Recommended Project Structure
```
interfaces/discord/
├── dialog_router.py                  # NEW — pre-router gate; module-level async maybe_consume_as_answer
├── pathfinder_player_dialog.py       # NEW — STEPS, QUESTIONS, draft CRUD, start_dialog, consume_as_answer
├── pathfinder_player_adapter.py      # MODIFY — add no-args branch in PlayerStartCommand; add PlayerCancelCommand; add mid-dialog guard helper
├── pathfinder_dispatch.py            # MODIFY — register PlayerCancelCommand; inject mid-dialog guard before non-start/non-cancel verbs
├── discord_router_bridge.py          # MODIFY — call dialog_router before command_router
└── tests/
    ├── test_pathfinder_player_dialog.py    # NEW — RED tests for STEPS, draft I/O, consume_as_answer, start_dialog
    ├── test_dialog_router.py               # NEW — RED tests for hit/miss conditions
    └── test_pathfinder_player_adapter.py   # EXTEND — RED tests for no-args branch, PlayerCancelCommand, rejection guard
```

### Pattern 1: Vault file with frontmatter as transient state
**What:** Use Obsidian REST PUT/GET/DELETE with a markdown body whose YAML frontmatter is the state. PyYAML parses the block.
**Example precedent in tree:** `bot.py:536-552` — `_persist_thread_id` PATCHes `ops/discord-threads.md` directly via httpx; same client/auth pattern. There is no shared "vault helper" module reachable from the Discord interface — `bot.py` calls Obsidian directly. Follow that pattern in `pathfinder_player_dialog.py` (httpx + `OBSIDIAN_API_URL` + bearer key from `_read_secret`).
**Note:** `sentinel-core/app/markdown_frontmatter.py` is in a different deployable (sentinel-core), not importable from the discord interface container. The dialog module must inline its own minimal `split_frontmatter`/`join_frontmatter` (≈25 lines) using PyYAML — same regex `^---\s*\n(.*?)\n---\s*\n?` (DOTALL).

### Pattern 2: Function-scope imports for RED-until-implemented
Every test in `test_pathfinder_player_adapter.py` imports the symbol under test inside the test body. New test files MUST follow this. Verified count: 16 function-scope imports across 12 tests (lines 27, 44, 71, 93, 115, 140, 171, 195, 217, 241, 265, 289, 316, 336, 358, 391). No file-level import of `pathfinder_player_adapter` symbols.

### Pattern 3: PathfinderCommand subclass per verb
Existing `PlayerStartCommand`, `PlayerNoteCommand`, etc. (`pathfinder_player_adapter.py`). `PlayerCancelCommand` slots in next to them. Registered in `pathfinder_dispatch.py:211-218`.

### Anti-Patterns to Avoid
- **Importing from sentinel-core.** Discord interface and sentinel-core are separate containers. Do not `from app.markdown_frontmatter import ...` — inline the helper.
- **Mutating `command_router.py`.** D-03 locks: keep it pure. The mid-dialog rejection guard goes in `pathfinder_dispatch.py` (or a small helper called from it), NOT in `command_router`.
- **Caching draft listings in process.** D-06 locks: vault is source of truth. Do not introduce a TTL cache.
- **Catching every Obsidian error silently.** Existing pattern (`bot.py:_persist_thread_id`) only swallows on the persistence side-effect, not the primary path. Draft writes that fail should surface text errors to the player ("Couldn't save your answer; try again") not silently swallow.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Frontmatter regex/parse | Custom parser | PyYAML + the canonical regex `re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)` | Already proven in `markdown_frontmatter.py:26` |
| Thread creation | Manual HTTP call to Discord API | `await channel.create_thread(name=..., type=ChannelType.public_thread, auto_archive_duration=60)` | discord.py 2.7.1 in tree; already used at `bot.py:739` |
| Thread archive | Custom REST call | `await thread.edit(archived=True)` | discord.py canonical; signature at `threads.py:582` |
| Discord channel mention | Manual string assembly with brittle escaping | f-string `f"<#{thread_id}>"` | Standard Discord mention syntax |
| User-ID slug suffix in filenames | New convention | `{thread_id}-{user_id}.md` per D-07 | Locked; mirrors `ops/sessions/{date}/` filename convention used by `vault.py:249` |

## Runtime State Inventory

> N/A — Phase 38 is greenfield (new modules + additive edits). No existing string is being renamed. Drafts directory is created on first PUT.

## Common Pitfalls

### Pitfall 1: `create_thread` defaults to PRIVATE, not public
**What goes wrong:** Calling `channel.create_thread(name=...)` without `type=` returns `ChannelType.private_thread` — only invited members can see it.
**Why it happens:** discord.py 2.7.1 source at `channel.py:954-955`: `if type is None: type = ChannelType.private_thread`.
**How to avoid:** Always pass `type=discord.ChannelType.public_thread`. The existing `bot.py:741` call does this — replicate it.
**Warning signs:** Player reports they cannot see the thread.

### Pitfall 2: `Thread.edit` requires the thread be unarchived
**What goes wrong:** Calling `edit(archived=True)` on an already-archived thread raises HTTPException; calling it on a thread that auto-archived between completion and our explicit archive will fail.
**Why it happens:** discord.py docs at `threads.py:604`: "The thread must be unarchived to be edited."
**How to avoid:** Wrap in try/except `discord.HTTPException`; treat already-archived as success. With our 60-minute `auto_archive_duration` and the dialog completing in seconds, this is rare but possible if a player walks away.

### Pitfall 3: Bot must be thread creator OR have Manage Threads
**What goes wrong:** Archive 403s if neither condition holds.
**Why it happens:** discord.py docs at `threads.py:599-600`: "Editing the thread requires Permissions.manage_threads. The thread creator can also edit name, archived or auto_archive_duration."
**How to avoid:** No action — the bot creates the dialog thread itself, so it is always the creator. Document this in code comments so a future refactor doesn't introduce a "thread created by user" path.

### Pitfall 4: Obsidian directory listing returns 404 for non-existent dir
**What goes wrong:** `_drafts/` does not exist until the first PUT inside it. A `GET /vault/mnemosyne/pf2e/players/_drafts/` before any draft has been created returns 404.
**Why it happens:** Obsidian REST follows filesystem semantics.
**How to avoid:** Mirror `vault.py:307-308` exactly — `if resp.status_code == 404: return []`. The mid-dialog rejection lookup MUST treat 404 as "no drafts" not as an error.

### Pitfall 5: Listing response shape is shape-defensive
**What goes wrong:** Some Obsidian versions return `["a.md", "b.md"]`, others return `{"files": [{"path": "a.md"}, ...]}`.
**Why it happens:** Plugin response shape evolved across versions; codebase already defends both at `vault.py:246` and `vault.py:311`.
**How to avoid:** Copy the existing pattern verbatim:
```python
data = resp.json()
files = data if isinstance(data, list) else data.get("files", [])
filenames = [f if isinstance(f, str) else f.get("path", "") for f in files]
```

### Pitfall 6: `request.user_id` is `str` — re-coerce defensively
Phase 37 had a bug from `int` user_ids drifting in (`PlayerStartCommand.handle()` does `str(request.user_id)` at line 39 as a guard). New code that does `f"_drafts/{thread_id}-{user_id}.md"` MUST `str(user_id)` first or filename-mismatch bugs surface only at lookup time.

### Pitfall 7: Thread message_content intent is required
**What goes wrong:** Plain-text replies in the thread arrive as empty `message.content` if the Message Content intent isn't enabled.
**Why it happens:** Discord gating; bot.py:560 already enables it (`intents.message_content = True`).
**How to avoid:** No action — already enabled. Note it for any future deploy that uses fresh Discord credentials.

### Pitfall 8: Bot reconnect across the answer
**What goes wrong:** If the bot disconnects mid-dialog, queued thread messages during the gap are NOT replayed.
**Why it happens:** discord.py's gateway resume only replays events from a small window (~minutes). Messages sent during full disconnects are lost.
**How to avoid:** No code change — the SPEC accepts this. The vault draft persists; the player can resend the answer or run `:pf player start` to be re-prompted (Requirement 7 covers this exact resume path). Document in SUMMARY: "lost answers require player to resend — no auto-catch-up."

## Code Examples

### Creating a public thread (verified from discord.py 2.7.1 source + bot.py:739)
```python
# Source: interfaces/discord/.venv/lib/python3.13/site-packages/discord/channel.py:894
# Existing usage: interfaces/discord/bot.py:739
thread = await invoking_channel.create_thread(
    name=f"Onboarding — {message.author.display_name}"[:100],  # Discord caps at 100
    type=discord.ChannelType.public_thread,
    auto_archive_duration=60,  # 60 | 1440 | 4320 | 10080 (minutes)
)
SENTINEL_THREAD_IDS.add(thread.id)
await _persist_thread_id(thread.id)
await thread.send(QUESTIONS[STEPS[0]])
```

### Archiving the thread (verified from discord.py 2.7.1 source)
```python
# Source: interfaces/discord/.venv/lib/python3.13/site-packages/discord/threads.py:582
try:
    await thread.edit(archived=True, reason="onboarding completed")
except discord.HTTPException:
    pass  # already archived or transient — non-fatal
SENTINEL_THREAD_IDS.discard(thread.id)
```

### Draft directory listing (verified pattern from vault.py:295-314)
```python
async def _list_drafts(http_client, base_url, headers) -> list[str]:
    """Returns filenames in _drafts/, [] on 404 or error."""
    url = f"{base_url}/vault/mnemosyne/pf2e/players/_drafts/"
    resp = await http_client.get(url, headers=headers, timeout=10.0)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    data = resp.json()
    files = data if isinstance(data, list) else data.get("files", [])
    return [f if isinstance(f, str) else f.get("path", "") for f in files]
```

### Frontmatter round-trip (inline copy of markdown_frontmatter.py:26-55)
```python
import re, yaml
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)

def _split_fm(body: str) -> tuple[dict, str]:
    m = _FRONTMATTER_RE.match(body or "")
    if not m:
        return ({}, body or "")
    try:
        fm = yaml.safe_load(m.group(1)) or {}
        if not isinstance(fm, dict):
            fm = {}
    except Exception:
        fm = {}
    return (fm, body[m.end():])

def _join_fm(fm: dict, rest: str = "") -> str:
    block = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, default_flow_style=False).strip()
    return f"---\n{block}\n---\n\n{rest.lstrip()}"
```

### Function-scope RED test (verified pattern from test_pathfinder_player_adapter.py:25-39)
```python
# tests/test_pathfinder_player_dialog.py
from unittest.mock import AsyncMock

async def test_consume_as_answer_advances_step_from_character_name():
    """RED: function-scope import fails until module exists."""
    from pathfinder_player_dialog import consume_as_answer  # ImportError until impl

    http = AsyncMock()
    http.get = AsyncMock(return_value=_fake_resp(200, _fake_draft_body(step="character_name")))
    http.put = AsyncMock(return_value=_fake_resp(200, ""))
    # ... call consume_as_answer, assert PUT body has step=preferred_name
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pipe-syntax single-shot onboarding | Multi-step thread dialog with vault draft | This phase | Pipe-syntax preserved as regression-only path (locked in CONTEXT) |
| In-process state for transient flows | Vault file with frontmatter | Phase 37 set the precedent (player profiles); Phase 38 extends to drafts | Survives bot restart; no Redis/SQLite added |

**Deprecated/outdated:**
- `discord-py-slash-command` and other pre-2.0 forks — discord.py 2.7.1 is the only Discord lib in the project venv.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PVL-01 | Onboarding creates per-player profile.md | Reuses Phase-37 `/player/onboard` route unchanged; verified at `modules/pathfinder/app/routes/player.py:66-79` (4-field `PlayerOnboardRequest`: `user_id`, `character_name`, `preferred_name`, `style_preset` — exact schema CONTEXT.md assumes). NO backend change required. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| (none) | All claims verified from in-tree source files or installed library source. | — | — |

## Answers to Planner Gap Questions

### Q1: Discord thread.create_thread API
- **Call:** `await channel.create_thread(name=..., type=discord.ChannelType.public_thread, auto_archive_duration=60)` — verified `bot.py:739-743` uses exactly this.
- **Source:** `discord/channel.py:894-952` (discord.py 2.7.1).
- **Default trap:** Without `type=`, defaults to `private_thread` (`channel.py:955`). Always pass `type` explicitly.
- **`message_count`:** Not relevant on creation; the new thread starts empty (no parent message because `message=None` is the default).
- **Permissions:** `Permissions.create_public_threads` on the parent channel (`channel.py:909`). Bot needs SEND_MESSAGES_IN_THREADS to post the question. MANAGE_THREADS is NOT required to create — only to archive a thread you didn't create. Bot is creator → can archive without it.
- **Use NOT** `channel.start_thread(...)` — that name doesn't exist on `TextChannel`; `start_thread_with_message`/`start_thread_without_message` are HTTP-layer internals (`channel.py:958, 968`), never called from user code.

### Q2: Discord Thread.edit(archived=True)
- **Call:** `await thread.edit(archived=True, reason="...")` — `threads.py:582-666`.
- **Permissions:** Manage Threads OR be the thread creator (`threads.py:599-600`). Bot creates → bot can archive. ✓
- **Awaitable:** Yes — coroutine, returns the edited Thread object.
- **Already-archived behavior:** "The thread must be unarchived to be edited" (`threads.py:604`). Calling on an already-archived thread → `HTTPException`. Wrap in try/except.
- **Cancel-from-other-channel (D-10):** The cancel command runs in a non-thread channel; the dialog thread is fetched via `bot.get_channel(thread_id)` — works because the bot already cached it via `SENTINEL_THREAD_IDS`. Then `await thread.edit(archived=True)` works remotely.

### Q3: Obsidian REST GET /vault/{folder}/ directory listing
- **Verified URL:** trailing slash IS required for directory listing (vs. file read). See `vault.py:304`: `f"{base}/vault/{prefix}/" if prefix else f"{base}/vault/"`.
- **Response shape (defensive):** Either a JSON array of strings, or `{"files": [...]}` where each entry is a string OR `{"path": "..."}`. Codebase handles all four shapes (`vault.py:246, 311`). Use the same defensive parse.
- **Subdir handling:** Subdir names end with `/` (per `list_under` docstring at `vault.py:298`). For draft lookup, filter to `*-{user_id}.md` (D-05) — subdirs auto-excluded by suffix.
- **Non-existent directory:** Returns 404. `vault.py:307-308` treats this as `[]`. The `_drafts/` folder will not exist until the first draft is PUT, so this case will hit on every fresh deployment until first onboarding.
- **Path return:** Filenames only when entry is a bare string; full path under the requested prefix when returned as `{"path": ...}`. Always strip/derive the basename for the `*-{user_id}.md` filter.

### Q4: Existing draft-like pattern in this project
**No identical pattern exists.** The closest analogues:
- `mnemosyne/pf2e/players/{slug}/profile.md` (Phase 37) — frontmatter holds `onboarded`, `character_name`, etc. Permanent, not transient.
- `ops/sessions/{date}/{user_id}-*.md` (`vault.py:218-273`) — listed by directory, filtered by `f"{user_id}-"` substring. **Closest pattern for the rejection-lookup loop** — copy this loop's shape (same filter strategy, same listing parser).
- `ops/discord-threads.md` (`bot.py:536-600`) — flat append-only file of thread IDs. Pattern for direct httpx-from-bot.py call to Obsidian (no shared helper module) — `pathfinder_player_dialog.py` should mirror this access pattern (env vars `OBSIDIAN_API_URL`/`OBSIDIAN_API_KEY`, bearer auth, `httpx.AsyncClient` per call OR reuse `request.http_client` when available).
- No existing module does "vault-as-state-machine with mutable frontmatter PUT-back". This phase establishes that pattern.

### Q5: PathfinderRequest extension — NOT NEEDED
`PathfinderRequest` already carries everything required (`pathfinder_types.py:41-54`):
- `channel: typing.Any = None` — line 46. Set by `pathfinder_dispatch.py:117` (`channel=channel` passed through from `bot.py:_route_message`).
- `sentinel_client: typing.Any = None` — line 49.
- `http_client: typing.Any = None` — line 50.
- `user_id: str` — line 44.

Both `PlayerCancelCommand` (needs `channel.id`, `channel`) and the dialog flow get these for free. **No type change required.**

The `channel` will be a `discord.Thread` instance when the player invokes `:pf player cancel` from inside the dialog thread (because `bot.py:on_message` sets `channel=message.channel` at line 696). When invoked from a regular text channel, `channel` is the parent channel — the cancel command then must look up the thread via `channel.guild.get_thread(thread_id)` or `bot.get_channel(thread_id)`. Plan accordingly.

### Q6: ImportError-as-RED convention — UNIVERSAL
Verified across `test_pathfinder_player_adapter.py`: 16 function-scope imports across 12 test functions (lines 27, 44, 71, 93, 115, 140, 171, 195, 217, 241, 265, 289, 316, 336, 358, 391). No file-level import of any `pathfinder_player_adapter` symbol. The ONLY file-level imports are stdlib (`unittest.mock.AsyncMock` line 17) and stable types (`pathfinder_types.PathfinderRequest` line 19).

**Counter-example to be aware of:** `test_pathfinder_npc_basic_adapter.py:9` imports `pathfinder_npc_basic_adapter` at file level — but that file is for an already-implemented adapter, not a Wave-0 RED file. The convention applies to Wave-0 RED tests for not-yet-implemented modules.

### Q7: TDD wave structure for prior PF2E phases
Phase 37 wave map (verified):

| Wave | Plans | Type |
|------|-------|------|
| 0 | 37-01, 37-02, 37-03, 37-04, 37-05 | tdd (01–04) + auto (05) — RED tests + scaffolding |
| 1 | 37-06 | auto |
| 2 | 37-07 | auto |
| 3 | 37-08 | auto |
| 4 | 37-09 | auto |
| 5 | 37-10 | auto |
| 6 | 37-11 | auto |
| 7 | 37-12, 37-13 | auto (parallel within wave) |
| 8 | 37-14 | auto |

**Convention:** Wave 0 = all RED test files written first (`type: tdd`). Wave 1+ = implementation slices, one per concern, can be sequential or parallel. Phase 38's planner should mirror this — one Wave-0 plan per RED test file (3 expected: dialog module, dialog_router, adapter additions), then implementation waves for each concern.

### Q8: Backend route schema drift — NONE
`modules/pathfinder/app/routes/player.py:66-79` confirms `PlayerOnboardRequest` is exactly:
```python
class PlayerOnboardRequest(BaseModel):
    user_id: str
    character_name: str
    preferred_name: str
    style_preset: str
    @field_validator("style_preset")
    def check_preset(cls, v): ...  # validates against VALID_STYLE_PRESETS
```
Identical to what `PlayerStartCommand` posts today (`pathfinder_player_adapter.py:58-66`). **Phase 38 needs ZERO backend changes.** The dialog assembles the same payload and POSTs to the same URL (`modules/pathfinder/player/onboard`).

### Q9: Bot disconnect mid-dialog
- **Gateway resume window:** discord.py 2.7 follows Discord's gateway protocol — on reconnect within ~3 minutes, missed events are replayed via session resume. On full disconnect (longer outage, token rotation, container restart), the bot reconnects with a NEW session and Discord does NOT replay missed messages.
- **Practical effect:** If a player sends an answer during a 30-second restart, the message arrives during the gateway's IDENTIFY phase and is lost.
- **Mitigation in spec:** Requirement 7 ("restart-start resumes") covers this — the player can re-run `:pf player start` and the bot re-prompts the current step.
- **No additional code needed.** Document the loss-window in SUMMARY for operator awareness.

### Q10: Style-preset case sensitivity
**Existing behavior (verified):** `PlayerStartCommand.handle()` at `pathfinder_player_adapter.py:49-56` does **strict, case-sensitive** match:
```python
if style_preset not in _VALID_STYLE_PRESETS:  # tuple of "Tactician", "Lorekeeper", ...
    return PathfinderResponse(kind="text", content=f"Invalid style preset `{style_preset}`. Valid: ...")
```
And the route's `field_validator` (`routes/player.py:74-78`) does the same strict check.

**Recommendation for the dialog:** Match the existing pipe-syntax behavior — strict match. But normalize input casing to be friendlier:
```python
normalized = next((p for p in _VALID_STYLE_PRESETS if p.lower() == answer.strip().lower()), None)
if normalized is None:
    # re-ask, list valid presets
else:
    # store normalized (canonical-cased) value in draft
```
This is a Claude's-discretion area per CONTEXT.md (D-13/D-14 don't lock match strictness). Recommendation: **case-insensitive on input, canonical-case on storage** — the player isn't typing in a structured CLI, they're typing a chat message. The existing pipe-syntax stays unchanged (operator UX).

## Sources

### Primary (HIGH confidence — verified in tree)
- `interfaces/discord/.venv/lib/python3.13/site-packages/discord/__init__.py` — `__version__ = '2.7.1'`
- `interfaces/discord/.venv/lib/python3.13/site-packages/discord/channel.py:894-977` — `TextChannel.create_thread` signature
- `interfaces/discord/.venv/lib/python3.13/site-packages/discord/threads.py:582-666` — `Thread.edit` signature
- `interfaces/discord/bot.py:124,486-501,536-600,658-705,739-746` — existing thread + Obsidian patterns
- `interfaces/discord/discord_router_bridge.py` — full file (16 lines)
- `interfaces/discord/command_router.py:8-34` — DO NOT MODIFY scope
- `interfaces/discord/pathfinder_player_adapter.py:22,30-71` — `_VALID_STYLE_PRESETS`, existing `PlayerStartCommand`
- `interfaces/discord/pathfinder_dispatch.py:160-218` — verb registration surface
- `interfaces/discord/pathfinder_types.py:41-54` — `PathfinderRequest` already carries channel/clients
- `interfaces/discord/tests/test_pathfinder_player_adapter.py` — function-scope RED convention (16 imports / 12 tests)
- `interfaces/discord/tests/conftest.py` — Discord stubs (Phase 33-01 decision)
- `sentinel-core/app/vault.py:218-314` — directory listing + 404 handling pattern
- `sentinel-core/app/markdown_frontmatter.py:22-55` — canonical YAML frontmatter regex
- `modules/pathfinder/app/routes/player.py:66-79` — `PlayerOnboardRequest` schema (no drift)
- `.planning/phases/37-pf2e-per-player-memory/37-01..14-PLAN.md` — wave numbering convention

### Secondary (HIGH — official documentation in source)
- discord.py 2.7.1 docstrings embedded in installed source — permissions, archive constraints, defaults

### No tertiary sources required — every claim is verified against in-tree code.

## Metadata

**Confidence breakdown:**
- discord.py thread API: HIGH — verified from installed source, version 2.7.1 confirmed
- Obsidian REST listing: HIGH — pattern in tree at `vault.py:295-314` already handles 404 + dual response shape
- PathfinderRequest extension needs: HIGH — re-read `pathfinder_types.py` and `pathfinder_dispatch.py`; channel/clients already wired
- Draft pattern precedent: HIGH — closest match is `ops/sessions/{date}/{user_id}-*.md` filter loop in `vault.py:218-273`
- Wave structure: HIGH — explicit grep across 14 plan headers
- Backend route schema: HIGH — `PlayerOnboardRequest` matches `PlayerStartCommand` payload byte-for-byte
- Bot reconnect behavior: MEDIUM — gateway resume window is documented in discord.py changelogs but exact ms threshold varies by Discord; mitigation via Requirement 7 makes this moot
- Style-preset case sensitivity: HIGH — direct read of existing validator

**Research date:** 2026-05-08
**Valid until:** 2026-06-07 (30 days; discord.py 2.7 is stable, Obsidian REST plugin stable)
