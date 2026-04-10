# Feature Research

**Domain:** Self-hosted personal AI assistant platform with persistent memory and pluggable modules
**Researched:** 2026-04-10
**Confidence:** MEDIUM-HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features that any self-hosted AI assistant must have. Missing these makes the platform feel broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Multi-provider LLM support | Open WebUI, AnythingLLM, and every major project supports switching between local and cloud models via OpenAI-compatible API. Users expect provider flexibility. | LOW | Already planned via LM Studio + Claude API. Use OpenAI-compatible protocol as the common interface. |
| Conversation history persistence | Every comparable tool (Open WebUI, SillyTavern, AnythingLLM) stores chat history. Without it, the assistant has amnesia. | LOW | Store in Obsidian vault as structured markdown. This is the project's core differentiator path. |
| Cross-session context recall | Users expect "you told me last week that..." to work. Mem0, SillyTavern CharMemory, and Open WebUI RAG all provide this. | HIGH | This is the Mnemosyne value prop. Requires retrieval from vault before prompt construction. RAG or structured search against Obsidian notes. |
| Streaming responses | Open WebUI, ChatGPT, Claude all stream token-by-token. Waiting for full completion feels broken in 2026. | MEDIUM | LM Studio supports streaming via SSE. FastAPI supports StreamingResponse. Wire these together. |
| Message envelope / structured I/O | Every multi-interface bot system needs a stable contract between interfaces and core. | LOW | Already planned. Define once, validate with Pydantic. |
| Error handling with user-facing feedback | When the LLM is down, the model isn't loaded, or Obsidian is unreachable, the user needs to know what happened, not get silence. | LOW | Health checks for each dependency. Return structured error envelopes. |
| Docker Compose single-command startup | Every self-hosted tool (Open WebUI, AnythingLLM, n8n) ships with `docker compose up` as the primary install path. | LOW | Already planned. Base compose + override pattern. |
| Provider configuration via env vars | Standard pattern across all comparable tools. No hardcoded API keys or URLs. | LOW | Already planned. |

### Differentiators (Competitive Advantage)

