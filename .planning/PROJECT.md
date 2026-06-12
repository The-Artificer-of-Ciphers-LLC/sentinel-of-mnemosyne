# Sentinel of Mnemosyne

## What This Is

A personal, self-hosted AI assistant that wires together your own AI, your own memory (an Obsidian
Vault), and your own interface. You bring your AI provider, your Obsidian vault becomes the
Sentinel's persistent memory, and pluggable Docker modules add capabilities — Pathfinder DM
assistant, music tracker, personal finance, autonomous trading — without touching the core engine.

## Core Value

The Vault persists everything the system learns and generates; the Sentinel retrieves relevant
context on every message — so conversations are always informed by history, never starting cold.

## Requirements

### Validated

- ✓ BYO AI via LiteLLM (LM Studio, Claude API, Ollama) — v0.1
- ✓ Obsidian vault as persistent memory (Session summaries written to `ops/sessions/`) — v0.2
- ✓ Discord interface container passing standard message envelopes to Sentinel Core — v0.3
- ✓ Sentinel persona sourced from `sentinel/persona.md` in the Vault, not hardcoded — ADR-0001, v0.50
- ✓ `Vault` Protocol seam at `app/vault.py` as sole persistence interface — ADR-0002, v0.50
- ✓ Hot tier (Self namespace + recent Session summaries) loaded on every message — v0.50
- ✓ Warm tier (BM25 Vault search above relevance threshold) — v0.50.1
- ✓ Vault sweeper with per-note embeddings (`embedding_b64`) in frontmatter — v0.50.2
- ✓ Pluggable module architecture (Docker Compose override fragments; `POST /modules/register`) — v0.50
- ✓ Pathfinder 2e module — NPC management, session notes, dialogue generation, Foundry NeDB import — v0.50
- ✓ MEM-01: Single `Recall` module assembles recalled memory for every message; `GET /context/{user_id}` uses the same module — no duplicated assembly logic — Validated in Phase 39: Extract the Recall Module
- ✓ MEM-02: Recall policy (relevance threshold, namespace exclusions, per-tier context budgets) consolidated into `RecallConfig`; no inline constants — Validated in Phase 39: Extract the Recall Module
- ✓ MEM-03: Recall by meaning via semantic vector search (`SemanticRecall` strategy backed by vault sweeper embeddings) — Validated in Phase 40: Semantic Recall
- ✓ MEM-04: Hybrid keyword+semantic retrieval merged via Reciprocal Rank Fusion (RRF); `KeywordRecall` and `SemanticRecall` coexist behind the `RetrievalStrategy` seam — Validated in Phase 40: Semantic Recall
- ✓ MEM-05: Sweeper-maintained embedding index; no per-note HTTP call at query time; model-mismatch notes skipped gracefully — Validated in Phase 40: Semantic Recall

See `.planning/REQUIREMENTS.md` for the full validated requirement history across phases 1–38.

### Active

Active requirements for v0.5.1 are enumerated in **Current Milestone** below. See `.planning/ROADMAP.md`
for the phase-level breakdown.

### Out of Scope

- Multi-user / multi-tenant support — personal tool; single-operator design is a deliberate constraint
- Mobile app — interface containers (Discord, Messages) handle mobile channels
- Proprietary cloud storage of the Vault — local-only vault is a core principle; iCloud sync is
  the only approved future option
- Real-time audio/voice interface — interesting future direction, not v1 scope
- Pi harness as in-path layer — removed in v0.50.3; optional power tool at `./sentinel.sh --pi`,
  scoped to v0.7 only
- Multi-tenant module ownership — each module has an independent version lifecycle but the
  Core does not arbitrate between users

## Context

Sentinel Core v0.50.3 shipped. Phases 1–38 are complete. The v0.5 "The Dungeon" milestone delivered
the Pathfinder 2e module suite: full NPC/session/rule/player/Foundry/Cartosia interface, Discord
command routing, and vault sweeper with embedding frontmatter.

Phase 39 complete — retrieval extracted into a first-class `Recall` module (`RecallConfig`/`RecalledContext`); `MessageProcessor` and `GET /context` both delegate to it; behavior-preserving, 287 tests green.

Phase 40 complete — semantic recall implemented (ADR-0004); `SemanticRecall` strategy activates the vault sweeper's `embedding_b64` frontmatter as live retrieval data; hybrid BM25+vector merge via RRF; sweeper maintains the embedding index at index time with no per-note HTTP calls at query time; model-mismatch notes skipped gracefully. MEM-03, MEM-04, and MEM-05 validated.

