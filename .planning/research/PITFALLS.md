# Pitfalls Research

**Domain:** Self-hosted AI assistant platform with local LLM, Obsidian memory, modular Docker architecture
**Researched:** 2026-04-10
**Confidence:** HIGH (most pitfalls verified across multiple sources and documented community issues)

## Critical Pitfalls

### Pitfall 1: Pi-mono Dependency Churn Breaks Your Integration Layer

**What goes wrong:**
Pi-mono releases every 2-4 days with frequent breaking changes. v0.65.0 removed session events, v0.63.0 changed API key methods, v0.62.0 restructured tool definitions. Your Pi harness wrapper breaks every few weeks if you track latest. If you pin a version, you miss bug fixes and model support updates.

**Why it happens:**
Pi-mono is a solo-developer project (badlogic/Mario Zechner) under active rapid iteration. The project is pre-1.0 and its API surface is not stable. Building a production system on top of a pre-1.0 dependency with weekly breaking changes is inherently fragile.

**How to avoid:**
- Pin to a specific npm version from day one (PROJECT.md already calls for this -- enforce it)
- Define a narrow interface contract between Sentinel Core and the Pi harness: stdin/stdout JSONL with a fixed envelope schema
- Build an adapter layer (Pi Client) that absorbs Pi's API changes. The rest of Sentinel never imports Pi types directly
- Schedule monthly "Pi upgrade" tasks where you bump the pin, run integration tests, and update the adapter
- Write integration tests against the JSONL contract, not Pi internals
- Have a documented fallback: if Pi breaks badly, the adapter can be swapped to call LM Studio's OpenAI-compatible API directly (bypassing Pi entirely)

**Warning signs:**
- Pi release notes mention "breaking" or "removed" keywords
- Your Pi container fails to build after `npm install` without code changes
- JSONL message format changes between Pi versions

**Phase to address:**
Phase 1 (v0.1) -- establish the adapter pattern before any other code depends on Pi. The adapter is the single point of contact.

---

### Pitfall 2: Obsidian Vault Memory Becomes Unusable Noise at Scale

**What goes wrong:**
Every AI interaction writes session summaries to the vault. Within months you have thousands of notes. Context retrieval degrades: the AI pulls irrelevant notes, misses relevant ones, or blows past token limits trying to include too much. A 500-note vault is 112K-375K tokens -- far beyond any context window. Grep-based search returns too many false positives once the vault has enough content.

**Why it happens:**
Flat-file markdown search is linear. No ranking, no relevance scoring, no semantic understanding. The Obsidian Local REST API's search can timeout on large vaults. Without curation, vaults fill with noise -- every session dumps a summary whether it was meaningful or not.

**How to avoid:**
- Implement a tiered memory architecture from the start:
  - Hot memory: last N interactions, loaded automatically (small, always relevant)
  - Warm memory: semantic search results from vault (loaded on demand)
  - Cold memory: full vault archive (never loaded into context directly)
- Use the Obsidian REST API's search endpoint for keyword retrieval, but plan to add vector embeddings (ChromaDB or similar) once the vault exceeds ~500 notes
- Write selectively: not every interaction deserves a vault note. Define a "memory threshold" -- only write when the interaction contains new facts, decisions, or preferences
- Structure vault paths by domain (`/pathfinder/`, `/music/`, `/finance/`, `/trading/`) so retrieval can be scoped
- Set a token budget per retrieval: never inject more than N tokens of context, regardless of how much the search returns

**Warning signs:**
- Context retrieval takes more than 2 seconds
- AI responses reference irrelevant past conversations
- Obsidian REST API search requests timeout
- Monthly vault growth exceeds 100 notes

**Phase to address:**
Phase 2 (v0.2) -- memory layer design. The tiered architecture must be the foundation, not bolted on later. Vector search can be deferred to a later phase but the hook points must exist from v0.2.

---

### Pitfall 3: LM Studio Context Window Crashes and Silent Truncation

**What goes wrong:**
LM Studio's API crashes when input exceeds the model's context window instead of truncating gracefully. The API is still in beta. Third-party tools consistently fail to detect LM Studio's actual context length, defaulting to wrong values. When you switch models (e.g., from a 4K context model to a 32K model), your prompt construction logic may not adapt, either wasting capacity or overflowing.

