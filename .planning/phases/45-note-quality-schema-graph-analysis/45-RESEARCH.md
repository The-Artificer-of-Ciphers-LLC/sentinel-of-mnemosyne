# Phase 45: Note-Quality Schema + Graph Analysis - Research

**Researched:** 2026-07-06
**Domain:** Trailing-metadata parsing (`_schema` fenced block), wikilink graph analysis, sidecar-index freshness, Discord command surface rewiring (Sentinel of Mnemosyne / sentinel-core, FastAPI + Obsidian REST vault)
**Confidence:** HIGH — every finding below is grounded in production source read directly this session (`sentinel-core/app/**`, `interfaces/discord/**`), the phase-10 master spec, and the two mandatory research documents (`ARCHITECTURE.md`, `PITFALLS.md`). No new external library was introduced, so no WebSearch/Context7 lookups were needed; this phase is 100% internal-codebase-grounded.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**`_schema` footer format**
- **D-01:** The `_schema` block is a **trailing fenced ` ```_schema ` block at the
  end of the note**, carrying at minimum `type` + hub membership. It is a distinct
  block, kept **separate from the leading YAML provenance frontmatter** that
  `markdown_frontmatter.py` already owns (`original_path`, `topic_moved_at`,
  `sweep_at`, …). A new `note_schema.py` module parses/validates exactly this
  trailing block (regex-from-end). Rejected: merging into frontmatter (two owners /
  one block = the anti-pattern ARCHITECTURE.md calls out), HTML comment
  (tooling-strip risk), Dataview inline (adds a plugin dependency the vault lacks).
  This confirms master-spec **D-05**.

**Enforcement point**
- **D-02:** Enforcement is **inspect-only**. Phase 45 adds `note_schema.py` +
  `graph_analysis.py` to back `:check` / `:graph` / `:stats`; it does **not** touch
  any write path and does **not** auto-fill the standard at write time. Rationale:
  matches the read-mostly constraint AND PITFALLS.md **Pitfall 6** ("enforce at
  Verify, never at file-time"); `note_classifier` routes content to `inbox/`, so
  Phase 45 has no `notes/` write path to hook onto anyway. Works identically for
  pipeline-produced and hand-authored notes. NOTE-01's "Notes *carry* the standard"
  is closed across two phases — Phase 46's Reduce is where notes are born compliant.

**Hub / MOC assignment**
- **D-03:** Hub assignment is **embedding-nearest + cosine-floor + minimum-cluster-
  size** (Pattern 4, embedding-first). A note joins the nearest existing hub whose
  cosine clears the floor; **reuse the existing `semantic_cosine_floor = 0.50`
  precedent (recall D-11)** rather than inventing a new threshold. If no hub clears
  the floor, the note is held **hub-pending**.
- **D-03a:** **Minimum cluster size = 2.** A hub materializes on the **2nd**
  topically-similar note that clears the floor; at that point the hub note is created
  and the cluster members are retroactively wikilinked to it.
- **D-03b:** **Hub-pending singletons are reported as orphans** by `:graph` (they
  genuinely have no hub/links yet) until a sibling arrives — no separate
  "pending" state.
- **D-03c:** A hub note's title is a **concept slug** (noun phrase), NOT a claim
  title. When an LLM-fallback names a new hub, constrain it (structured completion)
  to a short concept slug.
- **D-03d:** **Idempotent creation under the REST-only, transaction-less vault:**
  hub identity IS the idempotency key. Derive a deterministic path
  `notes/{concept-slug}.md`, always `read_note` that exact path first; if present,
  append the new wikilink under a stable section marker and re-`write_note` the
  merged body; if absent, `write_note` fresh with the marker already in place.
  Rejected: pure-embedding-threshold (one-note-hub sprawl), PARA/tag-keyed hubs
  (re-opens Phase A's locked flat-`notes/` Pattern 3).

**links-index.json sidecar (location + freshness)**
- **D-04:** **Location = persisted in-vault via REST** at `ops/graph/links-index.json`
  (mirrors the proven `embedding_sidecar_index.py` → `ops/sweeps/embedding-index.json`
  pattern; survives restarts with no rebuild tax; self-heals on parse failure). Its
  own path MUST be excluded from the walk it indexes (same trap the embedding sidecar
  already solved). Rejected: container-local cache (diverges across the two-checkout
  deploy topology, violates vault-sole-persistence) and in-memory-only
  (full-walk-per-restart cost).
- **D-04a:** **Freshness = hybrid** — incremental patch on writes the *service*
  performs, PLUS a **lazy full-rebuild-if-stale** on `:graph` / `:stats` / `:check`
  invocation to catch out-of-band Obsidian hand-edits the service never sees.
  Piggyback the existing `vault_sweeper` module/lock infrastructure rather than
  inventing a parallel mechanism. (Staleness signal is approximate — the REST API's
  `list_under` exposes no per-note mtime — so the lazy fallback is what guarantees
  eventual correctness.)

**`:check` claim-title validation**
- **D-05:** `:check`'s claim-title test (SC-4) is **structural only** — confirm an
  H1/title exists and is not a bare slug/filename. **No LLM calls** — `:check` stays
  a cheap, deterministic, read-only command. LLM-judged title quality is deferred.

### Claude's Discretion
- Exact command surface shape (`:graph` / `:stats` / `:check` as three distinct
  commands vs facets) and their terminal output formatting — planner/researcher to
  decide, grounded in the master-spec `:graph`/`:stats` spec.
- Module naming for the new graph/hub/links files (`note_schema.py`,
  `graph_analysis.py`, MOC-maintenance, links-sidecar) — follow ARCHITECTURE.md's
  Phase B component table.

### Deferred Ideas (OUT OF SCOPE)
- **Born-compliant note writing** — auto-filling `_schema` + claim title + wikilinks on
  the write path → **Phase 46 (6 Rs / Reduce)**. Explicitly kept out of Phase 45 to
  preserve the read-mostly constraint and avoid duplicating Reduce.
- **LLM-judged claim-title quality** (a `:check --deep` pass) — possible future
  enhancement; Phase 45 `:check` is structural-only (D-05).
- **Separate "hub-pending" (non-orphan) state** — considered for D-03b; deferred in
  favor of honest orphan reporting until a sibling note materializes the hub.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NOTE-01 | Notes carry an `_schema` footer block (type + hub membership), a claim-style title, and wikilinks | `note_schema.py` design (trailing-block regex-from-end parser, structural claim-title check, wikilink regex) — see Architecture Patterns §1, Code Examples §1-3 |
| NOTE-02 | Maps of Content (MOC/hub notes) are created lazily and updated as notes join a hub | `moc_maintenance.py` design reusing `SemanticRecall`'s `eligible_entries`/`cosine_similarity` machinery for embedding-first hub lookup (D-03), idempotent read-then-append preserving the trailing `_schema` block (D-03d) — see Architecture Patterns §3, Common Pitfalls §3 |
| NOTE-03 | The user can run graph analysis (`:graph`/`:stats`/`:check`) to see orphans, backlinks, link density, and `_schema` compliance, backed by a `links-index.json` sidecar | `graph_analysis.py` + `links_sidecar_index.py` mirroring `embedding_sidecar_index.py`'s self-healing incremental-index pattern (D-04/D-04a); command_router.py/bot.py rewiring from `call_core(fixed_prompt)` to real endpoints (mirrors `call_core_sweep_start/status`) — see Architecture Patterns §2, §4, Validation Architecture |
</phase_requirements>

## Summary

Phase 45 is purely additive: three new `sentinel-core/app/services/` modules
(`note_schema.py`, `graph_analysis.py`, `moc_maintenance.py`/hub logic — naming is
Claude's Discretion) plus a links-index sidecar module, wired behind three new
FastAPI routes that mirror the already-proven `/vault/sweep/start` + `/vault/sweep/status`
admin-route shape in `sentinel-core/app/routes/note.py`. The Discord side is a
surgical edit: `interfaces/discord/command_router.py`'s `graph` branch (currently
builds a fixed prompt string and calls `call_core`) and `bot.py`'s `_SUBCOMMAND_PROMPTS["stats"]`/`["check"]`
entries (currently dict-lookup fallback to `call_core`) both need to be replaced with
real HTTP calls into the new endpoints — exactly the `call_core_sweep_start`/`call_core_sweep_status`
pattern already proven in `interfaces/discord/core_gateway.py`.

No new note-writing code path exists or is created in this phase — `note_classifier.py`'s
`TOPIC_VAULT_PATH` (confirmed read this session) routes `learning`/`reference` to
`inbox/`, not `notes/`, so there is genuinely nothing for this phase to hook into on
the write side. This matches D-02's inspect-only decision exactly and is why the
whole phase can ship additive endpoints/modules with zero risk to the 473-passed/12-skipped
baseline (re-confirmed green this session).

The single highest-complexity piece is NOT the schema/graph parsing (straightforward
regex + dict-walk work) — it's **hub-note idempotent mutation** (D-03d): a hub note is
itself a note in `notes/` that will eventually carry its own trailing `_schema` block,
so appending a new member wikilink to an *existing* hub note must read-parse-modify-rewrite
the body while preserving that trailing block's position as the last thing in the file —
a naive `patch_append` (blind string concatenation) would push the appended wikilink
*after* the `_schema` block, breaking the "trailing" invariant `note_schema.py`'s
regex-from-end parser depends on. This is flagged as Common Pitfall 3 below.

**Primary recommendation:** Build `note_schema.py` (trailing-block parse/validate,
structural claim-title check, wikilink presence check) and `graph_analysis.py`
(notes/-scoped walk, wikilink extraction, orphan/backlink/density computation) as
pure-Python modules unit-tested against `tests/fakes/vault.py`'s `FakeVault` with zero
LLM dependency (satisfies D-05's "no LLM calls" for `:check`); build the
links-index sidecar as a structural clone of `embedding_sidecar_index.py`
(`build_embedding_index`/`eligible_entries` → `build_links_index`/analogous reader),
including its self-healing-on-parse-failure and incremental-carry-forward-by-content-hash
properties; reuse `SemanticRecall`'s `eligible_entries()` + `cosine_similarity()` +
`RecallConfig.semantic_cosine_floor` verbatim for hub matching (D-03) rather than
writing a second cosine-search implementation; and wire `:graph`/`:stats`/`:check`
in `command_router.py` to three new routes in a new `app/routes/graph.py` (or extend
`note.py`) that mirror `/vault/sweep/start`+`/vault/sweep/status`'s shape but need
**no admin gate and no model-readiness probe** — the sidecar rebuild is pure Python
(no LLM/embedding call in the read path itself; hub-lookup embedding reuse is a
sidecar *read*, not a fresh embed) and non-destructive to user content, unlike the
sweep's relocate/trash operations.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `_schema` block parse/validate | API / Backend (`sentinel-core/app/services/note_schema.py`) | — | Pure content-parsing logic; no I/O of its own, called by routes and by `moc_maintenance` |
| Wikilink extraction, orphan/backlink/density computation | API / Backend (`sentinel-core/app/services/graph_analysis.py`) | Database/Storage (reads note bodies via `Vault` seam) | Graph computation over vault content; the vault is the only "storage" tier here (Obsidian REST) |
| `links-index.json` sidecar persistence | Database / Storage (`ops/graph/links-index.json` via `Vault.write_note`) | API / Backend (build/read logic in a new `links_sidecar_index.py`) | Mirrors `embedding_sidecar_index.py`'s split: format/build logic in `app/services/`, physical bytes live in-vault |
| Hub embedding-nearest lookup | API / Backend (`moc_maintenance.py` calling `SemanticRecall`'s `eligible_entries`/`cosine_similarity`) | — | Retrieval-first, no new embedding call; reuses the already-computed sweeper-maintained embedding sidecar |
| Hub concept-slug LLM fallback naming | API / Backend (structured completion via `acompletion_with_profile`, mirrors `note_classifier.py`) | — | Only invoked when no existing hub clears the cosine floor; local-model call, JSON-schema constrained |
| `:graph`/`:stats`/`:check` command dispatch | Frontend/Interface (`interfaces/discord/command_router.py`, `bot.py`) | API / Backend (new FastAPI routes) | Discord is a thin dispatcher; all computation happens core-side, matching every other subcommand in this codebase |
| Idempotent hub-note read-then-write | Database / Storage (via `Vault.read_note`/`write_note`) | API / Backend (`moc_maintenance.py` decision logic) | The vault is transaction-less REST; idempotency is achieved by deterministic path + full-body read-modify-write, not a DB transaction |

## Standard Stack

### Core

No new external packages are introduced by this phase. Every capability is built on
dependencies already present and pinned in `sentinel-core`'s environment:

| Library | Version (as installed) | Purpose | Why Standard (for this codebase) |
|---------|-------------------------|---------|-----------------------------------|
| `re` (stdlib) | n/a | Trailing `_schema` block regex-from-end, wikilink `[[...]]` extraction, H1 claim-title check | Every existing frontmatter/index parser in this codebase (`markdown_frontmatter.py`, `embedding_sidecar_index.py`) is regex + stdlib, zero markdown-AST library — [VERIFIED: production source, `sentinel-core/app/markdown_frontmatter.py:26`] |
| `yaml` (PyYAML, already a dependency) | already pinned (see `sentinel-core/requirements`/`pyproject.toml`) | Parsing the `_schema` block's inner YAML-shaped content (`type:`, `hub:`, `status:`) | `markdown_frontmatter.py` already uses `yaml.safe_load`/`yaml.safe_dump` for the leading frontmatter block — [VERIFIED: production source, `sentinel-core/app/markdown_frontmatter.py:22,38,52`] |
| `numpy` (already a dependency) | already pinned | Cosine similarity for hub matching | `sentinel_shared/similarity.py`'s `cosine_similarity` and `embedding_sidecar_index.py`'s `eligible_entries` already do this — reuse verbatim, do not add a second numpy call site — [VERIFIED: production source, `shared/sentinel_shared/similarity.py:9-16`] |
| `pydantic` (already a dependency) | already pinned | Request/response models for the new `/vault/graph`, `/vault/stats`, `/vault/check` routes | Matches `app/routes/note.py`'s `ClassifyRequest`/`ClassifyResponse`/`SweepStartRequest` pattern — [VERIFIED: production source, `sentinel-core/app/routes/note.py:34-54,119-123`] |
| `sentinel_shared.llm_call.acompletion_with_profile` (already a dependency, internal shared package) | already pinned | Structured-completion fallback for hub concept-slug naming (D-03c) | Identical call shape already used by `note_classifier.classify_note` — [VERIFIED: production source, `sentinel-core/app/services/note_classifier.py:290-320`] |

### Supporting

No additional supporting libraries are required. FastAPI/httpx/discord.py are already
present for the route + Discord-side wiring and need no version bump for this phase.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Regex-based trailing-block parser | A markdown AST library (e.g. `markdown-it-py`, `mistune`) | Would correctly handle nested/edge-case markdown, but this codebase has zero markdown-AST dependency anywhere and every existing metadata parser (frontmatter, embedding index) is regex-based — introducing an AST library for one new module breaks the established pattern for no proven benefit at this vault's scale |
| Reusing `SemanticRecall`'s cosine machinery for hub lookup | A dedicated vector index library (faiss, hnswlib, sqlite-vec) | REQUIREMENTS.md's "Out of Scope" section already rejects persistent ANN indexes at this vault's personal scale ("an in-memory numpy cosine scan is sufficient") — the same reasoning applies to hub matching, which operates over an even smaller subset (hub notes only) |

**Installation:**
```bash
# No new packages — nothing to install for this phase.
```

**Version verification:** Not applicable — no new packages introduced. Existing
pins (`numpy`, `PyYAML`, `pydantic`, `fastapi`, `httpx`) are unchanged from the
Phase 44 baseline; the full test suite (`473 passed, 12 skipped`) was re-run this
session against the current lockfile with no changes required.

## Package Legitimacy Audit

**No new external packages are installed by this phase.** All functionality is
implemented with stdlib (`re`, `json`, `hashlib`) plus already-installed and
already-audited dependencies (`numpy`, `PyYAML`, `pydantic`, `fastapi`, `httpx`,
the internal `sentinel_shared` package). The Package Legitimacy Gate is therefore
not applicable — there is nothing to run `npm view`/`pip index versions`/the
`package-legitimacy check` seam against.

**Packages removed due to [SLOP] verdict:** none — no packages were proposed.
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
Discord :graph / :stats / :check
        │
        ▼
interfaces/discord/command_router.py (handle_subcommand)
  - "graph"/"stats"/"check" branches — CURRENTLY call_core(fixed_prompt)
  - REWIRE to call_core_graph()/call_core_stats()/call_core_check()
        │  (new gateway helpers in core_gateway.py, mirror call_core_sweep_start/status)
        ▼
POST/GET  /vault/graph | /vault/stats | /vault/check   (new: app/routes/graph.py)
  - NO admin gate (read-only, no destructive vault mutation of user content)
  - NO model-readiness probe (pure Python; no LLM in the read path itself)
        │
        ▼
app/services/links_sidecar_index.py
  ── rebuild_links_index_if_stale(vault) ──┐
        │  (staleness check: compare notes/ path-set + per-note content_hash
        │   against stored ops/graph/links-index.json entries)             │
        ▼                                                                  │
  STALE → walk notes/ (list_under, notes/-scoped, EXCLUDING                │
           ops/graph/links-index.json's own path per D-04) →               │
           read_note() each →                                              │
           app/services/graph_analysis.py: extract_wikilinks() +           │
           app/services/note_schema.py: parse_schema_block() →             │
           build_links_index() → write_note(LINKS_INDEX_PATH, ...)  ◄──────┘
        │
        ▼
graph_analysis.py: compute orphans / backlinks / link density / hub sizes
note_schema.py: compute _schema compliance (FAIL/WARN per note)
        │
        ▼
Structured report → rendered for Discord (mirrors format_classify_response style)


Separately — Hub assignment (NOTE-02, triggered from wherever Reflect-equivalent
logic lives; Phase 45 ships the machinery, Phase 46 wires the pipeline caller):

  new note's embedding (already in ops/sweeps/embedding-index.json,
  written by the sweeper — NO new embed call)
        │
        ▼
  moc_maintenance.find_hub_candidate()
    reuses embedding_sidecar_index.eligible_entries() +
    sentinel_shared.similarity.cosine_similarity() +
    RecallConfig.semantic_cosine_floor (0.50) — filtered to
    entries whose note carries _schema.type == "hub"
        │
   clears floor?  ── no ──► note stays hub-pending (reported as orphan, D-03b)
        │ yes
        ▼
  moc_maintenance.attach_to_hub(hub_path, member_path)
    read_note(hub_path) [deterministic notes/{concept-slug}.md] →
    split off trailing _schema block →
    insert/update member wikilink under stable "## Member Notes" marker →
    re-append (possibly updated) _schema block →
    write_note(hub_path, merged_body)   — idempotent full-body PUT, D-03d
```

