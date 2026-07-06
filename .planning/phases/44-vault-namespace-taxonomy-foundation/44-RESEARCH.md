# Phase 44: Vault Namespace + Taxonomy Foundation - Research

**Researched:** 2026-07-06
**Domain:** Sentinel Core vault taxonomy routing, recall recency-weighting, vault-sweeper move-planning (Python/FastAPI, REST-only Obsidian vault)
**Confidence:** HIGH — every finding below is grounded in a direct read of the live `sentinel-core` source and its test suite this session (all line numbers verified, not carried over from prior research documents). The design itself (WHAT to build) is LOCKED in `44-CONTEXT.md`; this document is scoped to HOW to build it safely, per the task boundary.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Carrier-allowlist / recency-weighting (VAULT-03, Pitfall 2)**
- **D-01 (Sessions-only collapse):** Retire `_CARRIER_NAMESPACE_PREFIXES` entirely. After migration every path it weighted is gone. Recency weighting applies **only to episodic Session summaries** — the pure MEM-09 end state. The warm-tier recency block in `recall.py` (~L795) becomes a no-op and is **removed, not repointed to dead paths**.
- **D-01a:** Preserve the T-41-08 principle in spirit — recency weighting must never apply to a namespace by omission/negation. With the allowlist gone, the invariant is "only typed Session summaries are recency-weighted," asserted by a regression test.

**inbox/ sweeper + embedding (VAULT-04, Pitfall 3)**
- **D-02 (Sweeper embeds inbox/, recall keeps it out of the keyword tier):** Remove `inbox/` from `SWEEP_SKIP_PREFIXES` (and `settings.sweep_skip_prefixes`) so staged captures get embedded. Keep `inbox/` in `RecallConfig.exclude_prefixes` so raw, pre-Reduce captures stay out of the keyword warm tier until Reduce (Phase 46) promotes them to `notes/`. Accepted trade-off: up to one sweep-cycle of latency before a fresh capture is embedded.
- **D-02a:** `VAULT-04` wording corrected in `REQUIREMENTS.md` this session to match ROADMAP SC-4 (sweeper embeds inbox/, does not skip it).

**PARA reroute table (VAULT-02)**
- **D-03 (Adopt ARCHITECTURE "AFTER" table verbatim):** `learning`, `reference` → `inbox/` (queued); `journal` → `ops/journal/{YYYY-MM-DD}/`; `accomplishment` → `ops/accomplishments/`; `observation` → `ops/observations/` (unchanged); `noise` → `""` (unchanged); `unsure` → `inbox/_pending-classification.md` (unchanged).
- **D-03a:** Classifier keeps its closed 7-slug vocabulary. Only `TOPIC_VAULT_PATH` routing changes.
- **D-03b (single source of truth — kills the Pitfall 2 root cause):** `TOPIC_VAULT_PATH` (or a routing helper derived from it) becomes the **one** module `recall.py`'s carrier/namespace logic imports, instead of a duplicated hand-maintained mirror.
- **D-03c (consequence, intended):** Moving `journal`/`accomplishment` under `ops/` removes them from warm recall entirely — deliberate, consistent with ops/=operational.

**self/ stubs + session-start read (VAULT-01, VAULT-05)**
- **D-04 (Lazy seeded-template stubs, D-14 pattern):** Auto-create `self/identity.md`, `self/methodology.md`, `self/goals.md`, `self/relationships.md` as minimal guiding stubs on first startup read when missing. REST-only lazy-create convention — no eager boot-time vault writes.
- **D-04a (VAULT-05 is ~90% already done):** `RecallConfig.self_paths` already reads all four `self/` files (+ 2 more) into every message today. Do NOT rebuild the self-read. The real delta is guaranteeing the four canonical files exist.

**Migration-window behavior (44→47)**
- **D-05 (Accept the transient, document it):** Existing top-level `journal/`, `accomplishments/`, `learning/`, `references/` notes are NOT physically migrated in Phase 44. They remain warm-recallable but lose recency weighting immediately — accepted, recorded in the MIG-03 regression ledger as a known, accepted behavior change. No throwaway compat shim.

