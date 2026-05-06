# Sentinel of Mnemosyne

A self-hosted, containerized AI assistant platform built for personal use. The Sentinel wires together a local AI engine (LM Studio on a Mac Mini), an Obsidian vault as persistent memory, and pluggable interface/module containers — so the same engine can serve as a DM co-pilot, music practice journal, finance tracker, or autonomous stock trader depending on what you attach to it.

**Core value:** A message goes in, an AI response that knows your history comes back — and what mattered gets written to Obsidian so the next conversation starts smarter.

---

## Architecture at a Glance

```
[ Interface Container ]     (Discord, Apple Messages, ...)
         |
         | HTTP POST /message  (X-Sentinel-Key header)
         v
[ Sentinel Core ]           (Python/FastAPI)
    |               |                   |
    | LiteLLM       | httpx proxy       | REST API
    v               v                   v
[ AI Providers ]  [ Module Containers ] [ Obsidian Local REST API ]
  LM Studio         (v0.50: Pathfinder,   Mnemosyne vault
  Claude API         Music/Finance next)
  Ollama (future)

[ Pi Harness ] — optional, ./sentinel.sh --pi, scoped to v0.7 (Coder module)
```

**Request flow:** Sentinel Core calls LiteLLM directly for all chat. The Pi harness is NOT in the default message path — it is an optional coding tool started only with the `--pi` flag and scoped to the v0.7 Coder module.

All components are Docker containers. LM Studio runs natively on a Mac Mini. The Obsidian vault is a local folder on your Mac — plain markdown files you always own.

---

## What It Does

The Sentinel is a pluggable AI assistant you can talk to over Discord, Apple Messages, or any interface you drop in as a Docker container. It remembers everything in an Obsidian vault. Modules extend it with specific capabilities — a Pathfinder 2e DM assistant, a music practice tracker, a personal finance ledger, an autonomous stock trader.

The design goal is maximum flexibility with a stable, narrow core API. You add a module by dropping in a Docker Compose fragment. You add an interface the same way. The core never changes.

---

## Modules

| Module | Purpose | Status |
|---|---|---|
| Core | Routing, context, Obsidian writes | Working (v0.50) |
| Pathfinder 2e DM | NPC management, dialogue, session notes, harvest, rules RAG, ingest | Working (v0.50) |
| Music Lesson Tracker | Practice logs, chord ideas, progress | Planned v0.6 |
| Coder Interface | AI-assisted module development (uses Pi harness) | Planned v0.7 |
| Personal Finance | OFX import, spending analysis, budgets | Planned v0.8 |
| Stock Trader | Research + rule-constrained paper/live trading | Planned v0.9 |
| Media Discovery | ListenBrainz + Discogs wantlist integration | Future |

---

## Prerequisites

