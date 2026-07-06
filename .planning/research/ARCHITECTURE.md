# Architecture Research

**Domain:** Sentinel of Mnemosyne — v0.6.0 "Restore the Second-Brain Core" (arscontexta + BASB engine as the core, Pathfinder demoted to a module)
**Researched:** 2026-07-05
**Confidence:** HIGH for current-codebase findings (all derived from production source, ADRs, and the recovered phase-10 master spec) — MEDIUM for the arscontexta upstream pattern citations (single WebFetch pass over `agenticnotetaking/arscontexta`, not independently cross-verified against a second source)

## Executive Finding

The Discord-side command surface for the 27-command system is **already substantially wired** —
`interfaces/discord/command_router.py` and `bot.py` already route `:capture`, `:seed`, `:ralph`,
`:pipeline`, `:reweave`, `:connect`, `:review`, `:check`, `:rethink`, `:refactor`, `:tasks`,
`:stats`, `:graph`, `:next`, `:learn`, `:remember`, `:revisit`, `:note`, `:inbox`, `:vault-sweep`,
and all ten `:plugin:*` verbs. `RecallConfig.self_paths` already reads `self/identity.md`,
`self/methodology.md`, `self/goals.md`, `self/relationships.md`, `ops/reminders.md`, and
`self/learning-areas.md` in parallel — D-02's session-start reading pattern is functionally
already implemented via the Recall module built in phases 39–41.

**What is actually missing — and the true meaning of "the core was gutted" — is orchestration,
not routing.** Every one of `:ralph`, `:pipeline`, `:reweave`, `:check`, `:rethink` today resolves
to a single fixed-text prompt (`_SUBCOMMAND_PROMPTS[subcmd]`) sent through `call_core()` →
`POST /message` → `MessageProcessor.process()` → one `ai_provider.complete()` call using the
conversational Hot/Warm tier context. There is **no tool-calling, no vault mutation loop, and no
per-phase context isolation** — the LLM receives one text instruction and returns one text reply;
nothing walks `inbox/`, writes `_schema` blocks, or updates a MOC. The 6 Rs pipeline does not
exist as executable behavior today; it exists only as a Discord-visible prompt string. This is the
single most important finding for phase sequencing: **building the 6 Rs pipeline is fundamentally
a new backend-orchestration problem, not a prompt-engineering problem**, and the existing
`vault_sweeper.py` / `note_sweep_runner.py` / `task_runner.py` / `sweep_status_store.py` stack —
already proven for a different long-running, admin-gated, background vault mutation (the sweep) —
is the correct architectural template to clone, not extend inline in `MessageProcessor`.

## Standard Architecture

### System Overview — Current State (v0.5.1, pre-milestone)

```
┌──────────────────────────────────────────────────────────────────────┐
│  Discord Interface (interfaces/discord/)                              │
│  bot.py → command_router.route_message() → handle_subcommand()        │
│    :capture :seed :ralph :pipeline :reweave :connect :review :check   │
│    :rethink :refactor :tasks :stats :graph :next :learn :remember     │
│    :revisit :note :inbox :vault-sweep :plugin:*         [ALL ROUTED]  │
│    :pf <noun> <verb>  → pathfinder_dispatch (module gateway)          │
└───────────┬─────────────────────────────────────────────┬────────────┘
            │ call_core(fixed prompt)                      │ :pf only
            ▼                                              ▼
┌───────────────────────────────────┐   ┌──────────────────────────────┐
│  Sentinel Core (FastAPI)          │   │  module_gateway.py           │
│  POST /message → MessageProcessor │   │  forward_get/forward_post    │
│    ├─ recall.assemble() (Hot+Warm)│──▶│  /modules/pathfinder/{path}  │
│    ├─ ONE ai_provider.complete()  │   └───────────────┬──────────────┘
│    └─ write session summary       │                   ▼
│                                    │   ┌──────────────────────────────┐
│  POST /note/classify (flat-7)     │   │  pf2e-module (own FastAPI,   │
│  POST /vault/sweep/start (bg task)│   │  own Vault reads, own tests) │
└───────────┬────────────────────────┘   └──────────────────────────────┘
            │
┌───────────▼────────────────────────────────────────────────────────────┐
│  Vault Protocol (app/vault.py, ADR-0002)                                │
│  ObsidianVault ←→ Obsidian Local REST API                               │
│  Namespaces: self/ sentinel/ ops/ inbox/(single-file queue) _trash/     │
│  Sweeper (vault_sweeper.py + vault_sweep_plan.py): noise-trash,         │
│    flat-7 topic-dir relocation, duplicate-trash, embedding maintenance  │
└──────────────────────────────────────────────────────────────────────┘
```

