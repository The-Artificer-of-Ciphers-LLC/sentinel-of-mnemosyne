# Phase 38: PF2E Multi-Step Onboarding Dialog - Context

**Gathered:** 2026-05-08
**Status:** Ready for planning

<domain>
## Phase Boundary

`:pf player start` (no args) becomes a stateful conversational onboarding flow. The bot creates a Discord thread, asks the player three questions across multiple messages (character name, preferred name, style preset), persists transient progress to a vault draft file, then calls the existing Phase-37 `/player/onboard` route with the assembled payload.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**7 requirements are locked.** See `38-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `38-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- New thread creation on no-arg `:pf player start`
- Draft file CRUD against `mnemosyne/pf2e/players/_drafts/`
- Plain-text answer capture inside a draft-bearing thread
- New `PlayerCancelCommand`
- Mid-dialog rejection guard for the seven non-`start`/`cancel` verbs
- Resume-on-restart-start behaviour
- Wave-0 RED tests for every new behaviour (TDD)

**Out of scope (from SPEC.md):**
- Modifying `/player/onboard` route schema or behaviour
- Configurable question text or i18n
- Editing already-onboarded profiles
- Slash-command modal alternative
- Listening to plain text in non-thread channels
- 24h hard expiry of drafts
- Replacing pipe-syntax one-shot path

</spec_lock>

<decisions>
## Implementation Decisions

### Router Seam
- **D-01:** New module `interfaces/discord/dialog_router.py` is wired into `discord_router_bridge.route_message` BEFORE `command_router`. It exposes a single async entrypoint (working name `maybe_consume_as_answer`) that returns the bot's response on hit, or `None` on miss. On `None`, the bridge falls through to `command_router.route_message` unchanged.
- **D-02:** Hit conditions inside `dialog_router`: message has no `:` prefix AND `channel` is a `discord.Thread` AND a draft exists at `mnemosyne/pf2e/players/_drafts/{thread.id}-{user_id}.md`. Any condition false → return `None` and let the existing router run.
- **D-03:** `command_router.py` is NOT modified. Decoupling keeps `command_router` pure: it still only knows about `call_core` / `pf_dispatch` and stays trivially testable.
- **D-04:** `bot.py:on_message` is NOT modified. The thread-only guard at line 668 already covers the channel-scope constraint from the SPEC; no further change needed at that layer.

### Mid-Dialog Rejection Lookup
- **D-05:** Lookup uses Obsidian `GET /vault/mnemosyne/pf2e/players/_drafts/` directory listing on every non-`start`/non-`cancel` `:pf player <verb>` invocation. Filter the returned filenames for `*-{user_id}.md` suffix; any match means the user has at least one in-flight draft.
- **D-06:** No in-process cache. The vault is the single source of truth. Cache invalidation cost > the network round-trip to localhost Obsidian.
- **D-07:** When a draft is found, the rejection message MUST link the player to the dialog thread (Discord channel mention syntax `<#thread_id>`). The thread_id comes from the draft filename (`{thread_id}-{user_id}.md`) — no draft body read needed for the rejection path.
- **D-08:** Multi-draft case (same user has drafts in two threads): rejection message lists every active thread link, not just the first.

### Thread Lifecycle
- **D-09:** On dialog completion (after `/player/onboard` returns successfully): bot posts the existing pipe-syntax success message ("Player onboarded as `{preferred_name}` ({style_preset}). Profile: `{path}`"), deletes the draft file, then archives the thread via `discord.Thread.edit(archived=True)`.
- **D-10:** On `:pf player cancel` with a draft present: bot posts cancel-acknowledgement, deletes the draft file, then archives the thread (symmetric with completion). Cancel from inside the dialog thread is the canonical path; cancel from another channel is also allowed and archives the dialog thread remotely.
- **D-11:** Once archived, the thread is removed from `SENTINEL_THREAD_IDS` to prevent stale routing if Discord ever unarchives it.

