# Sentinel of Mnemosyne

A self-hosted, containerized AI assistant platform built on open, composable components. You bring your own AI, your own memory, and your own interface — the Sentinel wires them together.

**The brain:** [pi-mono coding-agent](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent) — AI execution, tool use, skill dispatch.
**The heart:** [Obsidian](https://obsidian.md) vault (Mnemosyne) — persistent knowledge as human-readable markdown.
**The nervous system:** Sentinel Core — routes messages, retrieves context, orchestrates writes.

---

## What It Does

The Sentinel is a pluggable AI assistant you can talk to over Discord, Apple Messages, or any interface you drop in as a Docker container. It remembers everything in an Obsidian vault. Modules extend it with specific capabilities — a Pathfinder 2e DM assistant, a music practice tracker, a personal finance ledger, an autonomous stock trader.

The design goal is maximum flexibility with a stable, narrow core API. You add a module by dropping in a Docker Compose fragment. You add an interface the same way. The core never changes.

---

## Architecture at a Glance

```
[ Interface Container ]     (Discord, Apple Messages, Slack, ...)
         |
         | HTTP POST /message  (X-Sentinel-Key header)
         v
[ Sentinel Core ]           (Python/FastAPI — router & context manager)
    |          |                        |
    | HTTP      | HTTP                   | REST API
    v          v                        v
[ Pi Harness ] [ AI Provider Layer ] [ Obsidian Local REST API ]
[ (coding- ]   [ (ProviderRouter)  ] [ Mnemosyne vault          ]
[  agent)  ]   [ LM Studio/Claude/ ]
               [ Ollama/llama.cpp  ]
         |
         v
[ LM Studio on Mac Mini ]   (primary — or any OpenAI-compatible endpoint)
[ Claude API ]              (optional fallback)
[ Ollama / llama.cpp ]      (stub — future)
```

**Request flow:** Sentinel Core tries Pi harness first. If Pi is unreachable, it falls back to calling the AI provider layer directly via `ProviderRouter`. The Pi path is preferred because it supports tool use and skill dispatch; the direct path is the reliability backstop.

All components are Docker containers. LM Studio runs natively on a Mac Mini. The Obsidian vault is a local folder on your Mac — plain markdown files you always own.

---

## Modules (Planned)

| Module | Purpose | Status |
|---|---|---|
| Core | Routing, context, Obsidian writes | In development |
| Pathfinder 2e DM | NPC management, dialogue, session notes | Planned v0.5 |
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
- **Node.js 22 LTS** (used inside the Pi harness container — the Dockerfile handles this, but good to know)
- A Discord bot token if using the Discord interface

---

## Quick Start (v0.1 — Core Loop Only)

> This gets you a working AI response via `curl`. Full interface setup comes later.

**1. Clone the repo**
```bash
git clone https://github.com/The-Artificer-of-Ciphers-LLC/sentinel-of-mnemosyne.git
cd sentinel-of-mnemosyne
```

**2. Copy the environment template and fill it in**
```bash
cp .env.example .env
# Edit .env with your LM Studio IP, Obsidian API key, etc.
```

**3. Start LM Studio on your Mac Mini**
- Open LM Studio → Local Server → Start server
- Note the IP address and port (default: `1234`)
- Make sure a model is loaded

**4. Start the core containers**
```bash
./sentinel.sh up -d
# Or: docker compose up -d
```

**5. Test it**
```bash
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -H "X-Sentinel-Key: your-sentinel-api-key" \
  -d '{"id":"test-001","source":"curl","user_id":"you","channel_id":"test","timestamp":"2026-04-06T12:00:00Z","content":"Hello, are you there?","attachments":[],"metadata":{}}'
```

You should get an AI response back. That's v0.1.

---

## Adding an Interface

Each interface is a Docker Compose override file. To add Discord:

```bash
# Add your Discord bot token to .env, then:
./sentinel.sh --discord up -d
```

See `interfaces/discord/` for setup details.

---

## Adding a Module

Each module ships as a Docker Compose override file and a set of pi skill files. To add a module:

```bash
./sentinel.sh --discord --music up -d
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to build your own module.

---

## Repository Structure

```
sentinel-of-mnemosyne/
├── docker-compose.yml          # Core containers (Sentinel Core + Pi Harness)
├── .env.example                # Environment variable template
├── sentinel.sh                 # Convenience wrapper for docker compose
├── sentinel-core/              # Python/FastAPI core container
├── pi-harness/                 # Node.js 24 pi coding-agent container
├── interfaces/
│   ├── discord/                # Discord bot interface
│   └── messages/               # Apple Messages bridge (Mac-side component)
├── modules/                    # Module containers (added as project grows)
├── skills/                     # Pi skill files shared across modules
├── mnemosyne/                  # Obsidian vault (gitignored — your data stays yours)
└── docs/
    ├── PRD-Sentinel-of-Mnemosyne.md
    └── ARCHITECTURE-Core.md
```

---

## Configuration Reference

All configuration is done through `.env`. See `.env.example` for the full list with descriptions. Key variables:

| Variable | Purpose |
|---|---|
| `LMSTUDIO_BASE_URL` | LM Studio server URL (e.g., `http://192.168.1.x:1234/v1`) |
| `MODEL_NAME` | Model identifier for direct LiteLLM calls (e.g., `llama-3.2-8b-instruct`) |
| `PI_MODEL` | Model name passed to the Pi harness settings |
| `AI_PROVIDER` | Active AI backend: `lmstudio` (default), `claude`, `ollama`, `llamacpp` |
| `AI_FALLBACK_PROVIDER` | Fallback on connectivity failure: `claude` or `none` (default) |
| `ANTHROPIC_API_KEY` | Anthropic API key — required when `AI_PROVIDER=claude` or `AI_FALLBACK_PROVIDER=claude` |
| `CLAUDE_MODEL` | Claude model ID (default: `claude-haiku-4-5`) |
| `OBSIDIAN_API_URL` | URL for the Obsidian Local REST API plugin |
| `OBSIDIAN_API_KEY` | API key from the Obsidian plugin settings |
| `SENTINEL_API_KEY` | Shared secret between Core and interface containers |
| `LOG_LEVEL` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Documentation

- [Product Requirements Document](docs/PRD-Sentinel-of-Mnemosyne.md) — vision, modules, milestones
- [Core Architecture](docs/ARCHITECTURE-Core.md) — technical decisions, API specs, Docker layout
- [Contributing Guide](CONTRIBUTING.md) — how to build modules and interfaces
- [Roadmap](ROADMAP.md) — milestone summary

---

## Status

This project is in early development. v0.1 (the core loop) is the current target. The architecture and API contracts documented here are stable enough to build against, but may evolve before v1.0.

---

## License

MIT — see LICENSE file.

*The Sentinel watches. Mnemosyne remembers.*