### System Overview — Target State (v0.6.0, post-milestone)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Discord Interface — UNCHANGED routing surface, CHANGED backing calls     │
│    :capture :seed :note      → call_core_note()      (inbox intake — kept)│
│    :ralph :pipeline :reweave │→ NEW: call_core_pipeline_start/status      │
│    :check :rethink            (mirrors :vault-sweep's admin-gated shape) │
│    :review :graph :stats :connect → NEW: call_core_schema/graph endpoints│
│    :pf <noun> <verb>         → pathfinder_dispatch (UNCHANGED)           │
└───────────┬──────────────────────────────────────────┬───────────────────┘
            │                                            │ :pf only (unchanged)
            ▼                                            ▼
┌────────────────────────────────────────┐   ┌───────────────────────────┐
│  Sentinel Core (FastAPI) — additive     │   │  module_gateway (unchanged)│
│                                          │   └──────────────┬────────────┘
│  POST /message  (UNCHANGED shape)       │                  ▼
│    MessageProcessor → recall.assemble() │   ┌───────────────────────────┐
│    → ONE ai_provider.complete()         │   │  pf2e-module (untouched)  │
│                                          │   └───────────────────────────┘
│  POST /note/classify  (MODIFIED taxonomy)│
│    note_classifier: notes-bound vs       │
│    ops-bound routing decision            │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │ NEW: Pipeline Orchestrator         │ │
│  │ POST /vault/pipeline/start          │ │
│  │ GET  /vault/pipeline/status         │ │
│  │   → task_runner.schedule(           │ │
│  │       pipeline_orchestrator.run())  │ │
│  │   → per-phase FRESH structured      │ │
│  │     completion calls (Reduce/       │ │
│  │     Reflect/Reweave/Verify/Rethink) │ │
│  │   → writes directly via Vault seam  │ │
│  │   → pipeline_status_store (polling) │ │
│  └────────────────────────────────────┘ │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │ NEW: note_schema.py                │ │
│  │   parse/validate trailing _schema:  │ │
│  │   block (type/hub/status)           │ │
│  │ NEW: graph_analysis.py             │ │
│  │   orphans/triangles/density/hubs   │ │
│  │ NEW: moc_maintenance.py            │ │
│  │   lazy hub create/append, wikilink │ │
│  └────────────────────────────────────┘ │
└──────────┬───────────────────────────────┘
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Vault Protocol (app/vault.py) — UNCHANGED seam, EXTENDED namespaces      │
│  self/ sentinel/ ops/ notes/(NEW) inbox/(NEW real space) templates/(NEW)  │
│  _trash/                                                                  │
│  PROTECTED_NAMESPACES += templates/ (candidate)                           │
│  Sweeper: flat-7 topic-dir relocation RETIRED for notes/-bound content;   │
│    ops/-subdir routing (journal/accomplishment/observation) KEPT;        │
│    embedding maintenance (embedding_sidecar_index.py) UNCHANGED           │
└──────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | Status |
|-----------|----------------|--------|
| `interfaces/discord/command_router.py` | `:prefix` parsing, subcommand dispatch | **Modified** — `:ralph/:pipeline/:reweave/:check/:rethink/:graph/:stats/:review/:connect` swap from `call_core(fixed_prompt)` to new dedicated endpoint calls; `:capture/:seed/:note/:inbox/:vault-sweep/:pf` unchanged |
| `interfaces/discord/bot.py` `_SUBCOMMAND_PROMPTS` / `_PLUGIN_PROMPTS` | Fixed-prompt fallback dict | **Modified** — entries for pipeline/schema/graph commands removed (replaced by real endpoint calls); plugin prompts (`setup/tutorial/upgrade/reseed/architect/recommend`) stay as free-text prompts (no vault mutation required) |
| `app/services/message_processing.py` `MessageProcessor` | Single-turn chat: persona + Recall context + one completion + session write | **Unchanged** — this is deliberately NOT where the 6 Rs pipeline lives (see Anti-Pattern 4) |
| `app/services/recall.py` `Recall` / `RecallConfig` | Hot/Warm tier assembly, retrieval policy | **Modified (minor)** — `exclude_prefixes` gains `templates/`; confirm `notes/` stays un-excluded (it is the searchable knowledge graph); `self_paths` unchanged |
| `app/services/note_classifier.py` | Flat-7 closed-vocabulary classification + `TOPIC_VAULT_PATH` directory routing | **Modified** — taxonomy splits into notes-bound (→ `inbox/` for Reduce) vs ops-bound (→ `ops/{journal,accomplishments,observations}`); `noise`/`unsure` handling unchanged |
| `app/services/vault_sweep_plan.py` / `vault_sweeper.py` | Sweep move-intent planning + orchestration | **Modified** — misplaced-topic relocation retired for anything classified notes-bound (Reduce phase owns that now); ops/-subdir relocation kept; noise-trash/duplicate-trash/lock/embedding steps unchanged |
| `app/vault.py` `Vault` Protocol / `ObsidianVault` / `PROTECTED_NAMESPACES` | Sole persistence seam; protected-path guard | **Modified (additive)** — no signature changes; `PROTECTED_NAMESPACES` gains `templates/` as a candidate; namespace set conceptually extends to `notes/`, `inbox/` (already generic path strings, no protocol change needed) |
| `app/services/embedding_sidecar_index.py` | Sweeper-maintained embedding index for SemanticRecall | **Unchanged** — must keep indexing whatever lands in `notes/` regardless of taxonomy; eligibility rules are already directory-agnostic (fail-soft per-note), no code change expected |
| **NEW** `app/services/pipeline_orchestrator.py` | Background task: walks `inbox/` queue, drives each 6 Rs phase as an independent fresh-context structured completion, writes directly via `Vault` | **New** — mirrors `vault_sweeper.run_sweep` shape |
| **NEW** `app/services/pipeline_status_store.py` | Progress tracking for a running pipeline (idle/running/complete/per-phase counts) | **New** — mirrors `sweep_status_store.py` exactly |
| **NEW** `app/services/six_rs/reduce.py`, `reflect.py`, `reweave.py`, `verify.py`, `rethink.py` | Per-phase structured LLM calls (json-schema response format, minimal fresh context) | **New** — mirrors `note_classifier.py`'s model-resolution + `acompletion_with_profile(response_format=json_schema)` pattern |
| **NEW** `app/routes/pipeline.py` (or extend `note.py`) | `POST /vault/pipeline/start`, `GET /vault/pipeline/status` | **New** — mirrors `/vault/sweep/start` / `/vault/sweep/status` admin-gated shape verbatim |
| **NEW** `app/services/note_schema.py` | Parse/validate the trailing `_schema:` fenced YAML block (type, hub, status) — distinct from top-of-file frontmatter | **New** — backs `:review` (single-note, request-time) and `:check` (batch, background) |
| **NEW** `app/services/graph_analysis.py` | Walk `notes/`, parse wikilinks + `_schema`, compute orphans/triangles/link density/hub membership | **New** — backs `:graph`, `:stats`, and the hub-lookup half of `:connect` |
| **NEW** `app/services/moc_maintenance.py` | Lazy hub-note creation/append (D-06): decide create-vs-append, write bidirectional wikilinks | **New** — consumed by `:connect` and the Reflect phase |
| Vault directory bootstrap (`self/ notes/ ops/ inbox/ templates/`) | Lazy stub creation on first write (D-14 pattern already established) | **New usage of an existing pattern** — no new module; reuses `write_note` lazy-create semantics already used elsewhere |
| One-time migration task | Move existing flat-7 content (`learning/`, `accomplishments/`, `journal/`, `references/`) into the new shape | **New, transient** — a migration script/phase task, not a persistent component |
| `modules/pathfinder/*`, `docker-compose.yml`, module gateway | Pathfinder module, Docker Compose profile, proxy pattern | **Unchanged** — zero import coupling; no new container or compose entry required for the pipeline orchestrator (it lives inside `sentinel-core`, same process as the sweeper) |

## Recommended Project Structure

```
sentinel-core/
├── app/
│   ├── vault.py                        # UNCHANGED seam; PROTECTED_NAMESPACES += templates/
│   ├── services/
│   │   ├── note_classifier.py          # MODIFIED: notes-bound vs ops-bound routing
│   │   ├── vault_sweep_plan.py         # MODIFIED: retire notes/-bound topic-dir moves
│   │   ├── vault_sweeper.py            # MODIFIED: same scope narrowing
│   │   ├── recall.py                   # MODIFIED (minor): exclude_prefixes += templates/
│   │   ├── message_processing.py       # UNCHANGED
│   │   ├── pipeline_orchestrator.py    # NEW — background 6 Rs orchestration
│   │   ├── pipeline_status_store.py    # NEW — mirrors sweep_status_store.py
│   │   ├── note_schema.py              # NEW — trailing _schema: block parse/validate
│   │   ├── graph_analysis.py           # NEW — orphans/triangles/density/hubs
│   │   ├── moc_maintenance.py          # NEW — lazy hub create/append
│   │   └── six_rs/                     # NEW package
│   │       ├── __init__.py
│   │       ├── reduce.py               # extract claim + _schema, inbox/ → notes/
│   │       ├── reflect.py              # hub lookup (graph_analysis + optional SemanticRecall)
│   │       ├── reweave.py              # backward-pass update candidates
│   │       ├── verify.py               # claim-title / schema / wikilink check
│   │       └── rethink.py              # ops/observations + ops/tensions triage
│   └── routes/
│       └── pipeline.py                 # NEW — POST /vault/pipeline/start, GET .../status
└── tests/
    ├── test_note_classifier.py         # MODIFIED: notes-bound/ops-bound routing cases
    ├── test_vault_sweep_plan.py        # MODIFIED: topic-dir-move scope narrowing
    ├── test_pipeline_orchestrator.py   # NEW
    ├── test_six_rs_reduce.py / _reflect.py / _reweave.py / _verify.py / _rethink.py  # NEW
    ├── test_note_schema.py             # NEW
    └── test_graph_analysis.py          # NEW

interfaces/discord/
├── command_router.py                   # MODIFIED: pipeline/schema/graph commands call new endpoints
├── bot.py                               # MODIFIED: _SUBCOMMAND_PROMPTS entries removed for those verbs
└── core_gateway.py                      # MODIFIED (or extended): call_core_pipeline_start/status,
                                          #   call_core_schema_review/check, call_core_graph
                                          #   — mirrors existing call_core_sweep_start/status
```

### Structure Rationale

- **`six_rs/` as its own package, not flat under `services/`:** five phase modules sharing one
  structured-completion pattern (borrowed from `note_classifier.py`) are a cohesive unit; grouping
  them signals "these are the pipeline phases" the way `retrieval/` signaled "these are recall
  strategies" in phase 40.
- **`pipeline_orchestrator.py` + `pipeline_status_store.py` as siblings of `vault_sweeper.py` +
  `sweep_status_store.py`, not a replacement for them:** the sweep and the pipeline are two
  independent background vault-mutation processes with the same shape (admin-gated start,
  background task, pollable status, non-destructive-by-default). Cloning the proven shape is lower
  risk than inventing a new one.
- **`note_schema.py` is separate from `markdown_frontmatter.py`:** arscontexta's `_schema` block is
  a **trailing fenced block**, not the file's leading YAML frontmatter that `markdown_frontmatter.py`
  already owns (used for `original_path`/`topic_moved_at`/`sweep_at` provenance). Conflating the two
  would mean a single parser owning two structurally different metadata locations with different
  write orders — keep them as two small, single-purpose modules.

## Architectural Patterns

### Pattern 1: 6 Rs phases are independent structured completions, not one conversational prompt

**What:** Each 6 Rs phase (Reduce, Reflect, Reweave, Verify, Rethink) is its own
`acompletion_with_profile(..., response_format={"type": "json_schema", ...})` call, exactly
mirroring `note_classifier.classify_note()`'s existing model-resolution + JSON-schema-constrained
completion pattern. Each phase call receives **only the minimal context it needs** (e.g. Reduce
gets the one inbox entry's text; Reflect gets the entry's extracted claim plus a short list of hub
candidates from `graph_analysis`) — never the full conversational Hot/Warm tier that
`Recall.assemble()` builds for chat turns.

**When to use:** Any `:ralph` / `:pipeline` / `:reweave` / `:rethink` execution. This is the
concrete backend meaning of arscontexta's "fresh context per phase" principle inside a
non-agentic, non-tool-calling FastAPI + LiteLLM stack: since Sentinel Core has no coding-agent
subprocess/subagent runtime, "fresh context" is achieved by **issuing N independent LLM completions
with N deliberately narrow context payloads**, not by literally spawning OS-level subagents.

**Trade-offs:** More total LLM calls per `:ralph` run than today's one-shot prompt, but each call is
smaller, cheaper, and — critically — produces a **parseable, schema-validated result** the
orchestrator can act on deterministically (write a file, add a wikilink), rather than free text a
human has to trust the chat model executed correctly. This is the only way to get real vault
mutations out of a model that has no tool-use loop.

**Example:**
```python
# app/services/six_rs/reduce.py — mirrors note_classifier.py's model-resolution pattern
async def reduce_entry(entry_text: str, *, vault: Vault) -> ReduceResult:
    model_id, profile, api_base = await _resolve_model_for_task("structured")
    response = await acompletion_with_profile(
        model=model_id,
        messages=[
            {"role": "system", "content": _REDUCE_SYSTEM_PROMPT},
            {"role": "user", "content": entry_text},  # ONLY this entry — no Hot/Warm tier
        ],
        profile=profile,
        api_base=api_base,
        api_key="lmstudio",
        response_format={"type": "json_schema", "json_schema": _REDUCE_SCHEMA},
        temperature=0.0,
    )
    return ReduceResult.model_validate(_parse_or_coerce(response))
```

### Pattern 2: Pipeline orchestration is a background task, not a request-time chat turn

**What:** `POST /vault/pipeline/start` (admin-gated, same shape as `POST /vault/sweep/start`)
schedules `pipeline_orchestrator.run(...)` via the existing `task_runner.TaskRunner` seam
(`asyncio.create_task`). The orchestrator walks the `inbox/` queue, invokes each `six_rs/*` phase in
sequence per entry, writes results through the `Vault` Protocol, and updates
`pipeline_status_store` after each entry so `GET /vault/pipeline/status` can report progress.

**When to use:** Every pipeline-shaped command (`:ralph`, `:pipeline`, `:reweave`, `:rethink`,
`:check` batch mode). `:review` (single note) can stay request-time/synchronous since it is one
`note_schema` validation pass, not a queue walk.

**Trade-offs:** Discord UX changes from "one immediate text reply" to "started; poll `:tasks` or
`:vault-sweep status`-style follow-up for completion" — a real behavior change users will notice,
but it is the same UX the sweep already trained users on, and it is the only way to keep `POST
/message`'s existing latency/token-budget contract intact.

**Example:**
```python
# app/routes/pipeline.py — deliberately mirrors app/routes/note.py's sweep routes
@router.post("/vault/pipeline/start")
async def pipeline_start(req: PipelineStartRequest, request: Request):
    if not _is_admin_route(req.user_id):
        raise HTTPException(status_code=403, detail="admin only")
    ctx = get_route_context(request)
    return await start_pipeline(vault=ctx.vault, task_runner=ctx.task_runner, mode=req.mode)
```

### Pattern 3: Notes space stays flat — no directory-based topic filing inside `notes/`

**What:** arscontexta's three-space design (confirmed via `reference/three-spaces.md`) mandates a
**flat** `notes/` folder navigated via MOC/wikilinks and discovered via `description` frontmatter +
semantic search — never subdivided into topic directories. The **current** flat-7 classifier does
the opposite: `TOPIC_VAULT_PATH` files content into `learning/`, `accomplishments/`, `references/`
as separate top-level directories, and `vault_sweep_plan.propose_topic_move` actively relocates
misfiled notes between them. These two models are structurally incompatible for anything destined
for `notes/`.

**When to use:** Any content classified as durable knowledge (today's `learning`/`reference`
slugs). Route it to `inbox/` for the Reduce phase to transform into a `notes/{claim-slug}.md` file
with a trailing `_schema:` block and at least one wikilink — never directly into a
`notes/{topic}/` subdirectory.

**Trade-offs:** Content that is genuinely operational rather than durable knowledge (`journal`,
`accomplishment`, `observation`) keeps directory-based filing, but under `ops/` subdirectories
(`ops/journal/`, `ops/accomplishments/`, `ops/observations/`) rather than `notes/` — this matches
D-16's explicit guidance ("PARA's operational concepts likely map to `ops/` subdirectories, not
`notes/` subdirectories") and requires no new sweep-plan code, only a routing-table change in
`note_classifier.TOPIC_VAULT_PATH`.

### Pattern 4: MOC hub lookup reuses SemanticRecall's embedding infrastructure before reaching for a fresh LLM call

**What:** `:connect`'s "which hub does this note belong to" decision and the Reflect phase's hub
lookup can both be answered by running the note's embedding (already computed and indexed by the
sweeper via `embedding_sidecar_index.py`) against the subset of `notes/` entries whose `_schema.type
== hub`, using the same cosine-similarity machinery `SemanticRecall` already implements — no new
embedding client, no new LLM call required for the common case. A fresh LLM completion is only
needed as a fallback when no existing hub clears the similarity floor and a new hub must be named.