### Question Text & Step Machine
- **D-12:** New module `interfaces/discord/pathfinder_player_dialog.py` owns: question strings (module-level constants), step ordering, draft frontmatter read/write, and the `consume_as_answer()` function called by `dialog_router`.
- **D-13:** Step ordering and question text:
  ```python
  STEPS = ("character_name", "preferred_name", "style_preset")
  QUESTIONS = {
      "character_name": "What is your character's name?",
      "preferred_name": "How would you like me to address you?",
      "style_preset": (
          "Pick a style — reply with a number or the name:\n"
          "1) Tactician\n2) Lorekeeper\n3) Cheerleader\n4) Rules-Lawyer Lite"
      ),
  }
  ```
  Step values are literal strings (not Enum) — they round-trip through YAML frontmatter as strings anyway.
  **Refined 2026-05-10 (UAT G-06):** style_preset prompt is a 1-4 numbered list and `_normalise_style_preset` accepts numeric answers in addition to case-insensitive names with trailing-punctuation tolerance.
- **D-14:** Style-preset answer validation reuses the existing `_VALID_STYLE_PRESETS` tuple from `pathfinder_player_adapter.py:22` (re-exported or imported from there to avoid duplication). Invalid preset → bot re-asks the same question with the valid-preset list, draft `step` unchanged.
- **D-15:** `pathfinder_player_adapter.py` keeps the existing pipe-syntax `PlayerStartCommand` for one-shot use AND gains a new no-args branch that calls into `pathfinder_player_dialog.start_dialog(...)` to create the thread + draft. The adapter file remains the single registration surface for `:pf player start`.
- **D-16:** New `PlayerCancelCommand` lives in `pathfinder_player_adapter.py` next to `PlayerStartCommand` and is registered in `pathfinder_dispatch.py` alongside the other verbs.

### Multi-Draft Cancel Symmetry (added 2026-05-09 from checker C1)
- **D-17:** `:pf player cancel` issued from a non-dialog channel with N drafts archives ALL N threads symmetrically — there is no "pick one" branch and no asking the user to disambiguate. The adapter:
  1. Lists `_drafts/` and filters to `*-{user_id}.md` to enumerate every thread_id with an in-flight draft for this user.
  2. Iterates sequentially over each thread_id: calls `pathfinder_player_dialog.cancel_dialog(thread=bot.get_channel(tid), user_id=..., http_client=...)` which deletes the draft file, calls `Thread.edit(archived=True)`, and discards the id from `SENTINEL_THREAD_IDS`.
  3. Aggregates per-thread failures (e.g. `discord.HTTPException` on archive of one thread, `bot.get_channel` returning `None`) into a list — failure of any single archive does NOT abort the loop. Drafts with unreachable threads still get the draft file deleted (vault-side cleanup).
  4. Replies with a single text response: `Cancelled the onboarding dialog.` for N=1, or `Cancelled N onboarding dialogs.` for N>1. If any thread failed to archive cleanly, append a diagnostic line listing the affected `<#thread_id>` mentions.

  This preserves the locked "list-everything" / "no surprises" symmetry of D-08 (multi-draft rejection lists every link) and the D-10 invariant that cancel from outside the dialog thread is allowed.

### Router Seam — D-03 Refinement (added 2026-05-09 during 38-06 execution)
- **D-18:** `command_router.py` may carry **additive optional kwargs threaded through the bridge stack** (default-None pass-through plumbing for downstream handlers). The sealed promise of D-03 is **no new routing behavior, no new branches, no new awareness of subcommand semantics** — not byte-immutability of the file.
  - Allowed: appending `author_display_name: str | None = None` (or similar pass-through fields) to `route_message` / `handle_subcommand` signatures and forwarding them to `pf_dispatch`.
  - Still forbidden: any code that inspects, branches on, or transforms the new kwargs inside `command_router`.
  - Authorized retroactively for commit `af83958` (38-06 author_display_name plumbing) — the +10/-1 diff is purely additive forwarding with no behavioral change.

