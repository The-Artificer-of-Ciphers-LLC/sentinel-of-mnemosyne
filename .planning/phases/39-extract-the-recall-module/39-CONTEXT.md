# Phase 39: Extract the Recall Module - Context

**Gathered:** 2026-06-11
**Status:** Ready for planning
**Source:** ADR Ingest Express Path (docs/adr/0003-recall-module.md)

<domain>
## Phase Boundary

This phase extracts a deep **Recall** module that owns retrieval policy and sits **above** the `Vault` Protocol seam. Today, Hot-tier and Warm-tier assembly are private methods on `MessageProcessor` (`_append_hot_tier`, `_append_warm_tier`, `_allocate_budgets`) with every relevance threshold, exclusion list, session window, and budget ratio inlined as a literal in `message_processing.py`. The Sentinel "forgets after three" because retrieval has no module and cannot be tested without the full `POST /message` path; `GET /context/{user_id}` re-implements hot-tier assembly a second time.

After this phase, `Recall.assemble()` is the single entry point for hot + warm tier assembly, used by both the message path and `GET /context/{user_id}`. Recall returns a `RecalledContext` *value* (ranked, budget-trimmed memory items) — never chat messages, persona, or injection-defense formatting.

This phase does NOT build the `RetrievalStrategy` seam, does NOT type `SessionSummary`, and does NOT touch `app/vault.py` (ADR-0002 stands). Those are follow-up phases (40, 41).
</domain>

<decisions>
## Implementation Decisions

### Recall module ownership
- **D-01:** Extract a deep `Recall` module that owns retrieval policy and sits *above* the Vault seam.
- **D-02:** `Recall` owns *what to remember*: Self-namespace reads, recent Session summaries, Warm-tier vault search, the relevance threshold, the namespace exclusions, the recent-session window, and the per-tier selection budgets (the `0.15` / `0.10` split). These constants move into a `RecallConfig`.

### Return contract
- **D-03:** `Recall.assemble(request, budget)` returns a `RecalledContext` value — ranked, budget-trimmed memory items. It does NOT return chat messages.

### MessageProcessor boundary
- **D-04:** `MessageProcessor` keeps *how to present and defend*: the Sentinel persona read, `injection_filter.wrap_context()`, the "Understood." pairs, and the final whole-prompt `TokenBudget.check()`.

### Endpoint convergence
- **D-05:** `GET /context/{user_id}` delegates to `Recall` and serializes `RecalledContext`. The duplicated inline assembly is deleted.

### Dependency direction
- **D-06:** `Recall` depends on the `Vault` Protocol only. It does NOT move or modify `app/vault.py` (ADR-0002 stands).

### Claude's Discretion
- Internal structure of `RecallConfig` (dataclass vs pydantic), exact module/file layout under `app/`, naming of private helpers (`_warm_search`, etc.), and how raw Obsidian dicts are translated to `SearchResult` at Recall's edge — provided the leakage of raw dicts stops at that edge.
- Wiring/DI approach for injecting `Recall` into `MessageProcessor` and the `/context` route.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Recall design (this phase)
- `docs/adr/0003-recall-module.md` — locks the Recall module boundary, return contract, and scope fences (this phase's source ADR).

### Related / upstream
- `docs/adr/0002-vault-seam-location.md` — Vault seam decision; ADR-0003 explicitly does not modify `app/vault.py`. (Read to respect the boundary.)
- `sentinel-core/app/services/message_processing.py` — current home of `_append_hot_tier`, `_append_warm_tier`, `_allocate_budgets` and the inline constants to extract.
- `sentinel-core/app/vault.py` — the `Vault` Protocol that `Recall` depends on (do not modify).
- `sentinel-core/tests/fakes/` (FakeVault) — the test surface `test_recall.py` builds against.

</canonical_refs>

<specifics>
## Specific Ideas

- New tests `test_recall.py` are *added* against `FakeVault` — no `MessageProcessor` or AI provider needed. The existing through-`/message` tier tests are KEPT (project Test-Rewrite Ban — operator decides retirement separately).
- Raw Obsidian search dicts are translated to `SearchResult` at Recall's edge; the leakage stops there. Warm search stays a private `Recall._warm_search()`, *shaped* for later extraction but not yet a public seam.
- `RecalledContext` is half-typed by design this step: warm results typed, self/sessions stay raw (`sessions` is `list[str]`).

</specifics>

<scope_fence>
## Scope Fence (explicitly OUT)

Rejected/deferred alternatives from the ADR — do NOT implement in this phase:
- Recall returning ready-to-inject messages (owning `injection_filter` + pairs + per-tier truncation) — wrong layer.
- Folding the Sentinel persona into Recall — persona is operator-curated identity, not recalled memory.
- Building the `RetrievalStrategy` seam now — only one adapter exists today; the seam arrives with `SemanticRecall` (Phase 40).
- Typing `find()` in the Vault Protocol — touches `ObsidianVault`, `FakeVault`, adapter tests; later step.
- Migrating existing through-`/message` tier tests down to Recall — Test-Rewrite Ban.
- Typing `SessionSummary` now — deferred to Phase 41 (`RetentionPolicy` + typed `SessionSummary`).

</scope_fence>

<success_criteria>
## Success Criteria (from ADR consequences)

- The interface becomes the test surface: "given these vault notes + this message, `assemble` returns these ranked items" — provable with no `MessageProcessor`, no AI provider, no `injection_filter`.
- All retrieval constants concentrate in one module (locality); every memory tweak lands in one place (leverage across the message path and `/context`).
- `Recall.assemble()` is the sole entry point for hot + warm tier assembly; `GET /context/{user_id}` uses the same logic as the message path.
- Relevance threshold, namespace exclusion, and per-tier budgets live in `RecallConfig`.
- `test_recall.py` passes against `FakeVault`.

</success_criteria>

<risk_summary>
## Risk Summary

- The ADR records no negative consequences for the extraction itself. The principal risk is behavioral drift: the extracted `Recall.assemble()` must reproduce the existing hot/warm assembly exactly so the kept through-`/message` tests still pass. `RecalledContext` being half-typed (self/sessions raw) is an accepted, bounded scope boundary closed in Phase 41.

</risk_summary>

<deferred>
## Deferred Ideas

- Typed `SessionSummary` + `RetentionPolicy` → Phase 41.
- `RetrievalStrategy` seam + `SemanticRecall` adapter (semantic recall reading back the embeddings the sweeper already writes) → Phase 40.
- Typing `find()` in the Vault Protocol → later step.

</deferred>

---

*Phase: 39-extract-the-recall-module*
*Context gathered: 2026-06-11 via ADR Ingest Express Path*