**Why it happens:**
LM Studio exposes an OpenAI-compatible API, but compatibility is incomplete. Context length detection is unreliable across integrations. Different models have different context windows, and nothing in the API response tells you what the limit is before you hit it.

**How to avoid:**
- Build a model configuration registry in Sentinel Core that maps model names to their context windows, token limits, and capabilities
- Always count tokens before sending to LM Studio. Use tiktoken or a similar tokenizer. Never trust that the API will handle overflow
- Implement pre-flight validation: if prompt + expected response > (context_window * 0.85), truncate context or split the request
- Test model switching explicitly: have an integration test that loads each configured model and verifies basic request/response
- Set a hard timeout on LM Studio API calls (30s default, configurable). If it hangs instead of erroring, kill and retry with reduced context

**Warning signs:**
- LM Studio process crashes or returns exit code 18446744072635810000 (documented overflow bug)
- API calls hang indefinitely
- Responses become incoherent or cut off mid-sentence (silent context overflow)
- Token count tracking shows requests near context limit

**Phase to address:**
Phase 1 (v0.1) for basic token counting and timeouts. Phase 4 (v0.4) for full provider configuration with model registry and multi-provider fallback.

---

### Pitfall 4: Apple Messages Bridge is Fragile, Undocumented, and Actively Hostile

**What goes wrong:**
Apple provides no public API for iMessage. AppleScript-based Messages automation has been broken since Yosemite (2014) and Apple periodically breaks it further with OS updates. TCC (Transparency, Consent, and Control) permissions block automation silently. The bridge only works when Messages.app is running and the Mac is logged in. macOS updates can revoke automation permissions without notice.

**Why it happens:**
Apple actively discourages programmatic iMessage access. AppleScript is a dying technology that Apple maintains minimally. Each macOS version changes security permissions, and Messages.app's AppleScript dictionary is incomplete and buggy.

**How to avoid:**
- Treat the Apple Messages interface as a "best effort" tier-2 interface, not a reliable primary channel
- Discord must be the primary interface; Messages is a convenience addon
- Build the Messages bridge as a completely isolated Mac-side process (not containerized -- it must run on the Mac with Messages.app access)
- Use an HTTP bridge pattern: Mac-side script polls or listens, forwards to Sentinel Core via HTTP, receives response, sends back via AppleScript
- Pin to a specific macOS version for testing. Document exactly which TCC permissions are required. Script the permission granting if possible
- Build a health check endpoint that verifies Messages.app is running and AppleScript can send a test message
- Accept that macOS updates will break this. Budget time after every major macOS release to fix the bridge

**Warning signs:**
- AppleScript commands return errors about "not allowed to send events"
- Messages.app is not running and bridge silently queues or drops messages
- macOS upgrade changelog mentions TCC or automation changes
- Outgoing messages appear in Messages.app but don't actually send

**Phase to address:**
Phase 3 (v0.3) -- but scope it as explicitly experimental. Discord should be fully working before any time is spent on Messages. The Messages bridge should be behind a feature flag.

---

### Pitfall 5: Trading Module Regulatory Violations from AI Autonomy

**What goes wrong:**
An AI trading agent executes trades that violate PDT rules (4+ day trades in 5 business days with < $25K equity), creates wash sales (repurchasing substantially identical securities within 30 days of a loss), or generates errant/duplicate orders during connectivity issues. Alpaca's API rejects some of these at the API level (403 errors), but not all -- wash sale tax implications are your problem, not Alpaca's.

**Why it happens:**
AI agents optimize for the objective you give them without understanding regulatory context. The agent may see "buy the dip" as a valid strategy without tracking that it sold the same security at a loss 10 days ago. Connectivity glitches can cause duplicate order submissions. Paper trading doesn't enforce tax rules, so you don't discover wash sale issues until live trading.

**How to avoid:**
- Implement a pre-trade validation layer that checks EVERY order against:
  - PDT counter: track day trades in a rolling 5-business-day window, reject if >= 3 (leave margin for safety)
  - Wash sale detector: maintain a 61-day window (30 days before + 30 days after) of all loss-triggering sales, block repurchase of substantially identical securities
  - Duplicate order detector: reject orders for the same symbol within N seconds
  - Position limit enforcer: max percentage of portfolio in any single position
