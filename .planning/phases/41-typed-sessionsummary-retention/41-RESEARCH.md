# Phase 41: Typed SessionSummary + Retention - Research

**Researched:** 2026-06-12
**Domain:** Internal refactor of the Sentinel `Recall` module — typed value objects, retention policy, recency-weighted RRF merge. Pure Python (FastAPI/async); no external packages added.
**Confidence:** HIGH (entire blast radius is in-repo and was read directly; the only LOW item is the exact decay constant, which CONTEXT.md D-01 explicitly hands to the planner)

## Summary

This phase makes four coordinated changes to the in-repo `Recall` module (`sentinel-core/app/services/recall.py`) and its one bounded reach into the Vault seam (`get_recent_sessions`). All four requirements are satisfied by code already present in the repo — **there are no new external dependencies, no new services, and no new vault paths.** The work is a typed-value-object introduction plus a recency-weight helper, exactly as ADR-0005 specifies.

The "old sessions get recalled, not dropped" mechanism (MEM-07) is **already wired end-to-end** and was verified in this session: every substantive `/message` schedules `NoteIntake.classify_and_apply(content, searchable_only=True)` (`message.py:48,91`), which files a conversation note into `journal/` or a topic folder **outside `ops/`**, redirecting any ops-bound classification to `journal/` (`note_intake.py:79-82`). `journal/` is **not** in `sweep_skip_prefixes` (`config.py:102-117`), so the sweeper embeds it into `ops/sweeps/embedding-index.json`, and `SemanticRecall` already reads that index and surfaces those notes through `RecalledContext.warm`. The D-06 research gate therefore **passes** — see the Runtime State Inventory and Pitfall 1 for the one residual gap (`inbox/` notes are not embedded).

**Primary recommendation:** Introduce `SessionSummary` and `RetentionPolicy` as `@dataclass(frozen=True)` value types in `recall.py` (mirroring `SearchResult`/`RecallConfig`); change `Vault.get_recent_sessions` to return `list[SessionSummary]` and accept a `RetentionPolicy`; add a pure `recency_weight(date, *, now, half_life_days)` helper; apply it in both the hot-session ordering and the warm RRF merge (D-03), scoped to episodic sessions only. Update — in lockstep — the ~3 in-repo `get_recent_sessions` implementations, the 2 `recalled.sessions` consumers, and the ~25 test mock sites.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Recency is an **exponential decay blend** — each session's relevance score is combined with an exponential recency factor keyed on `SessionSummary.date`. Recent sessions get a real boost, but a strongly-relevant older session can still surface (recency does NOT hard-override relevance). Tunable half-life with a sensible default (~7 days suggested; researcher/planner confirm exact curve and constant).
- **D-02:** The recency factor input is the typed `SessionSummary.date`. Recency weighting applies to **episodic Session summaries only** — never to Self-namespace or deliberately-authored notes (validated out-of-scope boundary).
- **D-03:** Recency weighting applies in **both** places: (a) ordering the hot recent-session list, AND (b) weighting session-derived results inside the warm RRF merge (`recall.py` `_warm_search`).
- **D-04:** `RetentionPolicy` defaults live in code (`hot_limit=3`, `hot_window_days=2`) but are **env-overridable** via `Settings` (same pattern as `sweep_skip_prefixes` / `protected_namespaces`). Env config, NOT vault-file tuning — stays within v0.5.1 scope.
- **D-05:** The recall target for old sessions is the **existing conversation note already filed outside `ops/`** (via `NoteIntake.classify_and_apply` / `message.py` `_schedule_chat_note`), using its **full body**. The `ops/` exclusion is NOT relaxed.
- **D-06 (research gate):** Researcher MUST confirm the conversation-note carrier is (a) written on every message, (b) filed outside `ops/` in a sweep-eligible + warm-recall-eligible namespace, and (c) embedded by the sweeper. If any link is missing, that gap is in-scope to close. → **VERIFIED in this session; see Runtime State Inventory + Pitfall 1.**
- **D-07:** `Vault.get_recent_sessions` return type changes from `list[str]` to `list[SessionSummary]`, and it takes the `RetentionPolicy` (today+yesterday inline window in `vault.py:288` moves into `RetentionPolicy.hot_window_days`). Bounded ADR-0002 reopen — only this method's signature — touching `ObsidianVault`, `FakeVault`, and adapter tests.

### Claude's Discretion
- Exact decay curve constant / half-life value (D-01) — researcher recommends, planner locks; default ~7 days unless evidence says otherwise. **→ Researcher recommendation below in Pattern 3.**
- Internal placement of the recency-weight helper (in `Recall`, a small pure function, or `RetentionPolicy` method) — planner decides; keep it a pure, unit-testable function. **→ Researcher recommends a module-level pure function; see Pattern 3.**

### Deferred Ideas (OUT OF SCOPE)
- Relaxing the `ops/` exclusion — stays.
- Recency weighting on Self-namespace / authored notes — never.
- Persistent ANN vector index (hnswlib/faiss/sqlite-vec/chroma) — numpy cosine is sufficient.
- Operator-tunable RecallConfig via a **vault file** — env-override (D-04) is the in-scope middle ground.
- Cross-encoder reranking — RRF + recency blend is sufficient for v0.5.1.

