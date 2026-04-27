# Quick Task 260427-vl1: Note Import + Vault Sweeper - Context

**Gathered:** 2026-04-27
**Status:** Ready for research → planning

<domain>
## Task Boundary

Add an explicit note-import mechanism to the 2nd brain feature plus a vault sweeper that walks existing Obsidian notes, reclassifies them, and moves garbage to `_trash/`. Implements the requirements sketched at `.planning/sketches/note-import-and-vault-sweeper.md`.

Three new Discord subcommands: `:note`, `:inbox`, `:vault-sweep`. One new sentinel-core service: note classifier. One new vault structure: the taxonomy directories.

</domain>

<decisions>
## Implementation Decisions

### Taxonomy (Q1 → B, flat 7 categories)

Seven categories total. No nested namespaces (no `learning.course-completed` style sub-keys).

| Slug | Vault path | When applied |
|---|---|---|
| `learning` | `learning/` | Skill/course progress, completions, study notes |
| `accomplishment` | `accomplishments/` | One-off achievements, milestones |
| `journal` | `journal/{YYYY-MM-DD}/` | Reflections, feelings, daily entries |
| `reference` | `references/` | Discrete facts, useful info to remember |
| `observation` | `ops/observations/` | Methodology learnings (existing path; subsumes `:remember`) |
| `noise` | (do not file — chat reply only) | "hello", "thanks", small talk, low-signal |
| `unsure` | `inbox/_pending-classification.md` | Confidence < 0.5; user resolves later |

**Sweeper-specific action:** `move_to_trash` — applies only when the sweeper finds an existing vault note matching cheap-filter garbage heuristics (test artifacts, control inputs, < 20 chars). Not a category for incoming messages.

### Garbage / near-duplicate detection (Q2 → B, embedding similarity)

- **Cheap pre-filter first** (always runs before LLM): `< 20 chars`, regex match on conversational openers (`^(hi|hello|hey|test|are you there|what can you do|ping|yo)\b`), empty/whitespace-only, filename pattern test-*/tmp-*/untitled* combined with short content.
- **LLM classifier** runs on what survives pre-filter.
- **Embedding similarity (cosine ≥ 0.92)** for near-duplicate detection during sweep. Uses the same embedding endpoint already in production for pf2e rules retrieval (`text-embedding-nomic-embed-text-v1.5` via LM Studio). Two notes with cosine similarity ≥ 0.92 are flagged as duplicates; sweeper keeps the older one with longer content, moves the rest to `_trash/`.
- Embedding cache stored as base64 float32 in note frontmatter (matches existing pf2e ruling cache pattern).

### Inbox shape (Q3 → C, both)

- **Source of truth:** `inbox/_pending-classification.md` — a single Obsidian markdown note appended to by the bot. Each pending entry is a section with `### Entry {N}` header and frontmatter-style fields (timestamp, candidate_text, suggested_topics, confidence).
- **Discord interaction:** `:inbox` reads the note and renders the pending list; `:inbox classify <n> <topic>` and `:inbox discard <n>` rewrite the note in place.
- User can also edit the note directly in Obsidian — bot reads it on next access.

### Auto-classification trigger (Q4 → B, explicit only)

- `:note <content>` — explicit subcommand → classifier runs → high-conf files directly, medium-conf files with summary in chat, low-conf goes to inbox.
- `:note <topic> <content>` — bypass classifier, file under given topic.
- Implicit messages (no `:` prefix) keep current behavior — chat reply + session transcript log only. **No automatic classification on every message.**
- Existing `:remember` subcommand stays as a thin alias for `:note observation <content>`.

### Vault sweep first run (Q5 → B, full sweep with _trash recovery)

- `:vault-sweep` (admin only) does a real sweep on first invocation. No dry-run gate.
- Safety: never deletes — moves to `_trash/{YYYY-MM-DD}/`. The `_trash/` tree is gitignored and remains in Obsidian for user review.
- Idempotent via `sweep_pass: 2026-04-27T...` frontmatter marker — second sweep skips already-classified notes unless `--force-reclassify` passed.
- Per-sweep log written to `ops/sweeps/{YYYY-MM-DD}.md` listing every move with original path, new path, classifier confidence, and reason.
- Walks in chunks of 100 files at a time; `:vault-sweep status` reports progress.

### Claude's Discretion

- **Confidence thresholds:** sketch said ≥0.8 / 0.5–0.8 / <0.5. Keeping those as defaults; classifier output rounded to one decimal.
- **`:inbox` listing format:** numbered list with truncated content preview (first 80 chars), suggested topic in parens.
- **Sweep chunk size:** 100 files. Reduce to 50 if Obsidian REST API rate-limits.
- **Frontmatter schema for filed notes:** `topic`, `confidence`, `created`, `source` (`note-import` | `vault-sweep` | `legacy`), `embedding_b64` for sweep-classified notes.
- **`_trash/` reclamation:** notes in `_trash/` are NOT scanned by the sweeper or the warm-tier vault search. Out of scope unless user opts back in.
- **No Foundry / pf2e module concern** — this lives entirely in sentinel-core (the 2nd brain feature) and the Discord interface. pf2e module is unaffected.

</decisions>

<specifics>
## Specific Ideas / References

- The sweeper pre-filter regex should match the Discord transcripts of early testing — `hello`, `are you there`, `what can you do`, `test`, `ping`. Watch for false positives on legitimate short notes (e.g. a one-line journal entry).
- Embedding endpoint: reuse the existing one via `httpx` to LM Studio's `/v1/embeddings`. Already proven at scale in pf2e rules retrieval.
- Inbox file format prior art: the existing `ops/discord-threads.md` append pattern + the `ops/sessions/{date}/` per-day file structure.
- Existing `:remember` subcommand at `interfaces/discord/bot.py:1279-1282` is the closest analog to the new `:note` flow.

</specifics>

<canonical_refs>
## Canonical References

- `.planning/sketches/note-import-and-vault-sweeper.md` — original sketch with detailed requirements (this CONTEXT.md is the locked version)
- `interfaces/discord/bot.py:1279-1282` — `:remember` subcommand (pattern to follow for `:note`)
- `sentinel-core/app/routes/message.py` — warm-tier vault search injection (where note classifier service plugs in)
- `modules/pathfinder/app/llm.py::embed_texts` — embedding call pattern to reuse for sweeper similarity
- `modules/pathfinder/app/rules.py::check_ruling_answer_sanity` — sanity-gate pattern for pre-filter

</canonical_refs>