### Claude's Discretion
- Draft frontmatter field order and YAML formatting style (preserve readability — match existing player vault file style)
- Exact wording of the rejection message and the cancel-acknowledgement message (must contain the required information per D-07/D-10, but phrasing is open)
- Exception handling around Obsidian I/O failures (follow existing adapter conventions)
- Test file naming under `interfaces/discord/tests/` (recommended: `test_pathfinder_player_dialog.py` + extending `test_pathfinder_player_adapter.py`)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 38 spec & prior context
- `.planning/phases/38-pf2e-multi-step-onboarding-dialog/38-SPEC.md` — Locked requirements, boundaries, acceptance criteria — MUST read before planning
- `.planning/phases/37-pf2e-per-player-memory/37-CONTEXT.md` — Phase 37 design, especially line 129 originally specifying mid-dialog redirect behavior (now reinterpreted as rejection per SPEC)
- `.planning/REQUIREMENTS.md` §"Player Vault (Phase 37)" — PVL-01..PVL-07, especially PVL-07 (per-player isolation must extend to draft files)

### Routing & message dispatch
- `interfaces/discord/bot.py:486-501` — `_route_message` entrypoint
- `interfaces/discord/bot.py:658-699` — `on_message` thread guard (line 668-669) — DO NOT modify
- `interfaces/discord/discord_router_bridge.py` — Bridge module where `dialog_router` will be wired in
- `interfaces/discord/command_router.py:8-34` — `route_message` (`:`-prefix vs plain text branching) — DO NOT modify

### Player adapter & onboarding route
- `interfaces/discord/pathfinder_player_adapter.py:22` — `_VALID_STYLE_PRESETS` tuple (reuse for validation)
- `interfaces/discord/pathfinder_player_adapter.py:23-27` — `_USAGE` constant (the existing usage-string tuple — preserve byte-for-byte; the no-args branch wraps it for the legacy fallback path only when the operator explicitly invokes pipe syntax incorrectly)
- `interfaces/discord/pathfinder_player_adapter.py:30-71` — Existing `PlayerStartCommand` pipe-syntax path (preserve byte-for-byte for regression)
- `interfaces/discord/pathfinder_dispatch.py:111-126` — `PathfinderRequest` construction site (new `author_display_name` field plumbed in here)
- `interfaces/discord/pathfinder_dispatch.py:168-211` — Verb registration surface for `start`/`cancel`
- `interfaces/discord/bot.py:536` — `async def _persist_thread_id(thread_id: int) -> None` (reuse pattern for vault writes)
- `interfaces/discord/bot.py:708` — `bot = SentinelBot()` singleton (used by `PlayerCancelCommand` for `bot.get_channel(thread_id)` resolution)
- `modules/pathfinder/` — `/player/onboard` route (do NOT modify; reuse unchanged)
- `mnemosyne/pf2e/players/{slug}/profile.md` — Output artifact format (Phase 37)

### Test conventions
- `interfaces/discord/tests/test_pathfinder_player_adapter.py` — RED-test convention: `async def test_*`, `asyncio_mode = "auto"`, `AsyncMock` for `sentinel_client.post_to_module`, function-scope imports for RED-until-implemented
- `interfaces/discord/tests/conftest.py` — Discord stubs (no per-file stubs — Phase 33-01 decision)

