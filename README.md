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
  LM Studio         (v1.1.2: Pathfinder,  Mnemosyne vault
  Claude API         Music/Finance next)
  Ollama (future)

```

**Request flow:** Sentinel Core calls LiteLLM directly for all chat.

All components are Docker containers. LM Studio runs natively on a Mac Mini. The Obsidian vault is a local folder on your Mac — plain markdown files you always own.

---

## What It Does

The Sentinel is a pluggable AI assistant you can talk to over Discord, Apple Messages, or any interface you drop in as a Docker container. It remembers everything in an Obsidian vault. Modules extend it with specific capabilities — a Pathfinder 2e DM assistant, a music practice tracker, a personal finance ledger, an autonomous stock trader.

The design goal is maximum flexibility with a stable, narrow core API. You add a module by dropping in a Docker Compose fragment. You add an interface the same way. The core never changes.

---

## Modules

| Module | Purpose | Status |
|---|---|---|
| Core | Routing, context, Obsidian writes | Working (Sentinel Core v0.51.1) |
| Pathfinder 2e DM | NPC management, dialogue, session notes, harvest, rules RAG, ingest | Working (Pathfinder module v1.1.2) |
| Music Lesson Tracker | Practice logs, chord ideas, progress | Planned v0.6 |
| Coder Interface | AI-assisted module development | Planned v0.7 |
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

The stack runs entirely in Docker Compose — pull the sample files, populate your secrets, and `docker compose up -d`. For the full walkthrough including environment variables, secret file setup, and validation steps, see [docs/how-to/install.md](docs/how-to/install.md).

For the complete shipped capability list, see [docs/reference/features.md](docs/reference/features.md).

---

## sentinel.sh Flags

```
./sentinel.sh [flags] <docker compose args>

Flags:
  --discord      Start Discord bot interface
  --pf2e         Start Pathfinder 2e DM module (v1.1.2, shipped)
  --music        Start Music Lesson Tracker module (v0.6, planned)
  --finance      Start Personal Finance module (v0.8, planned)
  --trader       Start Stock Trader module (v0.9, planned)
  --coder        Start Coder Interface module (v0.7, planned)

Examples:
  ./sentinel.sh up -d                          # Core only
  ./sentinel.sh --discord up -d                # Core + Discord
  ./sentinel.sh --discord --pf2e up -d   # Core + Discord + Pathfinder
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
./sentinel.sh --discord --pf2e up -d
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to build your own module.

---

## Discord Commands

The bot responds to `/sen <message>` in allowed channels. Each
invocation creates a public thread; replies inside the thread continue
the conversation. Subcommands are prefixed with `:` inside the thread.

**Quick reference** — most common verbs:

| Command | What it does |
|---|---|
| `/sen <message>` | Free-form chat with the Sentinel |
| `/sen :help` | List all subcommands grouped by category |
| `/sen :capture <text>` | Capture an insight to `inbox/` for processing |
| `/sen :next` | What should I work on next? |
| `/sen :stats` | Vault metrics (note count, orphans, link density) |
| `/sen :pf <noun> <verb> ...` | Pathfinder 2e module — see Discord Commands reference |

**Full reference** — every shipped verb, every example response,
including the Pathfinder 2e module's eight noun namespaces (`npc`,
`harvest`, `rule`, `session`, `ingest`, `cartosia`, `foundry`,
`player`):

→ [docs/reference/discord-commands.md](docs/reference/discord-commands.md)

Any reply in a Sentinel thread also triggers the AI — no slash command
needed.

---

## Repository Structure

```
sentinel-of-mnemosyne/
├── docker-compose.yml          # Core + includes for all services (Compose v2.20+)
├── .env.example                # Non-secret configuration template
├── sentinel.sh                 # docker compose wrapper with --discord, --pf2e, etc. flags
├── sentinel-core/              # Python/FastAPI core container
│   ├── app/                    # Application code
│   │   ├── clients/            # LiteLLM provider, Obsidian client
│   │   ├── routes/             # /message, /modules, /status, /health
│   │   └── services/           # ProviderRouter, InjectionFilter, OutputScanner
│   └── compose.yml
├── interfaces/
│   ├── discord/                # Discord bot (/sen command)
│   └── messages/               # Apple Messages bridge (Mac-native component)
├── modules/                    # Module containers (Pathfinder module currently v1.1.2)
├── skills/                     # Skill files for module dispatch
├── secrets/                    # Secret files (gitignored — one file per secret)
├── security/                   # Security tooling
├── shared/                     # Shared Python client libraries
├── mnemosyne/                  # Obsidian vault (gitignored — your data stays yours)
└── docs/
    ├── index.md                    # Documentation hub (start here)
    ├── tutorial/                   # Learning-by-doing guides
    ├── how-to/                     # Task-oriented guides
    ├── reference/                  # Technical reference
    ├── explanation/                # Background and architecture
    ├── adr/                        # Architectural decision records
    └── PRD-Sentinel-of-Mnemosyne.md
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

---

## Documentation

Start here: [Documentation hub](docs/index.md)

- [Documentation hub](docs/index.md) — Diataxis-organised entry point for all docs
- [Installation Guide](docs/how-to/install.md) — operator setup and validation
- [Feature Reference](docs/reference/features.md) — current shipped and planned capabilities
- [Discord Commands](docs/reference/discord-commands.md) — every `/sen` command with examples
- [Obsidian Vault Layout](docs/reference/obsidian-vault.md) — vault structure and conventions
- [Architecture](docs/explanation/architecture.md) — technical decisions, API specs, Docker layout
- [Product Requirements Document](docs/PRD-Sentinel-of-Mnemosyne.md) — vision, modules, milestones
- [Contributing Guide](CONTRIBUTING.md) — how to build modules and interfaces
- [Secrets Setup](secrets/README.md) — all secret files and how to create them

---

## Status

This repo currently ships **Sentinel Core v0.51.1**, **Discord interface v0.2.1**, and **Pathfinder module v1.1.2**.

Module versions are independent from Sentinel Core versions.

Shipped and validated:
- Sentinel Core route/context/startup reliability improvements
- LiteLLM-direct provider path with fallback support
- Discord interface
- Pathfinder module registration + proxy execution
- Runtime health/status probing
- Note classify/inbox/sweep flows

Current baseline:
- Automated tests: component suites pass in CI before release
- Live smoke checks: `/health`, `/status`, `/modules`, `/note/classify`, `/message`

Core architecture: LiteLLM-direct chat via ProviderRouter (LM Studio, Claude, Ollama, llama.cpp).

---

## License

MIT — see LICENSE file.

*The Sentinel watches. Mnemosyne remembers.*