- The rules file format (mentioned in PROJECT.md) is the right approach -- make it a hard gate, not advisory
- Paper trading must run for 30 days minimum with the full validation layer active
- Human approval flow is mandatory for live trading (PROJECT.md already requires this)
- Log every trade decision with full rationale to Obsidian for audit
- Build an emergency stop that kills all open orders and prevents new ones

**Warning signs:**
- Paper trading logs show > 3 day trades in a 5-day window
- Agent buys a security it sold at a loss in the past 30 days
- Duplicate order IDs in execution logs
- Trade execution during market hours without human confirmation (live mode)

**Phase to address:**
Phase 9 (v0.9) for paper trading with full validation. Phase 10 (v0.10) for live with human approval. The validation layer must exist BEFORE the first paper trade.

---

### Pitfall 6: Docker Compose Override File Sprawl Creates an Untestable System

**What goes wrong:**
Each module adds an override file. By v0.8 you have 6+ override files that must compose correctly. Service name conflicts emerge. Shared networks have implicit dependencies. One override changes a volume mount that another override assumed was stable. Testing requires spinning up the full stack because overrides have cross-dependencies. The "base compose never changes" rule breaks when a module needs a new shared service.

**Why it happens:**
Docker Compose override files merge at the YAML level with complex precedence rules. There's no type checking or validation that overrides compose correctly. Each module author (even if it's just you) makes assumptions about what the base provides.

**How to avoid:**
- Define a strict base compose contract: which networks exist, which volumes are shared, which ports are reserved
- Use Docker Compose profiles instead of (or in addition to) override files for optional services
- Establish naming conventions: all module services prefixed with module name (`pathfinder-`, `music-`, `finance-`, `trader-`)
- Create a compose validation script that merges all active overrides and checks for port conflicts, network mismatches, and missing dependencies
- Test each module in isolation: `docker compose -f docker-compose.yml -f docker-compose.pathfinder.yml up` must work without other module overrides
- Document the base compose contract in a MODULE-SPEC.md (already planned for v1.0 -- move this earlier)

**Warning signs:**
- `docker compose config` shows unexpected merged results
- Services fail to start when a new override is added
- Port conflicts between modules
- Module works alone but fails when composed with other modules
- You can't remember which override files need to be active for a given workflow