### Recommended Project Structure
```
sentinel-core/app/
├── services/
│   ├── note_schema.py           # NEW — trailing _schema block parse/validate,
│   │                             #       structural claim-title + wikilink checks
│   ├── graph_analysis.py        # NEW — notes/ walk, wikilink graph, orphans/
│   │                             #       backlinks/density/hub-size computation
│   ├── links_sidecar_index.py   # NEW — build/decode/staleness-check for
│   │                             #       ops/graph/links-index.json (mirrors
│   │                             #       embedding_sidecar_index.py's shape)
│   └── moc_maintenance.py       # NEW — hub lookup (embedding-first + LLM
│                                 #       fallback) + idempotent hub read/write
└── routes/
    └── graph.py                  # NEW — GET /vault/graph, GET /vault/stats,
                                   #       GET /vault/check (mirrors note.py's
                                   #       /vault/sweep/* shape, no admin gate)

sentinel-core/tests/
├── test_note_schema.py           # NEW — unit tests against FakeVault fixtures
├── test_graph_analysis.py        # NEW
├── test_links_sidecar_index.py   # NEW
├── test_moc_maintenance.py       # NEW
└── test_graph_routes.py          # NEW — route-level tests (mirrors test_note_routes.py)

interfaces/discord/
├── command_router.py             # MODIFIED — "graph"/"stats"/"check" branches
│                                  #   swap call_core(fixed_prompt) for real
│                                  #   gateway calls
├── core_gateway.py                # MODIFIED — add call_core_graph/stats/check,
│                                  #   mirroring call_core_sweep_start/status exactly
└── bot.py                        # MODIFIED — remove "stats"/"check" entries from
                                   #   _SUBCOMMAND_PROMPTS (they no longer fall
                                   #   through to the fixed-prompt dict)
```

