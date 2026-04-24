# Phase 33: Rules Engine — Discussion Log

**Discussion held:** 2026-04-24
**Mode:** default (4 single-question turns + check-continue)
**Workflow:** `/gsd-discuss-phase 33`

## Areas selected by user

All four gray areas from the initial AskUserQuestion:
1. Rules corpus source
2. Ruling reuse matching (RUL-03)
3. PF1 / pre-Remaster rejection (RUL-04)
4. Output shape + citation format

---

## Area 1: Rules corpus source

### Q1 — Corpus source of truth

Options presented:
- Foundry pf2e rules JSON + RAG embeddings
- Archives of Nethys URL fetch + LLM
- LLM-only, no local corpus
- Hybrid — small hand-curated seed + LLM fallback

User answer (paraphrased): *"scan the basic pf2e rules and embed, no need for the more advanced rules at first, use that to seed, and then use the llm to fallback, however when a new rule is looked up, find if it exists, if it is not something that exists, use the llm to create a new rule — inform the GM when it is a 'homebrew' rule that is attempting to solve a situation that doesn't exist in the rules. we want to use the rules as the source of truth but allow for fun gameplay."*

Resolution: RAG over embedded basic-rules corpus; LLM fallback when not found. Gameplay-first philosophy — never decline just because corpus misses. Homebrew framing explicitly in the DM-facing output.

### Q2 — "Basic" scope

Options presented:
- Player Core + GM Core only
- Player Core + GM Core + Monster Core
- Player Core only

User answer: **Player Core + GM Core + Monster Core** (the three Remaster core books).

### Q3 — Advanced-book gap handling

Options presented:
- Treat as homebrew — LLM reasons from basic-rules analogs + marks `[HOMEBREW]`
- Decline with a 'not in seeded corpus' message
- LLM-training-data fallback, marked `[UNCORROBORATED]`

User answer (paraphrased): *"start importing other books off hours and seed the rulesets. we want to start with the big three, and then when there is down time overnight, pick a book and bring it in. eventually would have all the lore over time. if we need something hot, go get it and use the llm training data fallback but update the rules with accurate rules if they exist."*

Resolution: User's vision includes overnight background ingestion + self-healing corpus. These are scope-bigger than the phase strictly requires — captured as Deferred Ideas for a Phase 33.x follow-up. Phase 33 MVP ships: 3-book seed + LLM training-data fallback on corpus miss, stamped with the MVP marker.

### Q4 — Marker wording

Options presented:
- Citation / `[HOMEBREW — verify]` / `[UNCORROBORATED — from model recall]` (three states)
- Citation / `[GENERATED — verify]` (per ROADMAP literal)
- Citation / `[HOMEBREW — verify]` only (merge states 2 + 3)

User answer: **Citation / `[GENERATED — verify]` (per ROADMAP literal)**. Keeps the literal RUL-02 wording and simplifies the UX — single marker for any non-corpus ruling.

---

## Area 2: Ruling reuse matching (RUL-03)

### Q1 — Cache key / file-path strategy

Options presented:
- Topic-slug folders + question-hash files
- Citation-anchored (corpus hits) + query-hash (homebrew)
- Flat hash-per-query

User answer: **Topic-slug folders + question-hash files** — `mnemosyne/pf2e/rulings/{topic}/{sha1(query)[:8]}.md`.

### Q2 — Reuse-match threshold

Options presented:
- Embedding similarity ≥ 0.90 (tight)
- Embedding similarity ≥ 0.80 (medium) — recommended
- Exact normalized text only

User answer: **Embedding similarity ≥ 0.80 (medium)**.

---

## Area 3: PF1 / pre-Remaster rejection (RUL-04)

### Q1 — Filter strictness

Options presented:
- Keyword allowlist + gentle redirect
- Pure LLM classifier call before the main ruling flow
- Keyword denylist for PF1 only; ignore pre-Remaster distinctions

User answer: **Keyword denylist for PF1 only** — pre-Remaster queries flow through normally since the Remaster-only corpus re-anchors the output.

### Q2 — Decline message

Options presented:
- Strict + educational
- Educational + offer Remaster analog if one exists
- Terse decline

User answer: **Strict + educational**.

---

## Area 4: Output shape + citation format

### Q1 — Response structure

Options presented:
- Short-answer-first, reasoning-second, citation-footer
- Single prose block with trailing citation line
- Q / A / Why / Source field layout

User answer: **Q / A / Why / Source field layout** (4 Discord embed fields).

### Q2 — Citation format

Options presented:
- Book title + page + section heading + AoN URL
- Book title + page only
- AoN URL + book attribution

User answer: **Book + page + section + AoN URL** (most informative).

---

## Continuation check

After Area 4, asked: "Any remaining gray areas you want to pin down before the researcher starts?"

Options:
- I'm ready for context
- Discord noun choice (`:pf rule` vs `:pf rules` vs `:pf ruling`)
- Latency + streaming (slow-query UX)

User answer: **Discord noun choice**.

### Q1 — Noun form

Options presented:
- `:pf ruling <query>` — bare noun, no sub-verbs (harvest-style)
- `:pf rule <query>` — bare noun (shorter)
- `:pf rule <query|show|history|list>` — noun + verbs (NPC-style)

User answer: **`:pf rule <query|show|history|list>` — noun + verbs (NPC-style)**. Adds sub-verbs to browse/history topic folders; richer UX than Phase 32's bare-noun harvest pattern.

---

## Claude's discretion

The following were NOT asked about during discussion — researcher + planner decide:
- Embedding model (nomic-embed-text via LM Studio vs sentence-transformers vs OpenAI)
- Vector store tech (in-memory numpy vs faiss vs chromadb vs pgvector)
- Topic classifier approach (separate LLM call vs keyword rules vs Foundry-pack categories)
- Retrieval similarity threshold for "found vs missed" fall-through to `[GENERATED]`
- Slow-query UX (placeholder-and-edit vs streaming vs block)
- PF1 denylist completeness (initial list in D-06; researcher audits)

## Deferred ideas (captured, not acted on)

- Background overnight ingestion of additional Remaster books → Phase 33.x or dedicated "Corpus Expansion" phase
- Corpus self-healing loop → paired with the above
- Finer-grained markers (`[HOMEBREW]` vs `[UNCORROBORATED]`) → revisit if single-marker UX proves too coarse
- Per-citation marker granularity for composite rulings → wait for DM feedback
- Ruling analytics / history review UX → future phase

---

*Logged by: discuss-phase default mode*
*Phase: 33-Rules Engine*
