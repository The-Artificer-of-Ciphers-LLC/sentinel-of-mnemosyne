# Pathfinder 2e Module (`pf2e-module`)

Pathfinder 2e DM co-pilot module for the Sentinel of Mnemosyne. Provides
NPC management, dialogue, monster harvesting, rules lookups, session
notes, Foundry VTT event ingest, and per-player memory — all backed by
your Obsidian vault.

> **For Discord users:** see [`docs/USER-GUIDE.md`](../../docs/USER-GUIDE.md)
> for end-user command reference. This README documents the module
> internals: routes, persistence layout, deployment, and developer hooks.

## Features

- **NPC CRUD + outputs** (Phase 29-30) — create, update, relate, show,
  bulk-import, and export NPCs as Foundry actor JSON, Midjourney prompt,
  stat block, or printable PDF.
- **Dialogue engine** (Phase 31) — in-character NPC replies grounded in
  Obsidian profiles, with persistent mood state and multi-NPC scenes.
- **Monster harvesting** (Phase 32) — components, Medicine DCs,
  craftable items with Crafting DCs, batched encounter reports.
- **Rules engine** (Phase 33) — sourced PF2e Remaster rulings with
  embedding-based retrieval, deterministic reuse threshold, and
  PF1/pre-Remaster decline.
- **Session notes** (Phase 34) — auto-captured session recap on
  `/pf session end` with NPC/location wiki-links and timestamped event
  log.
- **Foundry VTT event ingest** (Phase 35-36) — pull NPC actor JSON from
  the Foundry world, post chat events to Discord, hook dice rolls into
  hit/miss interpretations.
- **Per-player memory** (Phase 37) — every Discord user gets an isolated
  vault namespace at `players/{slug}/` with note/ask/npc/recall/todo/
  style/canonize verbs. Foundry chat logs project deterministically into
  per-player chat-maps and `## Foundry Chat History` sections on NPC
  notes.

## Quick Start

```bash
# From repo root — bring up the full stack with the pf2e profile:
./sentinel.sh --discord --pf2e up -d

# Verify the module registered with sentinel-core:
curl -s -H "X-Sentinel-Key: $(cat secrets/sentinel_api_key)" \
     http://localhost:8000/modules | jq '.[0].routes | length'
# → 29 (as of v0.5)

# In Discord, the bot now responds to :pf <noun> <verb> commands.
# Onboard yourself for per-player memory:
:pf player start Kael Stormblade | Kael | Tactician
```

## Architecture

The module is a FastAPI app that registers with sentinel-core's module
gateway on startup (`POST /modules/register`) and serves requests via
the gateway's reverse proxy at `/modules/pathfinder/{path}`.

```
Discord user
    │ :pf player start ...
    ▼
discord container (interfaces/discord)
    │ pathfinder_dispatch → pathfinder_player_adapter.PlayerStartCommand
    │ POST /modules/pathfinder/player/onboard (X-Sentinel-Key)
    ▼
sentinel-core (proxy)
    │ forwards to http://pf2e-module:8000/player/onboard
    ▼
pf2e-module (this module)
    │ routes/player.py → orchestrator → player_vault_store
    │ PUT /vault/mnemosyne/pf2e/players/{slug}/profile.md (Obsidian REST)
    ▼
Obsidian (host)
    └─ profile.md persisted in ~/2ndbrain
```

For the full architecture map see
[`.planning/phases/37-pf2e-per-player-memory/37-CONTEXT.md`](../../.planning/phases/37-pf2e-per-player-memory/37-CONTEXT.md)
section "Architecture Map".

## Vault Layout

All module writes go under `mnemosyne/pf2e/` in the configured Obsidian
vault. The module never reads or writes outside this prefix.

```
mnemosyne/pf2e/
├── npcs/{npc_slug}.md              # global NPC profiles (GM-owned, :npc verbs)
├── rulings/{ruling_id}.md          # PF2e rules cache (Phase 33)
├── sessions/YYYY-MM-DD.md          # session notes (Phase 34)
├── sessions/foundry-chat/          # Foundry chat import reports (Phase 35-36)
└── players/                        # per-player memory (Phase 37)
    ├── _aliases.json               # optional user_id → slug overrides
    ├── {player_slug}.md            # chat-map (Foundry projection target)
    └── {player_slug}/
        ├── profile.md              # onboarding output
        ├── inbox.md                # :pf player note appends
        ├── questions.md            # :pf player ask appends
        ├── canonization.md         # :pf player canonize appends
        ├── todo.md                 # :pf player todo appends
        └── npcs/{npc_slug}.md      # per-player NPC knowledge (PVL-07)
```

