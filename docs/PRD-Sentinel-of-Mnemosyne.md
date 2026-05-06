# Product Requirements Document
## Sentinel of Mnemosyne
**Version:** 0.50
**Author:** Tom Boucher
**Date:** 2026-05-06
**Status:** Active Reference — v0.50 hardening baseline

---

## 1. Vision and Purpose

The Sentinel of Mnemosyne is a personal, self-hosted AI assistant platform built on open, composable, containerized components. It is designed around a simple but powerful idea: **you bring your own AI, your own memory, and your own interface** — the Sentinel wires them together and gets out of your way.

The name captures the intent well. *Mnemosyne* is the Greek goddess of memory — represented here by an [Obsidian](https://obsidian.md) vault that persists everything the system learns, records, and generates. The *Sentinel* is the watchful, always-available presence that sits between you and your AI, managing context, routing messages, and saving what matters.

The core philosophy is flexibility over prescription. Whether you want a Dungeon Master's assistant for Pathfinder 2e, a music practice journal, a coding co-pilot, or something nobody has thought of yet — the Sentinel should be able to support it without requiring you to rebuild the engine each time. You drop in a new Docker module, register it, and go.

---

## 2. Core Design Principles

**BYO AI (Bring Your Own AI).** The platform is not tied to any single AI provider. Development targets [LM Studio](https://lmstudio.ai) running locally on a Mac Mini, but the AI interface layer should be swappable. If you want to point it at Claude, GPT-4, or a fine-tuned local model — the system should support that with minimal friction.

**Obsidian as the heart.** All persistent knowledge — session summaries, NPC records, music practice logs, code snippets, user preferences — lives in an Obsidian vault. This means your data is always human-readable, portable plain-text markdown files, not locked in a proprietary database.

**LiteLLM-direct as the AI layer.** The Sentinel calls LiteLLM → the configured AI provider (LM Studio, Claude API, Ollama, LlamaCpp) directly. No intermediate layer. Pi harness is an optional power tool for advanced coding tasks, activated via `./sentinel.sh --pi`, scoped to v0.7.

**Pluggable interfaces.** How you talk to the Sentinel is up to you. Discord, Apple Messages, Slack, WhatsApp, Telegram — each interface lives in its own Docker container and talks to the core engine via a defined standard. You want a new interface? Drop in the container, wire the hooks, done.

**Pluggable modules.** Functionality beyond core routing (Pathfinder, music tracking, coding tools, etc.) is packaged as self-contained modules. Each module is a Docker Compose fragment — a clean addition to the running system that does not require touching the core compose configuration.

**Limited, stable core API.** Inspired by how pi works with its four core commands plus skills, the Sentinel will define a small, stable set of input/output message types. Modules and interfaces must speak this language. Keeping the contract narrow keeps the system predictable.

**Open source first.** All components should default to open source tooling. Docker over proprietary orchestration. Obsidian (local vault, not Obsidian Sync). LM Studio for local model serving. The goal is a system you fully own and can run indefinitely without vendor dependency.

---

## 3. System Architecture

### 3.1 High-Level Component Map

```
┌─────────────────────────────────────────────────┐
│            INTERFACE LAYER                      │
│   (Discord /sen, Messages — one container each) │
└────────────────────┬────────────────────────────┘
                     │  HTTP POST /message
                     │  X-Sentinel-Key header
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                 SENTINEL CORE CONTAINER                         │
│   FastAPI router · APIKeyMiddleware                             │
│   ModelRegistry · ProviderRouter · Module Registry              │
│   POST /message (chat) · POST /modules/register                 │
│   POST /modules/{name}/{path} (proxy)                           │
└──────────┬─────────────────┬───────────────────────────────────┘
           │                 │
           │ LiteLLM         │ httpx proxy (registered modules)
           ▼                 ▼
┌──────────────────┐  ┌──────────────────────┐
│  AI PROVIDER     │  │  MODULE CONTAINERS   │
│  LiteLLMProvider │  │  (v0.5+: Pathfinder, │
│  → LM Studio     │  │  Music, Finance, etc)│
│  → Claude API    │  │  Each: FastAPI        │
└──────────────────┘  │  POST /register →    │
                      │  sentinel-core       │
                      └──────────────────────┘

              ┌──────────────────────────┐
              │  OBSIDIAN VAULT (host)   │
              │  REST API plugin         │
              └──────────────────────────┘

[ Pi Harness ] — optional, only with sentinel.sh --pi flag, v0.7 scope
```

sentinel-core is the API gateway: it handles all chat completions via LiteLLM-direct and proxies all module requests to registered module containers. Interface containers translate channel-specific messages into the standard envelope and post to sentinel-core. Module containers register their endpoints with sentinel-core at startup via `POST /modules/register`.

### 3.2 Container Roles

**Interface Container(s)**
Responsible for receiving input from a specific communication channel (Discord, Apple Messages, etc.) and translating it into the standard Sentinel message envelope. It sends the envelope to the Core and delivers the response back to the originating channel. Interface containers know nothing about AI or Obsidian — they are pure translation layers.

**Sentinel Core Container**
The API gateway and context manager. Receives incoming message envelopes, enriches them with relevant context (retrieved from Obsidian), calls LiteLLM directly for chat completions, and handles the response. Also maintains the module registry and proxies module requests. This is the single process that must be running for chat and module routing to work.

**AI Provider (LiteLLM)**
LiteLLM runs inside the Sentinel Core container — not a separate service. It abstracts LM Studio, Claude API, Ollama, and llama.cpp behind a single `acompletion()` interface. The configured AI provider is set via environment variables. No intermediate layer between sentinel-core and the AI.

**Obsidian Vault**
Not a container — a folder on the host filesystem accessible via the Obsidian Local REST API plugin. Obsidian on your Mac reads the same folder. Markdown files, organized by module conventions. No database, no migrations.

**Module Containers**
Optional FastAPI containers (v0.5+) that add capability. Each module calls `POST /modules/register` on sentinel-core at startup, declaring its `name`, `base_url`, and available `routes`. sentinel-core then proxies `POST /modules/{name}/{path}` requests to the appropriate module. Modules may have their own Obsidian folder conventions (e.g., `/pathfinder/npcs/`, `/music/lessons/`).

**Pi Harness Container (optional — v0.7 scope)**
The pi-mono coding-agent running in Docker, activated via `./sentinel.sh --pi`. An advanced coding tool for interactive code-generation tasks. Not in the standard chat message path.

### 3.3 Standard Message Envelope (Draft)

All interface containers must produce and consume this envelope format. This is the core contract that makes the pluggable architecture possible.

```json
{
  "id": "uuid",
  "source": "discord | messages | slack | ...",
  "user_id": "string",
  "channel_id": "string",
  "timestamp": "ISO8601",
  "content": "string",
  "attachments": [],
  "metadata": {}
}
```

Responses follow a similar shape, with an added `reply_to` field and an optional `actions` array for interface-specific behavior (e.g., adding a reaction emoji in Discord).

### 3.4 Core API (Minimal, Stable)

The Core exposes a small HTTP API. The goal is four or fewer primary endpoints — everything else is a module skill.

| Endpoint | Method | Purpose |
|---|---|---|
| `/message` | POST | Receive a message envelope from an interface |
| `/status` | GET | Health check and system info |
| `/context/{user_id}` | GET | Retrieve recent context for a user |
| `/skill/{skill_name}` | POST | Directly invoke a named module skill |

### 3.5 Docker Compose Strategy

The base system has a `docker-compose.yml` that defines the Core and Pi harness containers. Each interface and module ships its own `docker-compose.override.yml` fragment. Docker Compose natively supports override files — you include them at startup:

```bash
docker compose -f docker-compose.yml -f discord/docker-compose.override.yml up
```

This means adding a new module never touches the base file. Anyone building a module publishes their override file alongside their container definition. No central "mega compose file" that gets unwieldy over time.

---

## 4. AI Provider Configuration

The Pi harness is configured to target a specific AI endpoint. For development, this is LM Studio running on a Mac Mini on the local network. LM Studio exposes an OpenAI-compatible API, making it straightforward to swap providers.

**v0.x target:** LM Studio (local, OpenAI-compatible endpoint)
**Secondary target:** Anthropic Claude API (for heavier reasoning tasks, especially in the Coder module)
**Future:** Any OpenAI-compatible endpoint, configurable per-module if needed

Provider configuration lives in environment variables in the Pi harness container — no hardcoding.

---

## 5. Obsidian Vault Structure (Mnemosyne)

The vault is the long-term memory of the system. Folder structure by module keeps things tidy. All writes from the system are standard markdown with YAML frontmatter where structured data is useful.

```
/mnemosyne/
  /core/
    /users/           ← per-user preference and context files
    /sessions/        ← session summaries
  /pathfinder/
    /campaigns/
    /npcs/
    /sessions/
    /rules/
  /music/
    /lessons/
    /practice-log/
    /pieces/
    /ideas/
  /coder/
    /projects/
    /snippets/
  /media/             ← music/vinyl/cd tracking (Discogs integration later)
  /finance/
    /transactions/    ← parsed OFX imports by month
    /budgets/         ← budget definitions and monthly summaries
    /accounts/        ← account metadata (no credentials ever stored here)
    /reports/         ← AI-generated spending analysis
  /trading/
    /watchlist/       ← researched stocks and thesis notes
    /positions/       ← current and historical positions
    /trades/          ← full trade log with AI rationale
    /rules/           ← personal trading rules the AI must follow
    /performance/     ← P&L tracking and period summaries
```

---

## 6. Module Specifications

### 6.1 Module: Pathfinder 2e DM Assistant

**Purpose:** Act as a GM co-pilot during Pathfinder 2e sessions. Manages NPCs, offers dialogue cues, tracks what was said in prior sessions, and can react to in-game events.

**Key capabilities:**
- NPC roster management (name, personality, voice, history, relationship map)
- Session note capture — what happened, who said what, unresolved plot threads
- Dialogue generation on demand ("what would Vareth say when the party accuses him?")
- Reaction triggers — if Foundry VTT integration is available, NPCs can react to combat events (rolled a 1, scored a critical hit)
- Campaign timeline and world state tracking

**Obsidian integration:** `/pathfinder/npcs/[name].md`, `/pathfinder/sessions/[date].md`

**Long-term stretch goal:** Foundry VTT integration to receive real-time event data from the VTT (rolls, initiative, deaths) and push NPC reactions back.

**Interface note:** This module is a good candidate for a dedicated Discord server or channel — GMs often already run Discord alongside their VTT.

### 6.2 Module: Music Lesson Tracker

**Purpose:** Track practice sessions, lessons, pieces worked on, chord ideas, and progress over time.

**Key capabilities:**
- Log a practice session (duration, pieces, focus area, notes)
- Record chord or melody ideas in a structured way
- Query practice history ("what did I work on last week?", "how long have I been working on this piece?")
- Optional: pull listening data from ListenBrainz to capture what you're listening to
- Optional: Discogs integration — flag a song you love, the system can add it to your Discogs wantlist or suggest related vinyl/CDs

**Obsidian integration:** `/music/lessons/[date].md`, `/music/practice-log/`, `/music/ideas/`

**ListenBrainz / Discogs note:** These are stretch goals, but the Discogs API is well-documented and the wantlist write operation is straightforward. Worth designing the music module's data model to accommodate these fields from day one.

### 6.3 Module: Coder Interface

**Purpose:** Provide a coding-focused AI environment that can write, review, and iterate on new Sentinel modules — eating its own cooking.

**Key capabilities:**
- Separate Pi harness instance (or separate profile) tuned for code tasks
- Can route heavy tasks to a more capable model (e.g., Claude API) while lighter tasks stay local
- Writes new module scaffolding, reviews container configs, helps debug compose files
- Does NOT run inside the main Sentinel engine — operates as a parallel environment that can optionally route through the Sentinel for memory/context

**Design note:** The "coder" Pi environment should be cleanly separated from the production Sentinel engine. You work in the coder environment to build new modules; those modules are then deployed to the Sentinel. Think of it as a dev environment that happens to be AI-assisted.

### 6.4 Module: Media & Music Discovery (Future)

**Purpose:** Connect music taste and listening habits to purchasing decisions and collection management.

**Key capabilities:**
- ListenBrainz integration to pull listening history
- "I love this track" → auto-add release to Discogs wantlist
- Suggest related artists or releases based on listening patterns
- Maintain a curated wantlist with notes

**Status:** Ideas phase. Design the music module's data model to leave room for this without building it now.

### 6.5 Module: Personal Finance Tracker

**Purpose:** Turn your bank's transaction exports into a living, searchable, AI-assisted spending ledger inside Obsidian. No cloud sync to a third-party service, no credentials shared with anyone — just your own data in your own vault.

**The OFX file format:** Most banks and credit unions let you download transaction history as an OFX file (Open Financial Exchange). It's a structured XML-based format that includes transaction amounts, dates, merchant names, and memo fields. Quicken and Mint both consume this format. The Sentinel will too.

**Key capabilities:**
- Accept OFX file uploads via Discord attachment, file drop to a watched folder, or direct message attachment
- Parse and normalize transactions — deduplicate if you import overlapping date ranges
- AI-assisted categorization: the AI reads merchant names and assigns categories (groceries, dining, utilities, subscriptions, etc.), learning your corrections over time
- Budget tracking — define monthly budgets per category, the system alerts when you're approaching or over
- Natural language queries: "How much did I spend on restaurants in March?", "What are all my active subscriptions?", "How does this month compare to last month?"
- Recurring charge detection — identify charges that appear on a regular cadence and flag new ones
- Monthly summary reports written to Obsidian as markdown — readable without the Sentinel running
- Spending trend notes: over time, the AI can note patterns ("your grocery spending has gone up 18% in three months")

**What it does NOT do:** Connect directly to your bank, store login credentials, share data externally, or make any financial transactions.

**Obsidian integration:**
- `/finance/transactions/{YYYY-MM}.md` — monthly transaction files with YAML frontmatter per transaction
- `/finance/accounts/{account-name}.md` — account metadata, balance history (manually updated or from OFX header)
- `/finance/budgets/current.md` — active budget definitions
- `/finance/reports/{YYYY-MM}-summary.md` — AI-generated monthly analysis

**OFX transaction note format (example):**
```markdown
---
date: 2026-03-15
amount: -47.83
merchant: WHOLE FOODS MARKET
category: groceries
account: checking-main
cleared: true
tags: [transaction, groceries, 2026-03]
---
Whole Foods Market — $47.83
```

**File input flow:**
1. User drops or sends an OFX file via the active interface
2. The module's parser container reads the OFX XML and extracts transactions
3. Transactions are deduped against existing vault entries (matched by date + amount + merchant)
4. New transactions are sent to the AI for category suggestions
5. Categorized transactions are written to the appropriate monthly file in Obsidian
6. Module responds with a brief import summary: "Imported 47 transactions, 3 needed your review for categorization"

**Interface command examples:**
- Send an OFX file attachment → triggers import flow
- "What did I spend last month?" → AI queries vault, returns summary
- "Categorize that Costco charge as household, not groceries" → updates the entry and remembers the rule
- "Am I on track with my dining budget?" → AI checks current month vs. budget definition

**Dependencies:** OFX parser library (Python's `ofxtools` is well-maintained and open source).

---

### 6.6 Module: Autonomous Stock Trader

**Purpose:** A small, rule-constrained AI trading agent that can research equities and execute real or simulated trades within a strictly defined boundary. Inspired by the experiments people ran giving AI systems a fixed amount of money and watching what they did with it — but with guardrails and a full audit trail.

**The idea in plain terms:** You allocate a fixed amount of money (say, $100–$500) to the Sentinel. You define your personal trading rules as a plaintext file in Obsidian. The AI researches stocks using public data, proposes trades with written rationale, and — in autonomous mode — executes them through a brokerage API. Everything it does and why it did it is written to Obsidian.

**Modes of operation:**

*Research-only mode (no trading):* The AI monitors a watchlist, reads earnings reports and news, and surfaces investment ideas with a written thesis. No trades happen — it's a research assistant.

*Paper trading mode (simulated, recommended starting point):* All trades happen in a simulated environment with no real money. The AI builds and manages a virtual portfolio, tracks P&L, and learns what its own reasoning gets right and wrong. This is where you evaluate whether you trust it before putting real money in.

*Live trading mode (real money, explicit opt-in):* Executes actual trades via the Alpaca brokerage API (commission-free, well-documented, designed for automated trading). This mode requires explicit configuration — it cannot be enabled accidentally.

**Brokerage integration — Alpaca:**
[Alpaca](https://alpaca.markets) is the recommended API because it is commission-free, has both paper and live trading APIs at the same endpoints (just different API keys), and is built specifically for algorithmic trading. It supports stocks and ETFs. The API is REST-based and well-documented. Alpaca is not a bank — you hold assets through them like any brokerage.

**Hard limits (enforced in the module, not just suggested):**
- Maximum single trade size: configurable, default $50
- Maximum total portfolio value: configurable, default matches your defined allocation
- No margin trading — cash only, you can only spend what's in the account
- No options, no futures, no crypto — equities and ETFs only in v1
- No short selling — long positions only
- Minimum hold period: configurable (default 24 hours) — prevents high-frequency churn
- Daily trade limit: configurable (default 3 trades/day) to stay clear of Pattern Day Trader rules (see below)
- All proposed trades in live mode require either automatic execution (if enabled) OR a human approval step via the interface ("The AI wants to buy 2 shares of NVDA at $112. Reply YES to confirm.")

**Pattern Day Trader (PDT) rule — important:** The SEC defines a Pattern Day Trader as anyone who makes four or more day trades (buy and sell same security in the same day) within five business days in a margin account with less than $25,000. This module tracks day trade count and will refuse to execute a trade that would trigger PDT status. The minimum hold period setting exists partly for this reason. Cash accounts have different rules (T+1 settlement). The module documentation will explain this clearly — it is not a lawyer and this is not legal advice, but it will keep count and warn you.

**Research capabilities:**
The AI can be pointed at public data sources for research:
- Yahoo Finance or similar for price history and basic fundamentals
- SEC EDGAR for earnings filings (10-Q, 10-K) — free and public
- News APIs (NewsAPI or similar) for recent coverage
- Your own notes in Obsidian — if you've written about a company, it reads that first

The research methodology and what the AI is allowed to consider is defined in `/trading/rules/research-guidelines.md` — a plaintext file you write and own.

**Your trading rules file (`/trading/rules/my-rules.md`):**
This is the most important piece of the module. It's a plain English document that tells the AI how to behave. Examples of things you might put in it:
- "Never buy a stock I haven't held for at least one prior research session"
- "Only buy companies with a market cap over $1B"
- "Avoid airlines and cruise lines"
- "Maximum 20% of the portfolio in any single position"
- "If a position is down more than 15%, sell it — no averaging down"
- "No earnings plays — don't buy within 48 hours of an earnings report"

The AI reads these rules before every decision and includes a rules-compliance check in its rationale.

**Audit trail (non-negotiable):** Every action the trading module takes — research reads, rationale generation, trade proposals, executions — is written to Obsidian with a timestamp. If you want to know why it did something, the answer is always in the vault.

**Trade log entry format (example):**
```markdown
---
date: 2026-03-15T10:32:00Z
action: buy
ticker: VTI
shares: 1
price: 268.40
total: 268.40
mode: paper
tags: [trade, buy, ETF, 2026-03]
---

# Buy — VTI — 2026-03-15

## Rationale
VTI is a total market ETF with very low expense ratio (0.03%). Given the current
allocation is 100% cash and the rules file specifies "index funds are always
acceptable as a base position," this is a low-risk starting point.

## Rules check
- ✓ Market cap: N/A (ETF)
- ✓ Single position limit: $268 is 26% of $1,000 portfolio — within 30% limit
- ✓ No earnings event within 48h: ETFs don't have earnings reports
- ✓ Hold period: N/A (new position)

## Data reviewed
- VTI 90-day price chart
- Vanguard fund page (expense ratio, holdings breakdown)
```

**Honest assessment of this module:** This is the highest-risk, highest-complexity module in the roadmap. The viral AI-trading stories (GPT-4 given $100, Claude given a brokerage account) were fascinating precisely because they were chaotic and unpredictable. This module is an attempt to do the same thing but with structure, rules, and a paper trading phase so you understand the AI's tendencies before it touches real money. Start in paper mode. Live a long time in paper mode. The AI's research will often be interesting even when the trades are bad.

**Obsidian integration:**
- `/trading/watchlist/{ticker}.md` — research thesis per ticker
- `/trading/positions/current.md` — live portfolio snapshot
- `/trading/trades/{YYYY-MM-DD}-{ticker}.md` — individual trade records
- `/trading/rules/my-rules.md` — your personal trading rules (you write this)
- `/trading/performance/{YYYY-MM}.md` — monthly P&L and analysis

**Dependencies:** Alpaca Python SDK (`alpaca-py`), a news/financial data API, Alpaca paper trading account (free to create).

---

## 7. Interface Specifications

### 7.1 Interface: Discord Bot

The first production interface. A Discord bot listens in designated channels (or via DM), translates messages to the standard envelope, and posts responses. The bot container handles all Discord API complexity — the Core sees only envelopes.

**Configuration:** Bot token, allowed channel/server IDs, command prefix or mention-based trigger.

**Commands (examples):**
- Mention the bot or use a prefix to send a message to the AI
- `/recall [topic]` — ask the Sentinel to surface relevant notes from Obsidian
- Module-specific slash commands registered by each module's container

### 7.2 Interface: Apple Messages (Mac)

Uses AppleScript or a Mac-native bridge to monitor and send iMessages. This is the most personal interface — messages from your phone go to the Sentinel and back naturally.

**Note:** This will require a Mac-hosted component (AppleScript cannot run in a Linux container). The architecture should support a lightweight Mac-side bridge process that connects to the Core container via HTTP — the container does not need to be on the same machine as Messages, just network-accessible.

### 7.3 Future Interfaces

Slack, WhatsApp (via Business API or unofficial bridge), Telegram, SMS (via Twilio). Each ships as its own container + override file. The standard envelope contract means none of these require Core changes.

---

## 8. Release Milestones

### v0.1 — The Spark
**Goal:** Prove the core loop works end-to-end.

- Pi harness running in Docker, accepting prompts via HTTP
- Minimal Core container that forwards a message to Pi and returns the response
- Test via `curl` or a simple web form — no fancy interface required
- LM Studio on Mac Mini confirmed as the AI backend
- Basic `docker-compose.yml` structure established

**Success criteria:** Send a message, get an AI response. That's it. Everything else is built on this.

### v0.2 — The Memory
**Goal:** Obsidian vault integration.

- Core can read relevant context from the vault before sending to Pi
- Core writes session summaries back to the vault after interactions
- Vault folder structure established (`/core/users/`, `/core/sessions/`)
- Demonstrate: ask a question referencing a prior session, get a contextually aware answer

**Success criteria:** The system remembers something across two separate conversations.

### v0.3 — The Voice
**Goal:** Real interface — Discord bot or Apple Messages bridge (whichever proves easier).

- Interface container operational and passing envelopes to Core
- Response posted back to the originating channel
- Standard envelope format finalized
- Docker Compose override pattern validated with the first real interface

**Success criteria:** Have a conversation with the Sentinel from a phone or desktop without touching a terminal.

### v0.4 — The Brain (AI Layer Polish)
**Goal:** Make the AI integration robust and configurable.

- Provider configuration via environment variables (not hardcoded)
- At least two providers testable (LM Studio + one other)
- Basic error handling, retry logic, timeout management
- Pi harness wrapper finalized — clean API the rest of the system depends on

**Success criteria:** Switch AI providers without touching anything except an env file.

### v0.5 — The Dungeon (Pathfinder 2e Module)
**Goal:** First real module demonstrating the pluggable architecture.

- NPC management — create, update, query NPCs via the interface
- Session note capture
- Dialogue generation
- Obsidian vault structure for `/pathfinder/` established
- Module delivered as a Docker Compose override file

**Success criteria:** Run a Pathfinder session using the Sentinel for NPC dialogue and session notes.

### v0.6 — The Practice Room (Music Lesson Module)
**Goal:** Second module, simpler than Pathfinder — validates the module pattern.

- Log a practice session via Discord or Messages
- Query practice history
- Obsidian structure for `/music/` established

**Success criteria:** Log a week of practice sessions and retrieve a summary.

### v0.7 — The Workshop (Coder Interface)
**Goal:** AI-assisted development environment for building new Sentinel modules.

- Separate Pi environment for coding tasks
- Routing to a capable cloud model (Claude API) for heavy lifting
- Scaffolding generator for new modules
- Does not interfere with production Sentinel

**Success criteria:** Use the coder interface to scaffold a new module stub.

### v0.8 — The Ledger (Personal Finance Module)
**Goal:** OFX import pipeline and spending intelligence in Obsidian.

- OFX parser container operational — accepts file uploads via interface
- Transaction deduplication and AI-assisted categorization working
- Budget definition file format established in Obsidian
- Natural language spending queries working ("what did I spend on dining last month?")
- Recurring charge detection producing alerts
- Monthly summary report auto-generated on last day of month

**Success criteria:** Import a real bank export, ask a spending question in Discord, get a useful answer.

### v0.9 — The Trader (Autonomous Stock Trader Module — Paper Only)
**Goal:** Paper trading agent running against Alpaca's simulated environment, with full audit trail.

- Alpaca paper trading API connected
- Personal rules file format established and AI reads it before every decision
- Watchlist research loop working — AI generates thesis notes for tracked tickers
- Trade execution in paper mode with full rationale written to Obsidian
- PDT rule counter tracking day trades
- Hard limits enforced (no margin, max position size, daily trade cap)
- Trade log and monthly P&L summary writing to Obsidian

**Success criteria:** Run the paper trader for 30 days. Read the trade logs. Decide if you trust it enough for live mode.

### v0.10 — The Trader Goes Live (Optional, Explicit Opt-In)
**Goal:** Live trading mode, only if paper trading results warrant it.

- Live Alpaca API keys configurable separately from paper keys
- Human approval flow for trades (interface sends proposal, waits for YES confirmation) as an option
- Rate limiting and emergency stop ("STOP TRADING" command halts all trading activity immediately)
- Weekly performance summary delivered via interface

**Success criteria:** Execute one real trade with human confirmation step. Review the full audit trail. Decide on autonomous mode.

### v1.0 — Polish, Stability, Community
- Documentation pass for external contributors
- Module development guide published (MODULE-SPEC.md)
- GitHub repository structured for open contribution
- Discogs / ListenBrainz integration (if music module has proven useful)
- Foundry VTT integration investigation begins

---

## 9. Open Questions and Decisions Pending

| Question | Notes |
|---|---|
| How does the Core retrieve relevant context from Obsidian? | Full-text search via grep? Obsidian's search API? A lightweight vector index? Start simple (grep/search), optimize later. |
| What language does the Core container use? | Python is a natural fit given the Pi harness ecosystem and available libraries. Needs a decision before v0.1. |
| AppleScript bridge architecture | Messages interface requires Mac-side component. Define the bridge protocol before v0.3. |
| Pi harness version pinning | The pi-mono project is under active development. Need a strategy for pinning and upgrading the Pi version. |
| Obsidian vault sync | Local vault only for now. If multi-device access is needed later, iCloud sync of the vault folder is the simplest option before considering Obsidian Sync. |
| Module discovery and registration | How does the Core know which modules are running? Environment variable list? A registration endpoint? Design for v0.5. |
| Authentication | Who is allowed to talk to the Sentinel? For personal use, a shared secret token in the envelope header is probably sufficient for v0.x. |

---

## 10. Out of Scope (for v1.0)

- Multi-user / multi-tenant support
- Mobile app (the interface containers handle mobile-friendly channels like Discord and Messages)
- Proprietary cloud storage of the Obsidian vault
- Any interface that requires non-open-source backend dependencies
- Real-time audio/voice interface (interesting future direction, not v1 scope)

---

## 11. Reference Links

- Pi harness (coding-agent): https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent
- LM Studio: https://lmstudio.ai
- Obsidian: https://obsidian.md
- Docker Compose override files: https://docs.docker.com/compose/how-tos/multiple-compose-files/
- ListenBrainz API: https://listenbrainz.readthedocs.io
- Discogs API: https://www.discogs.com/developers
- Foundry VTT: https://foundryvtt.com
- OFX format specification: https://www.ofx.net/downloads/OFX%202.2.pdf
- ofxtools (Python OFX parser): https://ofxtools.readthedocs.io
- Alpaca Markets (brokerage API): https://alpaca.markets
- Alpaca Python SDK: https://github.com/alpacahq/alpaca-py
- SEC EDGAR (free public filings): https://www.sec.gov/cgi-bin/browse-edgar
- Pattern Day Trader rule overview: https://www.finra.org/investors/learn-to-invest/advanced-investing/day-trading-margin-requirements-know-rules

---

*This document is a living reference. Update it as decisions are made and the architecture evolves. When a section becomes stable and implemented, mark it with a ✓ and the version it shipped in.*