### Obsidian REST API
- `https://coddingtonbear.github.io/obsidian-local-rest-api/` — Endpoints used: `GET /vault/{path}/` (list draft directory), `PUT /vault/{path}` (create/update draft), `DELETE /vault/{path}` (delete on completion/cancel), `GET /vault/{path}` (read draft frontmatter)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_VALID_STYLE_PRESETS` (pathfinder_player_adapter.py:22) — tuple of valid style strings; reuse in dialog validation
- `PathfinderCommand` / `PathfinderRequest` / `PathfinderResponse` (pathfinder_types) — existing command-class hierarchy; `PlayerCancelCommand` slots in
- `request.sentinel_client.post_to_module(...)` — async POST to module routes; reuse for `/player/onboard` call on completion
- `SENTINEL_THREAD_IDS` set + `_persist_thread_id` (bot.py:536) — thread tracking + persistence infrastructure already exists for new dialog threads
- `bot` singleton (bot.py:708) — used by `PlayerCancelCommand` for `bot.get_channel(thread_id)` resolution when cancel is issued from a non-thread channel
- Existing pipe-syntax `PlayerStartCommand.handle()` — pattern for assembling the four-field payload; the dialog completion path produces the same payload

### Established Patterns
- One PathfinderCommand subclass per verb (`pathfinder_player_adapter.py`) — `PlayerCancelCommand` follows this pattern
- Per-concern module split between `pathfinder_npc_basic_adapter.py` and `pathfinder_npc_rich_adapter.py` — supports the new `pathfinder_player_dialog.py` split from `pathfinder_player_adapter.py`
- Module-level constants for validation (e.g. `_VALID_STYLE_PRESETS`, `_NOTE_CLOSED_VOCAB`) — STEPS / QUESTIONS follow this pattern
- Vault as canonical state store for cross-restart persistence (Phase 37, foundry_event_log) — drafts under `_drafts/` follow this pattern
- RED tests use function-scope imports so collection fails until implementation lands; new tests for dialog/cancel follow this

### Integration Points
- `discord_router_bridge.route_message` — new `dialog_router.maybe_consume_as_answer()` call inserted before `command_router.route_message`
- `pathfinder_dispatch.py` `COMMANDS["player"]` dict — register `"cancel"` alongside existing `"start"`, `"note"`, etc.
- Obsidian REST client (existing in `sentinel_client` / `request.http_client`) — used for draft CRUD; same client/auth as the rest of the player vault
- Discord `discord.Thread.edit(archived=True)` — new API surface for completion/cancel archiving (no current usage in the bot)

</code_context>

<specifics>
## Specific Ideas

- Question wording (D-13) is the operator's preferred phrasing — ship it as-is.
- Rejection message must include the active dialog thread link via Discord `<#thread_id>` mention so the player can click through.
- Multi-draft handling (D-08) was an emergent constraint from the "yes, parallel dialogs allowed" decision in SPEC — surface every thread, not the first.
- Multi-draft cancel symmetry (D-17) is the cancel-side mirror of D-08: when N drafts exist, cancel ALL N rather than asking the user to pick one.

</specifics>

<deferred>
## Deferred Ideas

- 24h or operator-configured draft expiry sweep (out of scope by SPEC) — drafts persist until cancel; if accumulation becomes a problem, add a sweeper in a later phase.
- Slash-command Discord modal as an alternative onboarding UI — explicitly rejected in SPEC discussion; could revisit if Discord modals become preferable for accessibility.
- Configurable question text / i18n — locked out of scope; revisit only if multi-language users emerge.
- Editing an already-onboarded profile (`onboarded: true`) — different verb (likely `:pf player edit`) and different state machine; future phase.
- Pipe-syntax deprecation — keep it forever in v1, revisit when the dialog has been the dominant path for one full milestone.

</deferred>

---

*Phase: 38-pf2e-multi-step-onboarding-dialog*
*Context gathered: 2026-05-08*
*D-17 appended 2026-05-09 from checker feedback C1*

---

## Architecture Map (post-execution)

Appended 2026-05-09 at the end of Phase 38 execution (plan 38-09). Captures
the as-shipped wiring, file inventory, and test → requirement coverage map
for the multi-step onboarding dialog.

### New modules

| File | Role |
|------|------|
| `interfaces/discord/dialog_router.py` | Pre-router gate. Single entrypoint `maybe_consume_as_answer(...)` returns the bot's response on a draft hit, or `None` to fall through to `command_router.route_message`. Hit conditions per D-02: no `:` prefix AND channel is a `discord.Thread` AND a draft file exists at `mnemosyne/pf2e/players/_drafts/{thread.id}-{user_id}.md`. |
| `interfaces/discord/pathfinder_player_dialog.py` | Dialog state machine. Owns question strings (`QUESTIONS` dict per D-13), step ordering (`STEPS` tuple), draft frontmatter read/write, `start_dialog(...)`, `consume_as_answer(...)`, `cancel_dialog(...)`. Validates style preset against `_VALID_STYLE_PRESETS` re-imported from `pathfinder_player_adapter` (D-14). |

### Modified modules (additive only)