The slug `{player_slug}` is derived deterministically from the Discord
user_id. The optional `_aliases.json` file (underscore-prefixed —
verified compatible with the Obsidian REST API in Phase 37 plan 37-05)
maps `user_id → readable_slug` for operators who want stable,
human-friendly directory names.

## API Reference

The module exposes 29 routes. The Phase 37 additions are listed below;
see `app/main.py:REGISTRATION_PAYLOAD` for the complete list.

### Per-player memory routes

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/player/onboard` | Create `profile.md` with `onboarded: true` |
| POST | `/player/note` | Append to `inbox.md` |
| POST | `/player/ask` | Append to `questions.md` (store-only, no LLM) |
| POST | `/player/npc` | Per-player NPC knowledge |
| POST | `/player/todo` | Append to `todo.md` |
| POST | `/player/recall` | Deterministic keyword + recency recall |
| POST | `/player/canonize` | Yellow → green/red rule outcome with provenance |
| POST | `/player/style` | Set / list style preset |
| GET  | `/player/state` | Read profile state (orchestrator gate / debug) |

All POST routes accept JSON. `/player/onboard` requires four fields:
`user_id`, `character_name`, `preferred_name`, `style_preset` (one of
`Tactician`, `Lorekeeper`, `Cheerleader`, `Rules-Lawyer Lite`). Any
missing field returns `422` — the Discord adapter
(`PlayerStartCommand`) parses pipe-separated args from the user's
message and assembles the full payload before posting.

### Foundry chat memory projection

```
POST /foundry/messages/import
{
  "inbox_dir": "/vault/inbox",
  "dry_run": false,
  "project_player_memory": true,
  "project_npc_history": true
}
```

Projects each Foundry chat record into the per-player chat-map
(`players/{slug}.md`) and appends NPC-attributed lines to
`## Foundry Chat History` on existing NPC notes. Idempotent per record
per target via dedupe state at
`<inbox_dir>/.foundry_chat_import_state.json`.

The two boolean projection flags default to `true`; set either to
`false` to skip its projection while keeping the other. `dry_run: true`
returns metrics (`player_updates`, `npc_updates`, `unmatched_speakers`,
`deduped`) without writing to the vault.

## Configuration

