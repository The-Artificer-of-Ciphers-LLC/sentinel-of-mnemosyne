# Feature reference

Current shipped baseline:

- Sentinel Core `v0.51.1`
- Discord interface `v0.2.1`
- Pathfinder module `v1.1.2`

This is a reference list of shipped capabilities. For setup steps, see [Install Sentinel](../how-to/install.md). For command syntax, see [Discord Commands](discord-commands.md). For route-level details, see [API and Contracts](api-and-contracts.md).

---

## Sentinel Core

| Area | Features |
|---|---|
| Message API | Authenticated `POST /message` endpoint using the standard Sentinel message envelope |
| AI provider path | LiteLLM-direct chat completions through LM Studio by default |
| Provider fallback | Optional Claude fallback for connectivity failures when configured |
| Model safety | Model registry, context-window enforcement, and context truncation before provider calls |
| Persona | Reads `sentinel/persona.md` from Obsidian at startup and per message, with fallback only when the vault is unreachable |
| Recall | Assembles self context, recent session history, and warm semantic recall for message processing |
| Note filing | Best-effort chat note filing for substantive messages through the note classifier |
| Inbox | `GET /inbox`, classify, and discard flows for unprocessed capture items |
| Vault sweep | Admin-gated dry-run/live sweep with runtime model readiness checks before destructive moves |
| Module gateway | Module registration, module listing, and authenticated GET/POST proxying under `/modules/{name}/{path}` |
| Runtime status | `/health`, `/status`, and `/context/{user_id}` diagnostic endpoints |
| Browser access | CORS and Private Network Access support for Foundry and browser-based integrations |

---

## Discord Interface

| Area | Features |
|---|---|
| Slash command | `/sen <message>` creates a public thread and sends the message to Sentinel Core |
| Thread continuation | Replies inside Sentinel-created threads continue the same conversation path |
| Help routing | Short natural-language help requests return local command help without calling Core |
| Second-brain verbs | `:capture`, `:seed`, `:next`, `:health`, `:goals`, `:reminders`, `:ralph`, `:pipeline`, `:reweave`, `:check`, `:rethink`, `:refactor`, `:tasks`, `:stats`, `:graph`, `:learn`, `:remember`, `:connect`, `:review`, `:revisit` |
| Note intake verbs | `:note`, `:inbox`, `:inbox classify`, and `:inbox discard` |
| Admin verbs | `:vault-sweep`, `:vault-sweep dry-run`, `:vault-sweep force`, and `:vault-sweep status` gated by `SENTINEL_ADMIN_USER_IDS` |
| Plugin verbs | `:plugin:help`, `:plugin:health`, `:plugin:ask`, `:plugin:architect`, `:plugin:setup`, `:plugin:tutorial`, `:plugin:upgrade`, `:plugin:reseed`, `:plugin:add-domain`, `:plugin:recommend` |
| Pathfinder dispatch | Registry-backed `:pf <noun> <verb>` dispatch with typed text/embed/file outcomes |
| Foundry notifications | Internal notification endpoint used by the Pathfinder Foundry event bridge |

---

## Pathfinder 2e Module

The Pathfinder module registers with Sentinel Core as `pathfinder` and is normally started with the Docker Compose profile `pf2e`.

| Area | Features |
|---|---|
| NPC profiles | Create, update, show, relate, and bulk-import NPCs into `mnemosyne/pf2e/npcs/` |
| NPC outputs | Foundry actor JSON export, Midjourney token prompt, token image upload, structured stat block, printable PDF stat card |
| Dialogue | In-character NPC dialogue through `:pf npc say`, including multi-NPC scenes and recent thread history |
| Monster harvest | PF2e monster component reports with Medicine DCs, craftable outputs, Crafting DCs, and value estimates |
| Rules lookup | PF2e Remaster rule query, cached topic listing, cached ruling display, and recent history |
| Rules cache | Reuses sourced rulings when retrieval confidence is high; flags generated rulings for verification |
| Session notes | Start, show, and end session notes under `mnemosyne/pf2e/sessions/` with recap support |
| Archive ingest | Admin-only PF2e archive import with dry-run/live modes, item limits, force mode, large-import confirmation, and reports |
| Cartosia alias | Deprecated `:pf cartosia` command forwards to the archive ingest path |
| Foundry events | Receives Foundry events and forwards Discord notifications for play-table activity |
| Foundry actor pull | Lists Sentinel NPCs and returns PF2e actor JSON for Foundry import |
| Foundry chat memory | Imports Foundry chat logs, writes reports, projects player chat maps, appends NPC chat history, and dedupes per record per target |
| Per-player memory | Player onboarding, note, ask, NPC knowledge, recall, todo, style, canonize, and cancel flows |
| Player isolation | Per-player writes are constrained to that player's namespace under `mnemosyne/pf2e/players/{slug}/` |
| Onboarding dialog | Multi-step Discord onboarding persists drafts across bot restarts and supports cancellation |

---

## Foundry VTT Integration

| Area | Features |
|---|---|
| Static client assets | Pathfinder serves Foundry client assets under `/foundry/static` |
| Browser CORS | Allows local Foundry and Forge origins with explicit `X-Sentinel-Key` support |
| Private Network Access | Preflight support for browser requests from public/Forge contexts to local network services |
| Webhook fallback | Foundry settings support Discord webhook fallback when Sentinel is not reachable |
| Actor import | Foundry client can list Sentinel NPCs and import selected actor JSON |
| Event bridge | Foundry client posts play events to Sentinel for narration and Discord notification |

---

## Obsidian Vault Features

| Area | Features |
|---|---|
| Human-owned storage | Notes are plain markdown in the operator's Obsidian vault |
| Persona source | `sentinel/persona.md` controls Sentinel voice without redeploying |
| Core memory | Self context, reminders, recent sessions, warm recall, inbox, and classified notes |
| Session history | Core writes exchange summaries under `ops/sessions/{date}/` |
| Sweep safety | Protected namespaces prevent identity/security files from being moved by sweep flows |
| Pathfinder namespace | Pathfinder writes under `mnemosyne/pf2e/` |
| Import state | Foundry chat import dedupe state stays beside the imported inbox at `.foundry_chat_import_state.json` |

---

## Planned But Not Shipped

These entries are present in the product roadmap or compose wrapper but are not shipped as working modules in this baseline:

| Area | Status |
|---|---|
| Music Lesson Tracker | Planned |
| Coder Interface | Planned |
| Personal Finance | Planned |
| Stock Trader | Planned |
| Media Discovery | Future |
| Apple Messages bridge | Mentioned as an interface direction; not part of the validated Docker stack |