Session summaries exist but are dropped from context after 3 turns / today+yesterday — meaning
conversations longer than a day routinely lose history. This is the remaining gap for v0.5.1.

**Domain vocabulary** (canonical terms — see `CONTEXT.md` for full glossary):
- **Vault**: the Obsidian vault; the `Vault` Protocol in `app/vault.py` is the sole persistence seam
- **Hot tier**: Sentinel persona + Self namespace + recent Session summaries — loaded on every message
- **Warm tier**: Vault search results above a relevance threshold — owned by the Recall module
- **Recall**: the module that assembles recalled memory (`RecalledContext`) for a single message
- **Session summary**: markdown written to `ops/sessions/{date}/` after every Session
- **Sentinel persona**: system-prompt content sourced from `sentinel/persona.md` in the Vault

**Validated requirement and phase history:** `.planning/REQUIREMENTS.md`
**Full roadmap and phase queue:** `.planning/ROADMAP.md`

## Constraints

- **Tech stack**: Python / FastAPI / LiteLLM / Docker Compose — established across v0.1–v0.50; no migrations
- **Vault seam**: all persistence reads and writes go through the `Vault` Protocol at `app/vault.py` —
  routes and services must not bypass it (ADR-0002)
- **Open source first**: Docker, Obsidian local vault, LM Studio, LiteLLM — no proprietary orchestration
  or cloud storage dependencies
- **Non-destructive vault operations**: the sweeper only relocates to `_trash/`; no hard deletes
- **Module isolation**: modules register via `POST /modules/register`; Core does not import module code

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Sentinel persona sourced from `sentinel/persona.md` in the Vault (ADR-0001) | Operator-tunable content belongs in the Vault, not in code; takes effect on next message without restart | ✓ Good |
| Vault seam at `app/vault.py`, not under `app/clients/` (ADR-0002) | Single Protocol interface prevents scattered Obsidian client calls; `FakeVault` enables full unit-test isolation | ✓ Good |
| Recall is a module above the Vault seam, not inline in the message processor (ADR-0003) | Retrieval policy (thresholds, budgets, namespace exclusions) is domain logic that does not belong in the adapter | ✓ Good |
| `RetrievalStrategy` seam inside Recall: `KeywordRecall` + `SemanticRecall` (ADR-0004) | Makes sweeper embeddings live retrieval data; allows BM25 and vector search to coexist behind one interface | ✓ Good |
| Typed `SessionSummary` + `RetentionPolicy` + recency-weighted merge (ADR-0005) | Stops hard-dropping context after 3 turns; older sessions recalled via index instead of silently lost; recalled sessions ranked by recency | — Pending |
| LiteLLM-direct as the AI layer; Pi harness is optional (`--pi` flag) | Removes an unnecessary process boundary for standard chat; Pi harness reserved for advanced coding use at v0.7 | ✓ Good |
| Docker Compose override fragments per module/interface | Modules never touch the base compose file; zero central registry sprawl | ✓ Good |

---

## Current Milestone: v0.5.1 The Second Brain

**Goal:** Make recalled memory real — retrieval becomes a first-class module that actually surfaces
past content across conversations, instead of "write to Obsidian, never look again after three."

**Progress: 2 of 3 phases complete (Phase 39 + Phase 40 done; Phase 41 remaining).**

**Target features:**
- ✓ Extract the Recall module (ADR-0003) — retrieval becomes a deep module above the Vault seam,
  returning `RecalledContext`; the Sentinel persona and prompt-injection defense stay in prompt assembly. — Phase 39 complete
- ✓ Semantic recall (ADR-0004) — a `RetrievalStrategy` seam inside Recall (`KeywordRecall` +
  `SemanticRecall`); the vault sweeper's per-note embeddings (`embedding_b64`) become live retrieval
  data instead of dead frontmatter. — Phase 40 complete
- Typed `SessionSummary` + retention (ADR-0005) — typed sessions and a `RetentionPolicy`; older
  turns are recalled via the index instead of dropped past the 3-turn / today+yesterday hot window. Recalled sessions are recency-weighted so recent sessions rank above older ones.

---

## Evolution

PROJECT.md evolves throughout the project lifecycle.

**After each phase transition** (`/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (`/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state (users, feedback, metrics)

---

*Last updated: 2026-06-11*