| File | Change | Decision ref |
|------|--------|--------------|
| `interfaces/discord/discord_router_bridge.py` | Wires `dialog_router.maybe_consume_as_answer` ahead of `command_router.route_message`. | D-01 |
| `interfaces/discord/command_router.py` | Additive `author_display_name: str \| None = None` pass-through kwarg threaded to `pf_dispatch`. No new branches, no inspection of the value. | D-03 + D-18 |
| `interfaces/discord/bot.py` | `_pf_dispatch` gains `author_display_name` kwarg; `on_message` callsite populates it from `message.author.display_name`. The thread guard at `bot.py:668` is byte-unchanged. | D-04 |
| `interfaces/discord/pathfinder_dispatch.py` | Registers `PlayerCancelCommand` alongside `PlayerStartCommand` (D-16); plumbs `author_display_name` into `PathfinderRequest`. | D-16 |
| `interfaces/discord/pathfinder_bridge.py` | Forwards `author_display_name` from dispatch into the request envelope. | D-16 |
| `interfaces/discord/pathfinder_types.py` | Adds `author_display_name: str \| None` field to `PathfinderRequest`. | D-16 |
| `interfaces/discord/pathfinder_player_adapter.py` | `PlayerStartCommand` gains a no-args branch that calls `pathfinder_player_dialog.start_dialog(...)`; pipe-syntax branch preserved byte-for-byte. New `PlayerCancelCommand` next to it. Mid-dialog rejection guard via `reject_if_draft_open(...)` lookup over `_drafts/`. | D-15, D-16, D-05..D-08 |

### Untouched (proven by `git diff --stat`)

- `modules/pathfinder/` — zero diff. The `/player/onboard` route is reused unchanged.
- `interfaces/discord/bot.py:668` `on_message` thread guard — byte-unchanged.

### Vault layout addition

```
mnemosyne/pf2e/players/_drafts/{thread_id}-{user_id}.md
```

Frontmatter fields: `step`, `thread_id`, `user_id`, `character_name?`,
`preferred_name?`, `started_at`. Created by `start_dialog`, mutated by
`consume_as_answer`, deleted by completion or `cancel_dialog`. Per-player
isolation invariant from PVL-07 extends to these draft files (the slug
prefix `_drafts/` lives inside the player vault hierarchy).

### Routing flow

```
Discord on_message
  └─ bot._route_message
       └─ discord_router_bridge.route_message
            ├─ dialog_router.maybe_consume_as_answer
            │     ├─ HIT  → consume_as_answer (advance step or complete → POST /player/onboard)
            │     └─ MISS → fall through ↓
            └─ command_router.route_message
                 └─ pf_dispatch
                      ├─ PlayerStartCommand
                      │     ├─ no args → pathfinder_player_dialog.start_dialog (creates thread + draft)
                      │     └─ pipe args → /player/onboard direct (one-shot, byte-for-byte preserved)
                      ├─ PlayerCancelCommand → pathfinder_player_dialog.cancel_dialog (multi-draft symmetric per D-17)
                      └─ other player verbs → reject_if_draft_open guard, then route as before
```

### Test → SPEC requirement coverage

| SPEC req | Test file(s) |
|---------|--------------|
| 1. Thread-hosted dialog | `tests/test_pathfinder_player_dialog.py`, `tests/test_phase38_integration.py` |
| 2. Plain-text answer capture | `tests/test_dialog_router.py`, `tests/test_pathfinder_player_dialog.py` |
| 3. Vault-backed draft persistence | `tests/test_pathfinder_player_dialog.py`, `tests/test_phase38_integration.py` |
| 4. Completion calls `/player/onboard` | `tests/test_pathfinder_player_dialog.py`, `tests/test_phase38_integration.py` |
| 5. Mid-dialog command rejection | `tests/test_pathfinder_player_adapter.py`, `tests/test_phase38_integration.py` |
| 6. Cancel verb (with + without draft, multi-draft) | `tests/test_pathfinder_player_adapter.py`, `tests/test_pathfinder_player_dialog.py` |
| 7. Restart-start resume | `tests/test_pathfinder_player_dialog.py` |
| 10. RED-before-production ordering | Verified by `git log --diff-filter=A` — see 38-09-SUMMARY.md |

### Test file inventory

- `tests/test_dialog_router.py` (NEW, 11.5K)
- `tests/test_pathfinder_player_dialog.py` (NEW, 25.5K)
- `tests/test_phase38_integration.py` (NEW acceptance suite, 23.3K)
- `tests/test_pathfinder_player_adapter.py` (MODIFIED — added cancel + rejection cases, 38.5K)
- `tests/test_pathfinder_player_dispatch.py` (UNCHANGED reference, 2.2K)