### Claude's Discretion
- Exact home/name of the shared taxonomy module for D-03b (`note_classifier.py` is the natural home; `recall.py` imports from it).
- Exact stub content wording for D-04 — keep token-bounded (read every message).
- `PROTECTED_NAMESPACES += "templates/"` — include if it doesn't destabilize the suite; low-risk additive guard. **Verified safe this session** (see Code Seams Confirmed).

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope. `_schema`/wikilinks (Phase 45), 6 Rs pipeline orchestration (Phase 46), flat-7 backfill/migration (Phase 47) were all correctly routed out.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VAULT-01 | Three-space arscontexta structure with stub auto-creation | D-14 lazy-create pattern confirmed reusable from `note_intake.py`/`inbox.py` (see Code Examples). No dedicated "ensure-exists" primitive exists yet — must be written new, following the established read-then-conditionally-write shape. |
| VAULT-02 | PARA taxonomy supersedes flat-7 routing | `TOPIC_VAULT_PATH` (note_classifier.py:57-65) is the single edit point for the dict — but **two hardcoded string-literal call sites** (`topic_dir_for`'s journal special-case and `note_intake._topic_target_path`'s journal special-case) do NOT derive from the dict value and must be edited separately (see Common Pitfalls #1 — CRITICAL). |
| VAULT-03 | Recency-weighting recognizes new namespaces | `_CARRIER_NAMESPACE_PREFIXES` (recall.py:67-72) and the reweighting block (recall.py:795-819) confirmed at the cited locations; removal turns 3 existing tests non-representative (see Regression Test Surface). |
| VAULT-04 | Sweeper embeds inbox/, excludes it from keyword warm tier | `SWEEP_SKIP_PREFIXES` (vault_sweeper.py:69-75) and `settings.sweep_skip_prefixes` (config.py:137-152) both list `inbox/` and must both drop it. `RecallConfig.exclude_prefixes` (recall.py:247) already includes `inbox/` — no change needed there. `rebuild_embedding_index` (the every-boot startup path, vault_sweeper.py:282-385) ALSO consults the same skip-prefix set, so it too starts walking inbox/ on next boot (bounded — see Execution-Ordering Hazards #3). |
| VAULT-05 | Every message reads self/ files at session start | `RecallConfig.self_paths` (recall.py:262-270) already reads all 4 canonical files + 2 extras in parallel via `read_self_context`, which graceful-skips 404 silently. Confirmed: NO existing auto-create-on-miss behavior exists for these paths today — D-04's stub creation is genuinely new code, not a rebuild. |

</phase_requirements>

## Summary

This phase is a pure refactor of existing, already-shipped Python modules (`recall.py`, `vault_sweeper.py`, `vault_sweep_plan.py`, `note_classifier.py`, `config.py`, `vault.py`) — no new libraries, no new external dependencies, no new packages to vet. All five confirmed code seams from `44-CONTEXT.md` match the live source exactly (line numbers verified this session, see table below). The design is sound and the CONTEXT.md decisions are directly implementable.

However, direct tracing of the actual function bodies this session surfaced **three concrete, non-obvious implementation hazards that no prior research document identified**, because they only appear when you trace what the *code does*, not what the *routing table says*:

1. **A silent no-op bug waiting to happen:** both `note_classifier.topic_dir_for()` and `note_intake.NoteIntake._topic_target_path()` hardcode the literal string `f"journal/{today}"` / `f"journal/{today}/{slug}.md"` for the `journal` topic — they do **not** derive this path from `TOPIC_VAULT_PATH["journal"]`'s actual value. Editing the dict entry alone (`"journal": "journal"` → `"journal": "ops/journal"`) has **zero effect** on the journal topic's computed path unless these two f-string literals are also updated. There is currently **no test anywhere in the suite** that exercises either function's return value for topic="journal", so this would ship silently broken and undetected by CI.
2. **A latent path-matching bug in the sweeper's misplaced-note detector:** `vault_sweep_plan.is_in_topic_dir()` derives a "family root" by taking only the first `/`-segment of the topic directory. Under the OLD taxonomy this was safe (`journal/`, `learning/`, `accomplishments/`, `references/` were each uniquely-named top-level dirs). Under the NEW taxonomy, `journal`, `accomplishment`, and `observation` all resolve to `ops/{something}` — so the family-root check collapses to `"ops/"` for all three, and the sweeper will falsely believe a note already living in `ops/observations/` is "already in the right topic family" for a `journal`-classified note (and vice versa), silently defeating misplaced-note relocation for these three topics.
3. **A pre-existing "guarantee" that the taxonomy change now structurally breaks:** `message.py`'s background chat-note auto-filer (`_safe_file_chat_note`, `searchable_only=True`) exists specifically to guarantee that auto-classified chat content lands somewhere warm-tier-searchable, redirecting to a `journal` path if the classified destination is excluded. After D-03, **every one of the 7 classifier topics now resolves to an ops/- or inbox/-prefixed (i.e., excluded) destination** — including the `journal` redirect target itself. The safety net's fallback target is now also excluded, so the guarantee this code exists to provide can no longer be met by any redirect. One existing test (`test_chat_note_path_passes_warm_tier_exclusion_filter`) will keep **passing** while asserting something that becomes false in practice, because it checks against a stale duplicate list (`_WARM_TIER_EXCLUDE_PREFIXES`, recall.py:51) that doesn't yet include `inbox/`.

None of these three are blocking objections to the locked design — they are implementation details the plan must explicitly account for so the phase doesn't ship a silent regression exactly the type Pitfall 1/2 were named to prevent.

**Primary recommendation:** Implement D-01 through D-05 exactly as locked, but add three explicit repair items to the plan: (a) fix the two hardcoded `journal/` literals alongside the `TOPIC_VAULT_PATH` dict edit, in the same task/commit; (b) fix `is_in_topic_dir`'s family-root derivation to not collapse distinct `ops/`-nested topics into one family; (c) explicitly decide and document what happens to `_safe_file_chat_note`'s `searchable_only` guarantee now that no redirect target survives the taxonomy change (recommend: accept the same latency trade-off D-02 already accepts for `:capture`/`:seed`, retire the now-futile redirect-to-journal special case, and update the two affected tests in `test_message.py` to assert the new accepted behavior rather than silently keep asserting a stale, non-representative precondition).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Taxonomy routing table (`TOPIC_VAULT_PATH`) | API / Backend (`note_classifier.py`) | — | Pure routing decision, no I/O; single source of truth per D-03b |
| Recency-weighting policy | API / Backend (`recall.py`) | — | Consumes the routing table; must import, never re-derive |
| Sweeper move-planning | API / Backend (`vault_sweep_plan.py`) | — | Consumes `topic_dir_for()`; already imports it live (confirmed) |
| Vault persistence / stub creation | API / Backend (`vault.py` Vault seam) | Database / Storage (Obsidian REST vault) | REST-only; no local filesystem; PUT-creates-if-missing is the underlying primitive |
| Protected-path guard | API / Backend (`vault.py` `PROTECTED_NAMESPACES`) | — | Governs physical move/trash eligibility, independent of sweep-processing eligibility |
| Self-context injection | API / Backend (`recall.py` `RecallConfig.self_paths`) | — | Already wired; VAULT-05's only delta is guaranteeing file existence upstream |

## Code Seams Confirmed

All five citations from `44-CONTEXT.md`'s canonical-refs section were re-verified against the live source this session. All match exactly:

| File | Symbol | Cited line | Verified line | Status |
|------|--------|-----------|----------------|--------|
| `sentinel-core/app/services/recall.py` | `_CARRIER_NAMESPACE_PREFIXES` | ~L67 | L67-72 | MATCH |
| `sentinel-core/app/services/recall.py` | warm-tier recency block | ~L795 | L795-819 (the `if r.path.startswith(_CARRIER_NAMESPACE_PREFIXES):` gate is at L809) | MATCH |
| `sentinel-core/app/services/recall.py` | `RecallConfig.exclude_prefixes` | L247 | L247 | MATCH — already includes `inbox/` |
| `sentinel-core/app/services/recall.py` | `RecallConfig.self_paths` | L264-269 | L262-270 | MATCH |
| `sentinel-core/app/services/vault_sweeper.py` | `SWEEP_SKIP_PREFIXES` | L69 | L69-75 | MATCH — currently includes `inbox/` (to remove) |
| `sentinel-core/app/services/vault_sweeper.py` | `_active_skip_prefixes()` | L83 | L83-92 | MATCH |
| `sentinel-core/app/services/vault_sweeper.py` | `EMBEDDING_INDEX_PATH` | — | imported L24, re-exported L51 | MATCH |
| `sentinel-core/app/services/note_classifier.py` | `TOPIC_VAULT_PATH` | L57 | L57-65 | MATCH |
| `sentinel-core/app/services/note_classifier.py` | `topic_dir_for()` | L68 | L68-91 | MATCH — **but see Common Pitfall #1: journal branch ignores the dict value** |
| `sentinel-core/app/config.py` | `sweep_skip_prefixes` | L137-152 | L137-152 | MATCH — currently includes `inbox/` (to remove); also confirms `templates/` already present (L145) |
| `sentinel-core/app/vault.py` | `PROTECTED_NAMESPACES` | L56 | L56-60 | MATCH — currently `("sentinel/", "self/", "security/")`; `templates/` NOT yet present |

**Additional seams discovered this session, not cited in CONTEXT.md but directly in the phase's blast radius:**

| File | Symbol | Why it matters |
|------|--------|-----------------|
| `sentinel-core/app/services/vault_sweep_plan.py` | `is_in_topic_dir()` (L27-38), `propose_topic_move()` (L41-53) | `propose_topic_move` **already** imports `topic_dir_for` from `note_classifier.py` at call time (L45) — D-03b's single-source-of-truth is **already partially wired** for the sweeper (just not for `recall.py`). But `is_in_topic_dir`'s family-root logic breaks under the new shared-`ops/`-prefix shape (Common Pitfall #2). |
| `sentinel-core/app/services/note_intake.py` | `_topic_target_path()` (L144-152), `_WARM_TIER_EXCLUDE_PREFIXES` import (L24), `classify_and_apply()`'s `searchable_only` guard (L79-82) | Already imports `TOPIC_VAULT_PATH` directly (L23) — the explicit `:note`/chat-filing path is **already** derived from the same dict (good), but has its own hardcoded journal literal (Common Pitfall #1) and consumes the stale `_WARM_TIER_EXCLUDE_PREFIXES` tuple (Common Pitfall #3). |
| `sentinel-core/app/services/recall.py` | `_WARM_TIER_EXCLUDE_PREFIXES` (L51) | A **second**, older, narrower duplicate of `RecallConfig.exclude_prefixes` (`("ops/", "_trash/", "self/")` — missing `inbox/`). Re-exported by `message_processing.py` (L220) and consumed by `note_intake.py` and two tests in `test_message.py`. This is a second instance of exactly the dual-source-of-truth pattern Pitfall 2 warns about, in a location CONTEXT.md does not mention. |
| `sentinel-core/app/routes/message.py` | `_safe_file_chat_note()` (L82-93), `_queue_chat_note_write()` (L60-79) | The production call site that makes every substantive chat message flow through `NoteIntake.classify_and_apply(searchable_only=True)` — this is where Common Pitfall #3's consequence actually manifests in production traffic, not just in `:note`/`:capture` commands. |

## Execution-Ordering Hazards

The phase's own constraint (fix the trap in the same commit that creates the hazard, no red window) requires a specific edit order within the plan. Below are the concrete "what breaks if X lands before Y" answers the task asked for.

### 1. `note_classifier.TOPIC_VAULT_PATH` change vs. `recall.py`'s carrier logic repoint (D-03b)

**Safe order:** These must land in the **same task/commit**, not sequential waves. If the dict is edited first without touching `recall.py`, nothing breaks technically (the old `_CARRIER_NAMESPACE_PREFIXES` tuple is a hardcoded literal, independent of the dict, so it silently continues weighting the now-dead `learning/`, `accomplishments/`, `references/`, `journal/` prefixes — which is exactly Pitfall 2's failure mode: no crash, no test failure, just silently-wrong behavior for however long the gap lasts). If `recall.py` is fixed first (allowlist emptied/removed) while the dict still points learning/reference at their old top-level dirs, existing already-filed content simply loses recency weighting a few minutes early — harmless, but backwards from the intended sequencing. **Recommendation: one task does both edits together**, with the new shared-source-of-truth import wired in the same diff, verified by a single test run.

### 2. `inbox/` removed from `SWEEP_SKIP_PREFIXES` (D-02) — sidecar/embedding consequences

Two independent background/on-demand paths both consult `_active_skip_prefixes()`:
- `run_sweep()` (admin-triggered or scheduled `:vault-sweep`) — walks the vault, classifies, and would now walk into `inbox/`.
- `rebuild_embedding_index()` (the **every-boot** startup path, confirmed at vault_sweeper.py:282-385, wired via `composition.initialize_startup`'s `_startup_rebuild` task per its own docstring) — this ALSO reuses `walk_vault()`, which ALSO consults `_active_skip_prefixes()`. Once `inbox/` drops out of the skip set, **the very next container restart** will walk into `inbox/` and embed whatever is there — not just the next manual sweep.

**Is this safe/bounded?** Yes, with one caveat. Today `inbox/` contains essentially one file (`inbox/_pending-classification.md`, the merged "unsure" queue). Going forward, individual `learning`/`reference` captures will file as one-file-per-note (`inbox/{slug}-{date}.md` via `_topic_target_path`), so the directory grows at the same linear, bounded, per-note rate any other topic directory already does — not an unbounded backfill, since D-05 explicitly does NOT migrate old top-level `learning/`/`references/` content into `inbox/` in this phase. The one caveat: `rebuild_embedding_index` does **not** call the classifier (its docstring: "without ever calling the classifier, relocating notes... or de-duplicating" — only `run_sweep` classifies+relocates). So the startup path is embed-only and cannot trigger topic-move proposals; only a manual/scheduled `run_sweep` (which does classify) can trigger the topic-move hazard described next.

**A related, sharper risk not mentioned in CONTEXT.md:** the merged `inbox/_pending-classification.md` file will now get **re-classified whole** by `run_sweep` (since `_should_skip` only special-cases same-pass reprocessing, not "this file was swept last week" — confirmed at vault_sweeper.py:158-168; the real idempotency mechanism is `is_in_topic_dir` returning true once a note already lives in its target family). If the LLM classifies this multi-entry catch-all file's combined text as, say, `journal` (plausible — it's a mixed bag of user content), `plan_topic_move` would propose relocating the **entire pending-classification queue file** into `ops/journal/{date}/_pending-classification.md`. This happens to be a no-op in practice today only because the file already lives under `inbox/` and `learning`/`reference`'s new topic dir IS `inbox/` (so `is_in_topic_dir` correctly reports "already home" for those two topics specifically) — but for `journal`/`accomplishment`/`observation` classifications of that same merged file, there is no such protection. **Recommend an explicit test:** the sweeper must never propose a topic-move for `INBOX_PATH` (`inbox/_pending-classification.md`) itself, regardless of what topic the classifier assigns to its combined content.

### 3. Vault-sweep-plan family-root collapse (new finding, see Common Pitfall #2 below) directly affects ordering too

Because `is_in_topic_dir`'s bug makes `journal`/`accomplishment`/`observation` misplaced-note detection cross-contaminate, this fix must land in the **same task** as the `TOPIC_VAULT_PATH` dict edit — otherwise the dict change ships with a sweeper that silently stops correctly relocating misfiled ops-bound notes, which is itself a quiet new regression in exactly the class this phase exists to prevent.

## Standard Stack

No new external packages are introduced by this phase — it is a pure internal refactor of existing `sentinel-core` Python modules using only libraries already in `pyproject.toml` (stdlib `dataclasses`, `datetime`, `typing`; already-vendored `pydantic`, `yaml`; the project's own `sentinel_shared` package). No `npm view` / `pip index versions` verification is applicable.

## Package Legitimacy Audit

Not applicable — this phase installs no new packages. No `gsd-tools query package-legitimacy check` run was needed; skipping per the "Required whenever this phase installs external packages" gate condition (it does not).

## Architecture Patterns

### System Architecture Diagram — data flow through the taxonomy/recall/sweep seam this phase touches

```
                 ┌──────────────────────────────────────────────┐
                 │  note_classifier.py                          │
                 │  TOPIC_VAULT_PATH (dict)  ◄── SINGLE SOURCE   │
                 │  topic_dir_for(topic, today) ── OF TRUTH      │
                 └───────┬───────────────────┬───────────────────┘
                         │ import            │ import (NEW, D-03b)
                         ▼                    ▼
        ┌────────────────────────┐   ┌──────────────────────────┐
        │ vault_sweep_plan.py     │   │ recall.py                 │
        │ propose_topic_move()   │   │ carrier-namespace check    │
        │ is_in_topic_dir()      │   │ (recency-weight gate,      │
        │  ⚠ family-root bug     │   │  now derived — not a       │
        │  under shared ops/     │   │  hardcoded 2nd tuple)      │
        └───────────┬─────────────┘   └──────────┬────────────────┘
                    │ used by                     │ used inside
                    ▼                              ▼
        ┌────────────────────────┐   ┌──────────────────────────┐
        │ vault_sweeper.run_sweep│   │ Recall.assemble()          │
        │  walk → classify →     │   │  keyword+semantic RRF →    │
        │  plan_topic_move →     │   │  (no-op recency block,     │
        │  relocate (or dry-run) │   │   since carrier set = {})  │
        └───────────┬─────────────┘   └──────────┬────────────────┘
                    │                              │
                    ▼                              ▼
        ┌───────────────────────────────────────────────────────┐
        │            Vault Protocol (app/vault.py)                │
        │  PROTECTED_NAMESPACES (physical-move guard, += templates/)│
        │  read_note/write_note (REST PUT = lazy-create primitive) │
        └───────────────────────────────────────────────────────┘

  note_intake.py (chat + explicit :note path) also imports TOPIC_VAULT_PATH
  directly (existing, pre-Phase-44 wiring) → _topic_target_path()
  ⚠ journal branch is a 2nd hardcoded literal, same bug class as topic_dir_for()
```

### Recommended Project Structure

No new files. All work is edits to the five existing modules plus their test files:

```
sentinel-core/app/
├── services/
│   ├── note_classifier.py      # EDIT: TOPIC_VAULT_PATH values + topic_dir_for() journal literal
│   ├── vault_sweep_plan.py     # EDIT: is_in_topic_dir() family-root fix
│   ├── vault_sweeper.py        # EDIT: SWEEP_SKIP_PREFIXES drops inbox/
│   ├── note_intake.py          # EDIT: _topic_target_path() journal literal; searchable_only guard decision
│   ├── recall.py               # EDIT: remove _CARRIER_NAMESPACE_PREFIXES + reweighting block + _path_date();
│   │                           #       reconcile _WARM_TIER_EXCLUDE_PREFIXES; add self/ stub-ensure helper
│   └── inbox.py                # REFERENCE ONLY: build_initial_inbox() is the stub-builder pattern to mirror
├── config.py                   # EDIT: sweep_skip_prefixes drops inbox/
└── vault.py                    # EDIT: PROTECTED_NAMESPACES += "templates/" (verified safe)

sentinel-core/tests/
├── test_recall.py              # EDIT (3 tests) + ADD (1 new invariant test) — see Regression Test Surface
├── test_vault_sweep_plan.py    # EDIT (2 tests) + ADD (family-root regression test)
├── test_vault_sweeper.py       # EDIT (2 tests: SWEEP_SKIP_PREFIXES constant, inbox _should_skip)
├── test_note_classifier.py     # UNCHANGED — asserts vocabulary labels, not paths (verified, not path-affected)
├── test_message.py             # EDIT (2 tests) — searchable_only guarantee no longer holds as stated
└── test_obsidian_vault.py      # UNCHANGED (PROTECTED_NAMESPACES tests are dynamic/tolerant of additions)
```

### Pattern 1: Single source of truth via import, not value duplication (D-03b)

**What:** `recall.py` must `from app.services.note_classifier import TOPIC_VAULT_PATH` (or a small derived helper, e.g. `CARRIER_TOPICS: frozenset[str] = frozenset()` — empty after D-01, or a `is_carrier_path(path) -> bool` function) rather than maintaining its own tuple.

**When to use:** Any place that needs to answer "is this vault path a `{topic}`-filed note." `vault_sweep_plan.py` already does this correctly (`propose_topic_move` imports `topic_dir_for` lazily inside the function body, L45) — use that as the template.

**No circular-import risk confirmed:** `note_classifier.py`'s own imports (`app.config`, `app.services.model_selector`, `sentinel_shared.llm_call`, `sentinel_shared.model_profiles`) do not transitively import `recall.py`, so `recall.py` importing from `note_classifier.py` is safe.

**Example (existing precedent to mirror):**
```python
# app/services/vault_sweep_plan.py:41-53 — ALREADY does this correctly
def propose_topic_move(
    src_path: str, topic: str, *, today: str | None = None
) -> str | None:
    """Return the destination path a topic move would use."""
    from app.services.note_classifier import topic_dir_for   # import at call time

    topic_dir = topic_dir_for(topic, today=today)
    if not topic_dir:
        return None
    if is_in_topic_dir(src_path, topic_dir):
        return None
    filename = src_path.rsplit("/", 1)[-1]
    return f"{topic_dir}/{filename}"
```

### Pattern 2: D-14 lazy stub creation — read-then-conditionally-write, no separate "ensure" primitive

**What:** There is no existing `ensure_exists(path, stub)` helper anywhere in the codebase. The established idiom (confirmed live in `note_intake.py:classify_and_apply`, L53-63) is: read the path; if the body is empty/falsy, build stub content via a dedicated pure builder function; write it. `write_note`'s underlying transport is a raw `PUT /vault/{path}`, which the Obsidian Local REST API creates-if-missing — this IS the entire "lazy create" mechanism (confirmed: `write_note` at vault.py:507-515 does an unconditional PUT, no existence check).

**When to use:** VAULT-01/VAULT-05's stub creation for `self/identity.md`, `self/methodology.md`, `self/goals.md`, `self/relationships.md`.

**Example (existing precedent to mirror, from `note_intake.py:53-63`):**
```python
if result.topic == "unsure" or result.confidence < 0.5:
    body = await self._vault.read_note(INBOX_PATH)
    if not body or not body.strip():
        body = build_initial_inbox()          # pure stub-builder, no I/O (app/services/inbox.py)
    new_body = append_entry(body, content, result, suggested=...)
    await self._vault.write_note(INBOX_PATH, new_body)
```
Apply the same shape for each `self/*.md` path: `read_note(path)` → if empty, `write_note(path, build_self_stub(path))`. Do this at the point `RecallConfig.self_paths` is read (recall.py, inside `Recall.assemble()`'s self-context gather), NOT at startup/boot (D-14 explicitly rejects eager boot-time writes — "zero startup overhead — vault grows organically as it's used").

**Important distinction from `read_self_context`:** the existing `read_self_context()` (vault.py:367-386) is deliberately read-only and silently returns `""` on 404 per D-02 ("no log entry"). Do NOT bolt the stub-creation write onto `read_self_context` itself (that would change its contract for other unrelated callers, if any exist, and would violate its documented "graceful-skip" behavior). Instead, wrap the stub-ensure logic at the call site inside `Recall` where `self_paths` are gathered, or add a small dedicated method that composes read + conditional stub-write, keeping `read_self_context`'s existing contract untouched.

### Anti-Patterns to Avoid

- **Editing `TOPIC_VAULT_PATH`'s dict values without also editing `topic_dir_for()`'s and `_topic_target_path()`'s hardcoded `journal` literals.** This is the single highest-risk anti-pattern this research identified — it produces a change that looks complete (the dict says the right thing) but has zero runtime effect for the journal topic specifically, and nothing in the existing suite would catch it.
- **Treating `is_in_topic_dir`'s existing single-segment family-root logic as safe** just because it worked under the old (uniquely-named top-level directories) taxonomy. It does not generalize to the new shared-`ops/`-parent shape without a fix.
- **Assuming `_WARM_TIER_EXCLUDE_PREFIXES` (recall.py:51) and `RecallConfig.exclude_prefixes` (recall.py:247) are the same list.** They are not — one is missing `inbox/`. Reconcile them in this phase; don't let a second dual-source-of-truth survive right next to the one D-03b is explicitly fixing.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| "Does this vault path belong to topic X" | A second hand-maintained prefix tuple in `recall.py` | Import from `note_classifier.TOPIC_VAULT_PATH` / `topic_dir_for()` | This is precisely Pitfall 2's root cause; a second copy WILL drift again |
| "Create this file if it doesn't exist" | A new `ensure_exists()`/`vault_bootstrap.py` module or a startup-time provisioning pass | The existing read-then-conditionally-write shape already used by `note_intake.classify_and_apply` for `INBOX_PATH` | Established, tested, REST-only-safe pattern; a new module would be an unnecessary seam for a one-line idiom |
| "Is this note already correctly filed" | A bespoke per-topic string-matching function | `vault_sweep_plan.is_in_topic_dir()` (after the family-root fix) | Single choke point already consumed by the sweeper; don't fork a second implementation |

**Key insight:** every "don't hand-roll" item in this phase is really the same insight restated: the taxonomy routing table and its consumers already mostly follow single-source-of-truth discipline (`vault_sweep_plan.py` and `note_intake.py` both already import from `note_classifier.py`) — the phase's actual job is closing the ONE remaining gap (`recall.py`) and fixing the TWO latent bugs that only manifest once the dict values actually change.

## Common Pitfalls

### Pitfall 1 (CRITICAL — new this session): Hardcoded `journal/` literals silently defeat the `TOPIC_VAULT_PATH` dict edit

**What goes wrong:** `note_classifier.topic_dir_for()` (L68-91) and `note_intake.NoteIntake._topic_target_path()` (L144-152) both special-case `if topic == "journal":` with a **literal hardcoded string** (`f"journal/{today}"` and `f"journal/{today}/{slug}.md"` respectively) instead of building the path from `TOPIC_VAULT_PATH["journal"]`'s actual value. `base` is fetched from the dict only to check truthiness, then discarded for the journal branch.

**Why it happens:** The journal topic needs a per-day subdirectory the other topics don't, so the original author special-cased it — but hardcoded the literal top-level segment instead of interpolating `base` into the special-cased template.

**How to avoid:** When editing `TOPIC_VAULT_PATH["journal"]` from `"journal"` to `"ops/journal"`, edit both f-string templates in the same diff: `return f"{base}/{today}"` and `return f"{base}/{today}/{slug}.md"` respectively (using the fetched `base` variable instead of the literal). Add a new test asserting `topic_dir_for("journal", today="2026-07-06") == "ops/journal/2026-07-06"` — **no such test currently exists** for either function's journal-branch output at any point in the suite.

**Warning signs:** A PR changes `TOPIC_VAULT_PATH["journal"]` but the diff to `note_classifier.py`/`note_intake.py` doesn't touch any f-string literal containing `"journal/"`.

### Pitfall 2 (CRITICAL — new this session): `is_in_topic_dir`'s family-root collapse under shared `ops/` parents

**What goes wrong:** `is_in_topic_dir(path, topic_dir)` (vault_sweep_plan.py:27-38) computes `family_root = topic_dir.split("/", 1)[0] + "/"` — i.e., it truncates to the FIRST path segment. Under the OLD taxonomy this uniquely identified each topic (`journal/`, `accomplishments/`, `references/` were each a distinct top-level dir). Under the NEW taxonomy, `topic_dir_for("journal")`, `topic_dir_for("accomplishment")`, and `topic_dir_for("observation")` all begin with `"ops/"` — so `family_root` collapses to `"ops/"` for all three, and `is_in_topic_dir("ops/observations/x.md", "ops/journal/2026-07-06")` incorrectly returns `True` (any note anywhere under `ops/` looks "already home" for ANY of these three topics).

**Why it happens:** The single-segment heuristic was written when "first segment = family" held for every topic. It was never re-derived against a taxonomy where multiple topics nest under a shared parent.

**How to avoid:** Special-case the day-variable journal family explicitly rather than truncating universally:
```python
def is_in_topic_dir(path: str, topic_dir: str) -> bool:
    if not topic_dir:
        return False
    if topic_dir.startswith("ops/journal/"):
        family_root = "ops/journal/"          # nested-date family, any day matches
    else:
        family_root = topic_dir.rstrip("/") + "/"   # exact-match family (accomplishments, observations, inbox, ...)
    return path.startswith(family_root)
```
Add a regression test: `is_in_topic_dir("ops/observations/x.md", "ops/accomplishments") is False` and `is_in_topic_dir("ops/accomplishments/x.md", "ops/accomplishments") is True`, alongside the existing journal-nested-date assertion (`test_plan_topic_move_skips_existing_topic_family`'s first line, L24, which remains valid).

**Warning signs:** A misclassified note sitting in the wrong `ops/` subdirectory never gets relocated by a subsequent sweep even though the classifier correctly re-identifies its true topic.

### Pitfall 3 (new this session): `_safe_file_chat_note`'s "guaranteed searchable" contract becomes unsatisfiable

**What goes wrong:** `message.py`'s background auto-filer redirects a classified note to a `journal` path if its natural destination is warm-tier-excluded (`_WARM_TIER_EXCLUDE_PREFIXES`, recall.py:51 — currently `("ops/", "_trash/", "self/")`, missing `inbox/`). After D-03, **all seven** classifier topics resolve to either `ops/`- or `inbox/`-prefixed destinations (or are dropped as noise) — including the `journal` redirect target itself (now `ops/journal/...`). The redirect can no longer produce a searchable result for any topic. Meanwhile the one existing test that checks this (`test_chat_note_path_passes_warm_tier_exclusion_filter`, test_message.py:1264) uses topic `"learning"` and asserts the written path is not excluded — it will keep **passing** post-migration only because it checks against the stale `_WARM_TIER_EXCLUDE_PREFIXES` (which still doesn't list `inbox/`), even though the real warm-tier filter (`RecallConfig.exclude_prefixes`, which DOES include `inbox/`) would in fact treat that same path as excluded.

**Why it happens:** Two independent exclusion lists exist for what looks like the same concept (`_WARM_TIER_EXCLUDE_PREFIXES` vs. `RecallConfig.exclude_prefixes`) — the same dual-source-of-truth shape Pitfall 2 already warns about, in a location none of the prior research documents traced into.

**How to avoid:** This phase must make an explicit, documented decision (do not leave it as an accidental side effect):
1. Reconcile `_WARM_TIER_EXCLUDE_PREFIXES` with `RecallConfig.exclude_prefixes` (or delete the former and import the latter) so the redirect guard's precondition check reflects reality.
2. Decide whether the redirect-to-journal fallback should be retired entirely (recommended — there is no longer a valid redirect target; accept that chat-auto-filed content follows the same D-02 latency trade-off as `:capture`/`:seed`), or whether `_safe_file_chat_note` needs a different fallback (e.g., leaving the note at its natural classified destination and accepting D-02's window, same as explicit capture). Record this decision explicitly (mirrors D-05's "accepted, not silent" framing).
3. Update `test_chat_note_path_passes_warm_tier_exclusion_filter` and `test_observation_topic_chat_note_redirected_to_searchable_path` (test_message.py:1264, 1297) to assert the new, actually-true behavior rather than continuing to pass against a stale precondition.

**Warning signs:** A user's substantive chat message gets classified as `learning`/`reference` and becomes unsearchable via warm-tier keyword recall for a full sweep cycle, with no test failure anywhere flagging the change.

### Pitfall 4 (confirmed, matches PITFALLS.md Pitfall 2 exactly): Carrier-allowlist drift if D-03b's import isn't wired

Already fully described in the canonical `PITFALLS.md`. Confirmed via source read: `recall.py` currently has **zero** import of anything from `note_classifier.py` (verified: `recall.py`'s import block, L14-25, contains no such import) — so D-03b's "new coupling" is accurately described as new, not partially existing.

## Code Examples

### Removing the dead carrier-weighting block (D-01)

```python
# sentinel-core/app/services/recall.py — BEFORE (L67-72, L795-819)
_CARRIER_NAMESPACE_PREFIXES: tuple[str, ...] = (
    "journal/", "learning/", "accomplishments/", "references/",
)
# ... later, inside the warm-tier assembly ...
for r in merged:
    if r.path.startswith(_CARRIER_NAMESPACE_PREFIXES):
        date_str = _path_date(r.path)
        w = recency_weight(date_str if date_str is not None else "", now=now)
        reweighted.append(SearchResult(path=r.path, score=r.score * w, body=r.body))
    else:
        reweighted.append(r)
reweighted.sort(key=lambda r: (-r.score, r.path))
```
```python
# AFTER — D-01: no carrier namespaces survive migration; recency weighting is
# Session-summary-only (place (a), already handled by _hot_sessions ordering).
# Remove _CARRIER_NAMESPACE_PREFIXES and _path_date() (both now dead code —
# _path_date has no other caller). The warm-tier merge output flows straight
# through unchanged:
reweighted = merged
reweighted.sort(key=lambda r: (-r.score, r.path))  # tie-break stays deterministic
```
Note: `recency_weight()` itself (L600) must NOT be removed — it's still used by the hot-tier session sort at L747 (MEM-09 place (a)).

### Fixing the two hardcoded journal literals (Pitfall 1)

```python
# note_classifier.py:83-91 — BEFORE
base = TOPIC_VAULT_PATH.get(topic, "")
if not base:
    return ""
if topic == "journal":
    ...
    return f"journal/{today}"          # <-- hardcoded, ignores `base`
return base
```
```python
# AFTER
base = TOPIC_VAULT_PATH.get(topic, "")
if not base:
    return ""
if topic == "journal":
    ...
    return f"{base}/{today}"           # <-- derives from the dict value
return base
```
Apply the identical fix to `note_intake.py:150` (`return f"{base}/{today}/{slug}.md"`).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Flat-7 classifier with per-topic top-level directories (`learning/`, `accomplishments/`, `journal/`, `references/`) | PARA-aligned routing: durable-knowledge topics queue to `inbox/` pending Reduce; operational topics file under `ops/` subdirectories | This phase (44) | Recall's carrier-allowlist mechanism becomes entirely dead code; the sweeper's misplaced-note detector needs a family-root fix to keep working across the new shared `ops/` parent |
| Hand-maintained duplicate prefix tuple in `recall.py` for "which paths get recency weight" | Single source of truth in `note_classifier.py`, imported by all consumers | This phase (44) | Closes Pitfall 2's root cause structurally, not just for this one migration |

**Deprecated/outdated:** `_CARRIER_NAMESPACE_PREFIXES` and `_path_date()` in `recall.py` — both become fully dead code after D-01 and should be deleted, not left as unreachable code.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The recommended fix for `_safe_file_chat_note`'s broken "guaranteed searchable" contract (retire the redirect, accept D-02's latency trade-off) is the right call rather than inventing a new fallback destination | Common Pitfalls #3 | If wrong, chat-auto-filed learning/reference content becomes silently unsearchable for a sweep cycle with no compensating UX signal — low risk since it mirrors an already-accepted trade-off (D-02), but it is a NEW extension of that trade-off to a code path CONTEXT.md didn't explicitly discuss |
| A2 | 471 sentinel-core tests currently collected (verified via `pytest --collect-only -q` this session) is an accurate stand-in for the ROADMAP's "404+" baseline, and no other test directory (`modules/pathfinder/tests`, `interfaces/discord/tests`, `shared/tests`, `interfaces/imessage/tests`) needs to be included in this phase's regression gate | Regression Test Surface | If the "404+" baseline actually refers to a combined count across all test directories rather than sentinel-core alone, the plan's gate command may be incomplete — low risk since none of this phase's edits touch files outside `sentinel-core/app/` |

**If this table is empty:** N/A — two low-risk assumptions logged above; both are implementation-detail judgment calls, not open design questions requiring user re-confirmation of a locked decision.

## Open Questions

1. **Should `_safe_file_chat_note`'s redirect-to-journal special case be deleted, or repointed to some other still-searchable destination?**
   - What we know: every classifier topic now resolves to an excluded destination; the redirect currently has no valid target.
   - What's unclear: whether the phase owner wants an explicit compensating UX (e.g., surface a Discord note "this got queued, not immediately searchable") or considers silent latency acceptable (matching D-02's framing for `:capture`/`:seed`).
   - Recommendation: default to silent acceptance (matches existing precedent), record the decision explicitly in the phase's PROJECT.md/STATE.md decisions log so it isn't mistaken for an oversight later — this mirrors exactly how D-05 handled the analogous recency-weighting trade-off.

2. **Does the merged `inbox/_pending-classification.md` file need a permanent skip from topic-move proposals, or is a one-time test sufficient?**
   - What we know: today's `is_in_topic_dir` accidentally protects it only for topics whose new directory IS `inbox/` (learning/reference); topics resolving elsewhere (journal/accomplishment/observation) have no such protection.
   - What's unclear: how likely the LLM classifier is to actually mis-classify this multi-entry administrative file as one of those three topics in practice.
   - Recommendation: add an explicit path-based guard in `run_sweep()` (skip topic-move proposals — but still allow embedding — for `path == INBOX_PATH` specifically) rather than relying on the classifier's behavior being "probably fine." Cheap, deterministic, and closes a real (if narrow) gap.

## Environment Availability

This phase depends only on infrastructure already exercised by every prior shipped phase (the Obsidian REST vault via `ObsidianVault`, the already-configured LLM classifier endpoint via `acompletion_with_profile`). No new external dependency is introduced.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Obsidian Local REST API (vault seam) | All namespace/stub reads and writes | Pre-existing, already load-bearing for every prior phase | — | N/A — phase cannot function without it, same as all prior phases |
| LM Studio / exo (classifier LLM call) | `note_classifier.classify_note()` re-classification during sweeps | Pre-existing (Phase 42/43 provider registry) | — | Sweep already fails-soft on classifier errors (existing behavior, unchanged) |

**Missing dependencies with no fallback:** none — no new dependency introduced.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23 (`asyncio_mode = "auto"`) |
| Config file | `sentinel-core/pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`) |
| Quick run command | `cd sentinel-core && .venv/bin/python -m pytest tests/test_recall.py tests/test_vault_sweep_plan.py tests/test_vault_sweeper.py tests/test_note_classifier.py tests/test_message.py -q` |
| Full suite command | `cd sentinel-core && pytest` (per CONTRIBUTING.md) — confirmed 471 tests collected this session (`pytest --collect-only -q`), exceeding the ROADMAP's "404+" baseline |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VAULT-01 | `self/*.md` stub auto-created on first read-miss | unit | `pytest tests/test_recall.py -k self_stub -x` | ❌ Wave 0 — new test needed, no existing coverage of stub-creation behavior |
| VAULT-02 | `TOPIC_VAULT_PATH` routes learning/reference→inbox/, journal/accomplishment→ops/ | unit | `pytest tests/test_note_classifier.py::test_topic_dir_for_journal_derives_from_dict tests/test_vault_sweep_plan.py -x` | ❌ Wave 0 — journal-branch test doesn't exist yet (Pitfall 1) |
| VAULT-03 | Recency weighting applies only to Session summaries, never by omission | unit | `pytest tests/test_recall.py -k recency -x` | ⚠️ 3 existing tests need rewriting, not just re-running (see below) |
| VAULT-04 | Sweeper embeds inbox/, keyword tier still excludes it | unit | `pytest tests/test_vault_sweeper.py -k inbox tests/test_recall.py::test_inbox_gap_not_recalled -x` | ⚠️ 2 existing tests need updating (SWEEP_SKIP_PREFIXES constant, `_should_skip` inbox assertion) |
| VAULT-05 | Every message reads self/ files; missing files get created | unit + integration | `pytest tests/test_recall.py -k self_paths tests/test_message.py -k self -x` | ❌ Wave 0 — no test currently exercises stub-creation; existing `self_paths` read-through tests are unaffected and stay green as-is |

### Sampling Rate

- **Per task commit:** targeted file (`pytest tests/test_recall.py -q`, `pytest tests/test_vault_sweep_plan.py -q`, etc. per the module just touched)
- **Per wave merge:** `cd sentinel-core && pytest -q` (full 471-test suite)
- **Phase gate:** Full suite green (471/471, never fewer) before `/gsd-verify-work` — per SC-5 and MIG-03's regression-ledger discipline, a shrinking test count (e.g., deleting a failing test instead of fixing it) must be treated as a phase-gate failure, not a pass.

### Wave 0 Gaps

- [ ] `tests/test_note_classifier.py::test_topic_dir_for_journal_derives_from_dict` — covers Pitfall 1 (journal literal bug), asserts `topic_dir_for("journal", today="2026-07-06") == "ops/journal/2026-07-06"` after the fix
- [ ] `tests/test_vault_sweep_plan.py::test_is_in_topic_dir_does_not_conflate_ops_subdirs` — covers Pitfall 2 (family-root collapse), asserts `ops/observations/` and `ops/accomplishments/` are never mutually considered "in family"
- [ ] `tests/test_vault_sweeper.py::test_sweep_never_relocates_pending_classification_file` — covers Open Question #2 (merged inbox queue file protection)
- [ ] `tests/test_recall.py::test_recency_applies_only_to_session_summaries` — new replacement for the 3 tests below once `_CARRIER_NAMESPACE_PREFIXES` is removed; asserts D-01a's invariant directly (a `notes/`-namespace or `ops/`-namespace result dated today never outranks an older one purely on date, since neither is a carrier — only `result.sessions` ordering is recency-sensitive)
- Framework install: none — pytest/pytest-asyncio already present in `pyproject.toml`

**Existing tests requiring rewrite (not new, but must change in the same task as the code they exercise):**
- `tests/test_recall.py::test_recency_warm_carrier_journal` (L1464) — premise (`journal/` is a warm-tier-reachable, recency-weighted carrier) is invalidated by D-01/D-03c
- `tests/test_recall.py::test_recency_warm_carrier_topic_dir` (L1521) — same, using `learning/`/`accomplishments/` fixtures
- `tests/test_recall.py::test_recency_excludes_self` (L1576) — compares against a carrier path that no longer exists as a carrier; restructure around two `ops/sessions/`-shaped Session summaries instead
- `tests/test_vault_sweep_plan.py::test_plan_topic_move_skips_existing_topic_family` (L23-25) — `propose_topic_move("accomplishments/a.md", "accomplishment")` must become `propose_topic_move("ops/accomplishments/a.md", "accomplishment")` to still assert `None`
- `tests/test_vault_sweep_plan.py::test_plan_topic_move_describes_destination_and_reason` (L28-41) — expected `dst` changes from `"accomplishments/a.md"` to `"ops/accomplishments/a.md"`
- `tests/test_vault_sweeper.py::test_sweep_skip_prefixes_constant` (L462-467) — `assert "inbox/" in SWEEP_SKIP_PREFIXES` must flip to `assert "inbox/" not in SWEEP_SKIP_PREFIXES`
- `tests/test_vault_sweeper.py` L89 (`_should_skip` inline assertion) — `assert _should_skip("inbox/_pending-classification.md", {}, "now") is True` must flip to `is False` (a fresh path/frontmatter is no longer skip-listed by path prefix; it may still legitimately skip via the same-pass frontmatter check depending on test setup — verify against the actual fixture)
- `tests/test_message.py::test_chat_note_path_passes_warm_tier_exclusion_filter` (L1264) and `::test_observation_topic_chat_note_redirected_to_searchable_path` (L1297) — both depend on `_WARM_TIER_EXCLUDE_PREFIXES` staying in sync with reality (Pitfall 3); update per whatever decision is made for Open Question #1

*(Explicitly NOT affected, verified this session — no changes needed: `tests/test_note_classifier.py` in full, `tests/test_obsidian_vault.py`'s `PROTECTED_NAMESPACES` tests (dynamic/tolerant), `tests/test_recall.py::test_old_session_warm_reachable_journal` and `::test_old_session_warm_reachable_topic_dir` (use hardcoded path literals unrelated to `TOPIC_VAULT_PATH`, remain mechanically green though their docstrings become slightly stale — optional cosmetic follow-up, not a phase-gate blocker), `tests/test_vault_sweep_plan.py::test_plan_noise_trash_matches_dry_run_report_shape` and `::test_plan_duplicate_trash_matches_dry_run_report_shape` (no topic_dir_for involvement).)*

## Security Domain

`.planning/config.json` does not set `security_enforcement: false`, so this section is included per the default-enabled rule. This phase is a routing/internal-refactor phase with a small, well-understood security surface.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Phase touches no auth surface |
| V3 Session Management | No | Phase touches no session/token handling |
| V4 Access Control | Yes (narrow) | `PROTECTED_NAMESPACES` physical-move guard (`is_protected_path`) — verify the new `templates/` entry doesn't accidentally weaken existing `sentinel/`/`self/`/`security/` protection (confirmed this session: `is_protected_path` uses segment-boundary matching, additive entries cannot weaken existing ones) |
| V5 Input Validation | Yes (narrow) | The vault content read back into `self/*.md` stub files and re-injected into every message's context must continue to be treated as untrusted DATA, never as instructions — this is a pre-existing Sentinel design principle (per the untrusted-input-boundary reference); D-04's new stub-writer must not introduce any path the STUB CONTENT itself could be attacker-influenced (stub content is Claude/planner-authored boilerplate, not user input, so this is low risk but worth a one-line confirmation in the plan) |
| V6 Cryptography | No | No cryptographic surface touched |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Sensitive personal content in `self/relationships.md` (kids logistics, per the master spec) leaking into a wider-visibility namespace via a future MOC/wikilink pass | Information Disclosure | `self/` stays in `PROTECTED_NAMESPACES` (already true) and in `RecallConfig.exclude_prefixes` (already true) — Phase 44 must not accidentally narrow either list while adding `templates/`; verified this session that both are additive-only edits in the current plan scope |
| A malicious/crafted note in `inbox/` being read back into a future prompt (Reduce, Phase 46) as if it were an instruction rather than data | Tampering / Elevation of Privilege (prompt injection via vault content) | Out of this phase's direct scope (Reduce doesn't exist yet), but the routing decision that makes `inbox/` a first-class, longer-lived staging area (D-02/D-03) means Phase 46 inherits a slightly larger untrusted-content surface than before — worth a one-line note in this phase's SUMMARY so Phase 46's research/plan doesn't have to rediscover it |

## Sources

### Primary (HIGH confidence — direct source read this session)
- `sentinel-core/app/services/recall.py` — `_CARRIER_NAMESPACE_PREFIXES`, `_WARM_TIER_EXCLUDE_PREFIXES`, `RecallConfig`, warm-tier recency block, `_path_date`, `recency_weight` (all line numbers verified)
- `sentinel-core/app/services/vault_sweeper.py` — `SWEEP_SKIP_PREFIXES`, `_active_skip_prefixes`, `_should_skip`, `walk_vault`, `run_sweep`, `rebuild_embedding_index`, `_emit_embedding_index`
- `sentinel-core/app/services/vault_sweep_plan.py` — full file read; `is_in_topic_dir`, `propose_topic_move`, `plan_topic_move`, `plan_duplicate_trash`
- `sentinel-core/app/services/note_classifier.py` — `TOPIC_VAULT_PATH`, `topic_dir_for`, `TopicSlug`/`CLOSED_VOCAB`
- `sentinel-core/app/services/note_intake.py` — full file read; `classify_and_apply`, `_topic_target_path`, `_WARM_TIER_EXCLUDE_PREFIXES` usage
- `sentinel-core/app/services/inbox.py` — `build_initial_inbox`, `INBOX_PATH` (D-14 pattern source)
- `sentinel-core/app/routes/message.py` — `_queue_chat_note_write`, `_safe_file_chat_note`
- `sentinel-core/app/vault.py` — `PROTECTED_NAMESPACES`, `is_protected_path`, `read_self_context`, `read_note`, `write_note`
- `sentinel-core/app/config.py` — `sweep_skip_prefixes`, `protected_namespaces` settings defaults
- `sentinel-core/tests/test_recall.py`, `test_vault_sweep_plan.py`, `test_vault_sweeper.py`, `test_note_classifier.py`, `test_message.py`, `test_obsidian_vault.py`, `test_config.py` — read/grepped for exact test names, line numbers, and assertion shapes cited throughout this document
- `pytest --collect-only -q` run against `sentinel-core/tests` this session — confirmed 471 tests collected
- `.planning/phases/44-vault-namespace-taxonomy-foundation/44-CONTEXT.md` — locked design decisions D-01 through D-05
- `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md` — Phase A build order and Pitfalls 1/2/3/7 (canonical design source, this session's job was to verify + extend, not re-derive)
- `docs/2nd-brain-original-design/10-CONTEXT-master-spec.md` — D-01 vault structure, D-03 flat-7 definitions, D-14 lazy-create mandate
- `.planning/REQUIREMENTS.md`, `.planning/STATE.md` — VAULT-01..05 wording (corrected this session per D-02a) and the OQ1/D-06 decision history (carrier namespace = full 4-prefix set, inbox/ MEM-07 gap document-and-accept)

### Secondary / Tertiary
None used — every claim in this document traces to a primary source read this session.

## Metadata

**Confidence breakdown:**
- Standard stack: N/A — no new packages
- Architecture: HIGH — all cited seams re-verified against live source; 3 additional hazards found by direct function-body tracing
- Pitfalls: HIGH — all four pitfalls in this document are either directly confirmed against source (1, 2, 3) or directly cross-referenced against the canonical PITFALLS.md (4)
- Regression test surface: HIGH — exact test names, line numbers, and current pass/fail-after-change status derived from reading the actual test bodies and running `pytest --collect-only`, not inferred

**Research date:** 2026-07-06
**Valid until:** Effectively until this phase's code lands — this is a snapshot of production source line numbers that will shift the moment any of these files are edited. Re-verify line numbers if planning is deferred more than a few days past this research date.
