# Phase 33: Rules Engine — Context

**Gathered:** 2026-04-24
**Status:** Ready for planning

<domain>
## Phase Boundary

The DM asks a PF2e Remaster rules question; the Sentinel returns a ruling with a Paizo source citation when the rule is in the embedded corpus, or an LLM-composed ruling marked `[GENERATED — verify]` when it is not. Every ruling persists to `mnemosyne/pf2e/rulings/{topic-slug}/{query-hash}.md` so the same situation isn't re-adjudicated. Scoped exclusively to PF2e Remaster — PF1 queries are declined with a pointer to Archives of Nethys 1e; pre-Remaster PF2e queries flow through normally (the Remaster-only corpus forces Remaster-flavored answers).

**In scope (RUL-01..04):**
- Ingest + embed the three Remaster core books (Player Core, GM Core, Monster Core) at module startup
- RAG retrieval against the embedded corpus; LLM composes the ruling with citations when a rule is found
- LLM-only fallback (no corpus hit) — ruling stamped `[GENERATED — verify]`; still written to cache
- Reuse match (RUL-03): embedding similarity ≥ 0.80 within the classified topic folder → return cached ruling with an italic "_reusing prior ruling on <topic>_" note
- PF1 keyword denylist + strict-but-educational decline message (RUL-04)
- Discord `:pf rule` noun with verbs: `<query>`, `show <topic>`, `history`, `list`
- 14th entry in `REGISTRATION_PAYLOAD` for the pf2e module

**Out of scope (deferred to follow-up phases):**
- Background overnight ingestion of additional Remaster books (Guns & Gears, Secrets of Magic, Rage of Elements, Book of the Dead, Dark Archive, Howl of the Wild, Tian Xia, etc.)
- Corpus self-healing loop — training-data "hot" fallbacks that update the embedded corpus when they find an accurate rule
- Finer-grained markers (`[HOMEBREW]` vs `[UNCORROBORATED]`) — ship the single `[GENERATED — verify]` marker first, split only if DM feedback indicates the coarseness hurts

</domain>

<decisions>
## Implementation Decisions

### Corpus + ingestion
- **D-01 (seed corpus — REVISED 2026-04-24 post-research):** Scan and embed the **Player Core rules-prose + all Conditions + basic-actions + skill entries** from the Foundry pf2e system package at module startup (~130 chunks). Foundry does NOT ship Monster Core's rules-prose chapters (Building Encounters, Adjusting Creatures) or GM Core's rules-prose — confirmed by live inspection of `packs/pf2e/journals/gm-screen.json` on 2026-04-24. Monster Core / GM Core rules-prose ingestion moves to Phase 33.x (see `<deferred>`). The `[GENERATED — verify]` marker catches queries that miss Player Core, preserving the gameplay-fun-first philosophy. ORC-legal. No other books in this phase.
- **D-02 (retrieval flow):** On each query — (1) PF1 denylist check (D-06); (2) topic classification; (3) RAG lookup over the embedded corpus restricted to the classified topic, similarity threshold TBD-by-researcher; (4) if corpus hit → LLM composes the ruling from the retrieved passages and emits a Paizo citation; (5) if corpus miss → LLM composes the ruling from its training data and the ruling is stamped `[GENERATED — verify]`.
- **D-03 (advanced-book handling):** A query about a rule that lives only in an advanced book (e.g., Guns & Gears) is NOT declined — the LLM composes from training data with the standard `[GENERATED — verify]` stamp. The DM gets gameplay continuity; the `[GENERATED]` marker signals "double-check against the advanced book." No separate `[UNCORROBORATED]` marker in the MVP.

### Cache + reuse (RUL-03)
- **D-04 (cache path):** `mnemosyne/pf2e/rulings/{topic-slug}/{sha1(normalized-query)[:8]}.md`. LLM classifies each query into a topic slug at composition time (e.g., `flanking`, `grapple`, `off-guard`, `falling-damage`). Multi-topic queries pick the primary topic (researcher can refine tie-break policy). GET-then-PUT Obsidian writes (no PATCH — memory constraint).
- **D-05 (reuse match):** Embedding similarity threshold **0.80** within the same topic folder. On cache hit, the ruling is returned with an italic `_reusing prior ruling on <topic> — confirm applicability_` note in the Discord embed so the DM knows they are reading a prior adjudication rather than a fresh one.