Features that make Sentinel of Mnemosyne distinct from Open WebUI/AnythingLLM/SillyTavern.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Obsidian vault as the memory substrate | Other tools use SQLite, ChromaDB, or proprietary formats. Obsidian vault means: your memory is human-readable markdown, editable outside the AI, version-controllable with git, and survives the project dying. No vendor lock-in on your own memories. | MEDIUM | Use Obsidian Local REST API for reads/writes. Structure vault with clear conventions (`/sentinel/sessions/`, `/sentinel/entities/`, `/modules/pf2e/`, etc.). |
| Write-back memory loop | Most AI assistants retrieve context but don't write structured summaries back. Sentinel writes session summaries, entity updates, and learned preferences back to the vault after each interaction. The next conversation starts smarter. | HIGH | Requires post-conversation summarization pipeline. LLM generates summary, system writes to vault via REST API. Critical to get the write format right early. |
| Module system via Docker Compose overrides | AnythingLLM has workspaces, Open WebUI has plugins, but neither uses the Docker Compose override pattern for full-stack modules (own container, own storage, own compose fragment). This enables community-publishable modules. | MEDIUM | Each module = a compose override file + container + optional vault directory. MODULE-SPEC.md defines the contract. |
| Domain-specific modules with deep integration | SillyTavern does RP characters. Open WebUI does general chat. Nobody does Pathfinder 2e DM assistance + music practice tracking + personal finance + stock research in one coherent platform with shared memory. | HIGH | Each module is independently valuable but shares the memory substrate. Cross-module queries become possible ("How much did I spend on RPG books this month?"). |
| Natural language queries across personal data | Asking "what did I practice last Tuesday?" or "how much did I spend on dining out in March?" in Discord, getting an answer from your own data. No cloud service sees your data. | HIGH | Requires good retrieval from Obsidian vault. Structured data (finance, music logs) needs queryable format in vault. |
| AI-assisted transaction categorization with correction learning | YNAB and Copilot Money do this in the cloud. Doing it locally with your own LLM, where corrections improve future categorizations, is rare. | HIGH | OFX import -> LLM categorizes -> user corrects -> corrections stored as training signal for future categorization. |
| Autonomous stock research with thesis documentation | AI researches watchlist stocks, writes thesis notes to Obsidian with rationale. Full audit trail of every decision. No existing self-hosted tool does this. | HIGH | Alpaca API for data + execution. Personal rules file enforced before every decision. PDT counter. All rationale written to vault. |
| Multi-interface convergence | Same AI, same memory, accessible from Discord, Apple Messages, or future interfaces. SillyTavern is web-only. Open WebUI is web-only. | MEDIUM | Standard message envelope means any interface that can POST JSON can talk to Sentinel. Discord bot and Apple Messages bridge are first two. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem appealing but create disproportionate complexity or risk.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Multi-user / multi-tenant | "My family could use it too" | Adds auth complexity, data isolation, permission systems, and multiplies every design decision. Personal tool, not a platform. | Run separate instances if needed. Or add simple user switching later (not multi-tenant). |
| Real-time voice interface | Home Assistant does voice, seems cool | Requires TTS/STT pipeline, streaming audio, wake word detection. Massive complexity for incremental value when Discord voice exists. | Defer to v2+. Discord already handles voice channels. |
| Web UI dashboard | "Every tool has a web UI" | Open WebUI and AnythingLLM already exist. Building another chat UI is undifferentiated work. The value is in the backend + memory + modules. | Use Discord/Messages as the primary UI. If a web UI is ever needed, embed Open WebUI pointing at Sentinel's API. |
| Vector database (ChromaDB/Qdrant) for memory | "RAG needs vectors" | Adds another infrastructure dependency. Obsidian Local REST API already has full-text search. For a personal vault (not millions of docs), full-text search + structured markdown conventions are sufficient. | Start with Obsidian REST API search. Add vector embeddings only if retrieval quality proves insufficient after real usage. |
| Real-time market data streaming | "Need live prices for trading" | WebSocket market data feeds are complex, require always-on connections, and burn resources. Paper trading doesn't need millisecond updates. | Use Alpaca REST API for periodic data pulls. Batch research loops on configurable intervals (hourly/daily). |
| Crypto / options / margin trading | "Why limit to equities?" | Regulatory complexity, higher risk of catastrophic loss, more complex order types, different market hours. | Equities and ETFs only in v1. Explicit scope boundary. |
| Plugin marketplace / dynamic loading | "Let people install plugins at runtime" | Dynamic plugin loading is a security and stability nightmare. Version conflicts, untested combinations, supply chain attacks. | Static module system via Docker Compose overrides. Adding a module = adding a compose file + pulling a container. Explicit, auditable, reproducible. |
| Obsidian Sync / cloud vault backup | "What if my disk dies?" | Obsidian Sync is paid and proprietary. Defeats self-hosted principle. | Git-based vault backup. Or iCloud sync of vault folder if multi-device is needed. |
| Fine-tuning local models on personal data | "The AI should learn from my data" | Fine-tuning requires GPU resources, training pipelines, evaluation frameworks. The correction-learning loop for categorization is sufficient for personalization. | Use in-context learning (RAG + structured prompts with user corrections) instead of fine-tuning. Store learned preferences as vault documents the LLM reads at prompt time. |

## Feature Dependencies

```
[LM Studio / Provider Config]
    └──requires──> [Message Envelope Format]
                       └──requires──> [Sentinel Core (FastAPI)]
                                          ├──requires──> [Obsidian REST API Access]
                                          │                  ├──enables──> [Context Retrieval (Read)]
                                          │                  └──enables──> [Memory Write-back]
                                          │                                    └──enables──> [Cross-session Recall]
                                          ├──enables──> [Discord Bot Interface]
                                          │                  └──enables──> [Apple Messages Bridge]
                                          └──enables──> [Module System]
                                                             ├──enables──> [PF2e Module]
                                                             ├──enables──> [Music Module]
                                                             ├──enables──> [Finance Module]
                                                             │                  └──requires──> [OFX Import Pipeline]
                                                             └──enables──> [Stock Research Module]
                                                                                └──requires──> [Alpaca API Integration]

[Context Retrieval] + [Memory Write-back] = [Memory Loop] (the core differentiator)

[Finance Module] ──enhances──> [Stock Research Module] (shared financial context)

[Pi Harness (RPC)] ──wraps──> [LM Studio / Provider]
```

### Dependency Notes