**When to use:** `graph_analysis.py` / `moc_maintenance.py` implementation. Treat hub-matching as a
retrieval problem first, a generation problem second.

**Trade-offs:** Couples `moc_maintenance.py` to the embedding sidecar index's fail-soft contract
(missing/stale/model-mismatch entries must degrade to "no hub match, ask the model" rather than
raise) — acceptable since that contract is already load-bearing for `SemanticRecall` and well
tested.

## Data Flow

### Command dispatch — before and after

```
BEFORE (all pipeline-shaped commands):
  Discord :ralph
    → command_router.handle_subcommand("ralph", ...)
    → fixed_prompt = _SUBCOMMAND_PROMPTS["ralph"]
    → call_core(user_id, fixed_prompt)
    → POST /message → MessageProcessor.process()
    → recall.assemble() (Hot+Warm) + ONE ai_provider.complete()
    → free text back to Discord — NO vault mutation guaranteed

AFTER:
  Discord :ralph
    → command_router.handle_subcommand("ralph", ...)
    → call_core_pipeline_start(user_id, mode="ralph")
    → POST /vault/pipeline/start (admin-gated, mirrors /vault/sweep/start)
    → task_runner.schedule(pipeline_orchestrator.run(mode="ralph"))
    → orchestrator walks inbox/ queue:
         for entry in inbox_entries:
             reduce_result  = six_rs.reduce.reduce_entry(entry.text)      # fresh completion
             vault.write_note(f"notes/{reduce_result.slug}.md", ...)
             reflect_result = six_rs.reflect.find_hub(reduce_result)      # embedding-first, LLM fallback
             moc_maintenance.attach_to_hub(reflect_result)
             pipeline_status_store.advance(entry)
    → Discord shows "pipeline started" immediately; :tasks / follow-up poll shows progress
```

