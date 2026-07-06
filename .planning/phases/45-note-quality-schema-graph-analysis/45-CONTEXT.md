# Phase 45: Note-Quality Schema + Graph Analysis - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Give every authored note a durable quality standard — a trailing `_schema` footer
block (note type + hub membership), a claim-style title, and wikilinks — and let
the user inspect the vault's knowledge graph (orphans, backlinks, link density,
`_schema` compliance) through new **read-only** commands (`:graph` / `:stats` /
`:check`), backed by a `links-index.json` sidecar rather than a full vault walk on
every call. Maps of Content (MOC/hub notes) are created **lazily** as notes cluster,
never upfront.

**This phase is additive and read-mostly.** No change to `POST /message`, `Recall`,
semantic recall, or the existing 473-passing / 12-skipped test suite. Requirements:
NOTE-01, NOTE-02, NOTE-03.

**Explicitly NOT in this phase** (deferred to Phase 46 — 6 Rs pipeline / Reduce):
authoring born-compliant notes, writing `notes/` from `inbox/`, any write-path
enforcement of the standard.

</domain>

<decisions>
## Implementation Decisions

### `_schema` footer format
- **D-01:** The `_schema` block is a **trailing fenced ` ```_schema ` block at the
  end of the note**, carrying at minimum `type` + hub membership. It is a distinct
  block, kept **separate from the leading YAML provenance frontmatter** that
  `markdown_frontmatter.py` already owns (`original_path`, `topic_moved_at`,
  `sweep_at`, …). A new `note_schema.py` module parses/validates exactly this
  trailing block (regex-from-end). Rejected: merging into frontmatter (two owners /
  one block = the anti-pattern ARCHITECTURE.md calls out), HTML comment
  (tooling-strip risk), Dataview inline (adds a plugin dependency the vault lacks).
  This confirms master-spec **D-05**.

### Enforcement point
- **D-02:** Enforcement is **inspect-only**. Phase 45 adds `note_schema.py` +
  `graph_analysis.py` to back `:check` / `:graph` / `:stats`; it does **not** touch
  any write path and does **not** auto-fill the standard at write time. Rationale:
  matches the read-mostly constraint AND PITFALLS.md **Pitfall 6** ("enforce at
  Verify, never at file-time"); `note_classifier` routes content to `inbox/`, so
  Phase 45 has no `notes/` write path to hook onto anyway. Works identically for
  pipeline-produced and hand-authored notes. NOTE-01's "Notes *carry* the standard"
  is closed across two phases — Phase 46's Reduce is where notes are born compliant.

### Hub / MOC assignment
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

### links-index.json sidecar (location + freshness)
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

### `:check` claim-title validation
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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & build order (primary)
- `.planning/research/ARCHITECTURE.md` — Phase B build order; **Pattern 4:
  embedding-first hub lookup**; `note_schema.py` / `graph_analysis.py` split and the
  "Structure Rationale" for keeping the `_schema` trailing block separate from leading
  provenance frontmatter; flat-`notes/` Pattern 3.
- `.planning/research/PITFALLS.md` §Pitfall 6 — enforcement belongs at Verify, never
  at file-time (basis for D-02 inspect-only).

### Original design spec
- `docs/2nd-brain-original-design/10-CONTEXT-master-spec.md` — **D-05** canonical
  `_schema` fenced-block definition; the `:graph` / `:stats` command spec; hub/MOC
  concept-slug naming.

### Recall / embedding context (constraints)
- `docs/adr/0003-recall-module.md`, `docs/adr/0004-semantic-recall.md` — recall +
  semantic recall boundaries that must remain unaffected.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `sentinel-core/app/services/embedding_sidecar_index.py` + `vault_sweeper.py`
  (`_emit_embedding_index` / `rebuild_embedding_index`, boot rebuild via
  `composition.py` `_startup_rebuild`): the **direct precedent** for the links-index
  sidecar — in-vault JSON via `write_note`, incremental-during-sweep + non-destructive
  full rebuild, self-healing on parse failure. Extend this shape as
  `links_sidecar_index.py`.
- `sentinel-core/app/services/recall.py`: `RecallConfig.semantic_cosine_floor = 0.50`
  (D-11) — **reuse this constant** as the hub-membership floor (D-03); do not invent a
  new threshold.
- `embedding_sidecar_index.py` dimension-mismatch guard — reuse for hub cosine so a
  stored-dim ≠ active-model-dim entry is hard-skipped.
- `sentinel-core/app/markdown_frontmatter.py`: owner of the **leading** provenance
  frontmatter — the `_schema` trailing block must stay disjoint from it.
- `sentinel-core/app/vault.py`: `read_note` / `write_note` (full-body **PUT**, no
  partial PATCH) + `patch_append`; `list_under` (directory listing, **no per-file
  mtime** — informs the D-04a approximate-staleness reality).

### Established Patterns
- **Read-then-conditionally-write / lazy-create-if-missing (D-14)** — apply to
  idempotent hub creation (D-03d) and to sidecar self-heal.
- **Module-constant + settings-override + backstop** (`SWEEP_SKIP_PREFIXES` /
  `_active_skip_prefixes()`) — pattern for excluding `ops/graph/links-index.json` from
  the indexed walk.
- **Structured-completion for LLM naming** (`six_rs/reduce.py`
  `acompletion_with_profile(response_format=json_schema)`) — for the constrained
  hub concept-slug fallback (D-03c).

### Integration Points
- New `note_schema.py`, `graph_analysis.py`, MOC-maintenance, and links-sidecar
  modules back the new read-only `:graph` / `:stats` / `:check` commands. None of them
  touch `POST /message`, `Recall`, semantic recall, or any write path.
- The lazy full-rebuild fallback (D-04a) hooks the existing `vault_sweeper` walk/lock.

</code_context>

<specifics>
## Specific Ideas

- Hub floor is the **already-shipped 0.50 cosine** (recall D-11) — a deliberate reuse,
  not a new tunable.
- Hub note path is deterministic (`notes/{concept-slug}.md`) so re-derivation, not
  locking, provides idempotency — fits the transaction-less REST vault.
- The sidecar lives at `ops/graph/links-index.json` specifically (parallel to
  `ops/sweeps/embedding-index.json`).

</specifics>

<deferred>
## Deferred Ideas

- **Born-compliant note writing** — auto-filling `_schema` + claim title + wikilinks on
  the write path → **Phase 46 (6 Rs / Reduce)**. Explicitly kept out of Phase 45 to
  preserve the read-mostly constraint and avoid duplicating Reduce.
- **LLM-judged claim-title quality** (a `:check --deep` pass) — possible future
  enhancement; Phase 45 `:check` is structural-only (D-05).
- **Separate "hub-pending" (non-orphan) state** — considered for D-03b; deferred in
  favor of honest orphan reporting until a sibling note materializes the hub.

</deferred>

---

*Phase: 45-Note-Quality Schema + Graph Analysis*
*Context gathered: 2026-07-06*