**Note:** The recency-weighting *formula* was previously marked "deferred to post-v0.5.1." That deferral was **un-authorized**; the operator pulled it back into Phase 41 scope (now MEM-09). Nothing recency-related is deferred.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MEM-06 | Recent-session window is a tunable retention policy, not a fixed 3-turn/two-day limit | `RetentionPolicy(hot_limit=3, hot_window_days=2)` replaces `RecallConfig.recent_session_limit` (`recall.py:172`) and the inline today+yesterday window (`vault.py:288-291`). Env-overridable via `Settings` per the `sweep_skip_prefixes` pattern (`config.py:102-117`). |
| MEM-07 | Sessions older than the hot window are recalled via the index, not dropped | Carrier chain VERIFIED: `message.py:48` → `_schedule_chat_note` → `classify_and_apply(searchable_only=True)` files outside `ops/` → `journal/` not in `sweep_skip_prefixes` → sweeper embeds → `SemanticRecall` surfaces via `RecalledContext.warm`. No new code needed for reachability; phase work is to confirm + test it, not build it. |
| MEM-08 | Session data crosses the Recall interface as typed values | New `@dataclass(frozen=True) SessionSummary(date, user_id, time, user_msg, sentinel_msg, path, body)` becomes the type of `get_recent_sessions` return and `RecalledContext.sessions`. A parser reads the frontmatter/body shape emitted by `_build_session_summary` (`message_processing.py:189-203`). |
| MEM-09 | Recalled session summaries weighted by recency in the merge, episodic-only | Pure `recency_weight(SessionSummary.date, ...)` helper applied (a) to hot-session ordering and (b) inside `_warm_search` RRF when a result is session-derived (D-03). Never applied to Self-namespace / authored notes (D-02). |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Typed `SessionSummary` value | `Recall` module (`recall.py`) | Vault adapters (return type) | ADR-0003: retrieval policy + value types live in `Recall`; the Vault adapter only produces them at its edge. |
| `RetentionPolicy` (window/limit) | `Recall` module | `Settings` (env override) | ADR-0005 + D-04: policy is domain logic in `Recall`; env override is composition-root wiring (`composition.py:328`). |
| Parsing session frontmatter/body → `SessionSummary` | Vault adapter edge (`ObsidianVault.get_recent_sessions`) | — | Translation of raw markdown to typed value happens at the Vault edge, same as raw Obsidian dicts → `SearchResult` in `KeywordRecall`. |
| Recency weight helper | `Recall` module (pure fn) | — | Pure, unit-testable; no I/O. ADR-0004 RRF merge is the hook point. |
| Old-session reachability (the carrier note) | `NoteIntake` + sweeper (already shipped) | `SemanticRecall` | MEM-07 leans on existing carrier; this phase does not own it, only verifies/tests it. |
| Hot/warm presentation of sessions | `MessageProcessor` (`message_processing.py:108`) | `status.py` route | D-04: presentation stays in the processor; this phase updates how it reads the now-typed list. |

## Standard Stack

**No new packages.** This phase uses only what is already installed and imported in `sentinel-core`.

### Core (existing, already imported by the touched modules)
| Library | Version (installed) | Purpose | Why Standard |
|---------|---------------------|---------|--------------|
| `numpy` | already a dep (`recall.py:21`) | cosine + any vector math in recency composition | Already the warm-tier math backbone. No new import needed. |
| `pytest` + `pytest-asyncio` | `>=8.0` / `>=0.23` (`pyproject.toml:25-26`) | async test framework (`asyncio_mode="auto"`) | Project standard; all recall tests already use it. |
| `pyyaml` | already a dep (`note_intake.py:13`) | frontmatter parsing for `SessionSummary` | Already used for note frontmatter; reuse for the session-summary parser. |
| stdlib `dataclasses` | 3.12 | `@dataclass(frozen=True)` value types | The established pattern for `SearchResult`/`RecallConfig`/`RecalledContext`. |
| stdlib `datetime` | 3.12 | `SessionSummary.date` parsing + recency math | Already used in `_build_session_summary` and `vault.py` window logic. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-parse session frontmatter with `str.split("---")` | `yaml.safe_load` on the frontmatter block | yaml is already a dep and handles edge cases; but the summary frontmatter is a fixed 3-field shape (`timestamp`, `user_id`, `model`) — a small explicit parser is acceptable and avoids a yaml dep in the hot path. Planner decides; either is fine. |
| Pydantic model for `SessionSummary` | `@dataclass(frozen=True)` | CLAUDE.md + ADR-0003: pure value types are frozen dataclasses; Pydantic only at API boundaries. **Use the dataclass.** |

**Installation:** None. `uv sync` already satisfies all imports.

## Package Legitimacy Audit