### Structure Rationale

- **`note_schema.py` stays fully disjoint from `markdown_frontmatter.py`:**
  the two modules own two structurally different metadata locations in the same
  file (leading YAML frontmatter vs. trailing fenced `_schema` block) with different
  write orders — confirmed by ARCHITECTURE.md's "Structure Rationale" and this
  session's direct read of `markdown_frontmatter.py`'s leading-anchor regex
  (`^---\s*\n(.*?)\n---\s*\n?`, `re.DOTALL`, anchored at string start). `note_schema.py`
  must anchor at the **end** of the string instead — see Code Examples §1.
- **`links_sidecar_index.py` as its own module, not folded into `graph_analysis.py`:**
  mirrors the existing split between `embedding_sidecar_index.py` (format/build/decode
  logic) and `vault_sweeper.py` (the walk/orchestration that calls it). `graph_analysis.py`
  is the pure "what does this set of notes' wikilinks imply" computation;
  `links_sidecar_index.py` is the "how do we persist and cheaply reuse that computation"
  concern — same separation of concerns the embedding sidecar already proved.
- **`moc_maintenance.py` as its own module, not inside `graph_analysis.py`:**
  hub lookup + idempotent write is a *mutation* concern (even though Phase 45 doesn't
  wire a caller into the pipeline yet — Phase 46 does); keeping it separate from the
  pure-read `graph_analysis.py` keeps the read/write boundary legible, matching
  ARCHITECTURE.md's own component table (`graph_analysis.py` vs `moc_maintenance.py`
  as two distinct **New** rows).
- **New `app/routes/graph.py` rather than extending `app/routes/note.py`:**
  `note.py`'s docstring already enumerates a specific, closed set of endpoints
  (`/note/classify`, `/inbox`, `/vault/sweep/*`); adding three more unrelated routes
  there would make the "Endpoints:" docstring misleading. A sibling file mirrors the
  existing one-route-file-per-concern granularity in `app/routes/` (`embeddings.py`,
  `modules.py`, `provider.py`, `status.py` are each single-concern already —
  [VERIFIED: production source, `sentinel-core/app/routes/` directory listing]).

## Architectural Patterns

### Pattern 1: Trailing-block parsing is regex-from-end, structurally distinct from leading frontmatter

**What:** `markdown_frontmatter.py`'s existing parser anchors at the **start** of the
body (`^---\s*\n(.*?)\n---\s*\n?`). `note_schema.py` must anchor at the **end**:
search for the LAST occurrence of a ` ```_schema ... ``` ` fenced block, not the
first, so that prose content anywhere earlier in the note that happens to contain
the literal text `` ```_schema `` cannot be mistaken for the real block.

**When to use:** Every call into `note_schema.parse_schema_block()`.

**Trade-offs:** A pure "last match" regex is simpler than a "must be the terminal
content of the file" anchor, but slightly more permissive (a stray fenced block after
the real `_schema` block, though astronomically unlikely in practice, would win).
Recommend requiring the match to end at (or near) the end of the stripped body for
correctness, not just take `list(...).pop()`.

**Example:**
```python
# app/services/note_schema.py — mirrors markdown_frontmatter.py's regex style
# but anchored at the END of the body, not the start.
import re
import yaml

_TRAILING_SCHEMA_RE = re.compile(
    r"```_schema\s*\n(.*?)\n```\s*\Z", re.DOTALL
)


def parse_schema_block(body: str) -> dict | None:
    """Parse the trailing ```_schema fenced block. None if absent/malformed.

    Anchored with \\Z (end of string) after an rstrip, so a stray earlier
    fenced block with the same info-string can never be mistaken for the
    real trailing block — the block MUST be the last thing in the file.
    """
    stripped = (body or "").rstrip()
    m = _TRAILING_SCHEMA_RE.search(stripped)
    if not m:
        return None
    try:
        parsed = yaml.safe_load(m.group(1))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None