- **Memory Loop requires Obsidian REST API:** All context retrieval and write-back goes through the REST API. This must be stable before any module can use memory.
- **All modules require Core + Message Envelope:** No module works without the routing layer.
- **Discord bot is the first interface:** Validates the message envelope contract. Apple Messages bridge is second because it requires a Mac-side component (more complex).
- **Finance and Stock modules share context:** A user's financial situation informs stock research decisions. Cross-module vault queries make this possible.
- **Pi Harness wraps LLM access:** Core calls Pi via RPC, Pi calls LM Studio. The Pi layer handles conversation loop, tool calls, and skill dispatch.

## MVP Definition

### Launch With (v0.1-v0.2)

Minimum viable product: send a message, get an AI response that knows your history.

- [x] Sentinel Core container accepts message envelopes, routes to Pi/LLM, returns responses
- [x] LM Studio as AI backend via OpenAI-compatible API
- [x] Docker Compose base structure with override pattern
- [x] Obsidian REST API integration for vault reads
- [x] Context retrieval: pull relevant notes before building prompt
- [x] Memory write-back: session summaries written to vault after interaction
- [x] Cross-session memory demonstrated (references a prior conversation)

### Add After Validation (v0.3-v0.5)

Once core memory loop works, add interfaces and first domain module.

- [ ] Discord bot interface — validates multi-interface architecture
- [ ] Apple Messages bridge — second interface proves the pattern
- [ ] Provider fallback (local LLM -> Claude API) — when local model can't handle the query
- [ ] PF2e module — first domain module, validates module contract
- [ ] Streaming responses — UX polish for interactive use

### Future Consideration (v0.6+)

Features that depend on core being solid.

- [ ] Music practice module — simpler domain, good second module test
- [ ] Finance module with OFX import — complex but high personal value
- [ ] Stock research module — highest complexity, highest risk
- [ ] Live trading — only after extensive paper trading validation
- [ ] MODULE-SPEC.md for community modules — only after internal modules prove the pattern

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Core message routing (FastAPI + Pi) | HIGH | MEDIUM | P1 |
| Obsidian vault read/write | HIGH | LOW | P1 |
| Cross-session memory recall | HIGH | HIGH | P1 |
| Session summary write-back | HIGH | MEDIUM | P1 |
| Streaming responses | MEDIUM | MEDIUM | P1 |
| Discord bot interface | HIGH | MEDIUM | P1 |
| Provider fallback (local -> cloud) | MEDIUM | LOW | P2 |
| Apple Messages bridge | MEDIUM | HIGH | P2 |
| PF2e DM module | MEDIUM | MEDIUM | P2 |
| Music practice module | LOW | LOW | P2 |
| Finance OFX import + categorization | HIGH | HIGH | P2 |
| Natural language spending queries | HIGH | MEDIUM | P2 |
| Stock research loop | MEDIUM | HIGH | P3 |
| Paper trading with audit trail | MEDIUM | HIGH | P3 |
| Live trading | LOW | MEDIUM | P3 |
| MODULE-SPEC.md / community docs | LOW | LOW | P3 |

**Priority key:**
- P1: Must have for launch (validates the core value proposition)
- P2: Should have, add once core is stable
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Open WebUI | AnythingLLM | SillyTavern | Home Assistant AI | Sentinel (Planned) |
|---------|-----------|-------------|-------------|-------------------|-------------------|
| Multi-provider LLM | Yes (Ollama, OpenAI, Claude, etc.) | Yes (local + cloud) | Yes (many backends) | Yes (Ollama, OpenAI, OpenRouter) | Yes (LM Studio + Claude API) |
| RAG / document ingestion | Yes (PDF, docs) | Yes (workspaces with docs) | Via extensions | Limited | Obsidian vault as native knowledge base |
| Persistent memory | Chat history + RAG | Workspace memory + agent memory | CharMemory extension, Smart Context | Conversation history | Obsidian write-back loop (human-readable, editable) |
| Memory format | SQLite/internal | Internal DB | ChromaDB + lorebooks | Internal | Markdown files in Obsidian (portable, version-controllable) |
| Plugin/extension system | Python plugins | Agent skills | Extensions (JS) | Integrations (YAML) | Docker Compose overrides (full-stack modules) |
| Multi-interface | Web UI only | Web UI + API | Web UI only | Voice + web + app | Discord, Apple Messages, extensible |
| Domain modules | No | No | RP/character focused | Smart home focused | PF2e, Music, Finance, Stock Research |
| Self-hosted | Yes | Yes | Yes | Yes | Yes |
| Data ownership | SQLite files | Internal storage | Local files | Internal DB | Obsidian vault (markdown, git-friendly) |
| Community | 128K+ GitHub stars | Growing | Large RP community | Massive (smart home) | Greenfield |

