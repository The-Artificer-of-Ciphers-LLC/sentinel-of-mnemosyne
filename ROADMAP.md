# Sentinel of Mnemosyne — Roadmap

Current status: **Pre-v0.1 — Architecture and documentation phase.**

The full milestone details, module specifications, and design decisions live in the [PRD](docs/PRD-Sentinel-of-Mnemosyne.md) and [Architecture Doc](docs/ARCHITECTURE-Core.md). This file is the quick-reference version.

---

## Core Milestones

### v0.1 — The Spark
**Goal:** Prove the core loop works. Send a message via `curl`, get an AI response back.

- Pi harness container running, connected to LM Studio on Mac Mini
- Sentinel Core container routing messages to Pi
- Basic `docker-compose.yml` structure in place

### v0.2 — The Memory
**Goal:** Obsidian vault integration. The system reads context before responding and writes session notes after.

- Obsidian Local REST API plugin connected
- Core retrieves user context from vault before building Pi prompt
- Session summaries written to vault after each conversation
- Existing Obsidian data imported to `/inbox/imports/`

### v0.3 — The Voice
**Goal:** First real interface. Talk to the Sentinel without a terminal.

- Discord bot container OR Apple Messages bridge operational
- Standard message envelope format finalized
- Docker Compose override pattern validated

### v0.4 — The Brain (AI Layer Polish)
**Goal:** Robust, swappable AI provider configuration.

- Provider config via environment variables only
- At least two providers testable (LM Studio + one other)
- Error handling, retries, timeouts
- Pi harness API contract finalized — everything else builds on this

---

## Module Milestones

### v0.5 — The Dungeon (Pathfinder 2e DM Assistant)
First real module. Proves the pluggable module architecture works.

- NPC roster management (create, update, query)
- Session note capture and world state tracking
- Dialogue generation on demand
- Delivered as a Docker Compose override file

### v0.6 — The Practice Room (Music Lesson Tracker)
Simpler second module. Validates that the module pattern is repeatable.

- Log practice sessions via Discord or Messages
- Query practice history with natural language
- Chord/melody idea capture

### v0.7 — The Workshop (Coder Interface)
AI-assisted development environment for building new Sentinel modules.

- Separate Pi harness instance tuned for code tasks
- Routes heavy tasks to a more capable cloud model (e.g., Claude API)
- Scaffolding generator for new modules
- Isolated from production Sentinel

### v0.8 — The Ledger (Personal Finance Module)
OFX transaction import and spending intelligence.

- OFX file parsing and deduplication
- AI-assisted transaction categorization
- Budget tracking and natural language spending queries
- Recurring charge detection
- Monthly summary reports in Obsidian

### v0.9 — The Trader (Stock Trader — Paper Mode)
AI trading agent in simulated mode, full audit trail.

- Alpaca paper trading API connected
- Personal trading rules file (plain English, you write it)
- Watchlist research loop with thesis notes
- Hard limits enforced: no margin, position size caps, daily trade cap, PDT tracking
- Complete trade rationale written to Obsidian before every execution

### v0.10 — The Trader Goes Live (Explicit Opt-In)
Real money, only if paper trading results warrant it.

- Live Alpaca API keys configurable separately from paper keys
- Optional human approval step before each trade
- Emergency stop command
- Weekly P&L summary delivered via interface

---

## v1.0 — Community Release

- Full documentation pass for external contributors
- Module development guide (CONTRIBUTING.md) polished
- GitHub repo structured for open contribution
- Discogs / ListenBrainz integration (if music module has proven useful)
- Foundry VTT integration investigation begins

---

## Future / Ideas

These aren't on the roadmap yet but are worth keeping in mind as the architecture evolves:

- **Foundry VTT integration** — receive real-time combat events, push NPC reactions
- **Media Discovery** — ListenBrainz listening history → Discogs wantlist automation
- **Telegram / WhatsApp / Slack interfaces** — each as its own drop-in container
- **Voice interface** — interesting long-term direction, not v1 scope
- **Multi-device vault sync** — iCloud vault sync before considering Obsidian Sync

---

*For full specs on any milestone, see the [PRD](docs/PRD-Sentinel-of-Mnemosyne.md).*