```

### Pattern 2: `links-index.json` sidecar mirrors `embedding_sidecar_index.py` exactly — self-healing, content-hash-incremental, own-path-excluded

**What:** `links_sidecar_index.py` should structurally clone
`embedding_sidecar_index.py`'s three properties, confirmed this session in
`sentinel-core/app/services/embedding_sidecar_index.py`:
1. **Self-healing on parse failure** — `decode_index_body` returns `{}` on any
   JSON/regex failure rather than raising (line 52-72); the next rebuild re-derives
   a fresh index from scratch.
2. **Content-hash-based incremental carry-forward** — `build_embedding_index`
   (line 126-206) compares `content_hash(rest)` per survivor against the existing
   entry; unchanged notes are carried forward without recomputation.
3. **Own-path exclusion from the walk it indexes** — D-04 explicitly calls this
   out as "the same trap the embedding sidecar already solved." In the embedding
   sidecar's case this is solved implicitly: `EMBEDDING_INDEX_PATH` lives under
   `ops/sweeps/`, which `SWEEP_SKIP_PREFIXES` already excludes from `walk_vault`
   (confirmed: `ops/sweeps/` is in the skip tuple, `vault_sweeper.py:71-80`), AND
   `walk_vault` only yields `.md` paths (line 218: `elif entry.endswith(".md")`),
   so a `.json` sidecar is never picked up regardless. **`links-index.json` should
   follow the identical strategy**: scope its own walk to the `notes/` prefix only
   (Pattern 3's flat-notes invariant means nothing indexable ever lives under
   `ops/graph/`), which structurally cannot collide with its own path — but still
   add an explicit defensive `path != LINKS_INDEX_PATH` guard in the walk, matching
   the literal D-04 requirement and costing nothing.

**When to use:** `links_sidecar_index.py`'s build/decode functions.

**Trade-offs:** Content-hash-based incrementality catches "did this note's body
change" but NOT "did a note get added/removed" without also comparing the full
path-set against `list_under("notes")` — both checks are needed for the D-04a
staleness signal (see Common Pitfall 5 / Open Questions for the exact staleness
heuristic recommendation).

**Example:**
```python
# app/services/links_sidecar_index.py — structural clone of
# embedding_sidecar_index.py's encode/decode/build shape.
from app.services.embedding_sidecar_index import content_hash  # reuse verbatim

LINKS_INDEX_PATH = "ops/graph/links-index.json"


def encode_index_body(index: dict) -> str:
    import json
    return json.dumps(index, ensure_ascii=False)


def decode_index_body(raw: str) -> dict:
    import json
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}  # self-heal: corrupt index → empty → next rebuild repopulates
```

### Pattern 3: Hub matching reuses `SemanticRecall`'s cosine machinery verbatim — no second embedding call

**What:** `moc_maintenance.find_hub_candidate()` should call
`embedding_sidecar_index.eligible_entries()` (already reads/decodes/filters the
sweeper-maintained `ops/sweeps/embedding-index.json`, already has the dimension-mismatch
guard) filtered down to hub-note paths (via `note_schema.parse_schema_block(...).get("type") == "hub"`),
then `sentinel_shared.similarity.cosine_similarity(query_vec, entry.vector)` per
candidate, gated by `RecallConfig.semantic_cosine_floor` (confirmed `0.50` at
`sentinel-core/app/services/recall.py:285-287`) — this is the **exact** loop
`SemanticRecall.search()` already runs (confirmed `sentinel-core/app/services/recall.py:564-578`).

**When to use:** `moc_maintenance.py`'s hub-lookup path (consumed by Phase 46's
Reflect stage; Phase 45 only needs to *build* this function and unit-test it, since
no pipeline caller exists yet per D-02).

**Trade-offs:** Depends on the sweeper's embedding index already containing an
entry for the candidate note (it will, since the sweeper embeds everything under
`notes/` once Phase 46 starts writing there) — a note with no sidecar entry yet
(embedded on the next sweep cycle) degrades to "no hub match, hub-pending" rather
than raising, consistent with the sidecar's existing fail-soft contract.

**Example:**
```python
# app/services/moc_maintenance.py
from app.services.embedding_sidecar_index import eligible_entries
from sentinel_shared.similarity import cosine_similarity


async def find_hub_candidate(
    *, note_vector, hub_paths: set[str], index: dict, active_model: str, cosine_floor: float
) -> str | None:
    entries, _matched = eligible_entries(
        index,
        active_model=active_model,
        exclude_prefixes=(),          # hub candidates are already notes/-scoped by caller
        query_dim=len(note_vector),
    )
    hub_entries = [e for e in entries if e.path in hub_paths]
    best_path, best_sim = None, cosine_floor
    for entry in hub_entries:
        sim = float(cosine_similarity(note_vector, entry.vector))
        if sim >= best_sim:
            best_path, best_sim = entry.path, sim
    return best_path  # None => hub-pending (D-03b: reported as orphan)
```

### Pattern 4: Command-router rewiring mirrors the existing `call_core_sweep_start`/`status` shape exactly

**What:** `command_router.py`'s `graph` branch (line 114-117) currently builds a
free-text prompt and calls `call_core(user_id, prompt)`; `bot.py`'s
`_SUBCOMMAND_PROMPTS["stats"]`/`["check"]` entries (lines 185, 189) are dict-lookup
fallbacks that also resolve to `call_core(fixed_prompt)`. Both must be replaced with
real gateway calls, following the **exact** pattern `call_core_sweep_start`/
`call_core_sweep_status` already establish in `interfaces/discord/core_gateway.py`
(lines 78-115): an `async def call_core_graph(...)` that does its own
`httpx.AsyncClient()` GET/POST against the new route, logs+returns a friendly
string on `Exception`, and formats the structured JSON response into a Discord-ready
string (mirroring `format_classify_response`).

**When to use:** `command_router.handle_subcommand`'s `graph`/`stats`/`check`
branches, and the corresponding new functions added to `core_gateway.py` +
threaded through `handle_subcommand`'s keyword-argument surface (which already
threads `call_core_sweep_start`/`call_core_sweep_status` this same way — confirmed
`command_router.py:39-59`).

**Trade-offs:** This is a visible behavior change users will notice (structured
report instead of AI prose) — but ARCHITECTURE.md's Anti-Pattern 1 explicitly frames
this as the intended fix, not a regression: "commands that used to return AI prose
now return structured, deterministic reports — a visible improvement."

**Example:**
```python
# interfaces/discord/core_gateway.py — mirrors call_core_sweep_status exactly
async def call_core_graph(*, user_id: str, core_url: str, api_key: str) -> str:
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                f"{core_url.rstrip('/')}/vault/graph",
                headers={"X-Sentinel-Key": api_key},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("vault graph call failed: %s", exc)
        return f"Graph analysis failed: {exc}"
    return (
        f"Notes: {data.get('note_count', 0)}, "
        f"orphans: {len(data.get('orphans', []))}, "
        f"hubs: {data.get('hub_count', 0)}, "
        f"link density: {data.get('link_density', 0):.2f}"
    )