- **Docker Desktop** (Mac) or Docker + Docker Compose on Linux
- **LM Studio** running on a Mac Mini (or any machine on your local network) with a model loaded and the local server started
- **Obsidian** with the [Local REST API community plugin](https://github.com/coddingtonbear/obsidian-local-rest-api) installed and enabled
- A Discord bot token if using the Discord interface


### Operator Setup — Sentinel Persona File

Before first run, the operator must create `sentinel/persona.md` in the Obsidian Vault. The Sentinel reads this file on every message to source its system persona prompt; it lets the operator tune voice, tone, and behavior without redeploying.

**Startup contract:**
- If Obsidian is reachable AND `sentinel/persona.md` is missing (404), `sentinel-core` will fail to start with a clear error. This is intentional — a reachable vault without a persona file is an operator setup error.
- If Obsidian is unreachable at startup, the probe is skipped and `sentinel-core` starts in graceful-degrade mode using the hardcoded fallback persona.
- Per-message: if the vault read returns empty or fails transiently, the processor falls back to the hardcoded persona and logs a WARN — user traffic is never blocked over a vault edit.

**Suggested seed content** (matches the hardcoded fallback in `sentinel-core/app/services/message_processing.py` → `MessageProcessor._FALLBACK_PERSONA`):

```markdown
You are the Sentinel — the user's 2nd brain. You maintain their context via an
Obsidian vault that the system writes to automatically; the user does not need
to manage it.

Respond like a friend who has been listening. When the user shares a fact,
milestone, status update, or reflection, acknowledge it naturally and briefly
— usually one or two sentences. Ask a relevant follow-up only if it would feel
natural. Match their tone and length.

Never lecture the user about how to file, organize, link, tag, document,
summarize, follow up on, plan, or process information. The system handles
persistence and structure. You only respond. Do not produce numbered
procedural how-to lists unless the user explicitly asks for instructions.

Do not describe internal tools, system internals, or implementation details.
```

Edit the file in Obsidian to change voice; `sentinel-core` picks up the change on the next message.

---

## Quick Start

> This gets you a working AI response via `curl`. Full interface setup comes later.

**1. Clone the repo**
```bash
git clone https://github.com/The-Artificer-of-Ciphers-LLC/sentinel-of-mnemosyne.git
cd sentinel-of-mnemosyne
```

**2. Create your secret files**

Secrets live in the `secrets/` directory as individual files — one file per secret. See [secrets/README.md](secrets/README.md) for the full list and why this is safer than `.env`.

```bash
# Required always
echo -n "your-obsidian-api-key" > secrets/obsidian_api_key
echo -n "$(openssl rand -hex 32)" > secrets/sentinel_api_key

# Required for Discord interface
echo -n "your-discord-bot-token" > secrets/discord_bot_token

# Optional: Claude API fallback
echo -n "your-anthropic-key" > secrets/anthropic_api_key
```

**3. Configure non-secret settings**
```bash
cp .env.example .env
# Edit .env — set LMSTUDIO_BASE_URL to your Mac Mini IP, adjust MODEL_NAME if needed
# .env contains only non-secret config (URLs, log levels, modes)
```

**4. Start LM Studio on your Mac Mini**
- Open LM Studio → Local Server → Start server
- Note the IP address and port (default: `1234`)
- Make sure a model is loaded

**5. Start containers**
```bash
# Core only
./sentinel.sh up -d

# Core + Discord
./sentinel.sh --discord up -d

# Core + Discord + Pathfinder module (v0.50)
./sentinel.sh --discord --pathfinder up -d
```

**6. Test it**
```bash
SENTINEL_KEY=$(cat secrets/sentinel_api_key)
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -H "X-Sentinel-Key: $SENTINEL_KEY" \
  -d '{"id":"test-001","source":"curl","user_id":"you","channel_id":"test","timestamp":"2026-04-06T12:00:00Z","content":"Hello, are you there?","attachments":[],"metadata":{}}'
```

You should get an AI response back.

---

## sentinel.sh Flags

```
./sentinel.sh [flags] <docker compose args>

Flags:
  --discord      Start Discord bot interface
  --pi           Start Pi harness (optional coding tool)
  --pathfinder   Start Pathfinder 2e DM module (v0.50, shipped)
  --music        Start Music Lesson Tracker module (v0.6, planned)
  --finance      Start Personal Finance module (v0.8, planned)
  --trader       Start Stock Trader module (v0.9, planned)
  --coder        Start Coder Interface module (v0.7, planned)

Examples:
  ./sentinel.sh up -d                          # Core only
  ./sentinel.sh --discord up -d                # Core + Discord
  ./sentinel.sh --discord --pathfinder up -d   # Core + Discord + Pathfinder
  ./sentinel.sh down                           # Stop all services
```

---

## Adding an Interface

Each interface is a Docker Compose override file. To add Discord:

```bash
# Create secrets/discord_bot_token with your bot token, then:
./sentinel.sh --discord up -d
```

See `interfaces/discord/` for setup details.

---

## Adding a Module

Each module ships as a Docker Compose override file. To add a module:

```bash
./sentinel.sh --discord --pathfinder up -d
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to build your own module.

---

## Discord Commands

The bot responds to `/sen <message>` in allowed channels.

To use a subcommand, prefix your message with `:`:

| Command | What it does |
|---|---|
| `/sen :help` | List all subcommands |
| `/sen :capture <text>` | Capture text to Obsidian inbox |
| `/sen :next` | What to work on next based on your goals |
| `/sen :health` | Vault health check |
| `/sen :goals` | Show current active goals |
| `/sen :reminders` | Show current time-bound reminders |
| `/sen :ralph` | Batch process inbox queue |
| `/sen :pipeline` | Run full 6 Rs processing pipeline |
| `/sen :reweave` | Backward pass to update older notes |
| `/sen :check` | Validate schema compliance |
| `/sen :rethink` | Review observations and tensions |
| `/sen :refactor` | Suggest vault restructuring |
| `/sen :tasks` | Show task queue |
| `/sen :stats` | Vault metrics |
| `/sen :graph` | Graph analysis |
| `/sen :learn <topic>` | Research a topic and capture to vault |
| `/sen :remember <observation>` | Capture a methodology observation |
| `/sen :revisit <note>` | Revisit and update a note |
| `/sen :connect <note>` | Find connections for a note |
| `/sen :review <note>` | Verify note quality |
| `/sen :seed <content>` | Drop raw content into inbox/ |
| `/sen :plugin:help` | List plugin commands |
| `/sen :plugin:health` | Plugin health check |
| `/sen :plugin:architect` | Architecture review |

Any reply in a Sentinel thread also triggers the AI — no slash command needed.

---

## Repository Structure

```
sentinel-of-mnemosyne/
├── docker-compose.yml          # Core + includes for all services (Compose v2.20+)
├── .env.example                # Non-secret configuration template
├── sentinel.sh                 # docker compose wrapper with --discord, --pi, etc. flags
├── sentinel-core/              # Python/FastAPI core container
│   ├── app/                    # Application code
│   │   ├── clients/            # LiteLLM provider, Obsidian client
│   │   ├── routes/             # /message, /modules, /status, /health
│   │   └── services/           # ProviderRouter, InjectionFilter, OutputScanner
│   └── compose.yml
├── pi-harness/                 # Pi coding-agent container (optional — --pi flag)
├── interfaces/
│   ├── discord/                # Discord bot (/sen command)
│   └── messages/               # Apple Messages bridge (Mac-native component)
├── modules/                    # Module containers (Pathfinder shipped in v0.50)
├── skills/                     # Skill files for module dispatch
├── secrets/                    # Secret files (gitignored — one file per secret)
├── security/                   # Security tooling
├── shared/                     # Shared Python client libraries
├── mnemosyne/                  # Obsidian vault (gitignored — your data stays yours)
└── docs/
    ├── PRD-Sentinel-of-Mnemosyne.md
    └── ARCHITECTURE-Core.md
```

---

## Configuration Reference

Non-secret configuration lives in `.env`. See `.env.example` for the full list with descriptions. Secret values live in `secrets/` — see [secrets/README.md](secrets/README.md).

| Variable | Purpose |
|---|---|
| `LMSTUDIO_BASE_URL` | LM Studio server URL (e.g., `http://192.168.1.x:1234/v1`) |
| `MODEL_NAME` | Model identifier for LiteLLM calls (e.g., `llama-3.2-8b-instruct`) |
| `AI_PROVIDER` | Active AI backend: `lmstudio` (default), `claude`, `ollama`, `llamacpp` |
| `AI_FALLBACK_PROVIDER` | Fallback on connectivity failure: `claude` or `none` (default) |
| `ANTHROPIC_API_KEY` | In `secrets/anthropic_api_key` — required when provider is `claude` |
| `CLAUDE_MODEL` | Claude model ID (default: `claude-haiku-4-5`) |
| `OBSIDIAN_API_URL` | URL for the Obsidian Local REST API plugin |
| `OBSIDIAN_API_KEY` | In `secrets/obsidian_api_key` — from Obsidian plugin settings |
| `SENTINEL_API_KEY` | In `secrets/sentinel_api_key` — shared secret for interface auth |
| `DISCORD_ALLOWED_CHANNELS` | Comma-separated channel IDs (empty = all channels) |
| `LOG_LEVEL` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `PI_MODEL` | Model name for Pi harness — only needed with `--pi` flag |
| `PI_HARNESS_URL` | Pi harness address — only needed with `--pi` flag |

---

## Documentation

- [Installation Guide (v0.50)](docs/INSTALLATION-v0.50.md) — operator setup and validation
- [Product Requirements Document](docs/PRD-Sentinel-of-Mnemosyne.md) — vision, modules, milestones
- [Core Architecture](docs/ARCHITECTURE-Core.md) — technical decisions, API specs, Docker layout
- [Contributing Guide](CONTRIBUTING.md) — how to build modules and interfaces
- [Secrets Setup](secrets/README.md) — all secret files and how to create them

---

## Status

This project is at **v0.50**.

Shipped and validated:
- Sentinel Core route/context/startup reliability improvements
- LiteLLM-direct provider path with fallback support
- Discord interface
- Pathfinder module registration + proxy execution
- Runtime health/status probing
- Note classify/inbox/sweep flows

Current baseline:
- Automated tests: 279 passed, 12 skipped
- Live smoke checks: `/health`, `/status`, `/modules`, `/note/classify`, `/message`

Core architecture: LiteLLM-direct chat, with optional Pi harness (`--pi`) for future coder workflows.

---

## License

MIT — see LICENSE file.

*The Sentinel watches. Mnemosyne remembers.*