**Not applicable — this phase installs zero external packages.** All imports (`numpy`, `pyyaml`, `pytest`, `pytest-asyncio`, stdlib `dataclasses`/`datetime`) are pre-existing project dependencies already present in `pyproject.toml` / `uv.lock`. No registry lookup required; no `[SLOP]`/`[SUS]` risk introduced.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
POST /message
   │
   ├─► MessageProcessor.process(req)
   │       │
   │       ├─► Recall.assemble(req, budget) ───────────────► RecalledContext
   │       │       ├─ _hot_self()            → list[str]   (self/* + ops/reminders.md, NEVER recency-weighted, D-02)
   │       │       ├─ _hot_sessions(user_id) → list[SessionSummary]   ← TYPED (MEM-08)
   │       │       │     └─ vault.get_recent_sessions(user_id, policy=RetentionPolicy)  ← MEM-06, D-07
   │       │       │           └─ window = policy.hot_window_days (was inline today+yesterday, vault.py:288)
   │       │       │           └─ ORDER by recency_weight(SessionSummary.date)  ← MEM-09 place (a), D-03
   │       │       └─ _warm_search(content)  → list[SearchResult]
   │       │             ├─ KeywordRecall.search ─┐
   │       │             ├─ SemanticRecall.search ─┼─► _rrf_merge ─► [recency-weight session-derived results] ─► top_n
   │       │             │     (reads ops/sweeps/  │                  ← MEM-09 place (b), D-03, episodic-only
   │       │             │      embedding-index)   │
   │       │             └─ read bodies for survivors
   │       │
   │       └─ inject recalled.sessions (now SessionSummary → presentation) + recalled.warm
   │
   └─► background: _schedule_chat_note ─► NoteIntake.classify_and_apply(searchable_only=True)
           └─ files note OUTSIDE ops/ (journal/ or topic dir)  ← MEM-07 carrier (already shipped)
                 └─ next sweep embeds it into embedding-index.json
                       └─ future SemanticRecall surfaces it as warm  ← old session recalled, not dropped
```

### Component Responsibilities
| File | Implementation role this phase |
|------|--------------------------------|
| `app/services/recall.py` | Add `SessionSummary`, `RetentionPolicy`, `recency_weight()`. Change `_hot_sessions` to return typed + recency-ordered. Apply recency inside `_warm_search` for session-derived results. `RecalledContext.sessions: list[SessionSummary]`. |
| `app/vault.py` | `Vault` Protocol + `ObsidianVault.get_recent_sessions`: signature → `(user_id, policy)` returning `list[SessionSummary]`; parse frontmatter/body at the adapter edge; window from `policy.hot_window_days` (replaces `vault.py:288-291`). |
| `tests/fakes/vault.py` | `FakeVault.get_recent_sessions` (+ `read_recent_sessions` alias, line 105) → matching typed signature/return. |
| `app/config.py` | Add env-overridable `RetentionPolicy` fields to `Settings` (mirror `sweep_skip_prefixes`). |
| `app/composition.py` | Wire `RetentionPolicy` from `settings` into the `Recall`/`RecallConfig` construction (`composition.py:328-335`). |
| `app/services/message_processing.py` | `message_processing.py:108-110` reads `recalled.sessions` (now typed) → join `.body`/fields instead of raw strings. |
| `app/routes/status.py` | `status.py:55-57` serializes `recalled.sessions` to JSON → serialize `SessionSummary` fields, not raw strings. |

### Pattern 1: Frozen value type mirroring existing `SearchResult` (MEM-08)
**What:** Add `SessionSummary` as a frozen dataclass next to `SearchResult` / `RecallConfig`.
**When to use:** This is the typed boundary ADR-0005 specifies.
```python
# Source: ADR-0005 interface sketch + recall.py:123-148 existing pattern [CITED: docs/adr/0005-typed-session-summary.md]
@dataclass(frozen=True)
class SessionSummary:
    date: str        # "YYYY-MM-DD" from the summary frontmatter `timestamp`/path
    user_id: str
    time: str        # "HH-MM-SS" component (from path or timestamp)
    user_msg: str    # body under "## User"
    sentinel_msg: str  # body under "## Sentinel"
    path: str        # ops/sessions/{date}/{user_id}-{time}.md
    body: str        # full raw markdown (back-compat for any string consumer)

@dataclass(frozen=True)
class RetentionPolicy:
    hot_limit: int = 3        # was RecallConfig.recent_session_limit / vault limit=3
    hot_window_days: int = 2  # was the inline today+yesterday window (vault.py:288-291)
```
**Parser source-of-truth:** the exact frontmatter/body shape to parse is emitted by `MessageProcessor._build_session_summary` (`message_processing.py:189-203`): YAML frontmatter `timestamp` / `user_id` / `model`, then `## User\n\n{msg}\n\n## Sentinel\n\n{msg}`. Keep `body` populated so any not-yet-migrated string consumer still works during the change.

### Pattern 2: Recency-ordered hot sessions (MEM-09 place (a), D-03)
**What:** After fetching the hot session list, sort by recency weight on `SessionSummary.date`.
```python
# _hot_sessions becomes typed + ordered (recall.py:656-660 today)
async def _hot_sessions(self, user_id: str) -> list[SessionSummary]:
    sessions = await self._vault.get_recent_sessions(user_id, policy=self._policy)
    return sorted(sessions, key=lambda s: recency_weight(s.date, now=_now()), reverse=True)
```

### Pattern 3: Pure recency-weight helper + exponential blend (MEM-09, D-01) — RESEARCHER RECOMMENDATION
**What:** A module-level pure function (planner's discretion confirmed this placement is acceptable; keep it unit-testable, no I/O).
**Recommended curve:** exponential decay `w = 0.5 ** (age_days / half_life_days)`, **half-life = 7 days** (matches D-01's suggested default; gives `w≈1.0` today, `0.5` at 7d, `0.25` at 14d — a real boost that never fully zeroes a strongly-relevant old session). This satisfies "recent beats old of equal relevance, but a clearly-relevant old session still surfaces" (CONTEXT specifics) **only if** the weight *multiplies/biases* the existing RRF/relevance score rather than replacing it.
```python
# Source: ADR-0005 + CONTEXT D-01 (exponential decay, half-life ~7d) [ASSUMED: exact constant — planner locks]
def recency_weight(date_str: str, *, now: datetime, half_life_days: float = 7.0) -> float:
    """1.0 for a same-day session, halving every half_life_days. Pure; no I/O."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return 1.0  # unparseable date → no recency penalty (fail-open)
    age_days = max(0.0, (now - d).total_seconds() / 86400.0)
    return 0.5 ** (age_days / half_life_days)
```
**Composition with RRF (place (b), D-03):** in `_warm_search`, after `_rrf_merge`, for **session-derived** results only, multiply the RRF score by `recency_weight(...)` before the final `top_n` sort. The blend keeps a high-RRF old session competitive while letting a same-day session of equal RRF rank above it. **Non-session warm results (topic/journal notes, Self-namespace) are untouched (D-02).** This requires `_warm_search` to know which survivors are session-derived — see Open Question 1.

### Pattern 4: Env-overridable RetentionPolicy (MEM-06, D-04)
**What:** Add fields to `Settings` exactly like `sweep_skip_prefixes` (`config.py:102-117`), then build `RetentionPolicy` from them in `composition.py`.
```python
# config.py Settings (mirror the sweep_skip_prefixes / protected_namespaces idiom)
retention_hot_limit: int = 3          # env: RETENTION_HOT_LIMIT
retention_hot_window_days: int = 2    # env: RETENTION_HOT_WINDOW_DAYS
# composition.py:328 — build the policy and thread it into Recall/RecallConfig
_policy = RetentionPolicy(hot_limit=settings.retention_hot_limit,
                          hot_window_days=settings.retention_hot_window_days)
```

### Anti-Patterns to Avoid
- **Relaxing `exclude_prefixes`/`ops/` to reach old sessions.** Explicitly rejected (D-05, ADR-0005, success criterion 4). The carrier note outside `ops/` is the path. Do not touch `_WARM_TIER_EXCLUDE_PREFIXES` (`recall.py:53`) or `RecallConfig.exclude_prefixes`.
- **Applying recency weight to Self-namespace or authored notes.** Banned by D-02 / MEM-09 / validated boundary. The weight must be gated to episodic session-derived results only.
- **Hard-sorting purely by recency.** D-01 forbids a hard override; it must be a *blend* with relevance.
- **Returning a Pydantic model for `SessionSummary`.** Use a frozen dataclass (CLAUDE.md, ADR-0003).
- **Widening the `get_recent_sessions` reopen beyond its signature.** ADR-0005 + D-07: only this one method changes on the Vault surface. Do not retype `find()` or other Protocol methods.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cosine / vector math for recency-relevance composition | A new similarity fn | `sentinel_shared.similarity.cosine_similarity` (already imported `recall.py:24`) | SPOT — one cosine impl across core + pathfinder. |
| RRF merge | A new ranking fuser | existing `_rrf_merge` (`recall.py:566-597`) | Already validated; recency multiplies its output, does not replace it. |
| Old-session reachability | A new index / new vault path / relaxed exclusion | existing `NoteIntake` carrier + sweeper embed-index + `SemanticRecall` | Whole chain already shipped & verified this session (D-06 gate passes). |
| Frontmatter parse | A regex frontmatter splitter | `yaml.safe_load` (already a dep) on the block, OR a tiny explicit 3-field parser | Fixed known shape; yaml is already present. |
| Embedding index TTL cache | A new cache layer | `SemanticRecall`'s existing TTL cache (`recall.py:357-415`) | Already MEM-05-compliant (zero per-note REST at query time). |

**Key insight:** This phase is *almost entirely a typing + policy-extraction refactor over machinery that already exists.* The single genuinely new logic is the pure `recency_weight` function and its two application sites. Resist the urge to build new retrieval infrastructure.

## Runtime State Inventory

> This phase changes a Vault-method return type (a bounded refactor) and depends on an existing data-flow carrier. The inventory covers both the refactor blast radius and the D-06 carrier verification.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `ops/sessions/{date}/{user_id}-{time}.md` summary notes (written by `_build_session_summary`, `message_processing.py:189-203`). Frontmatter: `timestamp`, `user_id`, `model`; body: `## User` / `## Sentinel`. The new `SessionSummary` parser must read THIS exact shape. **No data migration** — existing summaries already match; the parser reads them as-is. | Code edit only (add parser at Vault edge). No record rewrite. |
| Stored data (carrier) | Conversation notes filed by `NoteIntake` into `journal/{date}/{slug}.md` or topic dirs (`note_intake.py:144-152`) — **outside `ops/`**, and into `inbox/` for unsure/low-confidence content (`note_intake.py:53-69`). | None for journal/topic (embedded). **`inbox/` notes are NOT embedded** (`inbox/` is in `sweep_skip_prefixes`, `config.py:115`) → see Pitfall 1. |
| Live service config | The embedding index `ops/sweeps/embedding-index.json` is regenerated by the sweeper on its own schedule; no manual config. `journal/` reachability depends on the sweeper having run since the carrier note was written. | None — but tests must account for the embed lag (Pitfall 1). |
| OS-registered state | None — no Task Scheduler / launchd / pm2 names reference sessions or retention. Verified: no such registrations in this Python/Docker stack. | None. |
| Secrets/env vars | New env vars `RETENTION_HOT_LIMIT` / `RETENTION_HOT_WINDOW_DAYS` (D-04). These are NEW additive optional vars with code defaults — no existing secret renamed. | Document in `.env` example; defaults preserve current behavior. |
| Build artifacts | None — no egg-info / compiled binary carries a session type. Pure source change; `uv` editable install picks it up. | None. |

**D-06 GATE RESULT — VERIFIED PASS:** carrier note is (a) written on every substantive message (`message.py:48` unconditional `_schedule_chat_note`, gated only by `_CHAT_NOTE_MIN_LENGTH`), (b) filed outside `ops/` with `searchable_only=True` redirecting ops-bound targets to `journal/` (`note_intake.py:79-82`), and (c) embedded because `journal/` and topic dirs are NOT in `sweep_skip_prefixes` (`config.py:102-117`). The one residual gap is `inbox/` (low-confidence content) — see Pitfall 1; per D-06 ("if any link is missing, that gap is in-scope to close") this must be surfaced, not deferred.

## Common Pitfalls

### Pitfall 1: The carrier covers confident notes but NOT inbox'd (low-confidence) content
**What goes wrong:** A substantive message whose classifier confidence `< 0.5` or topic `unsure` is appended to `inbox/_inbox.md` (`note_intake.py:53-69`), and `inbox/` IS in `sweep_skip_prefixes` (`config.py:115`) → it is never embedded → that turn is NOT recoverable via warm recall once it ages out of the hot window. MEM-07 ("sessions older than the hot window are recalled") therefore has a hole for low-confidence turns.
**Why it happens:** `searchable_only=True` only redirects *filed* notes away from `ops/`; it does not redirect the *inbox* branch, which short-circuits before the searchable-path check.
**How to avoid:** Surface this to the planner as an in-scope decision (D-06 mandate). Options: (a) accept the gap and document it (low-confidence turns are intentionally noise-filtered), or (b) ensure inbox content is also reachable. Recommendation: **document and accept** — inbox is deliberate noise quarantine; forcing it into recall would reintroduce the noise the `ops/`/inbox exclusions exist to suppress. But the planner must make this an explicit, recorded call, not a silent omission.
**Warning signs:** A test that writes a low-confidence message, ages it out, and asserts recall — will fail. Write that test to *characterize* the boundary, not to force-close it.

### Pitfall 2: `recalled.sessions` has TWO live consumers that break on the type change
**What goes wrong:** Changing `RecalledContext.sessions` from `list[str]` to `list[SessionSummary]` silently breaks: (1) `message_processing.py:108-110` does `"\n---\n".join(recalled.sessions)` — `join` on dataclasses raises `TypeError`; (2) `status.py:55-57` puts `recalled.sessions` straight into a `JSONResponse` — dataclasses are not JSON-serializable and `len()` still works but the payload is wrong.
**How to avoid:** Update both in lockstep. `message_processing.py` should join `s.body` (or a formatted `s.user_msg`/`s.sentinel_msg`). `status.py` should serialize the `SessionSummary` fields explicitly (like it already does for `warm`: `[{"path": r.path, ...} for r in recalled.sessions]`).
**Warning signs:** `test_status.py` and `test_message.py` paths that read sessions will fail with `TypeError`.

### Pitfall 3: ~25 test mock sites pin the old `list[str]` contract (Test-Rewrite Ban territory)
**What goes wrong:** `test_message.py` (~17 sites), `test_auth.py`, `test_integration_obsidian_llm.py:166` (asserts `get_recent_sessions.assert_called_once_with("test-user-123", limit=3)`), `test_obsidian_vault.py:119-132`, `test_status.py:21`, and `test_recall.py:118-127` all assume `list[str]` and/or the `limit=3` kwarg. `test_integration_obsidian_llm.py:166` will break specifically because the call signature changes from `limit=3` to a `policy=` argument.
**Why it matters:** These protect shipped MEM-01..05 behavior. CONTEXT.md explicitly authorizes **lockstep** updates to the new typed contract (operator-approved this phase) but **forbids weakening assertions or stubbing around the typed contract** (Test-Rewrite Ban). In particular `test_recall.py:126-127` (`any("session body here" in s for s in result.sessions)`) must be *strengthened* to assert on `SessionSummary` fields (e.g. `s.body` / `s.user_msg`), not loosened.
**How to avoid:** For each mock returning `[]`, the empty-list contract is type-agnostic and needs only signature alignment. For mocks returning string content (`test_status.py:21` returns `["session1"]`, `test_integration_obsidian_llm.py:38` returns `[KNOWN_SESSION]`), construct `SessionSummary(...)` values and keep/strengthen the downstream assertion. Update `test_integration_obsidian_llm.py:166` to assert the new `policy=` call shape.

### Pitfall 4: FakeVault must move in lockstep AND keep observable parity (ADR-0002 reopen)
**What goes wrong:** `FakeVault.get_recent_sessions` (`tests/fakes/vault.py:90-101`) and its alias `read_recent_sessions = get_recent_sessions` (line 105) currently return `list[str]`. If only `ObsidianVault` is retyped, `FakeVault`-backed tests (`test_recall.py`) diverge from production-backed tests — exactly the parity the FakeVault docstring promises (lines 1-9).
**How to avoid:** Retype both implementations and the alias together. The FakeVault must parse its in-memory `notes` bodies into `SessionSummary` the same way `ObsidianVault` parses REST responses — keep the user_id substring rule (`f"{user_id}-" in name`) intact.

### Pitfall 5: Recency weight must read `SessionSummary.date`, but warm results are `SearchResult` (no date)
**What goes wrong:** Place (b) of D-03 weights session-derived results inside `_warm_search`, but `_rrf_merge` emits `SearchResult` (path/score/body) with **no date field**. You cannot apply `recency_weight` without recovering the date. The session date is encoded in the path (`ops/sessions/{date}/...`) — but session summaries are `ops/`-excluded from warm search, so the warm-tier session-derived results are actually the **journal/topic carrier notes**, whose date is in their own frontmatter/path, not a `SessionSummary.date`.
**How to avoid:** This is the crux of Open Question 1. The planner must define precisely what "session-derived warm result" means and where its date comes from. The cleanest reading of D-03 + D-05: in the warm tier, the session carrier is a `journal/`/topic note; derive its recency from the note's own date (path `journal/{date}/...` or frontmatter `created`), gated to that namespace, never to Self.

## Code Examples

### Parsing a session summary at the Vault edge (MEM-08)
```python
# Source: shape emitted by message_processing.py:189-203 [CITED: in-repo writer]
def _parse_session_summary(path: str, raw: str) -> SessionSummary:
    # path: ops/sessions/2026-06-11/trekkie-12-00-00.md
    date = path.split("/")[2]                       # "2026-06-11"
    stem = path.rsplit("/", 1)[-1][:-3]             # "trekkie-12-00-00"
    user_id, time = stem.split("-", 1)              # "trekkie", "12-00-00"
    fm, _, body = raw.partition("---\n")[2].partition("\n---")
    user_msg = body.split("## User", 1)[-1].split("## Sentinel", 1)[0].strip()
    sentinel_msg = body.split("## Sentinel", 1)[-1].strip()
    return SessionSummary(date=date, user_id=user_id, time=time,
                          user_msg=user_msg, sentinel_msg=sentinel_msg,
                          path=path, body=raw)
```
*(Illustrative — planner finalizes parser robustness; the writer at `message_processing.py:189-203` is the contract.)*

### Recency-blended ordering of typed sessions (MEM-09 place a)
```python
sorted(sessions, key=lambda s: recency_weight(s.date, now=datetime.now(timezone.utc)), reverse=True)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sessions as raw `list[str]`, parsed at call sites | Typed `SessionSummary` value | This phase (ADR-0005) | Ends frontmatter string-parsing; enables recency merge. |
| Inline `limit=3` + today+yesterday window | `RetentionPolicy(hot_limit, hot_window_days)`, env-overridable | This phase (MEM-06) | "Three" becomes a tunable knob. |
| Sessions dropped at the hot-window cliff | Older sessions recalled via journal carrier + semantic index | Carrier shipped earlier (debug fix + Phase 40); this phase verifies/tests it | Closes "forgets after three." |
| RRF merge ranks by relevance only | RRF + episodic recency blend | This phase (MEM-09) | Recent sessions rank above equally-relevant older ones. |

**Deprecated/outdated:** `RecallConfig.recent_session_limit` (`recall.py:172`) is superseded by `RetentionPolicy.hot_limit`. Planner decides whether to remove it or alias it during transition (prefer remove to avoid two sources of truth, but check no test pins it — `test_recall.py:355,381` construct `RecallConfig()` with other fields).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Exponential half-life = 7 days is the right default decay constant | Pattern 3 | Wrong curve → recency over/under-weights; LOW risk — D-01 hands this to the planner to lock, and it is UAT-tunable. |
| A2 | A frozen dataclass (not Pydantic) is correct for `SessionSummary` | Pattern 1 | None — confirmed by CLAUDE.md + ADR-0003 (HIGH); listed as assumption only because it is a design choice. |
| A3 | `inbox/` low-confidence content should be left unembedded (accept the MEM-07 gap) | Pitfall 1 | If operator wants total recall, this under-delivers MEM-07 for low-confidence turns. Planner MUST make this an explicit recorded decision (D-06). |
| A4 | The "session-derived warm result" in place (b) is the journal/topic carrier note, dated from its own path/frontmatter | Pitfall 5 / OQ1 | If the intended carrier is something else, the warm-tier recency wiring is wrong. Planner must lock the definition. |

## Open Questions

1. **What exactly is a "session-derived warm result," and where does its date come from? (place (b) of D-03)**
   - What we know: `_rrf_merge` emits `SearchResult` (no date); `ops/sessions/` summaries are warm-excluded; the warm carrier for old sessions is the journal/topic note (D-05).
   - What's unclear: whether place (b) weights *only journal/topic carrier notes* (dated from their own path/frontmatter) or attempts to map warm results back to `SessionSummary.date`. The latter is impossible for carrier notes (they aren't `SessionSummary`s).
   - Recommendation: planner defines place (b) as "apply `recency_weight` to warm results whose path is in the conversation-carrier namespace (`journal/` + topic dirs), using the note's own date; never to Self." This honors D-02/D-03/D-05 consistently.

2. **Keep or remove `RecallConfig.recent_session_limit`?**
   - What we know: it is the old name for `hot_limit`; constructed by `RecallConfig()` in tests (`test_recall.py:355,381`) but not by name there.
   - Recommendation: remove it and move the limit into `RetentionPolicy` to avoid two sources of truth; verify no test passes `recent_session_limit=` by name (grep shows none do).

3. **Does the `RetentionPolicy` thread through `RecallConfig`, or sit beside it as a separate injected object?**
   - What we know: `RecallConfig` already holds `recent_session_limit`; ADR-0005 sketches `get_recent_sessions(user_id, policy)` taking the policy directly.
   - Recommendation: a separate `RetentionPolicy` injected into `Recall` (composition root), passed to `get_recent_sessions`, mirroring how `RecallConfig` is injected — keeps retention policy a distinct, testable value (ADR-0005 intent). Planner's discretion.

## Environment Availability

> All work is in-repo Python; the only external runtime dependencies are the existing ones already validated in prior phases.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Sentinel Core | ✓ (assumed per prior phases) | 3.12 | — |
| numpy | recency/cosine math | ✓ (imported `recall.py:21`) | installed | — |
| pyyaml | frontmatter parse | ✓ (imported `note_intake.py:13`) | installed | tiny explicit parser |
| pytest + pytest-asyncio | tests | ✓ (`pyproject.toml:25-26`) | >=8.0 / >=0.23 | — |
| Obsidian REST API | live `get_recent_sessions` at runtime | not needed for unit tests (FakeVault) | — | FakeVault covers all unit/integration test paths |
| LM Studio embeddings | live SemanticRecall warm path | not needed for unit tests (FakeVault/stub) | — | tests stub `embed_fn` |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** Obsidian/LM Studio are runtime-only; all phase tests run against `FakeVault` and stubbed `embed_fn`, so no live service is required to validate this phase.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8 + pytest-asyncio (`asyncio_mode="auto"`) |
| Config file | `sentinel-core/pyproject.toml` (`[tool.pytest.ini_options]`, line 29-31) |
| Quick run command | `cd sentinel-core && uv run pytest tests/test_recall.py -x -q` |
| Full suite command | `cd sentinel-core && uv run pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MEM-06 | Changing `RetentionPolicy.hot_window_days`/`hot_limit` changes the window | unit | `uv run pytest tests/test_recall.py -k retention -x` | ❌ Wave 0 |
| MEM-06 | Env vars `RETENTION_HOT_*` override defaults | unit | `uv run pytest tests/test_config.py -k retention -x` | ❌ Wave 0 |
| MEM-07 | A session older than the hot window is reachable via `RecalledContext.warm` (journal carrier) | integration | `uv run pytest tests/test_recall.py -k old_session_warm -x` | ❌ Wave 0 |
| MEM-07 | `ops/` exclusion NOT relaxed (criterion 4) | unit | `uv run pytest tests/test_recall.py::test_warm_excludes_self_and_ops_prefixes -x` | ✅ (exists, line 142 — keep green) |
| MEM-08 | `get_recent_sessions` returns `list[SessionSummary]` with parsed fields | unit | `uv run pytest tests/test_obsidian_vault.py -k session_summary -x` | ❌ Wave 0 (existing line 119 must be updated, not skipped) |
| MEM-08 | `RecalledContext.sessions` carries typed values; consumers read fields | unit | `uv run pytest tests/test_recall.py::test_assemble_returns_sessions -x` | ⚠️ exists (line 118) — STRENGTHEN to assert `SessionSummary` fields |
| MEM-09 | More-recent session ranks above older of equal relevance (hot ordering) | unit | `uv run pytest tests/test_recall.py -k recency_order -x` | ❌ Wave 0 |
| MEM-09 | Recency weight applied in warm RRF merge for carrier notes only | unit | `uv run pytest tests/test_recall.py -k recency_warm -x` | ❌ Wave 0 |
| MEM-09 | Recency weight NEVER applied to Self-namespace / authored notes (D-02) | unit | `uv run pytest tests/test_recall.py -k recency_excludes_self -x` | ❌ Wave 0 |
| MEM-09 | `recency_weight()` pure-function curve (today=1.0, 7d=0.5) | unit | `uv run pytest tests/test_recall.py -k recency_weight_curve -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd sentinel-core && uv run pytest tests/test_recall.py -x -q`
- **Per wave merge:** `cd sentinel-core && uv run pytest tests/test_recall.py tests/test_message.py tests/test_obsidian_vault.py tests/test_status.py tests/test_config.py -q`
- **Phase gate:** `cd sentinel-core && uv run pytest -q` green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_recall.py` — new cases: retention window tunability, old-session-warm reachability, recency hot ordering, recency warm-merge (carrier-only), recency-excludes-self, `recency_weight` curve.
- [ ] `tests/test_config.py` — `RETENTION_HOT_*` env-override cases (check whether a `test_config.py` exists; if not, add it).
- [ ] `tests/test_obsidian_vault.py` — update `test_get_recent_sessions_returns_list` (line 119) to the typed contract; add a frontmatter-parse case.
- [ ] Lockstep updates (NOT new files): `test_message.py` (~17 mock sites), `test_auth.py`, `test_integration_obsidian_llm.py` (lines 38, 166, 196), `test_status.py` (line 21), `tests/fakes/vault.py` typed return.
- [ ] No framework install needed — pytest/pytest-asyncio already present.

## Security Domain

> `security_enforcement` is enabled (no `false` in config). This phase is an internal data-typing refactor with no new external input surface, auth, or crypto.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | `X-Sentinel-Key` shared-secret auth is unchanged; no auth code touched. |
| V3 Session Management | no | "Session" here is a vault note, not an auth session; no web session state. |
| V4 Access Control | no | No new endpoints or capability surface (the `get_recent_sessions` change is internal). |
| V5 Input Validation | yes | The new `SessionSummary` parser consumes vault-stored markdown. Parse defensively: tolerate missing frontmatter fields, malformed dates (`recency_weight` already fails open), and odd path shapes — never raise into the recall path (recall already wraps tiers in `return_exceptions=True`). |
| V6 Cryptography | no | No crypto introduced. |

### Known Threat Patterns for Python/async recall
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed/hostile session frontmatter crashing recall | Denial of Service | Defensive parse with fail-open defaults; `assemble` already coerces tier exceptions to `[]` (`recall.py:748-764`). Keep the new parser inside that envelope. |
| Prompt injection via recalled session body | Tampering | Unchanged — injected context still passes through `injection_filter.wrap_context()` in `MessageProcessor` (`message_processing.py:115,123`). This phase does not bypass that boundary; ensure typed sessions still flow through `wrap_context`. |
| Embedding-index entry tampering (oversized b64) | DoS | Already mitigated in `SemanticRecall` (`recall.py:478,507`); this phase doesn't change that path. |

## Sources

### Primary (HIGH confidence — read directly this session)
- `docs/adr/0005-typed-session-summary.md` — locked phase design (SessionSummary fields, RetentionPolicy defaults, carrier resolution, rejected alternatives).
- `docs/adr/0002-vault-seam-location.md` — Vault Protocol location; bounded-reopen authority.
- `docs/adr/0003-recall-module.md` — Recall owns retention policy + value types; sessions deferred-typing note.
- `docs/adr/0004-semantic-recall.md` — RRF merge, RetrievalStrategy seam, sidecar embedding index (MEM-05).
- `sentinel-core/app/services/recall.py` (770 lines) — `SearchResult`/`RecallConfig`/`RecalledContext`, `_rrf_merge`, `_warm_search`, `_hot_sessions`, `SemanticRecall`.
- `sentinel-core/app/vault.py:115-156, 278-349` — Vault Protocol + `get_recent_sessions` + inline window.
- `sentinel-core/tests/fakes/vault.py` — FakeVault parity contract.
- `sentinel-core/app/services/message_processing.py:108-110, 165-203` — `recalled.sessions` consumer + `_build_session_summary` writer (parser contract).
- `sentinel-core/app/routes/message.py:40-94` + `app/services/note_intake.py` — D-06 carrier chain.
- `sentinel-core/app/config.py:95-140` — `sweep_skip_prefixes` / `protected_namespaces` env pattern; `journal/` NOT skipped.
- `sentinel-core/app/services/vault_sweeper.py` (grepped) — skip prefixes, `EMBEDDING_INDEX_PATH`, embed scope.
- `sentinel-core/app/routes/status.py:40-59` — second `recalled.sessions` consumer.
- `shared/sentinel_shared/similarity.py` — `cosine_similarity` signature (don't-hand-roll).
- `.planning/REQUIREMENTS.md:89-92` — MEM-06..09 exact wording.
- `sentinel-core/tests/test_recall.py`, `test_message.py`, `test_integration_obsidian_llm.py`, `test_obsidian_vault.py`, `test_status.py` (grepped) — blast-radius mock sites.

### Secondary / Tertiary
- None required — the entire domain is in-repo. No web/CITED sources beyond the project's own ADRs/code.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; every import already present and read.
- Architecture: HIGH — all four ADRs + the full code path read directly; blast radius enumerated by grep + read.
- Pitfalls: HIGH — each pitfall is grounded in a specific read line/test site.
- Recency constant (A1): LOW — by design handed to the planner (D-01).

**Research date:** 2026-06-12
**Valid until:** 2026-07-12 (stable internal domain; re-verify only if `recall.py`/`vault.py`/`note_intake.py` or `sweep_skip_prefixes` change before planning).