### Scope filter (RUL-04)
- **D-06 (PF1 detection):** **Keyword denylist for PF1 only.** Initial denylist: THAC0, touch AC, flat-footed AC (as a distinct stat), BAB, spell schools (abjuration/conjuration/divination/enchantment/evocation/illusion/necromancy/transmutation — these were removed in Remaster), "Core Rulebook 1st" / "CRB 1e" / "1st edition", "3.5e", "d20 System". Researcher audits this list for completeness. Pre-Remaster PF2e queries (e.g., using "flat-footed" as a condition) flow through normally — the Remaster-only corpus naturally re-anchors the LLM's output to Remaster terminology.
- **D-07 (decline message):** Strict + educational, single-line, no apology, points the DM somewhere useful:
  > "This Sentinel only supports PF2e Remaster (2023+). Your query references <term>, which is a PF1/pre-Remaster concept. For PF1 questions, try Archives of Nethys 1e (https://legacy.aonprd.com)."

### Output shape + citations
- **D-08 (response shape):** **Q / A / Why / Source field layout.** The JSON response body is:
  ```json
  {
    "question": "<the DM's query, normalized>",
    "answer": "<short ruling — 1-2 sentences, the TL;DR>",
    "why": "<reasoning from the retrieved rules or from the model>",
    "source": "<Paizo citation string when corpus-hit; null when [GENERATED]>",
    "citations": [
      {"book": "Player Core", "page": 234, "section": "Off-Guard", "url": "https://2e.aonprd.com/..."}
    ],
    "marker": "source" | "generated" | "declined",
    "topic": "<slug used for cache path>"
  }
  ```
  The Discord embed renders four fields: **Question** (user's query), **Answer** (short), **Why** (reasoning), **Source** (citation string or marker). Footer carries ORC attribution and the `[GENERATED — verify]` banner when applicable.
- **D-09 (citation format):** **Book + page + section heading + AoN URL** when all four are available from the corpus metadata, rendered as `Player Core p. 234 — Off-Guard | https://2e.aonprd.com/Conditions.aspx?ID=31`. The researcher confirms which of those four fields are reliably extractable from the chosen ingestion source (Foundry pack metadata vs AoN scrape); if any field is missing for a given rule, omit that field from the rendered citation but never fabricate.

### Discord dispatch surface
- **D-10 (noun + verbs):** Extends `_PF_NOUNS` from `{npc, harvest}` to `{npc, harvest, rule}` (IN-01's constant introduced in Phase 32). Dispatch verbs under the `rule` noun:
  - `:pf rule <free text>` — default, executes the RUL-01..04 query path
  - `:pf rule show <topic>` — list ruling files under `mnemosyne/pf2e/rulings/<topic>/`
  - `:pf rule history` — list the most recent N rulings across all topics (researcher picks N; default 10)
  - `:pf rule list` — enumerate the topic folders currently under `mnemosyne/pf2e/rulings/`
- **D-11 (slow-query UX):** Open question for the researcher — embedding retrieval + LLM composition can exceed 5s; the Discord dispatch should either (a) send a "thinking…" placeholder + edit when done, (b) stream the response, or (c) block. No user preference locked in discussion — researcher recommends based on Phase 31 dialogue patterns + Discord edit-message cost.

### Claude's Discretion
- **Embedding model** — `nomic-embed-text` (via LM Studio, same provider as chat) vs `all-MiniLM-L6-v2` (lightweight, Python-native via sentence-transformers) vs OpenAI `text-embedding-3-small`. Researcher picks based on latency, on-device compatibility, and quality benchmarks for technical/rules-text corpora.
- **Vector store** — in-memory numpy (simplest, OK for ~3-book corpus size), faiss, chromadb, or pgvector. Researcher picks; lifespan startup indexes the corpus once, so index build cost is paid at container start.
- **Topic classifier** — separate small LLM call, keyword-rule-based, or derived from corpus metadata (pf2e rules pack has per-entry categories). Planner decides.
- **Rate limit / DoS cap** — parallel to Phase 32's `MAX_BATCH_NAMES=20`. Single-query-only endpoint likely needs no batch cap; per-user rate limit if any comes from sentinel-core's existing middleware.
- **Retrieval threshold for "found vs missed"** — similarity score below which we fall through to `[GENERATED]`. Researcher benchmarks on a sample query set.

### Research Resolutions (added 2026-04-24 — user-confirmed)
- **D-12 (AoN URL map coverage):** Phase 33 ships with a partial hand-curated `modules/pathfinder/data/aon-url-map.json` covering ~60 entries (all Conditions + top GM-screen journal pages). Corpus entries without a map hit render the citation as `Book + page + section` with **no trailing URL** (D-09 explicitly allows omitting missing fields — do NOT fabricate URLs). The map file is version-controlled; additions are incremental follow-ups.
- **D-13 (embedding-version handling):** Every ruling file's YAML frontmatter stores three fields so reuse-match (D-05, 0.80 threshold) and any future re-embed job are model-aware:
  - `embedding_model: "nomic-embed-text-v1.5"` (string identifier returned by LM Studio)
  - `embedding_hash: "<sha1 of model-identifier-string>"` (for fast model-change detection without reading the vector)
  - `query_embedding: "<base64-encoded float32 little-endian array>"` (the full vector, ~3KB per ruling)
  Reuse-match in D-05 compares against the current-runtime model; mismatched rulings are skipped (not errored) until a future re-embed job rewrites them. No re-embed job in Phase 33.
- **D-14 (`:pf rule history` sort key):** Sort by `last_reused_at` descending (most recent activity first). Every ruling's frontmatter gets `composed_at: <iso8601>` set on creation and `last_reused_at: <iso8601>` updated on every cache hit (both fresh-compose and reuse-match). History default N = 10 per D-10; `:pf rule history N` allows an explicit override.
- **D-15 (scope boundary — Player Core MVP, user-confirmed):** Phase 33 ships corpus coverage for Player Core rules-prose + Conditions + basic actions + skills only. Monster Core rules-prose, GM Core rules-prose, and all advanced books (Guns & Gears, Secrets of Magic, etc.) are explicitly deferred to Phase 33.x "Corpus Expansion". Any query that misses the Player-Core corpus flows through the `[GENERATED — verify]` path — this preserves the gameplay-fun-first philosophy and matches the RUL-02 requirement literal. Do NOT expand scope in Phase 33 to add Monster Core or GM Core ingestion.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements
- `.planning/REQUIREMENTS.md` §Rules — RUL-01..04 authoritative wording
- `.planning/ROADMAP.md` — Phase 33 row (depends on Phase 28)
- `.planning/PROJECT.md` — project value statement + tech stack constraints

### Prior CONTEXT.md (pattern reuse + ADR continuity)
- `.planning/phases/28-pf2e-module-skeleton-cors/28-CONTEXT.md` — module architecture, CORS, sentinel-core proxy pattern
- `.planning/phases/29-npc-crud-obsidian-persistence/29-CONTEXT.md` — Pydantic models, slugify, Obsidian GET-then-PUT (the D-03b pattern referenced here)
- `.planning/phases/31-dialogue-engine/31-CONTEXT.md` — LLM integration patterns, dialogue flow
- `.planning/phases/32-monster-harvesting/32-CONTEXT.md` — fuzzy lookup tiering, ORC attribution, `[GENERATED — verify]` marker convention, `_PF_NOUNS` constant

### Prior VERIFICATION / UAT (failure modes to avoid)
- `.planning/phases/32-monster-harvesting/32-VERIFICATION.md` — 22 must-haves pattern, live-UAT gate
- `.planning/phases/32-monster-harvesting/32-HUMAN-UAT.md` — live-stack verification template; G-1 (Dockerfile dep dual-ship) and G-2 (LLM clamp fill-when-missing) are the two gaps to NOT re-open

### Live UAT automation (reuse / extend)
- `scripts/uat_harvest.py` — the script to clone/extend for Phase 33 live testing
- `scripts/uat_phase32.sh` — orchestrator pattern (rebuild → wait for healthy + registration → run assertions)

### External standards
- Paizo Open Reusable Content (ORC) license — https://paizo.com/orclicense — governs the corpus ingestion (same as Phase 32)
- Archives of Nethys PF2e — https://2e.aonprd.com — canonical citation URLs
- Archives of Nethys PF1 — https://legacy.aonprd.com — used in the PF1 decline message (D-07)
- pf2e Foundry system package — https://github.com/foundryvtt/pf2e — candidate corpus source (researcher confirms which files hold the rules prose — likely `packs/rules/` and/or `packs/conditions/`)

### Project constraints to re-acknowledge
- `CLAUDE.md` — AI Deferral Ban (no TODOs, no NotImplementedError, no "out of scope" skip-outs); Git workflow commits directly to main
- Memory: `project_obsidian_patch_constraint.md` — no PATCH for new-field writes; GET-then-PUT only
- Memory: `project_dockerfile_deps.md` — any new Python dep added to pyproject.toml MUST also be added to `modules/pathfinder/Dockerfile`'s inline `pip install` block or the container restart-loops on `ModuleNotFoundError`
- Memory: `project_uat_phase32.md` — live-UAT pattern; sentinel-core proxy is `/modules/{name}/{path}`; registry at `GET /modules`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `modules/pathfinder/app/harvest.py` — **pure-transform helper module pattern**. Phase 33 builds `app/rules.py` in the same shape: Pydantic models, module constants (thresholds, path prefixes), helpers that never do I/O. The LLM fallback stays in `app/llm.py` alongside `generate_harvest_fallback`.
- `modules/pathfinder/app/routes/harvest.py` — **route + lifespan singleton pattern**. Phase 33's `app/routes/rule.py` mirrors this: Pydantic request/response, input sanitiser (mirror of `_validate_monster_name`), module-level singletons (obsidian, rules_index, rules_embeddings) set by main.lifespan and nullified on shutdown.
- `modules/pathfinder/app/routes/npc.py` — `slugify` helper (reused by Phase 32). Phase 33 imports it too for topic-slug and cache-path construction — **do not re-implement**.
- `modules/pathfinder/app/llm.py` — `generate_harvest_fallback` is the template for `generate_ruling_fallback`. Same shape: litellm.acompletion with timeout=60, source/verified stamp, defensive output-shape validation (CR-02 pattern), DC-clamp-style post-parse normalization (here: the marker logic and citation presence).
- `modules/pathfinder/data/harvest-tables.yaml` — **load-at-startup YAML pattern**. Phase 33's corpus load-at-startup is an extension: `load_rules_corpus()` reads the Foundry rules pack (or AoN scrape output), embeds each entry, and populates the `rules_index` singleton.
- `interfaces/discord/bot.py` build_harvest_embed + `_PF_NOUNS` constant — **peer noun dispatch pattern**. Phase 33 adds `"rule"` to `_PF_NOUNS`, defines `build_ruling_embed(result)`, extends `_pf_dispatch` with a `rule` branch that itself has its own sub-verb parser (closer to the `npc` branch in structure than the `harvest` branch because of the show/history/list sub-verbs).
- `scripts/uat_harvest.py` + `scripts/uat_phase32.sh` — the live-UAT orchestration template. Phase 33 ships a parallel `scripts/uat_rules.py` + extends or clones `uat_phase32.sh` to `uat_phase33.sh`. Container rebuild check verifies new Python deps (embedding model, vector store) actually land in the pf2e-module image.

### Established Patterns
- **Pydantic response models** — one request model, one or more nested response models (see harvest.py `HarvestRequest`, `MonsterHarvestOut`, `ComponentOut`, `CraftableOut`). Phase 33 needs: `RuleQueryRequest`, `RuleCitation`, `RuleRulingOut`.
- **Lifespan singleton assignment** — `main.py` lifespan imports the route module, assigns `_rule_module.obsidian = obsidian_client`, `_rule_module.rules_index = build_corpus_index()`, nullifies on shutdown.
- **14th route registration** — extend `REGISTRATION_PAYLOAD["routes"]` with a `rule` entry (description covering RUL-01..04). Assert `len(REGISTRATION_PAYLOAD["routes"]) == 14` in the test.
- **TDD Wave 0** — Phase 32 shipped 31 RED stubs in a Wave 0 plan before any prod code. Plan 33 follows the same pattern: RED stubs for corpus-load, topic classification, RAG retrieval, ruling composition, cache round-trip, PF1 decline, bot dispatch (query + 3 sub-verbs), Discord embed builder, and regression coverage for the two Phase 32 gaps that Phase 33 re-visits (Dockerfile deps for embedding model package; LLM shape validator for the ruling JSON).
- **Live UAT after code review** — Phase 32 revealed that unit tests pass in host venv while the container restart-loops on missing deps; Phase 33 MUST run `scripts/uat_phase33.sh` before the phase is marked complete.

### Integration Points
- `modules/pathfinder/app/main.py` — add `rule_router` import + `app.include_router(rule_router)` + extend `REGISTRATION_PAYLOAD` + extend lifespan block that loads the rules corpus.
- `modules/pathfinder/app/routes/__init__.py` — add `from .rule import router as rule_router`.
- `interfaces/discord/bot.py` — extend `_PF_NOUNS`, add `build_ruling_embed`, add `rule` dispatch branch with sub-verbs.
- `modules/pathfinder/pyproject.toml` — new deps (embedding model library, vector store); ALSO in `modules/pathfinder/Dockerfile` pip install block.
- `modules/pathfinder/Dockerfile` — dual-ship deps (see canonical_refs `project_dockerfile_deps.md`).

</code_context>

<specifics>
## Specific Ideas

- **Corpus seed size — "the basic three":** Player Core + GM Core + Monster Core (the three Remaster core books). The user explicitly rejected Player-Core-only (too lean) and multi-book-from-day-one (too heavy). The three-book seed is the table-ready MVP; expansion to Guns & Gears, Secrets of Magic, etc. is a separate follow-up phase.
- **Gameplay-fun-first philosophy:** When a rule doesn't exist in the seeded corpus, the Sentinel composes a ruling and marks it `[GENERATED — verify]` — it does NOT decline. The user's framing: *"we want to use the rules as the source of truth but allow for fun gameplay."* This philosophy is LOAD-BEARING; a planner who drafts "decline when corpus misses" has mis-read the phase.
- **Topic-folder browsability:** Cache path structure intentionally supports `ls mnemosyne/pf2e/rulings/flanking/` and similar. The DM should be able to open Obsidian and audit their own ruling history per topic. This is why the topic-slug-folder layout was chosen over flat-hash.
- **Simple marker state in MVP:** Just one non-citation marker — `[GENERATED — verify]` per ROADMAP RUL-02 literal. No distinction between "homebrew" and "from model recall" in the initial ship. Refine only if DM feedback shows the coarseness hurts.

</specifics>

<deferred>
## Deferred Ideas

- **Monster Core + GM Core rules-prose ingestion (added 2026-04-24)** — Foundry's pf2e system package does NOT ship Monster Core's rules-prose chapters (Building Encounters, Adjusting Creatures, etc.) or GM Core's rules-prose. Live-verified against `packs/pf2e/journals/gm-screen.json` on 2026-04-24: 55/60 GM-screen pages cite Player Core, only 5 cite GM Core, zero cite Monster Core rules-prose. Adding these requires either AoN HTML scrape + bespoke chunker or hand-curated YAML extraction — both materially expand scope. Deferred to Phase 33.x. Queries targeting Monster Core / GM Core rules flow through `[GENERATED — verify]` in Phase 33, which is acceptable under RUL-02.
- **Background overnight ingestion of additional Remaster books** — phase 33.x or a dedicated Phase 34-like "Corpus Expansion" follow-up. Scheduled job pulls in Guns & Gears, Secrets of Magic, Rage of Elements, Book of the Dead, Dark Archive, Howl of the Wild, Tian Xia (etc.), one book per overnight window. User vision: *"eventually would have all the lore over time."* Not in Phase 33 MVP because the retrieval + ruling composition + cache + dispatch surface is already a large phase; the scheduling and incremental-index update mechanics deserve their own planning cycle.
- **Corpus self-healing** — when the `[GENERATED — verify]` fallback is used for a rule that exists in a yet-to-be-ingested advanced book, a background job finds and ingests the relevant passages so the next identical query hits the corpus with a real citation. Deferred for the same reason as above — it depends on the ingestion system being in place first.
- **Finer-grained markers** — `[HOMEBREW]` (true rules-gap + LLM-invented ruling) vs `[UNCORROBORATED]` (LLM recalled an advanced-book rule it wasn't trained to verify). Ship single `[GENERATED — verify]` first; if DM feedback shows the two states need distinct handling (different cache lifetimes? different double-check workflows?), revisit.
- **Ranger pet / companion + PC composite rulings** — the existing marker system treats the whole ruling as one marker state; composite rulings that draw from both corpus + homebrew reasoning would benefit from per-citation marker granularity. Not needed until the DM reports the blurring.
- **RULing analytics** — "most common rulings this campaign" / "oldest unrefreshed ruling" / "rulings that contradict each other." DM-review UX on top of the ruling cache. Future phase.

</deferred>

---

*Phase: 33-Rules Engine*
*Context gathered: 2026-04-24*