### 6 Rs phase sequence (per queue entry)

```
Record   :capture / :seed → NoteIntake → inbox/_pending-classification.md   [UNCHANGED — already works]
Reduce   pipeline_orchestrator reads one inbox entry
            → six_rs.reduce.reduce_entry() → ReduceResult{claim_title, schema_type, body}
            → vault.write_note("notes/{slug}.md", body_with_schema_block)
Reflect  → graph_analysis.hub_candidates() [+ SemanticRecall cosine floor]
            → six_rs.reflect.find_hub() only if no candidate clears the floor
            → moc_maintenance.attach_to_hub() writes wikilink both directions
Reweave  → graph_analysis walks notes/ for "recently referenced elsewhere but stale" candidates
            → six_rs.reweave.reweave_note() per candidate (fresh completion, old note + new context only)
Verify   → note_schema.validate(path) — claim-title heuristic, _schema block, ≥1 wikilink
            → six_rs.verify only invoked for the claim-title natural-language check (cheap heuristic
              or LLM assist); everything else is pure Python
Rethink  → reads ops/observations/ + ops/tensions/ (existing paths)
            → six_rs.rethink.triage() per item → PROMOTE / IMPLEMENT / METHODOLOGY / ARCHIVE / KEEP
```

### Taxonomy routing — before and after

