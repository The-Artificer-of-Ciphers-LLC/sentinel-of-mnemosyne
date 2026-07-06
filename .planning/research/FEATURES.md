# Feature Research

**Domain:** Agentic note-taking / personal knowledge management (arscontexta + Building a Second Brain, fused into an existing FastAPI+Discord+Obsidian assistant)
**Researched:** 2026-07-05
**Confidence:** MEDIUM-HIGH (primary-source repo content for arscontexta mechanics; MEDIUM for BASB/PARA framing, which is well-established public methodology)

---

## Context: What Already Exists (v0.5.1 baseline — do not re-research)

This is a **subsequent milestone** (v0.6.0) restoring functionality that the phase-27 "Path B" pivot
removed. The current system already has, and this milestone builds **on top of**, not instead of:

- `Vault` Protocol seam (`app/vault.py`) — sole persistence interface
- Recall module: hot tier (persona + Self namespace + recent sessions) + warm tier (BM25 + semantic,
  RRF-merged) — see `.planning/research/FEATURES.md` history (superseded content) for full detail
- Vault sweeper with per-note `embedding_b64` frontmatter, live semantic retrieval
- A **flat-7 note classifier** + `/note/classify` + `/inbox` + `/vault/sweep` — notes are currently
  sorted into 7 flat categories at classification time (no PARA, no 6 Rs, no `_schema`, no MOCs)
- Pathfinder 2e module (NPC/session/rule management) — must be preserved as a module, not reverted

This document covers **only** the note-taking-engine features this milestone adds: the three-space
vault, PARA taxonomy, the 6 Rs pipeline, `_schema`/claim-titles/wikilinks, MOC maintenance, and the
27-command surface. Where a new feature **replaces or conflicts with** flat-7 behavior, this is flagged
explicitly (see "Conflicts with Existing flat-7 Behavior" below the tables).

---

## What arscontexta Actually Is (grounding, from primary source)

arscontexta (`github.com/agenticnotetaking/arscontexta`) is a Claude Code plugin that **derives** a
personal knowledge system from a conversation about how the user thinks and works, then generates:
folder structure, note templates with `_schema` blocks, a processing pipeline (skills), automation
hooks, and MOC navigation — backed by a 249-claim internal research corpus ("kernel.yaml" defines 15
universal primitives every generated system must include). It explicitly synthesizes Zettelkasten,
Cornell Note-Taking, Evergreen Notes, **PARA**, GTD, and cognitive-science research on context-switching
cost and spreading activation.