**Key competitive insight:** No existing tool combines persistent human-readable memory (Obsidian) + multi-interface access (Discord/Messages) + domain-specific modules (finance, RPG, music). Open WebUI and AnythingLLM are general-purpose chat interfaces. SillyTavern is RP-focused. Home Assistant is smart-home-focused. Sentinel's niche is the personal assistant that remembers everything in a format you own and can read.

## Domain-Specific Feature Details

### Discord Bot UX (for interface design)

**Patterns that work well:**
- Slash commands (`/ask`, `/remember`, `/finance`, `/pf2e`) for structured interactions
- Thread-based conversations for multi-turn exchanges (keeps channels clean)
- Rich embeds for formatted responses (tables, code blocks, images)
- Buttons/selects for confirmations (approve trade, correct categorization)
- DM support for private queries (finance, personal notes)

**Patterns that work poorly:**
- Prefix commands (e.g., `!ask`) -- deprecated pattern, accessibility issues
- Long responses in main channels -- use threads or DMs
- No typing indicator -- users think the bot is dead during LLM inference
- Requiring exact syntax -- natural language should work for most queries

### Personal Finance Features (for Finance Module)

**High-value features users love:**
- Auto-categorization of transactions (YNAB, Copilot Money pattern)
- Correction learning: user fixes a category, system remembers for next time
- Natural language spending queries ("how much on groceries this month?")
- Monthly/weekly spending summaries auto-generated
- Budget alerts when approaching limits
- OFX/CSV import from bank exports (78% of users prefer zero-touch imports)

**Lower-value features to defer:**
- Plaid/bank API direct connections (complex, security-sensitive, regulatory burden)
- Investment tracking (overlap with stock module)
- Bill prediction/reminders (nice but not core)

### Stock Research Features (for Stock Research Module)

**High-value data sources:**
- Alpaca API: free market data, paper/live trading, commission-free
- SEC EDGAR: earnings reports, 10-K/10-Q filings (free, public)
- Yahoo Finance API (unofficial): fundamental data, historical prices
- News aggregation: financial news sentiment analysis

**High-value features:**
- Watchlist management with AI-generated thesis notes
- Earnings analysis: compare reported vs estimates
- Personal rules file: enforced constraints before every decision
- Full audit trail: every decision rationale written to Obsidian
- PDT rule counter: hard limit enforcement for day trading
- Paper trading sandbox: test strategies risk-free

**Explicitly out of scope (per PROJECT.md):**
- Real-time HFT (high-frequency trading)
- Options, crypto, margin, futures
- Automated live trading without human approval

## Sources

- [Open WebUI](https://openwebui.com/) -- feature reference for self-hosted AI chat (128K+ GitHub stars)
- [AnythingLLM](https://docs.useanything.com/) -- workspace/agent/memory architecture reference
- [SillyTavern](https://docs.sillytavern.app/) -- memory persistence patterns (CharMemory, Smart Context, ChromaDB)
- [Home Assistant AI](https://www.home-assistant.io/blog/2025/09/11/ai-in-home-assistant/) -- local LLM integration, MCP, multi-agent patterns
- [Obsidian RAG integration](https://dasroot.net/posts/2025/12/rag-personal-knowledge-management-obsidian-integration/) -- vault-based RAG patterns
- [Alpaca Markets](https://alpaca.markets/) -- paper trading API, Python SDK
- [Mem0](https://mem0.ai/) -- persistent memory layer for AI applications
- [n8n self-hosted AI workflows](https://ngrok.com/blog/self-hosted-local-ai-workflows-with-docker-n8n-ollama-and-ngrok-2025) -- Docker Compose AI stack patterns
- [Docker Compose for AI Agents](https://www.docker.com/blog/build-ai-agents-with-docker-compose/) -- compose-based agent architecture

---
*Feature research for: Sentinel of Mnemosyne*
*Researched: 2026-04-10*