**Phase to address:**
Phase 1 (v0.1) for base compose contract. Phase 5 (v0.5) when the first module override lands -- validate the pattern works before adding more modules.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hardcoding LM Studio URL | Faster v0.1 | Can't switch providers, can't test without LM Studio running | Never -- use env vars from day one |
| Skipping token counting | Simpler prompt construction | Context overflow crashes, unpredictable behavior | Never -- basic counting is cheap |
| Writing all interactions to vault | Complete history | Vault noise, slow retrieval, wasted storage | Only during initial development (< 1 month) |
| Single-file Pi adapter | Faster initial integration | Becomes unmaintainable as Pi API evolves | Acceptable for v0.1, refactor by v0.2 |
| No message deduplication in Discord bot | Simpler bot code | Duplicate AI responses from retry storms | Never -- Discord retries are common |
| Shared Docker network for all services | Simpler compose config | Any service can reach any other service, security boundary violation | Acceptable for v0.1-v0.3, isolate by v0.4 |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| LM Studio API | Assuming full OpenAI API compatibility | Test each endpoint you use. Chat completions work; function calling support varies by model. Don't assume streaming works the same way. |
| Obsidian REST API | Ignoring the 200-request-per-15-minute rate limit | Batch reads where possible. Cache vault content in Sentinel Core. Don't hit the API on every incoming message. |
| Obsidian REST API | Writing files while Obsidian is syncing | Use the API's atomic write endpoints. Avoid direct filesystem writes. Check for sync conflicts in the vault. |
| Discord API | Not handling the 2000 character limit | AI responses will frequently exceed 2000 chars. Implement chunking at natural boundaries (paragraphs, code blocks) or use embeds for structured data. |
| Discord API | Ignoring interaction timeouts | Slash commands must acknowledge within 3 seconds. Defer the response, then edit it when the AI finishes. |
| Alpaca API | Not distinguishing paper vs live environments | Use completely separate configuration objects. Never let env var confusion route a paper trade to live. Use different API key variable names. |
| Apple Messages | Assuming AppleScript is synchronous | Sending is fire-and-forget. You cannot confirm delivery. Build the bridge assuming messages may silently fail. |
| Pi harness (stdin/stdout) | Not handling Pi process crashes | Pi can crash, OOM, or hang. Implement process supervision with restart logic and a circuit breaker that falls back to direct LM Studio calls. |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full vault search on every message | Response latency > 5s, Obsidian REST API timeouts | Scoped search by domain, cached recent context, token budget | > 500 vault notes |
| Loading full conversation history into context | Token overflow, incoherent responses | Sliding window of last N turns, summarize older history | > 20 conversation turns |
| Synchronous Pi harness calls blocking FastAPI | Second request waits for first to complete, timeouts cascade | Async process pool, queue incoming requests, set per-request timeouts | > 2 concurrent users/interfaces |
| Docker volume mounts for Obsidian vault | File locking conflicts, slow I/O on macOS with bind mounts | Use the REST API exclusively, never mount the vault directory into containers | Immediately on macOS (known Docker for Mac I/O issue) |
| Unthrottled Discord message processing | Rate limit 429 errors, temporary bot ban | Queue incoming messages, process sequentially with backpressure | > 50 messages/second (unlikely for personal use, but bot storms happen) |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing Alpaca API keys in docker-compose.yml | Live trading credentials in git history | Use `.env` files excluded from git, or Docker secrets. Never commit API keys. |
| Running Pi harness with full filesystem access | Pi executes arbitrary code (by design). A malicious prompt could read/write host files | Run Pi container with minimal volume mounts. No access to vault, config, or trading credentials from inside Pi container. |
| Shared `X-Sentinel-Key` across all interfaces | One compromised interface key allows full system access | Use per-interface keys. Discord gets one key, Messages gets another. Revoke individually. |
| Not validating OFX file contents before parsing | Malformed OFX files could exploit parser vulnerabilities | Validate file size limits, run parser in a sandboxed context, sanitize output before storing in vault |
| Apple Messages bridge running as root or admin | Automation scripts with elevated privileges | Run the bridge under a dedicated macOS user with minimal permissions. Only grant Messages automation access. |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| AI responses that start with "As an AI assistant..." | Breaks immersion, especially for Pathfinder DM module | System prompts must establish persona. Strip common AI disclaimers. |
| No feedback during slow AI responses | User thinks bot is broken, sends duplicate messages | Send a "thinking..." indicator immediately. For Discord, use deferred responses. |
| Slash command explosion (one per feature) | Overwhelming command list, hard to discover | Use a small set of base commands with natural language routing. `/ask [anything]` beats `/pathfinder-npc-create`, `/pathfinder-session-note`, etc. |
| Showing raw AI errors to the user | Confusing technical messages | Catch all errors, present friendly messages. Log the real error for debugging. |
| No way to correct AI memory | AI remembers wrong information forever | Provide explicit "forget this" and "correct: X should be Y" commands that modify vault entries |
| Pathfinder module using game mechanics jargon the AI hallucinates | Wrong Pathfinder 2e rules cited confidently | Ground the module with actual PF2e rules data (SRD). Don't rely on the LLM's training data for game mechanics. |

## "Looks Done But Isn't" Checklist