Environment variables consumed by the module (loaded from `.env` at
repo root via `compose.yml`'s `env_file`):

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `OBSIDIAN_BASE_URL` | yes | — | Obsidian Local REST API base URL |
| `OBSIDIAN_API_KEY` | yes | — | Obsidian REST bearer token |
| `LITELLM_MODEL` | yes | — | Default model for dialogue/rules/etc |
| `LITELLM_API_BASE` | yes | — | LM Studio (or other OpenAI-compatible) base URL |
| `OPENAI_API_KEY` | yes | `lmstudio` | Required by LiteLLM; any non-empty string works for LM Studio |
| `SESSION_AUTO_RECAP` | no | `false` | Auto-trigger session recap on `:pf session end` |
| `SESSION_TZ` | no | `America/New_York` | Timezone for session note dates |
| `SESSION_RECAP_MODEL` | no | falls back to `LITELLM_MODEL` | Override model for recap generation |
| `FOUNDRY_NARRATION_MODEL` | no | falls back to `LITELLM_MODEL` | Override model for Foundry narration |
| `DISCORD_BOT_INTERNAL_URL` | yes | `http://discord-bot:8001` | Internal notification endpoint |

The Obsidian vault is mounted into the container at `/vault` for
filesystem-backed import flows (Foundry LevelDB chat extraction). The
mount is **read-write** because Foundry's LevelDB needs to create lock
files during the export; the module otherwise only reads.

The `X-Sentinel-Key` shared secret authenticates incoming requests at
sentinel-core; the module trusts the proxy and does not re-validate.

## Development

The module uses `uv` for dependency management and `pytest` for tests.

```bash
# Install dependencies (from this directory):
cd modules/pathfinder
uv sync

# Run unit + integration tests:
uv run pytest tests/ -q

# Run a single phase's regression suite:
uv run pytest tests/test_phase37_integration.py -v

# Run live UAT against the running stack (requires LM Studio + Obsidian):
LIVE_TEST=1 \
  UAT_SENTINEL_KEY="$(cat ../../secrets/sentinel_api_key)" \
  UAT_OBSIDIAN_KEY="$(cat ../../secrets/obsidian_api_key)" \
  uv run --project ../../interfaces/discord \
    python ../../scripts/uat_player_start.py
```

### Adding a new Python dependency

The Dockerfile pins runtime dependencies separately from `pyproject.toml`
to keep the image layer cache stable. **You must dual-ship** every new
dependency: add it to both `pyproject.toml` and the `RUN pip install`
block in `Dockerfile`. Forgetting either causes a `ModuleNotFoundError`
restart loop on the next `docker compose up` (project memory:
`project_dockerfile_deps`).

### Adding a new route

1. Add the handler under `app/routes/`. Mirror the pattern in
   `app/routes/npc.py` — `APIRouter`, module-singleton injection
   (`obsidian = None`, set in `main.py` lifespan), Pydantic request
   model, behavioral test in `tests/test_<route>.py`.
2. Append the route to `REGISTRATION_PAYLOAD` in `app/main.py` so
   sentinel-core proxies it.
3. Wire `app.include_router(<router>)` in `main.py`'s lifespan setup.
4. If the route is user-facing via Discord, add a `PathfinderCommand`
   subclass under `interfaces/discord/pathfinder_<noun>_adapter.py` and
   register it in `pathfinder_dispatch.py`'s `COMMANDS` dict.

> **Phase 37 lesson** (CONTEXT.md `PHASE37-A`): when adding a Discord
> verb that wraps a route, write **both** an adapter unit test that
> mocks `post_to_module` AND a live UAT script that exercises the route
> through the sentinel-core proxy. Adapter tests with mocked HTTP cannot
> detect contract drift between the adapter's payload and the route's
> Pydantic model.

### Required behaviors

The module's contract with the rest of Sentinel:

- **Vault-only persistence** — the module never opens a database, never
  writes to disk outside `/vault` (the Obsidian mount), and never
  reads/writes Obsidian notes outside `mnemosyne/pf2e/`.
- **Idempotent imports** — Foundry chat imports must produce zero new
  writes when re-run on the same source (FCM-04). Dedupe state is
  in-place at `.foundry_chat_import_state.json`, never in a parallel
  store.
- **Per-player isolation** — `:pf player <verb>` writes are gated by a
  slug-prefix check in `player_vault_store`. The store rejects any path
  not prefixed with `mnemosyne/pf2e/players/{slug}/` regardless of how
  the route assembled it.
- **Behavioral tests only** — per project CLAUDE.md, tests must call the
  function under test and assert on observable behavior. No source-grep,
  no vacuous truths, no echo-chamber assertions.

## Roadmap

- **Phase 38** (queued) — Multi-step Discord onboarding dialog. Replaces
  the pipe-separated one-shot syntax for `:pf player start` with a
  stateful conversational flow. Pipe-args remain supported as a power-user
  shortcut. See `.planning/ROADMAP.md` Phase 38.
- Future PF2E milestones live in `docs/plans/PF2E-Future-Roadmap-Prioritized.md`.

## See Also

- [`docs/USER-GUIDE.md`](../../docs/USER-GUIDE.md) — Discord command
  reference for end users.
- [`docs/foundry-setup.md`](../../docs/foundry-setup.md) — Foundry VTT
  module installation + Forge/Tailscale connectivity options.
- [`docs/ARCHITECTURE-Core.md`](../../docs/ARCHITECTURE-Core.md) —
  Sentinel Core architecture (module gateway pattern, Path B).
- [`CONTEXT.md`](../../CONTEXT.md) — domain glossary and known
  session-issues log (`session_issues` section).
- [`.planning/REQUIREMENTS.md`](../../.planning/REQUIREMENTS.md) — full
  PVL-* / FCM-* / NPC-* / OUT-* / DLG-* / HRV-* / RUL-* / SES-* /
  FVT-* requirement IDs.