```
BEFORE (note_classifier.TOPIC_VAULT_PATH, flat-7):
  learning       → learning/                (direct file, no schema, no wikilink)
  accomplishment → accomplishments/
  journal        → journal/{date}/
  reference      → references/
  observation    → ops/observations
  noise          → "" (never filed)
  unsure         → inbox/_pending-classification.md

AFTER:
  learning, reference   → inbox/  (queued; Reduce phase produces notes/{slug}.md + _schema + wikilink)
  journal               → ops/journal/{date}/           [ops-bound, directory filing KEPT]
  accomplishment        → ops/accomplishments/           [ops-bound, directory filing KEPT]
  observation           → ops/observations/               [unchanged]
  noise                 → "" (unchanged)
  unsure                → inbox/_pending-classification.md (unchanged)
```

## Build Order and Dependency Edges

### Build order: Phase A (taxonomy/namespace foundation) → Phase B (schema + graph, additive) → Phase C (6 Rs orchestrator) → Phase D (migration cutover + hardening)

```
Phase A — Vault namespace + taxonomy foundation
    │  Creates: notes/, templates/ directory conventions (lazy-create, D-14 pattern)
    │  Modifies: note_classifier.TOPIC_VAULT_PATH (notes-bound vs ops-bound split),
    │            vault_sweep_plan.py / vault_sweeper.py (retire notes/-bound topic-dir moves),
    │            app/vault.py PROTECTED_NAMESPACES (+= templates/),
    │            recall.py RecallConfig.exclude_prefixes (+= templates/, confirm notes/ NOT excluded)
    │  Non-breaking because: Recall/embeddings/warm-tier/Pathfinder untouched; only the
    │    classifier's routing table and the sweeper's topic-dir move scope change; full
    │    existing test suite (404+) must stay green; migration script moves old flat-7
    │    directory content into the new shape as a one-time, reviewable operation.
    │
    ├──▶ Phase B — Note-quality schema + graph analysis (read-mostly, additive)
    │        │  Requires from A: notes/ + templates/ namespaces exist; taxonomy routing decided
    │        │  Creates: note_schema.py, graph_analysis.py, moc_maintenance.py
    │        │  Modifies: command_router.py / bot.py — :review, :check, :graph, :stats, :connect
    │        │    swap from call_core(fixed_prompt) to real endpoint calls
    │        │  Non-breaking because: these are net-new read/analysis endpoints; commands that
    │        │    used to return AI prose now return structured, deterministic reports — a
    │        │    visible improvement, not a regression; no change to POST /message or Recall.
    │        │
    │        └──▶ Phase C — 6 Rs pipeline orchestrator (highest complexity, most new code)
    │                 │  Requires from A: taxonomy routing (what lands in inbox/ for Reduce)
    │                 │  Requires from B: note_schema (Verify), graph_analysis + moc_maintenance
    │                 │    (Reflect hub lookup)
    │                 │  Creates: pipeline_orchestrator.py, pipeline_status_store.py,
    │                 │    six_rs/{reduce,reflect,reweave,verify,rethink}.py,
    │                 │    routes/pipeline.py (POST/GET mirroring sweep routes)
    │                 │  Modifies: command_router.py / bot.py — :ralph, :pipeline, :reweave,
    │                 │    :rethink, :check-batch-mode swap to the new background-task endpoints
    │                 │  Non-breaking because: entirely new background-task surface, admin-gated
    │                 │    like the sweep; POST /message and MessageProcessor untouched; can be
    │                 │    feature-flagged / left unwired in Discord until its own regression
    │                 │    pass is green.
    │                 │
    │                 └──▶ Phase D — Migration completion + cutover hardening
    │                          Full vault migration execution (remaining flat-7 content),
    │                          retirement of any now-dead directory-routing code paths,
    │                          USER-GUIDE/README updates, full regression + live UAT pass.
```

