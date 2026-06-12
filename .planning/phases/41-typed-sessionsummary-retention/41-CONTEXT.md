# Phase 41: Typed SessionSummary + Retention - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Close the conversation-history cliff. Today session summaries are dropped from context after the fixed 3-turn / today+yesterday hot window, so conversations longer than a day lose history. This phase makes four changes, all owned by the `Recall` module above the `Vault` seam:

1. **MEM-08** — `Session` data crosses the Recall interface as typed `SessionSummary` values (not raw markdown strings).
2. **MEM-06** — the recent-session window becomes a tunable `RetentionPolicy` (`hot_limit`, `hot_window_days`) instead of inline magic numbers.
3. **MEM-07** — sessions older than the hot window stay retrievable via the semantic index (through a conversation note filed **outside** `ops/`), instead of being silently dropped.
4. **MEM-09** — recalled sessions are weighted by recency in the merge so a more recent session ranks above an older one of equal relevance.

**Out of this phase:** relaxing the `ops/` exclusion; recency weighting on Self-namespace / authored notes; a persistent ANN vector index; operator-tunable RecallConfig via a vault file.
</domain>

<decisions>
## Implementation Decisions

### Recency formula (MEM-09)
- **D-01:** Recency is an **exponential decay blend** — each session's relevance score is combined with an exponential recency factor keyed on `SessionSummary.date`. Recent sessions get a real boost, but a strongly-relevant older session can still surface (recency does NOT hard-override relevance). Use a tunable half-life with a sensible default (~7 days suggested; planner/researcher confirm the exact curve and constant).
- **D-02:** The recency factor input is the typed `SessionSummary.date`. Recency weighting applies to **episodic Session summaries only** — never to Self-namespace or deliberately-authored notes (validated out-of-scope boundary).

### Where recency applies (MEM-09)
- **D-03:** Recency weighting applies in **both** places: (a) ordering the hot recent-session list, AND (b) weighting session-derived results inside the warm RRF merge (`recall.py` `_warm_search`). This is required to fully satisfy MEM-09 ("recalled session summaries weighted by recency in the merge") — hot-tier-only ordering would under-deliver it.

### Retention policy tunability (MEM-06)
- **D-04:** `RetentionPolicy` defaults live in code (`hot_limit=3`, `hot_window_days=2`) but are **env-overridable** via `Settings` (same pattern as `sweep_skip_prefixes` / `protected_namespaces`) so the operator can widen the window without a redeploy. This is env config, NOT vault-file tuning — it stays within v0.5.1 scope (vault-file RecallConfig tuning remains deferred).

### Old-session recall carrier (MEM-07)
- **D-05:** The recall target for old sessions is the **existing conversation note already filed outside `ops/`** (via `NoteIntake.classify_and_apply` / `message.py` `_schedule_chat_note`), using its **full body**. The `ops/` exclusion is NOT relaxed — `ops/sessions/` summaries stay un-embedded; reachability comes from the conversation-note carrier, which the sweeper already embeds and warm recall already includes.
- **D-06 (research gate):** The researcher MUST confirm the conversation-note carrier is actually (a) written on every message, (b) filed outside `ops/` in a sweep-eligible + warm-recall-eligible namespace, and (c) embedded by the sweeper. If any link is missing, that gap is in-scope to close (it is the mechanism MEM-07 depends on) — surface it, do not defer it.

### Vault seam reopen (bounded — ADR-0002)
- **D-07:** `Vault.get_recent_sessions` return type changes from `list[str]` to `list[SessionSummary]`, and it takes the `RetentionPolicy` (today+yesterday inline window in `vault.py:288` moves into `RetentionPolicy.hot_window_days`). This is a **bounded** ADR-0002 reopen — only this method's signature — touching `ObsidianVault`, `FakeVault`, and adapter tests.

### Claude's Discretion
- Exact decay curve constant / half-life value (D-01) — researcher recommends, planner locks; default ~7 days unless evidence says otherwise.
- Internal placement of the recency-weight helper (in `Recall`, a small pure function, or `RetentionPolicy` method) — planner decides; keep it a pure, unit-testable function.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase design contract (read first)
- `docs/adr/0005-typed-session-summary.md` — the locked design record for this phase: typed `SessionSummary` (`date, user_id, time, user_msg, sentinel_msg, path, body`), `RetentionPolicy(hot_limit=3, hot_window_days=2)`, the "reach old sessions via a note outside `ops/`" resolution, and the rejected alternatives (raise limit / keep strings / relax `ops/`).

