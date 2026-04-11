# Sentinel of Mnemosyne — Roadmap

Current status: **v0.4 gap closure in progress (Phases 21–24) — v0.5 The Dungeon begins after gaps closed.**

The full milestone details, module specifications, and design decisions live in the [PRD](docs/PRD-Sentinel-of-Mnemosyne.md) and [Architecture Doc](docs/ARCHITECTURE-Core.md). This file is the quick-reference version.

---

## ✅ v0.1 — The Spark *(COMPLETE)*
**Goal:** Prove the core loop works. Send a message via `curl`, get an AI response back.

**Phases delivered:**
- Phase 01 — Core Loop (Pi harness container, Sentinel Core, base docker-compose)

**Success criteria met:** Message in → AI response out via curl.

---

## ✅ v0.2 — The Memory *(COMPLETE)*
**Goal:** Obsidian vault integration. The system reads context before responding and writes session notes after.

**Phases delivered:**
- Phase 02 — Memory Layer (Obsidian REST API integration, context injection, session write-back)

**Success criteria met:** The system remembers something across two separate conversations.

---

## ✅ v0.3 — The Voice *(COMPLETE)*
**Goal:** First real interface. Talk to the Sentinel without a terminal.

**Phases delivered:**
- Phase 03 — Interfaces (Discord bot container, message envelope format, Docker Compose override pattern)

**Success criteria met:** Conversation via phone/desktop without touching a terminal.

---

## ⚠️ v0.4 — Functional Alpha *(gap closure in progress)*
**Goal:** Robust, swappable AI provider configuration — stable foundation everything else builds on.

**Phases delivered:**
- Phase 04 — AI Provider / Multi-provider support, retry logic, fallback
- Phase 05 — AI Security / Prompt injection hardening
- Phase 06 — Discord Regression Fix
- Phase 07 — Phase 2 Verification / Memory layer UAT
- Phase 08 — Requirements Traceability Repair *(scoped, never executed — see Phase 22)*
- Phase 10 — Knowledge Migration Tool / Import from existing second brain (2nd brain vault structure, 27-command Discord system, parallel context injection)

**Audit status (2026-04-11):** 4 critical regressions found — `POST /message` crashes on every request, Discord container re-commented (3rd time), Phase 08 never executed, Pi `/reset` route missing. See `.planning/v0.1-v0.4-MILESTONE-AUDIT.md`.

**Gap closure phases (must complete before v0.4 is signed off):**
- Phase 21 — Production Recovery: restore `injection_filter.py`, `output_scanner.py`, uncomment Discord (closes SEC-01, SEC-02, IFACE-02/03/04, CORE-03)
- Phase 22 — Requirements Traceability Repair: execute Phase 08 scope + extend through Phase 10 (closes documentation gaps)
- Phase 23 — Pi Harness `/reset` Route: add missing route to `bridge.ts`, restore configurable timeout (closes CORE-07)
- Phase 24 — Pentest Agent Wire + Verification Artifacts: wire `pentest-agent/compose.yml`, generate missing VERIFICATION.md for Phases 02/05/07 (closes SEC-04, GAP-06)

**Success criteria:** Switch AI providers via env file only. Pi harness API contract finalized. Existing Obsidian data migrated. All E2E flows operational.

---

## v0.5 — The Dungeon *(Pathfinder 2e DM Assistant)*
**Goal:** First real module. Proves the pluggable module architecture works.

**Planned capabilities:**
- NPC roster management (create, update, query)
- Session note capture and world state tracking
- Dialogue generation on demand
- Delivered as a Docker Compose override file
- Obsidian vault structure for `/pathfinder/` established

**Success criteria:** Run a Pathfinder session using the Sentinel for NPC dialogue and session notes.

---

## v0.6 — The Practice Room *(Music Lesson Tracker)*
**Goal:** Second module. Validates that the module pattern is repeatable.

**Planned capabilities:**
- Log practice sessions via Discord or Messages
- Query practice history with natural language
- Chord/melody idea capture
- Obsidian structure for `/music/` established

**Success criteria:** Log a week of practice sessions and retrieve a summary.

---

## v0.7 — The Workshop *(Coder Interface)*
**Goal:** AI-assisted development environment for building new Sentinel modules.

**Planned capabilities:**
- Separate Pi harness instance tuned for code tasks
- Routes heavy tasks to a more capable cloud model (e.g., Claude API)
- Scaffolding generator for new modules
- Isolated from production Sentinel

**Success criteria:** Use the coder interface to scaffold a new module stub.

---

## v0.8 — The Ledger *(Personal Finance Module)*
**Goal:** OFX transaction import and spending intelligence in Obsidian.

**Planned capabilities:**
- OFX file parsing and deduplication
- AI-assisted transaction categorization
- Budget tracking and natural language spending queries
- Recurring charge detection
- Monthly summary reports in Obsidian

**Success criteria:** Import a real bank export, ask a spending question in Discord, get a useful answer.

---

## v0.9 — The Trader *(Stock Trader — Paper Mode)*
**Goal:** AI trading agent in simulated mode, full audit trail.

**Planned capabilities:**
- Alpaca paper trading API connected
- Personal trading rules file (plain English, you write it)
- Watchlist research loop with thesis notes
- Hard limits enforced: no margin, position size caps, daily trade cap, PDT tracking
- Complete trade rationale written to Obsidian before every execution

**Success criteria:** Run the paper trader for 30 days. Read the trade logs. Decide if you trust it enough for live mode.

---

## v0.10 — The Trader Goes Live *(Explicit Opt-In)*
**Goal:** Real money, only if paper trading results warrant it.

**Planned capabilities:**
- Live Alpaca API keys configurable separately from paper keys
- Optional human approval step before each trade
- Emergency stop command
- Weekly P&L summary delivered via interface

**Success criteria:** Execute one real trade with human confirmation step. Review the full audit trail.

---

## v1.0 — Community Release

- Full documentation pass for external contributors
- Module development guide (CONTRIBUTING.md / MODULE-SPEC.md) polished
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