```

### Anti-Patterns to Avoid

- **Blind `patch_append` onto a hub note that already carries a trailing `_schema`
  block:** would push the new wikilink line *after* the `_schema` block, breaking
  the "trailing block is the last thing in the file" invariant `note_schema.py`'s
  regex-from-end parser depends on. Always read-full-body → split off the trailing
  block → mutate the body → re-append the (possibly updated) block → single
  `write_note`. See Common Pitfall 3.
- **Adding a fresh LLM/embedding call for hub matching "to be safe":** defeats
  Pattern 4/ARCHITECTURE.md's explicit "retrieval problem first, generation problem
  second" guidance and duplicates work the sweeper's embedding index already did.
- **Admin-gating `:graph`/`:stats`/`:check` "for consistency with `:vault-sweep`":**
  the sweep is destructive (relocate/trash real user content); the links-index
  rebuild only writes a derived cache file and never touches note content — gating
  it behind `SENTINEL_ADMIN_USER_IDS` would silently break these commands for
  non-admin users with no functional justification. Keep them open like every
  other non-destructive `:` command.
- **Treating vault note bodies read during hub-naming LLM fallback as instructions:**
  per the project's existing untrusted-input-boundary convention and PITFALLS.md's
  Security Mistakes table (prompt-injection-via-vault-content), any note text fed
  into the `acompletion_with_profile` call for hub naming (D-03c) must be treated as
  untrusted data in the prompt, never as directives — same posture `note_classifier.py`
  already takes with `candidate_text`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cosine similarity for hub matching | A second cosine-similarity helper local to `moc_maintenance.py` | `sentinel_shared.similarity.cosine_similarity` (already the cross-package single source of truth — its own docstring says it "closes the cross-package SPOT violation") | Already handles zero-norm vectors safely, already vec×vec and matrix×vec overloaded; a second copy would reintroduce the exact SPOT problem this helper was created to close |
| Reading the sweeper-maintained embedding index | A new `read_note(EMBEDDING_INDEX_PATH)` + custom JSON decode in `moc_maintenance.py` | `embedding_sidecar_index.eligible_entries()` (already has the dimension-mismatch guard, model-string match, b64-length cap) | Re-implementing the read side risks silently dropping the D-08/EMB-04 dimension guard that prevents cosine-across-mismatched-dimension corruption |
| Frontmatter YAML parse/emit | A custom regex+yaml pair inside `note_schema.py` for the trailing block's *inner* YAML | `yaml.safe_load`/`yaml.safe_dump` exactly as `markdown_frontmatter.py` already does (only the anchoring regex differs — leading vs. trailing) | Consistency of YAML parse semantics (safe_load rejects arbitrary object construction) across both metadata locations in the same file |
| Vault directory walk | A hand-rolled recursive `list_under` loop in `graph_analysis.py` | `vault_sweeper.walk_vault()`'s BFS-over-`list_under` shape, scoped to `root="notes"` | Already handles the `entry.endswith("/")` vs `.md` distinction and skip-prefix filtering; reinventing it risks missing an edge case (e.g. trailing-slash normalization) already handled there |

**Key insight:** Every "don't hand-roll" item above already has exactly one
correct existing implementation in this codebase from the embedding-index/recall
work (phases 39-43). This phase's entire risk profile is "did we accidentally build
a second, subtly different copy of an already-solved problem" — not "is there a
third-party library we should be using instead."

## Common Pitfalls

### Pitfall 1: Hub-note write corrupts the trailing `_schema` invariant

**What goes wrong:** `moc_maintenance.attach_to_hub()` appends a new member's
wikilink to an existing hub note using `vault.patch_append()` (a simple string
concatenation primitive — confirmed `Vault` protocol only exposes `patch_append(path, body)`
which appends `body` to whatever is currently stored, `sentinel-core/app/vault.py:151`
and `tests/fakes/vault.py:168-169: self.notes[path] = self.notes.get(path, "") + body`).
If the hub note already carries a trailing `` ```_schema `` block (which it will,
once it's `_schema.status: ready`), the appended wikilink lands **after** that
block, and `note_schema.parse_schema_block()`'s regex-from-end search (Pattern 1)
either fails to match (block no longer terminal) or, worse, matches a stale earlier
block if one somehow exists.

**Why it happens:** `patch_append` is the obvious, already-available primitive
(used correctly elsewhere for logs and session summaries, which have no trailing
structured block to preserve) — but hub notes are the one document type in this
vault where trailing-position matters, and nothing in the `Vault` Protocol signals
that distinction.

**How to avoid:** `moc_maintenance.attach_to_hub()` must NEVER call `patch_append`
on a hub note. Always: `body = await vault.read_note(hub_path)` → split off the
trailing `_schema` block (reuse the same regex, capturing everything before the
match too) → insert/update the member wikilink under the stable section marker in
the *pre-schema* body → re-append the (possibly updated) `_schema` block → single
`await vault.write_note(hub_path, merged_body)`.

**Warning signs:** A test asserts `hub_body.rstrip().endswith("```")` after a
second member is attached — if this fails, the wikilink landed after the block.

### Pitfall 2: `:graph`/`:stats`/`:check` triggering a lazy rebuild races the sweeper's lock

**What goes wrong:** If `links_sidecar_index.rebuild_links_index_if_stale()` reuses
`vault.acquire_sweep_lock()`/`release_sweep_lock()` (D-04a explicitly says "piggyback
the existing `vault_sweeper` module/lock infrastructure") and a `:vault-sweep` is
already running, `acquire_sweep_lock()` will fail and the caller must decide what
happens to the user's `:graph` invocation — raising `SweepInProgressError` (confirmed
`sentinel-core/app/errors.py:85`, already used by `run_sweep`/`rebuild_embedding_index`)
straight through to the Discord response would produce a confusing "sweep in
progress" error for a read-only graph query the user never associated with sweeping.

**Why it happens:** The lock is shared infrastructure by design (D-04a), but its
error semantics were built for an admin-gated destructive operation, not a
read-mostly, any-user command.

**How to avoid:** `links_sidecar_index.rebuild_links_index_if_stale()` should catch
`SweepInProgressError` specifically and gracefully degrade to serving the
**existing** (possibly stale) index rather than propagating the error — the same
graceful-degrade posture `_emit_embedding_index` already takes on any write
failure (log a warning, keep going). A `:graph` result computed from a slightly
stale index is still useful; a hard error is not.

**Warning signs:** A test fires `:vault-sweep force` and `:graph` concurrently and
asserts the `:graph` response is still a valid (if stale) report, never a raw
exception/500.

### Pitfall 3: `_CARRIER_NAMESPACE_PREFIXES`-style drift between `graph_analysis.py`'s notion of "notes/" and the sweeper's

**What goes wrong:** PITFALLS.md's Pitfall 2 (taxonomy migration silently breaking
Recall's carrier allowlist) is a documented drift class in this exact codebase.
The equivalent risk here: if `graph_analysis.py` hardcodes its own notion of "which
prefix is the flat notes graph" independently of whatever `note_classifier.py`/
`vault_sweep_plan.py` currently consider notes-bound, a future taxonomy tweak could
silently desync the two, producing orphan/link-density numbers that don't match
what's actually being filed.

**How to avoid:** Scope `graph_analysis.py`'s walk to a single named constant
(e.g. `NOTES_ROOT = "notes"`) defined once and imported wherever the notes-bound
root is needed, rather than a second hardcoded `"notes/"` string literal. Since
`note_classifier.TOPIC_VAULT_PATH` doesn't currently define a `"notes"` value at all
(learning/reference route to `inbox/`, not `notes/`, confirmed this session), there
is no existing single-source-of-truth constant to import yet — this phase should
create one deliberately rather than repeat the string literal across
`graph_analysis.py`, `moc_maintenance.py`, and `links_sidecar_index.py`.

**Warning signs:** `grep -rn '"notes' app/services/` returns more than one distinct
string-literal definition site.

### Pitfall 4: Structural claim-title check false-positives/negatives on H1-less or slug-titled notes

**What goes wrong:** D-05's structural-only claim-title test ("confirm an H1/title
exists and is not a bare slug/filename") is deliberately cheap and heuristic. A
naive implementation (e.g. "H1 text != filename") will misclassify:
(a) a genuinely good claim title that happens to be short and hyphen-free but
coincidentally matches its filename slug loosely, and (b) a note with an H1 that
is descriptive but still essentially a topic label ("Notes on X") rather than a
claim — which D-05 explicitly says is out of scope for Phase 45 (LLM-judged title
quality is deferred), so this is an accepted limitation, not a bug to fix here.

**How to avoid:** Keep the heuristic honestly narrow and documented as
structural-only in code comments: (1) an H1 line exists, (2) its normalized text
is not byte-equal (case/hyphen-insensitive) to the derived filename slug, (3)
optionally require >1 word. Do not attempt to approximate "is this actually a
claim" beyond that — that's the explicitly deferred `:check --deep` LLM pass.

**Warning signs:** `:check`'s FAIL/WARN counts trend toward "everything passes"
(heuristic too permissive) or "everything fails" (heuristic too strict, e.g.
comparing against the wrong slug derivation) in a manual spot-check against a
handful of hand-seeded fixture notes.

### Pitfall 5: Sidecar staleness signal is a path-set + content-hash proxy, not true freshness

**What goes wrong:** D-04a is explicit that "the REST API's `list_under` exposes
no per-note mtime — so the lazy fallback is what guarantees eventual correctness"
— but "eventual correctness" needs a concrete cheap check, not an unconditional
full walk-and-reread on every `:graph`/`:stats`/`:check` call (which would work,
but at personal-vault scale is an acceptable-but-wasteful O(N) HTTP-read tax on
every single invocation, mirroring the O(N) HTTP-latency trap the prior
PITFALLS.md v0.5.1 research already flagged).

**How to avoid:** Two concrete staleness checks compose the "hybrid" freshness
model D-04a asks for: (1) **incremental** — whenever a service-side writer (e.g.
`moc_maintenance.attach_to_hub`) touches a note, it directly patches that note's
`links-index.json` entry (single-entry update, no full walk) at write time; (2)
**lazy full-rebuild-if-stale** — on `:graph`/`:stats`/`:check`, compare
`set(await vault.list_under("notes"))`-derived path set against
`set(index.keys())`; any mismatch (add/remove/rename) triggers a full walk+rebuild.
A change to an *existing* note's wikilinks with no path-set change (e.g. hand-editing
an existing note's body in Obsidian) is the one case the cheap check cannot detect
without a full re-read — document this explicitly as an accepted approximation
(this is the literal meaning of "staleness signal is approximate" in D-04a) rather
than treating it as a bug to fix in this phase.

**Warning signs:** A test hand-edits an existing note's wikilinks directly in the
`FakeVault.notes` dict (simulating an out-of-band Obsidian edit) without adding/removing
any path, then calls `:graph`, and the assertion incorrectly expects the change to
be reflected — this is the known, accepted gap; the test should instead assert the
gap explicitly (characterize it) rather than assert full freshness.

## Code Examples

### Wikilink extraction (graph_analysis.py)
```python
# app/services/graph_analysis.py
import re

# Excludes the alias/heading-anchor portion of [[Target|Alias]] / [[Target#Heading]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


def extract_wikilinks(body: str) -> set[str]:
    """Return the set of wikilink targets referenced in body (raw text, not resolved paths)."""
    return {m.group(1).strip() for m in _WIKILINK_RE.finditer(body or "")}
```

### Structural claim-title check (note_schema.py)
```python
# app/services/note_schema.py
import re

_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def has_claim_title(body: str, filename_slug: str) -> bool:
    """D-05 structural-only test: an H1 exists and isn't a bare slug/filename."""
    m = _H1_RE.search(body or "")
    if not m:
        return False
    title = m.group(1).strip()
    normalized = title.lower().replace(" ", "-").replace("_", "-")
    bare_slug = filename_slug.lower().replace("_", "-")
    return normalized != bare_slug and len(title.split()) > 1
```

### Orphan/backlink/density computation (graph_analysis.py)
```python
# app/services/graph_analysis.py
from dataclasses import dataclass, field


@dataclass
class GraphReport:
    note_count: int = 0
    orphans: list[str] = field(default_factory=list)     # no inbound AND no outbound links
    backlinks: dict[str, list[str]] = field(default_factory=dict)  # path -> [referencing paths]
    hub_count: int = 0
    link_density: float = 0.0                              # total edges / note_count


def build_graph_report(notes: dict[str, str], hub_paths: set[str]) -> GraphReport:
    outlinks: dict[str, set[str]] = {path: extract_wikilinks(body) for path, body in notes.items()}
    backlinks: dict[str, list[str]] = {path: [] for path in notes}
    for src, targets in outlinks.items():
        for target in targets:
            for candidate in notes:  # naive title/slug match — see Open Questions
                if candidate.endswith(f"/{target}.md") or candidate == f"{target}.md":
                    backlinks[candidate].append(src)

    orphans = [
        path for path in notes
        if not outlinks[path] and not backlinks[path]
    ]
    total_edges = sum(len(v) for v in outlinks.values())
    return GraphReport(
        note_count=len(notes),
        orphans=orphans,
        backlinks=backlinks,
        hub_count=len(hub_paths),
        link_density=(total_edges / len(notes)) if notes else 0.0,
    )
```

### New route mirroring `/vault/sweep/*`'s shape, no admin gate (app/routes/graph.py)
```python
# app/routes/graph.py
from fastapi import APIRouter, Request

from app.services.links_sidecar_index import rebuild_links_index_if_stale
from app.services.graph_analysis import build_graph_report
from app.state import get_route_context

router = APIRouter()


@router.get("/vault/graph")
async def vault_graph(request: Request):
    ctx = get_route_context(request)
    index = await rebuild_links_index_if_stale(ctx.vault)  # D-04a hybrid freshness
    notes = {p: e["body_cache"] for p, e in index.items()}  # or re-read as needed
    hub_paths = {p for p, e in index.items() if e.get("schema", {}).get("type") == "hub"}
    report = build_graph_report(notes, hub_paths)
    return report.__dict__
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `:graph`/`:stats`/`:check` resolve to `call_core(fixed_prompt)` → one AI completion returning free text, no vault read guarantee | Real endpoints backed by deterministic Python computation over a maintained sidecar index | This phase (45) | Matches ARCHITECTURE.md's own framing: this is the intended fix for Anti-Pattern 1 ("today's fixed-prompt commands ARE NOT the feature, done") — a visible, deliberate behavior change, not a regression |

**Deprecated/outdated:**
- The `_SUBCOMMAND_PROMPTS["stats"]` / `["check"]` dict entries in `interfaces/discord/bot.py`
  (lines 185, 189) become dead code for those two keys once the command_router branches
  are added for `stats`/`check` (mirroring the existing dedicated `graph` branch shape)
  — remove the now-unreachable dict entries in the same change, don't leave them as
  silent dead code.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The lazy full-rebuild-if-stale staleness signal should combine a `notes/` path-set diff with per-note content-hash comparison (my synthesis of D-04a's "approximate... guarantees eventual correctness" language, not a literal quote from CONTEXT.md) | Architecture Patterns §2 / Common Pitfall 5 | If the planner picks a different staleness heuristic (e.g. unconditional full rebuild every call, or a fixed TTL like `SemanticRecall`'s 60s), the tradeoff (O(N) HTTP cost per call vs. missed out-of-band edits) shifts — should be confirmed with the user or explicitly chosen by the planner, not silently assumed |
| A2 | New routes should live in a new `app/routes/graph.py` rather than extending `app/routes/note.py` | Structure Rationale | Low risk — either placement works functionally; wrong guess only costs a file-location bikeshed, not a behavior change |
| A3 | `:graph`/`:stats`/`:check` should NOT be admin-gated (unlike `:vault-sweep`) | Anti-Patterns, Security Domain | If the user actually wants these gated (e.g. to control who can trigger the sidecar-rebuild HTTP/compute cost), an ungated implementation would need retrofitting an admin check later — low-likelihood since D-02 already frames this phase as "read-mostly, additive" with no admin-gate language anywhere in CONTEXT.md |
| A4 | The hub note's stable section marker for member wikilinks is something like `## Member Notes` (not specified anywhere in CONTEXT.md or the master spec) | Architecture Patterns §3, Code Examples | Purely cosmetic — any consistent marker string works as long as `moc_maintenance.py`'s read-then-append logic and any human reading the vault agree on it; should be confirmed/finalized by the planner as a named constant |
| A5 | `note_classifier.TOPIC_VAULT_PATH` does not currently define a canonical `"notes"` constant, so Phase 45 should introduce one (e.g. `NOTES_ROOT = "notes"`) rather than repeating the string literal | Common Pitfall 3 | If a `notes/`-path constant already exists elsewhere under a different name that this session's search missed, introducing a second one would itself become the SPOT-drift risk Pitfall 3 warns against — the planner should re-grep for any existing `"notes"` path constant before introducing a new one |

**If this table is empty:** N/A — see entries above; all are low-to-medium risk
design-synthesis choices, not compliance/security/retention-policy claims.

## Open Questions (RESOLVED during planning — 2026-07-06)

> All three resolved by the Phase 45 plans (plan-checker confirmed): Q1 → plan `45-06` adopts one shared `GraphReport` computation with three thin renderers; Q2 → plan `45-03` uses filename-stem `resolve_wikilink` plus a Wave-0 fixture (`45-01`) pinning the rule; Q3 → plan `45-06` surfaces a "may be stale" caveat field on the response during an active sweep. Kept below for provenance.

1. **Exact command surface shape — three distinct commands vs. facets of one `:vault` command**
   - What we know: CONTEXT.md explicitly leaves this to Claude's Discretion, grounded
     in the master-spec `:graph`/`:stats` definitions (D-06: separate commands with
     distinct responsibilities — `:graph` reports hub membership/orphans/density,
     `:stats` reports note count/hub count/avg-notes-per-hub/orphan-count, `:check`
     validates `_schema` compliance).
   - What's unclear: whether `:stats` and `:graph` should share one underlying
     `GraphReport` computation (cheaper, since both read the same sidecar) with two
     different Discord-formatted renderings, or be entirely independent endpoints.
   - Recommendation: one shared `GraphReport` dataclass/computation, two thin
     rendering functions (`format_graph_response`/`format_stats_response`) and a
     third (`format_check_response`) that adds `note_schema` compliance counts —
     minimizes duplicate sidecar reads while keeping the three Discord commands
     and their existing distinct help-text entries unchanged.

2. **Whether `graph_analysis.py`'s backlink resolution matches wikilinks by title, filename-stem, or full path**
   - What we know: PITFALLS.md's Pitfall 7 (wikilink integrity across migration)
     flags that Obsidian's own wikilink resolution is typically **title-based**,
     not path-based, and this should be "verified empirically against the actual
     vault before assuming risk" — a check this research session could not perform
     (no live Obsidian instance queried).
   - What's unclear: the exact matching rule `graph_analysis.py` should use to
     resolve a `[[Target]]` wikilink string to a concrete `notes/{file}.md` path
     for backlink-counting purposes.
   - Recommendation: match on filename-stem first (matches the Code Examples §3
     approach above: `candidate.endswith(f"/{target}.md")`), which is the
     conservative choice given the flat-`notes/` (Pattern 3) invariant means no two
     notes should share a filename stem; the planner should add a Wave 0 fixture
     test asserting this against a hand-seeded `FakeVault` with a hub + two members.

3. **Concurrent `:graph` staleness-rebuild interaction with the sweeper's `STALE_LOCK_SECONDS`-timeout takeover**
   - What we know: `vault_sweeper.py`'s lock has a 1-hour stale-takeover WARNING path
     (`STALE_LOCK_SECONDS = 3600`, `vault_sweeper.py:100`) — a long-running sweep
     legitimately holds the lock for extended periods.
   - What's unclear: whether a `:graph` invocation during a legitimately-still-running
     (not stale) sweep should silently serve the stale index (Common Pitfall 2's
     recommendation) indefinitely, or surface a "index may be stale, a sweep is in
     progress" note in the Discord response so the user isn't confused by numbers
     that don't yet reflect a just-completed `:ralph` run.
   - Recommendation: surface the degraded state explicitly in the response text
     (e.g. append "(index may be stale — a vault operation is in progress)")
     rather than silently returning numbers with no caveat — cheap to implement,
     matches PITFALLS.md's Pitfall 10 principle (background-task failures/degradation
     must be visible to the user, not silent).