- [ ] **Core loop (v0.1):** Handles the case where LM Studio is not running or has no model loaded -- verify graceful degradation, not a crash
- [ ] **Memory layer (v0.2):** Handles Obsidian not running -- the REST API requires Obsidian desktop app. Verify the system works (degraded) without vault access
- [ ] **Discord bot (v0.3):** Handles messages that arrive while the bot is restarting -- verify no messages are silently dropped
- [ ] **Discord bot (v0.3):** Handles the 2000-character response limit -- verify with a response that's exactly 2001 characters
- [ ] **Pi harness (v0.1):** Handles Pi process hanging indefinitely -- verify timeout kills and restarts the process
- [ ] **Finance module (v0.8):** Handles OFX files from multiple banks with different formatting -- test with at least 3 different bank exports
- [ ] **Finance module (v0.8):** Handles duplicate transaction detection across OFX imports -- same transaction imported twice should not create duplicate entries
- [ ] **Trading module (v0.9):** Handles Alpaca API downtime during market hours -- verify queued orders don't fire unexpectedly when connection resumes
- [ ] **Trading module (v0.9):** Handles partial fills -- verify position tracking accounts for partially filled orders, not just filled/unfilled
- [ ] **Live trading (v0.10):** Emergency stop actually stops everything -- verify with a test during active paper trading that the kill switch works within 5 seconds

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Pi-mono breaking update breaks harness | LOW | Revert Pi npm version pin. Adapter pattern limits blast radius to one file. |
| Vault polluted with noise notes | MEDIUM | Write a cleanup script that archives notes below a quality threshold. Add the write-selectivity filter retroactively. |
| LM Studio context overflow corrupts session | LOW | Session state is stateless by design (each request is independent). Just retry with smaller context. |
| Apple Messages bridge breaks after macOS update | LOW | Disable the bridge. Discord is the primary interface. Fix Messages at leisure. |
| Trading validation misses a wash sale | HIGH | Manual IRS form amendment. This is why 30-day paper trading with full validation is mandatory before live. |
| Docker Compose override conflict takes down stack | MEDIUM | `docker compose config` to inspect merged state. Remove conflicting override. Fix naming collision. Restart. |
| Obsidian REST API rate limit hit | LOW | Cache more aggressively. Reduce polling frequency. Batch operations. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Pi-mono dependency churn | v0.1 (adapter pattern) | Pi can be upgraded by changing only the adapter file |
| Vault noise at scale | v0.2 (memory architecture) | Vault note count stays proportional to meaningful interactions, not total interactions |
| LM Studio context crashes | v0.1 (token counting), v0.4 (model registry) | No unhandled crashes from oversized prompts |
| Apple Messages fragility | v0.3 (feature-flagged, tier-2) | System functions fully with Messages bridge disabled |
| Trading regulatory violations | v0.9 (validation layer before trading) | PDT counter and wash sale detector have unit tests with edge cases |
| Docker Compose override sprawl | v0.1 (contract), v0.5 (first module validates pattern) | Each module's override passes `docker compose config` validation in isolation |
| Discord UX issues (char limit, timeouts) | v0.3 (interface implementation) | Integration tests cover 2000-char boundary and 3-second acknowledgment |
| OFX parsing across banks | v0.8 (finance module) | Test suite includes OFX samples from 3+ banks |
| Scope creep across 10 milestones | All phases | Each milestone has a definition of done; features not in the milestone are rejected |

## Sources

- [Pi-mono releases and changelog](https://github.com/badlogic/pi-mono/releases) -- verified release frequency and breaking changes (HIGH confidence)
- [Obsidian Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) -- rate limits and search limitations (HIGH confidence)
- [Discord Rate Limits documentation](https://docs.discord.com/developers/topics/rate-limits) -- 50 req/s limit, 2000 char limit (HIGH confidence)
- [Alpaca PDT Protection](https://alpaca.markets/support/pattern-day-trading-protection) -- PDT rule enforcement (HIGH confidence)
- [Alpaca Wash Trade Rules](https://forum.alpaca.markets/t/wash-trade-rules/18200) -- wash trade vs wash sale distinction (MEDIUM confidence)
- [LM Studio context window bug](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1620) -- crash on context overflow (HIGH confidence)
- [Apple Messages AppleScript limitations](https://discussions.apple.com/thread/252124165) -- no public API, broken since Yosemite (HIGH confidence)
- [Obsidian vault AI memory scaling](https://limitededitionjonathan.substack.com/p/stop-calling-it-memory-the-problem) -- token math and curation challenges (MEDIUM confidence)
- [Docker anti-patterns](https://codefresh.io/blog/docker-anti-patterns/) -- container best practices (HIGH confidence)
- [OFX parsing documentation](https://ofxtools.readthedocs.io/en/latest/parser.html) -- ofxtools handling of malformed data (MEDIUM confidence)

---
*Pitfalls research for: Sentinel of Mnemosyne -- self-hosted AI assistant platform*
*Researched: 2026-04-10*