**Why B cannot precede A:** `graph_analysis.py` needs `notes/` populated with `_schema`-bearing
files to compute anything meaningful; those files only start existing once A's taxonomy routing
sends notes-bound content to `inbox/` for eventual Reduce output (which itself needs Phase C) — but
`graph_analysis`'s *code* can be written and unit-tested against `FakeVault` fixtures in B without
waiting for C, since it operates on whatever `notes/` content exists (including hand-seeded test
fixtures or migrated content).

**Why C cannot precede A or B:** `six_rs.reduce` needs the taxonomy decision (what counts as
notes-bound) to know what an "inbox entry destined for Reduce" even is; `six_rs.reflect` needs
`graph_analysis`/`moc_maintenance` to find hub candidates; `six_rs.verify` needs `note_schema` to
validate its own output. Building C first would mean re-deriving all of A and B's logic inline and
then extracting it later — the same "seam introduced too early" anti-pattern the v0.5.1 milestone's
own ADR-0003 explicitly avoided.

**Why D is last:** migrating remaining live vault content and deleting old directory-routing code
should only happen once A–C are validated in production against real Discord traffic; doing it
earlier risks a destructive migration against a taxonomy that is still shifting.

## Integration Points

### New vs Modified — Per Phase

#### Phase A — Taxonomy + namespace foundation

| File | Change Type | What Changes |
|------|-------------|---------------|
| `app/services/note_classifier.py` | **Modified** | `TOPIC_VAULT_PATH` routing split: `learning`/`reference` → `inbox/`; `journal`/`accomplishment` → `ops/{journal,accomplishments}/`; `observation`/`noise`/`unsure` unchanged |
| `app/services/vault_sweep_plan.py` | **Modified** | `propose_topic_move` scope narrowed — no longer proposes moves for notes-bound slugs; ops-bound slugs unchanged |
| `app/services/vault_sweeper.py` | **Modified** | Orchestration unchanged; consumes the narrowed sweep plan |
| `app/vault.py` | **Modified** | `PROTECTED_NAMESPACES` gains `templates/` |
| `app/services/recall.py` | **Modified (minor)** | `RecallConfig.exclude_prefixes` gains `templates/`; `notes/` confirmed NOT excluded |
| One-time migration script | **New, transient** | Moves existing `learning/`, `accomplishments/`, `journal/`, `references/` content per the new routing table |
| `tests/test_note_classifier.py`, `tests/test_vault_sweep_plan.py` | **Modified** | Assertions updated for new routing table |
| `app/services/embedding_sidecar_index.py`, `app/services/recall.py` `SemanticRecall` | **Unchanged** | Directory-agnostic already; no code change expected |
| Docker Compose, module gateway, `modules/pathfinder/*` | **Unchanged** | Zero coupling |

#### Phase B — Note-quality schema + graph analysis

| File | Change Type | What Changes |
|------|-------------|---------------|
| `app/services/note_schema.py` | **New** | Parse/validate trailing `_schema:` block: `type` (permanent\|hub\|literature\|fleeting), `hub`, `status`; claim-title heuristic |
| `app/services/graph_analysis.py` | **New** | Walk `notes/`, parse wikilinks + `_schema`, compute orphans/triangles/link density/hub sizes |
| `app/services/moc_maintenance.py` | **New** | Lazy hub create/append; bidirectional wikilink write (topics footer + hub back-link) |
| `app/routes/note.py` (or new `app/routes/graph.py`) | **New endpoints** | `POST /note/review`, `GET /vault/check`, `GET /vault/graph`, `GET /vault/stats` |
| `interfaces/discord/command_router.py`, `bot.py`, `core_gateway.py` | **Modified** | `:review`, `:check`, `:graph`, `:stats`, `:connect` call new endpoints instead of `call_core(fixed_prompt)` |
| `tests/test_note_schema.py`, `tests/test_graph_analysis.py` | **New** | Unit tests against `FakeVault` fixtures |

#### Phase C — 6 Rs pipeline orchestrator

| File | Change Type | What Changes |
|------|-------------|---------------|
| `app/services/six_rs/reduce.py`, `reflect.py`, `reweave.py`, `verify.py`, `rethink.py` | **New** | Per-phase structured completions, mirroring `note_classifier.py`'s pattern |
| `app/services/pipeline_orchestrator.py` | **New** | Background-task orchestration; mirrors `vault_sweeper.run_sweep` |
| `app/services/pipeline_status_store.py` | **New** | Mirrors `sweep_status_store.py` |
| `app/routes/pipeline.py` | **New** | `POST /vault/pipeline/start`, `GET /vault/pipeline/status` — admin-gated, mirrors `/vault/sweep/*` |
| `interfaces/discord/command_router.py`, `bot.py`, `core_gateway.py` | **Modified** | `:ralph`, `:pipeline`, `:reweave`, `:rethink` call the new pipeline endpoints; `_SUBCOMMAND_PROMPTS` entries for these verbs removed |
| `app/state.py` / `app/composition.py` | **Modified (additive)** | Wire `task_runner` (already exists) and new orchestrator into `RouteContext`/`AppGraph`, same pattern as `Recall` in phase 39 |
| `tests/test_pipeline_orchestrator.py`, `tests/test_six_rs_*.py` | **New** | Unit + integration tests against `FakeVault` |