**Critical portability note:** arscontexta's automation is built as Claude Code plugin primitives —
`SessionStart` hook (tree injection, identity load), `PostToolUse` hook (schema validation on every
Write, async git auto-commit), and literal subagent spawning via the Task tool for "fresh context per
phase." Sentinel is a FastAPI service driven by Discord messages calling an Obsidian REST vault — it
has **no filesystem hooks and no Task-tool subagent spawner**. Every mechanism below needs a Sentinel-
native analog (sequential `call_core()` prompts per pipeline stage, background-task writes, vault-REST
reads instead of `tree`/`rg`), not a literal port. This is called out per-feature below.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features the phase-10 spec commits to and that the "second brain" promise is not credible without.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Three-space vault (`self/ notes/ ops/` + `inbox/ templates/`)** | The whole milestone's premise. `self/` = agent's persistent mind (identity, methodology, goals — read on every session start); `notes/` = the durable knowledge graph; `ops/` = temporal scaffolding (queue, sessions, health, observations, tensions). Conflating spaces is documented in the source as producing "six failure modes" (e.g. ops-into-notes pollutes search with processing debris, inflates note counts, degrades MOC coherence). | MEDIUM | Directory + path convention change, not new infra. Existing `ops/sessions/` write path already correct. Lazy stub creation on first write (per D-14) keeps this cheap — no big-bang migration needed beyond `core/` → `self/`/`ops/` per D-01. |
| **Session-start reading pattern (`self/identity.md`, `methodology.md`, `goals.md`, `relationships.md`, `ops/reminders.md`)** | A second brain that "forgets who you are" every message breaks the core trust promise — same failure class as the v0.5.1 "forgets after three turns" gap this milestone follows. | LOW-MEDIUM | Pure read-path extension: `asyncio.gather()` of 5 additional vault GETs, 404-silent per D-02. Composes cleanly with the existing hot-tier assembly in Recall — this is additional hot-tier content, not a new retrieval strategy. |
| **PARA taxonomy replacing the flat-7 classifier** | Users expect note organization that reflects actionability (Projects/Areas/Resources/Archives), not an arbitrary flat category set. This is the single largest **behavior change** in the milestone — see Conflicts section. | HIGH | Requires re-deciding what `/note/classify` outputs and how `/vault/sweep` routes notes. Per D-16, PARA's Projects/Areas map to `ops/` subdirectories (deadline/responsibility-bound, temporal), not `notes/` subfolders — `notes/` stays flat per arscontexta's kernel invariant ("no subfolders for organization; prevents folder reorganization from breaking links"). Resources ≈ `notes/` graph; Archives ≈ `ops/` rolling archive. |
| **Claim-title convention for `notes/`** | "This note argues that [title]" readability test. One insight per file is the atomic-note discipline the whole graph depends on — MOCs, wikilinks, and `:connect` all assume one claim per note. | LOW-MEDIUM | Prompt-engineering + validation problem (a title-quality check), not new plumbing. Bounded by local-model capability per D-11's "design prompts to work well with smaller models" constraint — needs example-rich prompts, not just an instruction. |
| **`_schema` block on every note** | arscontexta's kernel primitive `schema-enforcement`: "templates define required fields and enums; deterministic validation catches what instruction-following misses" as context fills. Without it, `:review`/`:check` have nothing to validate against. | MEDIUM | Minimum viable fields per D-05: `type` (permanent\|hub\|literature\|fleeting), `hub` (wikilink), `status` (draft\|ready). arscontexta's own kernel adds `description` (~150 char, distinct from title) and `topics` (MOC membership footer) as universal fields — recommend adopting both; they're what makes `:stats`/`:graph` and progressive disclosure work at all. |
| **Wikilinks connecting every note to the graph** | Without at least one `[[wikilink]]`, a note is an orphan — invisible to `:connect`, `:graph`, and MOC traversal. This is the mechanism that makes "second brain" not just "folder of files." | LOW | Enforced at `:review`/`:check` time; creation-time enforcement is a stretch goal (arscontexta's `PostToolUse` write-validate hook has no direct Sentinel equivalent — see Anti-Features). |
| **MOC / hub notes, created lazily** | Flat `notes/` with 50+ files needs a navigation layer or nothing is findable. This is the arscontexta answer to "how do you organize without folders." | MEDIUM | `:connect` finds/creates the owning hub; `:graph` reports hub membership + orphans; `:stats` reports hub count/avg-notes-per-hub. Depends on **PARA taxonomy landing first** (hub concept titles are how Resources gets organized without folders). |
| **Core command subset as Discord `:prefix` subcommands** | The phase-10 spec commits to all 27; but the ones with load-bearing dependencies on other table-stakes features are: `:capture`, `:seed` (Record), `:ralph`/`:pipeline` (orchestration), `:connect` (Reflect), `:review`/`:check` (Verify), `:stats`/`:graph` (navigation/health), `:help`. | MEDIUM | Same routing pattern as existing `_SUBCOMMAND_PROMPTS` dict (D-03) — additive, not a rewrite of `handle_sentask_subcommand()`. |
| **Reduce stage — inbox → notes/ with `_schema` + claim title** | The mechanical core of "the AI actually organizes my notes." Without it, `:capture`/`:seed` just dump text into `inbox/` forever — the pipeline has no output. | MEDIUM-HIGH | This is the stage most exposed to local-model quality limits (D-11). Depends on PARA taxonomy + `_schema` format landing first (Reduce writes both). |
| **Non-destructive vault operations preserved** | Existing constraint (sweeper only relocates to `_trash/`, never hard-deletes) must extend to all new pipeline writes — `:refactor`, `:reweave`, `:rethink` all touch existing notes. | LOW | Carry the existing constraint forward explicitly into every new write path; do not silently narrow it during the note-engine rebuild. |

### Differentiators (Competitive Advantage)

Features that go beyond "notes get filed somewhere" — where this milestone earns the "agentic" label.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Reweave (backward pass)** | The single most "second-brain" feature: old notes get updated when new understanding arrives, rather than staying frozen at the moment they were written. arscontexta describes this as the pipeline's most intellectually rich step; D-15 maps it directly to BASB's Distill phase. Genuinely differentiates from "just file it and forget it" note apps. | HIGH | Requires the system to search *its own* graph for stale-but-related notes given new content — closest thing to a "read the whole vault and reconsider" operation. Highest risk of being slow/expensive and of local-model quality ceiling (D-11) producing shallow updates. Depends on PARA + `_schema` + MOCs already being populated (nothing to reweave against otherwise). |
| **Operational learning loop (`ops/observations/`, `ops/tensions/` → `:rethink`)** | The system notices its own friction (an observation) or contradictions between new content and existing notes (a tension), accumulates them, and periodically surfaces them for the user to triage — arscontexta's kernel calls this "scientific method applied to knowledge systems: systems that cannot observe their own friction cannot evolve." This is what makes the vault self-correcting instead of static. | MEDIUM | Threshold-based surfacing (arscontexta default: >10 pending observations or >5 pending tensions triggers a `:rethink` suggestion at session-start) is a cheap, high-value pattern — pure counting + a nudge, no new retrieval infra. Composes with the existing session-start read pattern (table stakes above). |
| **`:graph` / `:stats` vault health analytics** | Orphan detection, link density, hub-size distribution, dangling-link detection — turns "is my vault healthy" from a vague feeling into a number. Directly actionable ("Inbox has 4 items older than 3 days — want to process?" per D-07 voice). | MEDIUM | Sentinel-native adaptation needed: arscontexta computes this via `tree` + `ripgrep` against a local filesystem; Sentinel must compute it via Vault-REST reads (list + parse frontmatter) since there's no local mount (see memory: "Vault is REST-only"). This is a real engineering cost the arscontexta repo doesn't have to pay. |
| **Fresh-context-per-phase orchestration for `:ralph`/`:pipeline`** | arscontexta's stated rationale: "LLM attention degrades as context fills; spawning a fresh subagent per phase keeps every phase in the smart zone." This is genuinely valuable for local-model quality (D-11's stated constraint) since smaller models degrade faster with context bloat than frontier models. | HIGH | No literal port possible — no Task-tool subagent spawner in a FastAPI service. D-13 already specifies the correct-scoped analog: `:ralph` sends **one** `call_core()` prompt and lets the AI orchestrate using vault context it already has; a truer "fresh context per phase" would instead issue **separate, sequential `call_core()` calls per 6 Rs stage** (Reduce call, then a fresh Reflect call with a clean context window, etc.) rather than one prompt asking the model to do all of it internally. This is the deepest design decision this research surfaces for requirements/roadmap: cheap-but-shallow (D-13's single-prompt approach) vs. faithful-but-costlier (sequential per-stage calls). Recommend starting with D-13's single-prompt approach for MVP and treating per-stage isolation as a differentiator to add once quality gaps are observed. |
| **Task-stack (`:tasks`, `:next`)** | Unified queue (pipeline tasks + auto-generated maintenance tasks) gives "what should I work on" a concrete answer instead of an open-ended vault. `:next` reconciling maintenance conditions (e.g. "12 notes connected, no orphans, inbox has 4 items older than 3 days") is what makes the system feel proactive rather than passive. | MEDIUM | Builds on `ops/queue/` (already specified, D-09) + the health/`:graph` metrics above. Natural second-phase feature once Record/Reduce/Reflect are solid. |
| **Plugin-tier commands (`:plugin:health`, `:plugin:architect`, `:plugin:recommend`, `:plugin:tutorial`)** | Meta-commands that reason about the vault's own configuration and give architecture advice — arscontexta's "derivation over templating" philosophy applied ongoing, not just at setup. Genuinely differentiates from static note tools. | MEDIUM | Lower priority than the standard 17 — these are meta/reflective tools on top of a working pipeline, not core to daily capture-organize-retrieve. Good candidates for a later phase once `:stats`/`:graph`/`:check` exist to give them something to reason about. |
| **Semantic search reused for `:connect`/`:reweave`/`:graph` candidate-finding** | The existing `SemanticRecall` strategy (already shipped, v0.5.1) is exactly the retrieval primitive arscontexta's optional `qmd` semantic layer provides — "not required, the system works with ripgrep + MOC traversal" but recommended when available. Sentinel already has this; arscontexta treats it as an add-on. | LOW | This is a genuine head start: reuse the existing embedding index for hub-candidate discovery (`:connect`) and stale-note discovery (`:reweave`) instead of building a new retrieval path. Flag explicitly for the roadmap — this dependency should be called out so planning doesn't accidentally re-invent semantic search inside the note engine. |

### Anti-Features (Do Not Build These)

| Feature | Why Requested | Why Problematic | Better Approach |
|---------|---------------|-----------------|-----------------|
| **Literal port of arscontexta's Claude Code hooks (`SessionStart`, `PostToolUse` write-validate, async git auto-commit)** | The source repo's automation looks complete and battle-tested; tempting to replicate 1:1. | These are Claude Code **plugin** primitives that fire on local filesystem events inside a Claude Code session. Sentinel has no local filesystem (vault is REST-only per memory), no Claude Code session lifecycle, and no git-auto-commit requirement in its constraints. Attempting a literal port invents infrastructure Sentinel doesn't have and wasn't asked to build. | Build the *outcome* each hook produces via Sentinel-native means: session-start reads via `asyncio.gather()` (D-02, already specified), schema validation as a step inside `:review`/`:check`/the Reduce stage (not a write-time hook), and skip git-auto-commit entirely — non-destructive `_trash/`-relocation is the existing durability guarantee. |
| **Scheduled/batch vault reorganization sessions** | "Clean up the vault every night" sounds like good hygiene. | Violates BASB's explicit "just-in-time organization" principle: organize only when acting on the information, not preemptively on a schedule. Scheduled reorg also risks destructive-feeling changes to notes the user hasn't touched in a while, undermining trust that the vault won't move things without being asked. | `:refactor`/`:rethink` are user- or threshold-triggered (arscontexta pattern: >10 pending observations / >5 tensions), never cron-scheduled. Lazy hub creation (D-06) and lazy stub creation (D-14) are the structural embodiment of "organize as a natural consequence of working." |
| **Premature full pipeline automation (auto-running `:pipeline` on every message without being asked)** | "Why doesn't it just always keep the vault perfectly organized in real time" is an intuitive ask. | The 6 Rs stages (especially Reduce and Reweave) are exactly where local-model quality is weakest (D-11 constraint) — auto-running them on unreviewed input risks silently degrading note quality at scale before anyone notices, and burns compute on every message even when nothing note-worthy was said. This is the note-engine's version of the v0.5.1 "over-retrieval" anti-feature: more automation is not better automation. | Keep `:capture`/`:seed` as explicit, user-invoked Record actions; `:ralph`/`:pipeline` as explicit batch operations the user triggers (matching D-13's existing decision). Auto-processing is a post-validation enhancement, not day-one scope. |
| **PARA subfolders inside `notes/` (`notes/projects/`, `notes/areas/`)** | Seems like the "obvious" way to implement PARA — just make the folders. | Directly contradicts arscontexta's kernel invariant that `notes/` is flat with no organizational subfolders ("prevents folder reorganization from breaking links") — and directly contradicts D-16's explicit instruction not to create these folders unless synthesis strongly calls for it. Folders reintroduce exactly the flat-7-style rigid categorization this milestone is meant to replace, just one level deeper. | PARA's Projects/Areas route to `ops/` subdirectories (temporal, deadline/responsibility-bound); Resources maps onto the flat `notes/` graph via MOC/hub organization; Archives maps to `ops/` rolling archive. `notes/` stays flat, always. |
| **Auto-updating `self/identity.md` from inferred user behavior without confirmation** | "The system should learn who I am automatically" sounds like the natural evolution of the self-space idea. | Explicitly deferred in the original phase-10 spec ("Deferred Ideas": auto-updating identity is future work). Self-space content (identity, relationships — including sensitive data like kids' schedules per the phase-10 spec) is high-trust content; silently auto-writing inferred facts into it risks embedding wrong or unwanted inferences into the system's persistent sense of the user. | Self-space updates flow through the explicit `:remember` command (user- or session-triggered) and the observation-promotion pipeline (`ops/observations/` → `self/methodology.md`, one-directional, requires the content to "earn permanence" by recurring) — never silent auto-write. |
| **Sentinel's own generated replies indexed as recalled/graph content** | Carried forward from the v0.5.1 research: "full conversation memory" intuition. | Same failure mode as before, now compounded: if the Reduce stage ever extracted "insights" from the Sentinel's own prior replies into `notes/`, hallucinations become permanent knowledge-graph nodes indistinguishable from user-authored claims — far worse than the existing session-recall issue because notes are the durable, trusted layer. | The `ops/` exclusion from Recall (already validated, v0.5.1) must extend to the Reduce stage's input sources: only user-authored `inbox/` content and explicitly user-provided source material are eligible for promotion into `notes/`. |
| **Over-retrieval during `:connect`/`:reweave` candidate search** | "Search the whole vault for every possible connection" feels thorough. | Same anti-pattern as v0.5.1's over-retrieval finding: injecting dozens of loosely-related notes into a Reflect/Reweave prompt buries the 1-2 genuinely relevant hub/notes and degrades local-model output quality (D-11) faster than it would degrade a frontier model. | Reuse the existing relevance-threshold + budget discipline from Recall (already validated) for hub-candidate and stale-note discovery — top-k within budget, not exhaustive scan-and-dump. |

---

## Conflicts with Existing flat-7 Behavior (flagged per quality gate)

| arscontexta/PARA feature | Conflicts with | Resolution needed |
|---|---|---|
| PARA taxonomy (Projects/Areas/Resources/Archives) | The flat-7 classifier's existing category set and `/note/classify` output contract | `/note/classify` must be re-specified to emit PARA-oriented routing (or a superseding classification) instead of the current 7 categories. This is a breaking change to an existing, already-shipped endpoint — requirements must decide whether flat-7 is replaced outright or PARA is layered as a second classification dimension during a transition window. |
| Flat, folder-less `notes/` with MOC navigation | Whatever folder/category structure `/vault/sweep` currently sweeps notes into under the flat-7 model | Sweeper routing logic must change from "file under one of 7 categories" to "file in `inbox/` first, then Reduce moves to flat `notes/` with `_schema`+hub membership." This changes `/vault/sweep`'s effective behavior, not just its output labels. |
| `_schema` block + claim-title + wikilink requirement for "done" notes | Any existing flat-7-classified notes that lack these fields | Needs a migration/backfill decision: are pre-milestone notes retroactively brought up to the new standard (via `:check`/`:review` batch pass), or grandfathered as-is with the new standard applying only going forward? Not resolved by this research — flag for requirements. |

---

## Feature Dependencies

```
[Three-space vault: self/ notes/ ops/ + inbox/ templates/]
    └──required by──> [PARA taxonomy replacing flat-7]
    └──required by──> [Session-start reading pattern]
    └──required by──> [_schema block standard]

[PARA taxonomy replacing flat-7]
    └──required by──> [Reduce stage: inbox/ -> notes/ with _schema]
    └──conflicts with──> [Existing flat-7 classifier / note/classify output]

[_schema block standard + claim-title convention]
    └──required by──> [MOC / hub notes]
    └──required by──> [:review, :check (Verify stage)]

[MOC / hub notes]
    └──required by──> [:connect (Reflect stage)]
    └──required by──> [:graph, :stats]

[Reduce + Reflect (6 Rs stages 2-3)]
    └──required by──> [Reweave (6 Rs stage 4)]
    └──required by──> [:rethink, :refactor (6 Rs stage 6)]

[Existing SemanticRecall (v0.5.1, already shipped)]
    └──enables──> [:connect hub-candidate discovery]
    └──enables──> [:reweave stale-note discovery]

[Existing Vault Protocol seam (app/vault.py)]
    └──required by──> [all new vault paths and writes — no bypass]

[ops/observations/, ops/tensions/]
    └──required by──> [:rethink threshold-triggered surfacing]
    └──enhances──> [session-start reading pattern (surfaces maintenance signals)]
```

### Dependency Notes

- **Three-space vault gates almost everything.** PARA taxonomy, `_schema`, MOCs, and the session-start
  read pattern all assume the `self/notes/ops/inbox/templates` structure exists first. This is the
  correct phase-1 foundation for the roadmap.
- **PARA taxonomy directly conflicts with the shipped flat-7 classifier** — this is not a pure addition,
  it is a replacement of already-shipped behavior (`/note/classify`, `/vault/sweep` routing). Roadmap
  should sequence this as an explicit "supersede" phase, not bundle it silently inside a "vault structure"
  phase.
- **Reweave, `:rethink`, `:refactor` (6 Rs stages 4 and 6) require Reduce+Reflect (stages 2-3) to already
  be populating a non-trivial `notes/` graph** — there is nothing to reweave, rethink, or refactor against
  on an empty or freshly-migrated vault. These are correctly late-phase.
- **`:connect` and `:reweave` should reuse the existing `SemanticRecall` strategy**, not build new
  retrieval. This is a genuine architectural head start from the v0.5.1 work and should be an explicit
  phase dependency, not rediscovered.
- **Fresh-context-per-phase orchestration has no existing Sentinel primitive.** Whichever design is
  chosen (D-13's single-prompt approach vs. true sequential per-stage calls) is independent of the vault-
  structure work and can be deferred/iterated without blocking Record/Reduce/Reflect landing.

---

## MVP Definition

### Launch With (v0.6.0 core)

- [ ] **Three-space vault structure** (`self/ notes/ ops/ inbox/ templates/`) with migration from `core/`
- [ ] **Session-start reading pattern** (`self/*.md`, `ops/reminders.md`) — parallel reads, graceful 404
- [ ] **PARA taxonomy replacing flat-7** — `/note/classify` and `/vault/sweep` re-specified
- [ ] **`_schema` block + claim-title + wikilink note-quality standard**, with `:review`/`:check`
- [ ] **Record → Reduce → Reflect (6 Rs stages 1-3)** — `:capture`, `:seed`, `:ralph` (Reduce+Reflect batch)
- [ ] **MOC/hub notes created lazily** via `:connect`
- [ ] **Core command subset**: `:capture :seed :ralph :pipeline :connect :review :check :stats :graph :help`
- [ ] **Non-destructive writes preserved** across all new pipeline paths (`_trash/` relocation only)

### Add After Validation (v0.6.x)

- [ ] **Reweave (6 Rs stage 4)** — depends on a populated graph existing first; validate Reduce/Reflect
      quality before adding backward-pass complexity
- [ ] **Operational learning loop** (`ops/observations/`, `ops/tensions/`, `:rethink`) — threshold-based
      surfacing once there's enough pipeline activity to generate friction signals
- [ ] **Task-stack** (`:tasks`, `:next`) — natural once `ops/queue/` and health metrics exist
- [ ] **`:refactor`, `:revisit`, `:learn`, `:remember`** — remaining standard commands
- [ ] **True fresh-context-per-phase orchestration** (sequential per-stage `call_core()` calls) — only if
      D-13's single-prompt `:ralph` shows quality degradation on the local model

### Future Consideration (v0.7+)

- [ ] **Plugin-tier commands** (`:plugin:health`, `:plugin:architect`, `:plugin:recommend`,
      `:plugin:tutorial`, `:plugin:add-domain`, `:plugin:reseed`, `:plugin:upgrade`) — meta/reflective
      tools that need a working pipeline to reason about first
- [ ] **Vault-wide backfill of pre-milestone notes to the `_schema`/claim-title standard** — decide
      migrate-vs-grandfather in requirements before scoping
- [ ] **Multi-domain extension** (`:plugin:add-domain`) — not relevant to a single-operator personal vault
      per existing Out-of-Scope constraints

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Three-space vault structure | HIGH | MEDIUM | P1 — gates everything |
| Session-start reading pattern | HIGH | LOW-MEDIUM | P1 — closes "forgets who I am" |
| PARA taxonomy replacing flat-7 | HIGH | HIGH | P1 — core milestone deliverable, but a breaking change |
| `_schema` + claim-title + wikilinks | HIGH | MEDIUM | P1 — required for Verify stage and MOCs |
| Record → Reduce → Reflect | HIGH | MEDIUM-HIGH | P1 — the pipeline's actual output |
| MOC/hub notes | HIGH | MEDIUM | P1 — navigation layer, no flat-graph alternative |
| Core command subset | HIGH | MEDIUM | P1 — user-facing surface |
| Reweave | MEDIUM-HIGH | HIGH | P2 — depends on a populated graph existing |
| Operational learning loop | MEDIUM | MEDIUM | P2 — self-correction, not core capture/organize/retrieve |
| Task-stack (`:tasks`/`:next`) | MEDIUM | MEDIUM | P2 — proactive layer on top of health metrics |
| Fresh-context-per-phase orchestration | MEDIUM | HIGH | P2/P3 — no Sentinel primitive exists; validate need first |
| Plugin-tier meta-commands | LOW-MEDIUM | MEDIUM | P3 — reflective tools needing a working pipeline first |

**Priority key:**
- P1: Must have for launch (v0.6.0 core)
- P2: Should have, add when possible (v0.6.x)
- P3: Nice to have, future consideration (v0.7+)

---

## What "Good Note-Taking" Looks Like to the User

Synthesized from arscontexta's design rationale and BASB's stated principles:

1. **Capture is zero-friction.** `:seed`/`:capture` never ask the user to categorize anything up front —
   raw content goes to `inbox/`; organization happens later, during Reduce, not at capture time.
2. **Organization happens just-in-time, not on a schedule.** Nothing gets reorganized because a timer
   fired; it gets processed because the user ran `:ralph`/`:pipeline`, or because a threshold (pending
   observations/tensions) earned a nudge.
3. **Every finished note makes exactly one claim, titled as that claim, and is reachable from a hub.**
   If a note can't pass "this note argues that [title]," or has no wikilink into the graph, it isn't done.
4. **Old knowledge gets revised, not frozen.** Reweave means today's insight can change what a note
   written months ago says — the graph is alive, not an append-only log.
5. **The system notices its own friction and surfaces it, unprompted but not naggingly** — "Inbox has 4
   items older than 3 days — want to process?" (per D-07's stated voice), triggered by a threshold, not
   every session.
6. **Stable self-knowledge is never silently rewritten.** `self/identity.md` and `self/relationships.md`
   change only through explicit user action (`:remember`) or a promotion pipeline that requires an
   observation to recur — never a silent inference.
7. **The vault never surprises the user with data loss.** All restructuring (`:refactor`, `:reweave`)
   relocates to `_trash/` at worst; it never hard-deletes.

---

## Sources

**Primary source (HIGH confidence — direct repository read, not summarized):**
- `https://raw.githubusercontent.com/agenticnotetaking/arscontexta/main/README.md` — command list, 6 Rs
  table, hooks table, three-space overview, philosophy/synthesis statement
- `https://raw.githubusercontent.com/agenticnotetaking/arscontexta/main/reference/three-spaces.md` —
  full self/notes/ops specification, growth/load/durability profiles, six failure modes of conflation,
  content promotion rule
- `https://raw.githubusercontent.com/agenticnotetaking/arscontexta/main/reference/kernel.yaml` — 15
  universal kernel primitives (markdown-yaml, wiki-links, moc-hierarchy, schema-enforcement, self-space,
  session-rhythm, discovery-first, operational-learning-loop, task-stack, methodology-folder,
  session-capture, etc.) with validation thresholds and cognitive-science grounding citations

**Secondary sources (MEDIUM confidence — WebFetch summarization + web search, cross-checked against
primary source above):**
- WebFetch digest of `github.com/agenticnotetaking/arscontexta` (general repo overview)
- WebFetch digest attempted on `lobehub.com/skills/agenticnotetaking-arscontexta-reflect` — blocked
  (HTTP 403), not used as a source
- Web search on Tiago Forte's Building a Second Brain — PARA (Projects/Areas/Resources/Archives) and
  CODE (Capture/Organize/Distill/Express) framework, "just-in-time organization" principle

**Project-internal sources (authoritative for Sentinel-specific constraints):**
- `.planning/PROJECT.md` — v0.6.0 milestone scope, existing validated requirements, Out-of-Scope
  constraints (single-user, no proprietary cloud, non-destructive vault ops)
- `docs/2nd-brain-original-design/10-CONTEXT-master-spec.md` — the phase-10 master spec: D-01 through
  D-16 implementation decisions, the 27-command table with 6 Rs mapping, note-quality standard (D-05),
  MOC pattern (D-06), migration scope (D-10), PARA/arscontexta synthesis guidance (D-16)
- `.planning/research/FEATURES.md` (prior version, v0.5.1) — existing Recall/semantic-search/retention
  feature landscape this milestone builds on top of, referenced for continuity and reuse opportunities

---
*Feature research for: Sentinel of Mnemosyne — v0.6.0 "Restore the Second-Brain Core" milestone*
*Researched: 2026-07-05*