### Requirements & scope
- `.planning/REQUIREMENTS.md` §"Memory & Recall (v0.5.1)" — MEM-06, MEM-07, MEM-08, **MEM-09** (recency, added this phase) and the §"Out of Scope" boundaries (`ops/` stays; no recency on Self-namespace; no ANN index; no vault-file RecallConfig).
- `.planning/ROADMAP.md` §"Phase 41" — the 5 success criteria (criterion 5 = recency weighting).
- `.planning/PROJECT.md` — Core Value ("retrieve relevant context on every message — never start cold") and the validated MEM-01..05 that must not regress.

### Upstream architecture decisions (constrain HOW)
- `docs/adr/0002-*` — `Vault` Protocol seam at `app/vault.py`; this phase's `get_recent_sessions` return-type change is the bounded reopen.
- `docs/adr/0003-*` — Recall is a module above the Vault seam; retention/recency policy is domain logic that lives here, not in the adapter.
- `docs/adr/0004-*` — `RetrievalStrategy` seam + RRF hybrid merge; the warm-tier recency weighting (D-03) hooks into this merge.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `sentinel-core/app/services/recall.py` — `SearchResult`, `RecalledContext`, `RecallConfig` are all `@dataclass(frozen=True)`; mirror this pattern for `SessionSummary` and `RetentionPolicy` (pure value types).
- `RecallConfig.recent_session_limit` (`recall.py:173`, default 3) — becomes `RetentionPolicy.hot_limit`.
- `Recall._warm_search` (`recall.py`, the RRF merge) — the hook point for warm-tier recency weighting (D-03).
- `ObsidianVault.get_recent_sessions` (`vault.py:128` signature, `vault.py:288-291` inline today+yesterday window) — return type → `list[SessionSummary]`; window → `RetentionPolicy.hot_window_days`.
- `MessageProcessor._build_session_summary` (`message_processing.py:182-203`) — current raw-markdown session writer; defines the frontmatter/body shape a `SessionSummary` parser must read (`timestamp`, `user_id`, `model`, `## User`, `## Sentinel`).
- `NoteIntake.classify_and_apply` / `message.py` `_schedule_chat_note` — the conversation-note-outside-`ops/` carrier MEM-07 relies on (D-05/D-06).
- `Settings` (`config.py`) env-overridable fields (`sweep_skip_prefixes`, `protected_namespaces`) — the pattern for env-overridable `RetentionPolicy` (D-04).

### Established Patterns
- Pure value types = `@dataclass(frozen=True)`; Pydantic `BaseModel` only at API boundaries.
- Recall-layer tunables default in code and are wired at the composition root (`composition.py`); operator-tunable knobs go through `Settings` env vars.
- In-memory numpy cosine over the sweeper-maintained `ops/sweeps/embedding-index.json`; no per-note HTTP at query time (MEM-05, validated — do not regress).

### Integration Points
- `Vault` protocol + `ObsidianVault` + `FakeVault` + adapter tests all move in lockstep with the `get_recent_sessions` return-type change.
- **Test-Rewrite Ban note for the planner:** the scout found ~17 mock sites (`get_recent_sessions.return_value = []` expecting `list[str]`) across `test_message.py`/recall tests. These protect shipped behavior. Updating them **in lockstep** with the operator-approved return-type change (this phase) is permitted; weakening assertions or stubbing around the new typed contract is NOT. Where a session-summary test asserts on recalled content, keep/strengthen the assertion against the typed fields.
</code_context>

<specifics>
## Specific Ideas

- Recency curve: exponential decay, half-life default ~7 days, keyed on `SessionSummary.date` (D-01).
- "Recent beats old of equal relevance, but a clearly-relevant old session still surfaces" is the explicit behavioral target — recency is a blend, not a hard sort.
- Operator wants to widen the hot window without a redeploy → env override (D-04).
</specifics>

<deferred>
## Deferred Ideas

- Persistent ANN vector index (hnswlib/faiss/sqlite-vec/chroma) — stays deferred; numpy cosine is sufficient at personal-vault scale (RetrievalStrategy seam allows a later swap). *Operator-deferred in REQUIREMENTS.md, not by this session.*
- Operator-tunable RecallConfig via a **vault file** — stays deferred; env-override (D-04) is the in-scope middle ground.
- Cross-encoder reranking of recall results — deferred; RRF + recency blend is sufficient for v0.5.1.

**Note:** The recency-weighting *formula* was previously marked "deferred to post-v0.5.1" in REQUIREMENTS.md. That deferral was **un-authorized**; the operator pulled it back into Phase 41 scope this session (now MEM-09). Nothing recency-related is deferred.

### Reviewed Todos (not folded)
None — no pending todos matched this phase.
</deferred>

---

*Phase: 41-typed-sessionsummary-retention*
*Context gathered: 2026-06-12*