#### Phase D — Migration completion + hardening

| File | Change Type | What Changes |
|------|-------------|---------------|
| Migration completion script | **New, transient** | Executes remaining content migration against the live vault |
| Dead-code removal (old flat-7-only directory routing, if any remains) | **Modified/Removed** | Only after A–C are validated live |
| `USER-GUIDE.md`, `README.md` | **Modified** | Reflect new command behaviors (background-task UX for pipeline commands) |

### External Service Boundaries

| Service | Integration Pattern | Phase impact |
|---------|---------------------|--------------|
| Obsidian Local REST API | `ObsidianVault` — unchanged transport | Phase A adds no new HTTP verbs; Phase C reuses `read_note`/`write_note`/`list_under` already in the Protocol |
| LM Studio (chat completion) | `acompletion_with_profile` — already used by `note_classifier.py` | Phase C's `six_rs/*` modules reuse this exact call pattern for each phase |
| LM Studio (embeddings) | `Embeddings` client + `embedding_sidecar_index.py` | Phase B's hub-matching (Pattern 4) reuses the existing sweeper-maintained index; no new embedding calls at pipeline-run time |
| Discord | `discord.py` bot, existing subcommand router | Phases B/C change response shape (structured report vs free text; "started" ack vs immediate reply) but not the routing surface |
| Pathfinder module (`modules/pathfinder`) | HTTP proxy via `module_gateway.py`, `POST /modules/register` | **Untouched across all phases** — no import coupling, no compose changes |

### Internal Module Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `pipeline_orchestrator` ↔ `six_rs/*` | Direct async function calls, one per phase | Each call constructs its own minimal prompt — no shared "conversation" object crosses phase boundaries |
| `pipeline_orchestrator` ↔ `Vault` | Protocol method calls only (`read_note`/`write_note`/`list_under`) | Same seam as everything else; no new persistence interface |
| `six_rs.reflect` ↔ `graph_analysis` / `SemanticRecall` | Direct calls | Embedding-first hub lookup (Pattern 4); LLM only as fallback |
| `note_schema` ↔ `markdown_frontmatter` | `note_schema` parses the trailing `_schema:` block; `markdown_frontmatter` continues to own the leading YAML frontmatter | Two distinct metadata locations in the same file, two distinct small modules |
| `command_router` ↔ new pipeline/schema/graph routes | HTTP calls via `core_gateway.py`-style helpers | Mirrors the existing `call_core_sweep_start/status` pattern exactly — proven, low-risk template |
| `MessageProcessor` ↔ everything above | **No direct coupling** | Deliberate — see Anti-Pattern 4 |

## Anti-Patterns

### Anti-Pattern 1: Treating today's fixed-prompt `:ralph`/`:pipeline` as "the 6 Rs pipeline, done"

**What people do:** See that `_SUBCOMMAND_PROMPTS["ralph"]` already contains a plausible-sounding
instruction and conclude the feature exists because the command routes and the model replies with
prose describing what it "did."

**Why it's wrong:** No vault mutation is guaranteed. The chat model has no tool-calling loop in
this stack — it cannot actually walk `inbox/`, move a file, or write a `_schema` block from inside
`MessageProcessor.process()`. The Discord reply looks like a completed pipeline run; the vault is
untouched.

**Do this instead:** Build the actual orchestrator (Phase C) with per-phase structured completions
that produce parseable results the backend writes via the `Vault` Protocol.

### Anti-Pattern 2: Reintroducing directory-based topic filing inside `notes/`

**What people do:** Extend the existing flat-7 `TOPIC_VAULT_PATH` pattern with more slugs/folders
inside `notes/` (e.g. `notes/learning/`, `notes/reference/`) because that machinery already exists
and works.

**Why it's wrong:** Violates arscontexta's three-space invariant (flat `notes/`, MOC/wikilink
navigation, no topic subdirectories) and reproduces two of the six documented failure modes
("notes into ops" analog: schema confusion contaminating the graph; discoverability loss since MOC
traversal assumes a flat namespace).

**Do this instead:** Route notes-bound content to `inbox/` for Reduce-phase transformation into a
single-level `notes/{claim-slug}.md` with a `_schema` block and hub wikilink.

### Anti-Pattern 3: Putting the pipeline orchestrator inside `MessageProcessor` or triggering it synchronously from `POST /message`

**What people do:** Add an `if is_pipeline_command(req.content): await run_pipeline(...)` branch
inside `MessageProcessor.process()` since that's where all Discord commands already terminate.

**Why it's wrong:** Repeats the exact layering mistake ADR-0003 explicitly rejected for Recall vs
presentation — domain orchestration (multi-minute, multi-phase, vault-mutating) does not belong in
the single-turn chat request path. It would also break the request/response latency contract every
other `POST /message` caller depends on, and couples pipeline failures to chat-turn error handling.

**Do this instead:** A dedicated background-task route (`POST /vault/pipeline/start`) scheduled via
the existing `task_runner` seam — the same shape already proven for the sweep.