## Environment Availability

Not applicable — this phase introduces no new external tool, service, runtime, or
CLI dependency. It runs entirely inside the existing `sentinel-core` FastAPI process
against the already-required Obsidian Local REST API (a hard dependency since Phase 2,
confirmed still required and functioning — the full test suite ran green this session
against the current environment). No LLM/embedding backend readiness probe is needed
for the read path itself (Pattern 4); the hub-naming LLM fallback (D-03c) reuses the
already-configured LM Studio/exo backend that `note_classifier.py` already depends on,
introducing no new environment requirement.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (already configured; `pytest.ini`/`pyproject.toml` present in `sentinel-core/`) |
| Config file | `sentinel-core/pytest.ini` (or equivalent existing config — unchanged by this phase) |
| Quick run command | `cd sentinel-core && .venv/bin/python -m pytest tests/test_note_schema.py tests/test_graph_analysis.py tests/test_links_sidecar_index.py tests/test_moc_maintenance.py -q` |
| Full suite command | `cd sentinel-core && .venv/bin/python -m pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NOTE-01 | `_schema` trailing block parses correctly (present/absent/malformed) | unit | `pytest tests/test_note_schema.py::test_parse_schema_block_trailing -x` | ❌ Wave 0 |
| NOTE-01 | Claim-title structural check accepts real claims, rejects bare slugs | unit | `pytest tests/test_note_schema.py::test_has_claim_title -x` | ❌ Wave 0 |
| NOTE-01 | Wikilink presence check | unit | `pytest tests/test_note_schema.py::test_has_wikilink -x` | ❌ Wave 0 |
| NOTE-02 | Hub materializes on 2nd cluster member (min-cluster-size=2), not the 1st | unit | `pytest tests/test_moc_maintenance.py::test_hub_materializes_on_second_member -x` | ❌ Wave 0 |
| NOTE-02 | Hub creation is idempotent — 2nd invocation with the same member is a no-op append, never a duplicate wikilink | unit | `pytest tests/test_moc_maintenance.py::test_attach_to_hub_idempotent -x` | ❌ Wave 0 |
| NOTE-02 | Attaching a member to a hub that already has a trailing `_schema` block preserves the block's terminal position (Pitfall 1) | unit (characterizing) | `pytest tests/test_moc_maintenance.py::test_attach_preserves_trailing_schema -x` | ❌ Wave 0 |
| NOTE-02 | Hub-pending singleton (no hub clears cosine floor) is reported as orphan, not a separate state (D-03b) | unit | `pytest tests/test_graph_analysis.py::test_hub_pending_reported_as_orphan -x` | ❌ Wave 0 |
| NOTE-03 | `:graph` reports orphans/backlinks/density correctly against a hand-seeded `FakeVault` fixture | unit | `pytest tests/test_graph_analysis.py::test_build_graph_report -x` | ❌ Wave 0 |
| NOTE-03 | `links-index.json` self-heals on corrupt/unparseable content | unit | `pytest tests/test_links_sidecar_index.py::test_decode_index_body_corrupt_self_heals -x` | ❌ Wave 0 |
| NOTE-03 | Sidecar excludes its own path from the notes/ walk | unit | `pytest tests/test_links_sidecar_index.py::test_own_path_excluded -x` | ❌ Wave 0 |
| NOTE-03 | `:check` reports `_schema` FAIL/WARN items without any LLM call (D-05) | unit | `pytest tests/test_note_schema.py::test_check_no_llm_dependency -x` | ❌ Wave 0 |
| NOTE-03 | `/vault/graph`, `/vault/stats`, `/vault/check` routes respond correctly and are NOT admin-gated | integration | `pytest tests/test_graph_routes.py::test_graph_route_no_admin_gate -x` | ❌ Wave 0 |
| NOTE-03 | Command router `:graph`/`:stats`/`:check` call the new gateway functions, not `call_core` | unit | `pytest ../interfaces/discord/tests/test_command_router_module.py::test_graph_calls_new_gateway -x` | ❌ Wave 0 |
| — (regression) | Full suite stays at 473+ passed, 0 regressed, count only grows | integration | `pytest tests/ -q` (assert `473 passed` floor, new tests additive) | ✅ baseline confirmed this session |

### Sampling Rate
- **Per task commit:** the quick-run command above (new-module unit tests only, <2s)
- **Per wave merge:** `cd sentinel-core && .venv/bin/python -m pytest tests/ -q` (full suite, ~15s per this session's baseline run)
- **Phase gate:** Full suite green (473+ passed, 12 skipped, zero new failures) before `/gsd-verify-work`; additionally re-run the Discord-side test suite (`cd interfaces/discord && python -m pytest tests/` or equivalent, per the existing `interfaces/discord/tests/` layout) since `command_router.py`/`bot.py` are modified

### Wave 0 Gaps
- [ ] `sentinel-core/tests/test_note_schema.py` — covers NOTE-01
- [ ] `sentinel-core/tests/test_graph_analysis.py` — covers NOTE-01, NOTE-02, NOTE-03
- [ ] `sentinel-core/tests/test_links_sidecar_index.py` — covers NOTE-03
- [ ] `sentinel-core/tests/test_moc_maintenance.py` — covers NOTE-02
- [ ] `sentinel-core/tests/test_graph_routes.py` — covers NOTE-03 (route-level, mirrors `test_note_routes.py`'s structure)
- [ ] `interfaces/discord/tests/test_command_router_module.py` additions — covers NOTE-03's command-router rewiring
- [ ] No new fixture infrastructure needed — `sentinel-core/tests/fakes/vault.py`'s `FakeVault` already implements the full `Vault` Protocol (`read_note`/`write_note`/`list_under`/`patch_append`) and is the established canonical test double; reuse it directly rather than introducing a second mock vault

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | no | No new auth surface — routes sit behind the existing `X-Sentinel-Key` header already required for all `/vault/*` and `/note/*` endpoints |
| V3 Session Management | no | No session state introduced |
| V4 Access Control | yes | Deliberately **NOT** admin-gated (see Anti-Patterns, Assumption A3, Open Question 1) — this is a considered decision, not an oversight: the sidecar rebuild is non-destructive to user content and read-only from the user's perspective, unlike `/vault/sweep/start`'s relocate/trash operations which correctly ARE admin-gated via `_is_admin_route` |
| V5 Input Validation | yes | Pydantic response models for the new routes (mirrors `ClassifyResponse`/`SweepStartRequest` pattern); the trailing `_schema` block is parsed with `yaml.safe_load` (never `yaml.load`/`eval`) exactly as `markdown_frontmatter.py` already does — never parse untrusted vault content with an unsafe YAML loader |
| V6 Cryptography | no | No new cryptographic material introduced |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Prompt injection via vault note content read into the hub-naming LLM fallback (D-03c) | Tampering / Elevation of Privilege | Treat all note body text fed into `acompletion_with_profile` as untrusted data in the user-message slot, never as system-level instructions — same posture `note_classifier.classify_note` already takes with `candidate_text` (confirmed `sentinel-core/app/services/note_classifier.py:284-287`); this extends the project's existing untrusted-input-boundary convention (already referenced project-wide, PITFALLS.md Security Mistakes table) to the one new LLM call site this phase introduces |
| Unsafe YAML deserialization of the trailing `_schema` block | Tampering | `yaml.safe_load` only (never `yaml.load` without `Loader=yaml.SafeLoader`, never `eval`/`exec` on parsed content) — matches `markdown_frontmatter.py`'s existing precedent exactly |
| A malicious/malformed `_schema` block or corrupted `links-index.json` crashing the read path | Denial of Service | Both `note_schema.parse_schema_block()` and `links_sidecar_index.decode_index_body()` must catch parse exceptions and degrade to `None`/`{}` rather than propagate — mirrors `embedding_sidecar_index.decode_index_body`'s existing self-healing contract exactly (confirmed `sentinel-core/app/services/embedding_sidecar_index.py:52-72`) |

## Sources

### Primary (HIGH confidence — production source read directly this session)
- `sentinel-core/app/services/embedding_sidecar_index.py` — sidecar format, self-heal, incremental-by-content-hash, dimension-mismatch guard (`eligible_entries`, `build_embedding_index`)
- `sentinel-core/app/services/vault_sweeper.py` — `walk_vault`, `SWEEP_SKIP_PREFIXES`, lockfile (`acquire_sweep_lock`/`release_sweep_lock`, `STALE_LOCK_SECONDS`), `rebuild_embedding_index` (non-destructive startup path), `run_sweep`
- `sentinel-core/app/services/vault_sweep_plan.py` — `is_in_topic_dir`, `propose_topic_move`, taxonomy-aware family-root derivation
- `sentinel-core/app/services/recall.py` — `RecallConfig.semantic_cosine_floor = 0.50`, `RecallConfig.exclude_prefixes`/`self_paths`, `SemanticRecall.search()`'s cosine-floor loop
- `sentinel-core/app/services/note_classifier.py` — `TOPIC_VAULT_PATH` (confirms learning/reference route to `inbox/`, not `notes/`), `_resolve_model_for_classification`/`classify_note`'s `acompletion_with_profile(response_format=json_schema)` structured-completion pattern
- `sentinel-core/app/markdown_frontmatter.py` — leading-frontmatter regex/parse/emit (`split_frontmatter`/`join_frontmatter`), the pattern `note_schema.py` must mirror but anchor oppositely
- `sentinel-core/app/vault.py` — `Vault` Protocol (`read_note`/`write_note`/`list_under`/`patch_append`/`find`), `PROTECTED_NAMESPACES`
- `sentinel-core/app/routes/note.py` — `/vault/sweep/start`+`/vault/sweep/status` route shape, `_is_admin_route`, request/response Pydantic models
- `sentinel-core/app/state.py`, `sentinel-core/app/composition.py` — `RouteContext` dataclass, `get_route_context`, `_startup_rebuild` wiring pattern
- `sentinel-core/tests/fakes/vault.py` — canonical `FakeVault` test double (full `Vault` Protocol implementation, dict-backed)
- `sentinel-core/tests/test_vault_sweeper.py` — confirms `FakeVault` is the established test-double convention (migrated off a test-local `FakeObsidian` class)
- `shared/sentinel_shared/similarity.py` — `cosine_similarity` (cross-package SPOT, vec×vec/matrix×vec overload)
- `interfaces/discord/command_router.py` — `handle_subcommand`'s existing `graph` branch (fixed-prompt `call_core` call to be replaced)
- `interfaces/discord/bot.py` — `_SUBCOMMAND_PROMPTS` dict (`"stats"`, `"check"` entries to be replaced), `SUBCOMMAND_HELP` text
- `interfaces/discord/core_gateway.py` — `call_core_sweep_start`/`call_core_sweep_status`/`call_core_note` — the exact pattern new `call_core_graph`/`call_core_stats`/`call_core_check` must mirror
- `sentinel-core/app/errors.py` — `SweepInProgressError`, `ProtectedPathError` class hierarchy
- Full test suite run this session: `cd sentinel-core && .venv/bin/python -m pytest tests/ -q` → `473 passed, 12 skipped` (confirms the baseline this phase must not regress)

### Secondary (MEDIUM confidence — prior curated research documents, not re-verified against a second source this session)
- `.planning/research/ARCHITECTURE.md` — Phase B build order, component responsibility table, Pattern 4 (embedding-first hub lookup), Anti-Patterns 1-6, `note_schema.py`/`graph_analysis.py`/`moc_maintenance.py` component split and its Structure Rationale
- `.planning/research/PITFALLS.md` — Pitfall 2 (carrier-allowlist/taxonomy drift, adapted here as Common Pitfall 3), Pitfall 5 (MOC/hub-note drift, orphan explosion), Pitfall 6 (enforcement at Verify not Reduce — basis for D-02), Pitfall 7 (wikilink integrity, title- vs. path-based resolution — basis for Open Question 2), Pitfall 10 (background-task failure visibility — basis for Open Question 3's recommendation), Security Mistakes table (prompt-injection-via-vault-content)
- `docs/2nd-brain-original-design/10-CONTEXT-master-spec.md` — D-05 (`_schema` canonical definition, claim-title test wording), D-06 (MOC/hub notes, `:graph`/`:stats`/`:connect` command spec, lazy hub creation), D-09 (6 Rs sequencing, confirms Reduce/Reflect/Verify staging)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; every dependency already installed and its usage pattern directly read from production source this session
- Architecture: HIGH — every pattern cited mirrors an already-shipped, already-tested analog in this exact codebase (embedding sidecar, sweep routes, sweep lock, cosine search)
- Pitfalls: HIGH for the codebase-specific pitfalls (trailing-block corruption, sidecar own-path exclusion, lock-race, taxonomy drift) — all derived from direct code reads and the project's own PITFALLS.md; MEDIUM for the wikilink title-vs-path resolution question (Open Question 2), which PITFALLS.md itself flags as unverified against a live Obsidian instance

**Research date:** 2026-07-06
**Valid until:** 30 days (stable internal-codebase research; no external library version drift risk since no new external dependency was introduced) — but should be re-checked if Phase 46 (6 Rs pipeline) lands first and changes `note_classifier.TOPIC_VAULT_PATH` or introduces a `notes/` write path before Phase 45 executes, since that would change the "no write path exists yet" premise Common Pitfall 3/Assumption A5 depend on