### Anti-Pattern 4: Letting `six_rs/*` phase calls inherit the conversational Hot/Warm tier context

**What people do:** Reuse `Recall.assemble()` inside a `six_rs` phase "for consistency" or "so the
model has full context."

**Why it's wrong:** Defeats the entire "fresh context per phase" principle this milestone is
explicitly restoring — a Reduce call bloated with unrelated session history and warm-tier search
results degrades exactly the attention/quality problem the pattern exists to prevent, and makes the
phase's structured-output contract far less reliable (more context, more chance the model deviates
from the schema).

**Do this instead:** Each phase constructs its own minimal, explicit prompt from only the inputs it
actually needs (the one entry, the short hub-candidate list, etc.).

### Anti-Pattern 5: Relaxing the warm-tier `exclude_prefixes` to add `notes/` "for safety" alongside `templates/`

**What people do:** When adding `templates/` to `RecallConfig.exclude_prefixes` (Phase A), also add
`notes/` out of an abundance of caution about the new namespace.

**Why it's wrong:** `notes/` is precisely the durable knowledge graph the Warm tier exists to
surface. Excluding it silently makes semantic/keyword recall blind to the very content this
milestone is building. This mirrors the historical WARM-tier exclusion bugs already fixed in
v0.50.1 (`session_issues` in `CONTEXT.md`) — a documented regression class for this exact list.

**Do this instead:** Only add genuinely operator-scaffolding or non-knowledge namespaces
(`templates/`, alongside the existing `ops/`, `_trash/`, `self/`, `inbox/`) to the exclusion list.

### Anti-Pattern 6: Standing up a new Docker container or module registration for the pipeline orchestrator

**What people do:** Because the 6 Rs pipeline is a big new capability, propose it as a new module
(new compose profile, `POST /modules/register`) to "keep it isolated," following the Pathfinder
precedent.

**Why it's wrong:** The pipeline orchestrates mutations to the Sentinel's own core vault namespaces
(`notes/`, `inbox/`, `ops/`) using the same `Vault` Protocol the rest of Sentinel Core already uses
in-process — it is core-domain behavior, not a pluggable capability with independent versioning
like Pathfinder. Modularizing it would require either duplicating the `Vault` seam across a process
boundary or granting a "module" direct Obsidian REST access, undermining the module-isolation
principle (Core does not arbitrate between modules' persistence) for no benefit.

**Do this instead:** Ship it as `sentinel-core` in-process services alongside `vault_sweeper.py`,
scheduled the same way — no new container, no new compose entry, no module registry entry.

## Sources

- `sentinel-core/app/vault.py` — Vault Protocol, `PROTECTED_NAMESPACES`, sweep primitives (production source)
- `sentinel-core/app/services/message_processing.py` — current single-turn message flow (production source)
- `sentinel-core/app/services/recall.py` — `RecallConfig.self_paths`/`exclude_prefixes` (confirms D-02 already substantially implemented) (production source)
- `sentinel-core/app/services/note_classifier.py` — flat-7 closed vocabulary + `TOPIC_VAULT_PATH` (production source)
- `sentinel-core/app/services/vault_sweep_plan.py`, `vault_sweeper.py` — topic-dir move logic to be narrowed (production source)
- `sentinel-core/app/services/task_runner.py`, `note_sweep_runner.py`, `sweep_status_store.py` — the background-task template being cloned for the pipeline orchestrator (production source)
- `sentinel-core/app/routes/note.py` — `/vault/sweep/*` admin-gated route shape being mirrored (production source)
- `interfaces/discord/command_router.py`, `interfaces/discord/bot.py` — confirms the 27-command Discord surface is already routed; `_SUBCOMMAND_PROMPTS`/`_PLUGIN_PROMPTS` are the fixed-prompt fallback being replaced for pipeline/schema/graph verbs (production source)
- `docker-compose.yml`, `sentinel-core/compose.yml`, `modules/pathfinder/compose.yml` — confirms module-gateway isolation and that no new compose entry is implied by this milestone (production source)
- `docs/2nd-brain-original-design/10-CONTEXT-master-spec.md` — recovered phase-10 master spec: D-01 (vault structure), D-02 (session-start reading), D-03 (27 commands), D-05 (note quality standard), D-06 (MOC/hub notes), D-09 (6 Rs pipeline definition), D-14 (lazy stub creation), D-16 (PARA/arscontexta synthesis guidance) (curated primary source)
- `docs/adr/0001-sentinel-persona-source.md`, `0002-vault-seam-location.md`, `0003-recall-module.md` (referenced via `.planning/research/` prior findings), `0006-pathfinder-command-contracts.md` — architectural precedent for seam placement and layering discipline (curated primary source)
- `CONTEXT.md` — canonical domain glossary, current namespace set, `session_issues` change log (documents the WARM-tier exclusion-list regression class cited in Anti-Pattern 5) (curated primary source)
- `.planning/research/ARCHITECTURE.md` (v0.5.1 prior research) — Recall/RetrievalStrategy/SemanticRecall architecture this milestone must preserve (curated primary source)
- `https://github.com/agenticnotetaking/arscontexta` (WebFetch, single pass) — three-space design, 6 Rs pipeline definition, 15 kernel primitives, command architecture, "fresh context per phase" principle; `reference/three-spaces.md` and `reference/kernel.yaml` fetched directly for the flat-`notes/` invariant and confirmation that no dedicated subagent/orchestration primitive is specified upstream (MEDIUM confidence — single-source WebFetch summarization, not independently cross-verified against a second citation)

---
*Architecture research for: Sentinel of Mnemosyne v0.6.0 — Restore the Second-Brain Core (arscontexta + BASB)*
*Researched: 2026-07-05*
