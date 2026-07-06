# Pitfalls Research

**Domain:** Restoring the arscontexta+BASB agentic note-taking core (6 Rs pipeline, PARA taxonomy, MOCs, `_schema`, 27-command system) into an existing FastAPI Sentinel Core that already has semantic Recall, embeddings-through-Sentinel, Retention, and a Pathfinder module — without repeating the phase-27 regression that silently gutted the original core.
**Researched:** 2026-07-05
**Confidence:** HIGH for all integration-specific pitfalls (grounded directly in live code: `note_intake.py`, `note_classifier.py`, `recall.py`, `vault_sweeper.py`, the phase-10 master spec, and the `pre-27-pivot` git tag/history). MEDIUM for general second-brain/Zettelkasten domain patterns (orphan/MOC decay, PARA over-organization) sourced from cross-checked community documentation — arscontexta's own repo documents no anti-patterns, so those two pitfalls are triangulated from adjacent-methodology sources, not the upstream project itself.

---

## Critical Pitfalls

### Pitfall 1: Silent Core Regression During Restructure (repeating phase-27)

**What goes wrong:**
The v0.6.0 milestone exists specifically because phase 27's "Path B" pivot (removing the Pi harness) **unintentionally gutted** the arscontexta+BASB core that phases 1–26 had built. Git history confirms the shape of the failure: the `pre-27-pivot` tag preserves the full second-brain core at the end of phase 26, and the phase-27+ commit trail shows the codebase pivoting toward LiteLLM-direct / provider-registry / embeddings-gateway concerns (phases 39–43) with no equivalent phase ever re-validating that `:capture`, `:ralph`, `:pipeline`, `_schema`, MOC/hub notes, or the 27-command surface still worked. Nobody "deleted the second brain" in one commit — it eroded because a refactor with a different focus (Pi-harness removal, provider abstraction) touched shared code paths (message handling, vault writes, Discord routing) without a regression contract that would have caught the silent loss of note-processing behavior.

**Why it happens:**
Refactors that are scoped around a *different* concern (e.g. "remove the Pi harness," "add semantic recall") touch the same shared surfaces (`message.py`, `bot.py`, `NoteIntake`, `Vault` seam) that the note-taking core depends on. Without an explicit, versioned list of second-brain capabilities treated as a *requirements contract* (the way MEM-01..MEM-09 are tracked for Recall), there is nothing forcing a "did we just remove X" check. The same failure mode can now recur in the other direction: v0.6.0 restoring the note-taking core could just as easily gut MEM-01..MEM-09 (Recall, semantic recall, retention) if the restoration phases aren't held to the same regression discipline.

**How to avoid:**
1. Before any restoration phase starts, enumerate the pre-27 command surface (all 27 `:` commands from D-03) and the current MEM-01..MEM-09 requirements as **two parallel requirement ledgers** that must both stay green through every phase of v0.6.0.
2. Every phase plan must include an explicit regression gate: "MEM-01..MEM-09 still pass" AND "no `:command` from the restored surface silently no-ops." Treat this the same way phase 39–41 treated `Recall` requirements — as UAT-verifiable, not just unit-tested.
3. Never let a phase whose stated goal is "restore command X" also silently touch `Recall`, `RetentionPolicy`, or `SemanticRecall` internals as a side effect without its own explicit sub-requirement and test.
4. Add a standing full-suite regression run (`404+ passed` baseline, per PROJECT.md) as a hard gate at the end of every phase, not just at milestone close.

**Warning signs:**
- A phase diff touches `message.py`, `recall.py`, or `bot.py` for a stated reason unrelated to the file being touched (e.g. "add `:reweave`" also changes hot-tier assembly).
- STATE.md or a phase SUMMARY says a command "should still work" without a UAT entry proving it.
- The full test suite count drops or a previously-passing MEM-0x test is deleted rather than updated.

**Phase to address:**
Every phase of v0.6.0 (this is a cross-cutting gate, not a single phase) — but it must be **established first**, in the phase that sets up the migration/scaffolding, as a checklist artifact (e.g. `v0.6.0-REGRESSION-LEDGER.md`) that later phases are graded against.

---

### Pitfall 2: Taxonomy Migration Silently Breaks Recall's Carrier Allowlist

**What goes wrong:**
`recall.py`'s `_CARRIER_NAMESPACE_PREFIXES` (`journal/`, `learning/`, `accomplishments/`, `references/`) is a **hand-maintained positive allowlist** that mirrors `note_classifier.py`'s flat-7 `TOPIC_VAULT_PATH` values, explicitly documented in-code as "NOT derived by negating `_WARM_TIER_EXCLUDE_PREFIXES`" so a future non-carrier namespace is never silently weighted (T-41-08). If the PARA/`notes/` migration changes where classified content is filed (e.g. `learning/` and `references/` both collapse into `notes/` with `_schema.type: permanent`), this allowlist becomes stale: migrated content **still gets recalled** (nothing crashes) but **silently loses recency weighting** — a regression with zero errors and zero test failures unless a test specifically asserts recency-weight application per namespace.

**Why it happens:**
The allowlist and the classifier's topic-to-path map live in two different files with no shared source of truth and no test that fails when they drift. Because the failure mode is "ranking quality slightly worse," not "exception thrown," it will not surface in CI and may not surface in manual testing either — only in degraded recall quality over weeks.

**How to avoid:**
Treat `TOPIC_VAULT_PATH` (or its PARA-migration successor) as a single source of truth that both `NoteIntake` and `Recall` import from — not two independently maintained constants. If the new taxonomy still needs an episodic-vs-permanent-knowledge distinction for recency weighting, encode it as a property on the taxonomy definition itself (e.g. a `carrier: bool` flag per PARA category) rather than a second hardcoded prefix tuple. Add an explicit test: for every path the new classifier/pipeline can file a note to, assert whether it is or isn't in the recency-weighted set, and require that test to be updated whenever the taxonomy changes.

**Warning signs:**
- A PR changes `note_classifier.py` or introduces the PARA taxonomy without a corresponding diff to `recall.py`'s carrier prefixes.
- Recency-weighted recall quality degrades for content types that existed before the migration (journal-equivalent, learning-equivalent notes).
- No test asserts carrier-namespace membership for the new `notes/` structure.

**Phase to address:**
The phase that introduces the PARA taxonomy / replaces the flat-7 classifier. This must ship in the **same phase** as any `recall.py` carrier-prefix update — never split across phases, per the Pitfall 1 discipline.

---

### Pitfall 3: Embedding/Sweeper Blind Spot During Pipeline Migration

**What goes wrong:**
`vault_sweeper.py`'s `SWEEP_SKIP_PREFIXES` (`_trash/`, `pf2e/`, `ops/sessions/`, `ops/sweeps/`, `inbox/`) means **`inbox/` content is never embedded**. This is correct today (inbox is transient, pre-classification). But the restored 6 Rs pipeline makes `inbox/` a first-class, potentially long-lived staging area (D-09: "notes never go directly to `notes/`; all content routes through `inbox/` first" with a queue in `ops/queue/`). Two concrete regressions follow: (a) content sitting in `inbox/` awaiting `:ralph`/`:pipeline` processing is **semantically unrecallable** until Reduce moves it to `notes/` and a sweep runs — if the sweep cadence is slower than the pipeline cadence, freshly-reduced notes have a recall blind-spot window; (b) directory renames during migration (`learning/foo.md` → `notes/foo.md`) risk orphaning `embedding_b64`/`embedding_model` frontmatter if the migration tool does a delete+recreate instead of an in-place frontmatter-preserving move, forcing a full-vault re-embed that Pitfall 5 of the prior PITFALLS.md (O(N) HTTP cost) already flagged as expensive.

**Why it happens:**
The sweeper and the 6 Rs pipeline are two independently-scheduled systems that both mutate the vault; nothing coordinates "a note just got Reduced, trigger/wait-for a sweep" or "a note just got moved, carry its embedding forward." The migration tooling built for D-10 (directory migration) was scoped before semantic recall existed (phase 10 predates phase 40), so its "move, don't recreate" assumption was never verified against the embedding-preservation requirement.

**How to avoid:**
1. Migration/move operations for existing notes (flat-7 → PARA `notes/`) must be implemented as vault-native renames (preserve frontmatter, including `embedding_b64`/`embedding_model`) — never a read-then-delete-then-write that drops frontmatter.
2. Decide explicitly whether Reduce (inbox → `notes/`) triggers an on-demand embed for the single moved note (cheap: one note) rather than waiting for the next full sweep cycle. This closes the recall blind-spot without reintroducing O(N) per-message cost.
3. Add a migration dry-run report (counts of notes moved, embeddings preserved vs. dropped) before committing the migration, following the non-destructive `_trash/`-only constraint already established for the sweeper.

**Warning signs:**
- A note processed by `:ralph` this session doesn't show up in semantic recall until the next scheduled sweep.
- Post-migration, `embedding_model` frontmatter is missing on notes that had it pre-migration.
- Migration script uses `write_note(new_path, content)` + separate delete rather than a single rename/move call.

**Phase to address:**
The taxonomy-migration phase (moving flat-7 content into PARA structure) must include an embedding-preservation test as part of its Nyquist validation. The pipeline-core phase (implementing Reduce) must decide the embed-on-reduce vs. wait-for-sweep tradeoff explicitly, not by default.

---

### Pitfall 4: Over-Automation of the 6 Rs Pipeline Against a Bounded Local Model

**What goes wrong:**
D-09/D-13 design `:ralph` and `:pipeline` as a single `call_core()` prompt with "no bot-side vault reads, no iteration loop — the AI handles the orchestration." Combined with D-16's explicit acknowledgment that "the quality of note reduction, connection finding, and reweave is bounded by the local model's capability," this means a single local-model completion is being asked to: extract a claim, write a compliant `_schema` block, find or create a hub, add wikilinks, and (for `:pipeline`) also run Reweave/Verify/Rethink — all in one shot, ungoverned by any per-stage quality gate. If this is ever wired to run unattended (a cron-triggered `:ralph`, or a Discord auto-reaction), a bad local-model output doesn't just miss — it **writes a wrong claim title, a malformed `_schema` block, or a spurious wikilink directly into `notes/`**, and nothing stops the next `:pipeline` run from reweaving *other* notes around that bad claim, compounding the error across the graph.

**Why it happens:**
The zero-friction capture principle (D-14, "just-in-time organization") correctly keeps `inbox/` low-friction, but the temptation is to extend "zero friction" to the *processing* side too — running `:ralph`/`:pipeline` automatically so the user never has to think about it. That inverts the design: Record should be zero-friction; Reduce/Reflect/Verify should stay human-gated, especially against a small local model.

**How to avoid:**
Keep `:ralph`/`:pipeline` **explicitly user-invoked** (as currently designed) — do not add a scheduled/background trigger for them in this milestone. If batch processing is desired later, gate it behind a `:review`-equivalent confirmation step per note rather than blind auto-file. Track local-model output quality with a lightweight heuristic (e.g. `_schema` block parses as valid YAML, claim title passes a length/shape check) and route failures back to `inbox/` rather than filing malformed notes — never let a malformed `_schema` land in `notes/` silently.

**Warning signs:**
- Any code path invokes `:ralph`/`:pipeline` on a timer, `on_ready` hook, or Discord auto-reaction rather than an explicit user command.
- `notes/` accumulates entries with `_schema.status: draft` that were never reviewed.
- `:check` batch validation surfaces a growing count of non-compliant notes with no corresponding `:review` activity.

**Phase to address:**
The command-system phase (`:ralph`, `:pipeline`, `:reweave`). Explicitly scope these as human-invoked only for v0.6.0, and record "no scheduled auto-processing" as a constraint in that phase's plan, not an oversight.

---

### Pitfall 5: MOC/Hub-Note Drift — Orphan Explosion or Premature Hub Sprawl

**What goes wrong:**
D-06 correctly designs hub notes to be created **lazily** by `:connect` rather than upfront — this avoids the well-documented Zettelkasten failure mode of building MOC structure before there's enough content to justify it ("don't create MOCs upfront; let them emerge naturally... building MOCs too early creates structure for structure's sake"). But the opposite failure is equally real at scale: because `:connect` is a manual, per-note command (D-06: "`:connect [note title]` finds which hub the note belongs to") and nothing in the design **automatically** invokes it after Reduce, a note filed by `:ralph`/`:pipeline` can sit in `notes/` indefinitely without ever being connected to a hub — i.e. every Reduce that isn't followed by an explicit Reflect step becomes a permanent orphan. At vault scale (hundreds of notes, matching this project's existing sweep-scale assumptions), orphan count grows unbounded with no forcing function to reduce it, since `:stats`/`:graph` are read-only reporting commands, not corrective ones.

**Why it happens:**
The 6 Rs are modeled as discrete, independently-invocable stages (D-09) for good reason (composability, `:ralph` = Reduce+Reflect only), but `:pipeline` running "all 6 Rs in sequence" is the only path that guarantees Reflect actually runs. If users mostly reach for `:ralph` (batch inbox processing) rather than `:pipeline`, D-13's own table shows `:ralph` = "Reduce + Reflect" — so `:ralph` *does* include Reflect. The real gap is notes filed by `:capture`/`:seed` that get Reduced through some other path (or partially through the pipeline) without ever hitting `:connect`.

**How to avoid:**
Make `:stats`/`:graph`'s orphan count a first-class, surfaced metric (D-07's proactive-nudge voice pattern: "12 notes connected, no orphans" is already the intended UX — operationalize it, don't just document it). Consider having `:ralph` refuse to mark an item "processed" if Reflect (hub assignment) didn't succeed — file it back to a "needs connection" state rather than silently leaving it hub-less in `notes/`. Track orphan count as a metric across phases (a regression if orphan count only grows, never shrinks, over a testing period).

**Warning signs:**
- `:graph`/`:stats` orphan count grows monotonically across a testing session with no `:connect` activity resolving it.
- Hub notes proliferate for near-duplicate concepts (hub sprawl) because `:connect`'s lazy-creation has no dedup/similarity check against existing hubs before creating a new one.
- `notes/` contains permanent notes with `_schema.hub:` empty or missing despite `_schema.status: ready`.

**Phase to address:**
The command-system phase (`:connect`, `:stats`, `:graph`) and the note-quality phase (`_schema`, `:review`, `:check`). `:review`'s three-part validation (claim title, `_schema`, wikilink — D-05) should be the enforcement point that catches hub-less "ready" notes, not a separate mechanism.

---

### Pitfall 6: `_schema` Enforcement Applied at the Wrong Pipeline Stage Breaks Zero-Friction Capture

**What goes wrong:**
D-14's "just-in-time organization" principle and D-09's "notes never go directly to `notes/`" are both designed so that `:capture`/`:seed` stay frictionless — raw content lands in `inbox/` with no validation. D-05's note-quality standard (claim title + `_schema` block + wikilink) is meant to apply only once a note is "done" (in `notes/`), checked by `:review`/`:check` (Verify stage). If an implementation detail accidentally validates `_schema` compliance *before* filing (e.g. Reduce refuses to move inbox content to `notes/` unless the LLM's first attempt at a `_schema` block is well-formed, with no fallback), Reduce silently stalls — content sits in `inbox/` forever whenever the local model's first-pass `_schema` output is even slightly malformed, defeating the whole point of `:ralph` batch processing and quietly re-introducing the friction the design explicitly rejects.

**Why it happens:**
It is tempting to enforce quality "early" because it seems cheaper to reject bad output before it's filed rather than clean it up after. But that inverts the arscontexta design intent: `_schema`/claim-title/wikilink compliance is a **Verify-stage** concern (D-05, D-09 step 5), not a Reduce-stage gate. Local-model output is explicitly expected to be imperfect (D-16); the pipeline is designed to tolerate a `_schema.status: draft` note existing in `notes/` pending review, not to block filing until perfect.

**How to avoid:**
Reduce should file to `notes/` with `_schema.status: draft` even if the LLM's `_schema` block is imperfect (repair minimally — ensure it parses as YAML — rather than rejecting). Reserve hard compliance enforcement (claim-title test, hub membership, wikilink presence) for `:review`/`:check`, which report actionable feedback rather than blocking. Never let Reduce's success be gated on passing the same bar `:review` checks.

**Warning signs:**
- Items accumulate in `inbox/`/`ops/queue/` with no corresponding `notes/` output despite repeated `:ralph` runs.
- Reduce implementation calls the same validation function `:check` uses and treats a failure as "do not file" rather than "file as draft."
- Users report `:ralph` "does nothing" on certain inbox items.

**Phase to address:**
The pipeline-core phase (Reduce implementation) and the note-quality phase (`_schema`, `:review`, `:check`) must share validation logic but apply it at different severities — this split should be an explicit design decision recorded in that phase's CONTEXT, not implied.

---

### Pitfall 7: Wikilink Integrity Breaks Across the Taxonomy Migration

**What goes wrong:**
Migrating existing flat-7 content (`learning/`, `accomplishments/`, `references/`, `ops/observations/`) into the PARA `notes/` structure means renaming/moving files. If the migration is implemented as a raw REST `PUT` (write new path) + separate delete via `ObsidianClient`, rather than an Obsidian-native rename, **any existing `[[wikilink]]` referencing the old path/title becomes dangling** — Obsidian's automatic backlink-rewriting on rename only fires for renames performed through Obsidian itself (via its UI or a plugin), not for external REST clients doing move-by-copy. Since the Vault Protocol (`app/vault.py`, ADR-0002) is the sole persistence seam and there is no confirmed rename primitive in the existing `ObsidianClient` (only `read_note`/`write_note` per the code inspected), a naive migration silently breaks every existing cross-reference into migrated content.

**Why it happens:**
The existing Vault seam was built for a system with no wikilink graph to preserve (pre-restoration, the flat-7 classifier files content into flat directories with no `_schema`/hub relationships). The migration tooling required for D-10 predates the wikilink-integrity requirement this milestone introduces, so "move a note" was never previously required to also "rewrite every note that links to it."

**How to avoid:**
Before migrating any note, scan the vault for `[[wikilink]]` references to its title/path (the existing `search_vault` capability can support this). After moving, either (a) rewrite discovered referencing notes' wikilinks to the new title/path, or (b) rely on Obsidian's title-based (not path-based) wikilink resolution — if wikilinks reference note *titles* rather than full paths, a same-title move across directories may not break links at all, which should be verified empirically against the actual vault before assuming risk. Either way, this must be tested against the real Obsidian instance, not assumed from REST semantics alone.

**Warning signs:**
- Post-migration `:graph`/`:check` reports a spike in dangling-link count.
- Notes that previously had inbound links (per pre-migration `:stats`) show zero inbound links post-migration.
- Migration script performs `write_note` to a new path followed by a separate delete call, with no link-rewrite step.

**Phase to address:**
The taxonomy-migration phase. Must include an explicit pre/post wikilink-integrity check (`:graph`/`:check` dangling-link count) as a Nyquist validation gate, not just a "files moved successfully" check.

---

### Pitfall 8: 6 Rs Pipeline Acting on a Stale/Torn Vault Snapshot (No Concurrency Guard)

**What goes wrong:**
`vault_sweeper.py` already has a lockfile pattern (`LOCKFILE_PATH = "ops/sweeps/_in-progress.md"`) because the team learned sweeps must not run concurrently with themselves. The 6 Rs pipeline commands (`:ralph`, `:pipeline`) have **no equivalent guard**: D-13 explicitly designs `:ralph` as "no bot-side vault reads, no iteration loop — the AI handles the orchestration using vault context it already has access to," meaning the entire inbox-queue view the AI reasons over is assembled once, at prompt-construction time, in a single long-running completion. If a user fires `:ralph` twice in quick succession (impatience, or two Discord threads), or a scheduled sweep runs mid-`:pipeline`, both processes can act on the same inbox entries — double-filing a note, or one process removing an inbox entry the other is mid-way through summarizing, producing a `InboxChangedConflict`-class failure (the existing `inbox_classify`/`inbox_discard` paths already detect and raise on this for their narrower operations, but `:ralph`/`:pipeline`'s single-completion design has no analogous conflict check on the file-then-verify boundary).

**Why it happens:**
The single-completion design (D-13) was chosen for simplicity ("no new routing layer") and works fine for the common single-user, single-invocation case, but it was never load-tested against concurrent invocation or concurrent sweeper activity, and the existing conflict-detection pattern (`_content_hash` compare-and-swap in `NoteIntake.inbox_classify`/`inbox_discard`) is not wired into the pipeline commands.

**How to avoid:**
Reuse the sweeper's lockfile pattern (or the `NoteIntake` content-hash compare-and-swap pattern) for `:ralph`/`:pipeline`: acquire a lightweight lock (e.g. `ops/queue/_in-progress.md`) before processing and refuse/queue a second concurrent invocation with a clear user-facing message rather than silently racing. At minimum, apply the same pre/post content-hash check `inbox_classify` already uses to detect a changed inbox mid-operation and fail loudly rather than silently double-processing.

**Warning signs:**
- Two `:ralph` invocations in the same session both report processing the same inbox entry.
- A note appears twice in `notes/` with slightly different content (same source, processed by two overlapping runs).
- `ops/queue/` entries reference inbox items that no longer exist.

**Phase to address:**
The command-system phase implementing `:ralph`/`:pipeline`. Concurrency guarding should ship with the initial implementation — retrofitting it after a double-file incident requires auditing every already-filed note for duplication.

---

### Pitfall 9: Local-Model Cost/Latency Compounding Across a Single-Call 6-Stage Pipeline

**What goes wrong:**
`:pipeline` is designed (D-09, D-13) to run **all 6 Rs stages in one `call_core()` completion** against a local model (LM Studio/exo, per the hard local-AI-only constraint and the current provider-registry work in phases 42–43). This compounds three real costs the phase-10 design under-weighted: (a) **context window** — a single completion asked to reason over inbox content, the existing hub graph, and reweave candidates simultaneously may exceed a small local model's context far sooner than any single-stage command would; (b) **latency** — Discord message handling has practical response-time expectations, and a single completion covering claim-extraction + `_schema` authoring + hub-finding + reweave-candidate-selection is a materially longer generation than any existing single-purpose prompt in the codebase; (c) **exo's idle-unload behavior** (confirmed operationally: exo unloads idle models and 404s until reloaded) means a `:pipeline` invoked after any idle period risks a cold-start delay or an outright failed call mid-pipeline, with no partial-progress recovery since the design has no iteration loop to resume from.

**Why it happens:**
D-16 acknowledges local-model quality limits ("design prompts to work well with smaller models") but does not address latency/context budget, because phase 10 predates the current provider-registry/embeddings-gateway work (phases 42–43) that made the model topology (LM Studio vs. exo, context-window registry per provider) an explicit first-class concern. The pipeline design was written before the project had a `SentinelCoreClient`/provider-registry abstraction to route through, so its single-completion assumption was never benchmarked against real provider behavior.

**How to avoid:**
Before shipping `:pipeline` as a single call, benchmark actual latency and context usage against the currently configured local provider (LM Studio and exo both, given the project's provider-registry work). If a single completion cannot reliably complete all 6 stages within the local model's context window and a reasonable Discord response time, decompose `:pipeline` into sequential calls per stage (Record output feeds Reduce, Reduce output feeds Reflect, etc.) rather than one giant prompt — accepting the added complexity of state-passing between calls, which should be a deliberate architecture decision (ADR-worthy), not a default. Explicitly handle the exo idle-unload case: warm the model (or detect and surface a clear "model is loading" message) before starting a `:pipeline` run rather than letting it fail silently mid-batch.

**Warning signs:**
- `:pipeline` invocations against exo intermittently fail with a 404 or unexpectedly long latency after any idle period.
- Local model output for `:pipeline` truncates or drops earlier pipeline stages' output when reasoning about later stages (context overflow symptom).
- `:pipeline` response times are an order of magnitude longer than single-stage commands (`:capture`, `:connect`) in manual testing.

**Phase to address:**
The command-system phase implementing `:pipeline` — must include a real-provider latency/context benchmark as part of its verification, using the existing provider-registry (phase 42) rather than assuming LiteLLM-direct.

---

### Pitfall 10: Background-Task Failures in the Pipeline Are Invisible to the User

**What goes wrong:**
The established pattern in this codebase is that Obsidian writes triggered from message handling are best-effort background tasks: "log warning on failure, never fail the HTTP response" (confirmed in the prior PITFALLS.md's Integration Gotchas). If `:ralph`/`:pipeline` inherit this same fire-and-forget pattern (likely, since they route through the same `call_core()`/background-task machinery as every other Discord command), a mid-pipeline failure — a dropped LM Studio/exo connection, a vault write conflict, a malformed `_schema` the repair step can't fix — produces **no user-visible signal**. The user sees `:ralph` "complete" (the Discord command returned) while the inbox queue is actually unchanged or partially processed, and only discovers this later via `:stats`/`:graph` showing unprocessed items, with no error message connecting cause to effect.

**Why it happens:**
The best-effort background-task pattern is correct for its original purpose (session-summary writes, where silent degradation is an acceptable tradeoff for never blocking a chat response). Extending the same pattern to `:ralph`/`:pipeline` — which are explicit, foreground user commands whose entire value is "did my inbox get processed" — inherits a failure-visibility tradeoff that doesn't fit the new use case.

**How to avoid:**
`:ralph`/`:pipeline` should report an explicit success/failure/partial-success summary back to the Discord thread ("processed 3 of 4 inbox items; 1 failed — model unavailable, retry with `:ralph`") rather than silently succeeding on the HTTP/command-ack layer while the underlying work fails. This requires the command handler to await and inspect the actual outcome rather than fire-and-forget it — a deliberate deviation from the session-summary background-task pattern that should be documented as intentional, not an oversight.

**Warning signs:**
- `:ralph` always returns the same "processing your inbox" acknowledgment regardless of whether processing actually succeeded.
- `ops/queue/` or `inbox/` item counts don't change after a `:ralph` invocation that reported success.
- No test exercises a simulated LM Studio/exo failure mid-`:ralph` and asserts the user is told about it.

**Phase to address:**
The command-system phase implementing `:ralph`/`:pipeline`. Explicit result reporting should be a stated requirement in that phase's CONTEXT, distinguishing it from the fire-and-forget session-summary pattern.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|-----------------|
| Migrate flat-7 directories to `notes/` via delete+recreate instead of a preserving rename | Simpler migration script | Drops `embedding_b64`/`embedding_model` frontmatter, forces a full re-embed; breaks wikilinks referencing old paths | Never — always preserve frontmatter and check wikilink integrity |
| Let `:pipeline` run all 6 Rs as one uninterruptible completion | Matches D-13's "no new routing layer" simplicity goal | No partial-progress recovery on mid-run failure (exo idle-unload, context overflow); compounding latency | Acceptable only after benchmarking confirms the local model handles it within budget; otherwise decompose per-stage |
| Hardcode `_CARRIER_NAMESPACE_PREFIXES` as a second copy of the taxonomy's path map | Fast, no shared-module refactor needed | Silently drifts from the classifier taxonomy on any migration, degrading recency weighting with no test failure | Never past the taxonomy-migration phase — must become a derived/shared value |
| Apply `:ralph`/`:pipeline` best-effort background-task pattern (fire-and-forget) | Reuses existing session-summary infrastructure | User gets no failure signal; inbox appears "stuck" with no diagnosis path | Never for foreground, user-invoked commands whose value is the processing outcome itself |
| Enforce `_schema` compliance at Reduce (file-time) instead of Verify (`:review`/`:check`) | Prevents "bad" notes from ever landing in `notes/` | Reintroduces the friction the design explicitly rejects (D-14); local-model imperfection stalls the whole pipeline | Never — enforcement belongs at Verify, not Reduce |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|-----------------|-------------------|
| `NoteIntake.classify_and_apply` / new PARA classifier | Change classification target paths without updating `recall.py`'s `_CARRIER_NAMESPACE_PREFIXES` in the same change | Treat the taxonomy-to-path map as a single shared source of truth imported by both `NoteIntake` and `Recall` |
| `vault_sweeper.py` `SWEEP_SKIP_PREFIXES` | Assume the sweeper will pick up newly-Reduced `notes/` content promptly; leave `inbox/` permanently unembedded without checking pipeline cadence vs. sweep cadence | Decide explicitly whether Reduce triggers an on-demand single-note embed, or document the acceptable recall-blind-spot window |
| `ObsidianClient` (`app/vault.py` seam) | Migrate/move notes via write-new-path + delete-old-path | Confirm whether a native rename primitive exists (or add one) that preserves frontmatter and lets Obsidian's own link-aware rename behavior apply; verify empirically whether wikilinks are title- or path-keyed before assuming risk |
| Discord command routing (`bot.py`) | Reuse the fire-and-forget background-task pattern for `:ralph`/`:pipeline` | Await and report actual pipeline outcome (success/partial/failure) back into the Discord thread |
| Provider registry / exo (phase 42–43 work) | Assume `:pipeline`'s single-completion design behaves the same on exo as on LM Studio | Benchmark both configured providers explicitly; handle exo's idle-unload/404 case with a clear user-facing message, not a silent pipeline failure |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| Single-completion `:pipeline` exceeding local-model context window | Later 6-Rs stages ignored/truncated in the model's reasoning; incoherent `_schema`/hub output | Benchmark against actual configured provider's context window before shipping; decompose into per-stage calls if needed | As soon as the vault graph context + inbox batch exceeds the smallest configured local model's context |
| Sweep cadence lagging pipeline cadence | Freshly-Reduced notes invisible to semantic recall for a window after processing | Decide and implement an explicit embed-on-reduce (single note) vs. wait-for-sweep policy | Any gap where a user runs `:ralph` then immediately queries something that should recall the just-processed note |
| Orphan-count growth with no corrective mechanism | `:graph`/`:stats` orphan count trends upward indefinitely across sessions | Make orphan count a tracked regression metric; gate `:review`"ready" status on hub membership | Vault scale where manual `:connect` discipline can't keep pace with `:ralph` throughput |
| Migration re-embedding the entire vault due to lost frontmatter | Full-vault sweep triggered post-migration, repeating the O(N) HTTP cost already flagged in prior PITFALLS.md | Preserve `embedding_b64`/`embedding_model` frontmatter across the flat-7 → PARA move | Any migration implemented as delete+recreate rather than a preserving rename |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| `self/relationships.md` (kids logistics, per phase-10 spec) surfaced through a `:connect`/`:reweave` pass that treats `self/` content as linkable graph material | Sensitive personal data could get wikilinked into `notes/` and surfaced via `:graph`/semantic recall outside its intended `self/`-only scope | Keep the existing `self/` warm-tier exclusion (`_WARM_TIER_EXCLUDE_PREFIXES`) intact through the migration; explicitly test that `:connect`/`:reweave` never create wikilinks *from* `notes/` *into* `self/` content as if it were a hub source |
| `_schema` blocks or note content processed by a local model and then executed/interpreted as instructions by a later pipeline stage (e.g. Reweave reading a "malicious" injected note) | Prompt-injection-via-vault-content: a captured note could contain text designed to manipulate the AI's behavior on a later `:reweave`/`:pipeline` pass | Treat all vault content read back into a prompt as untrusted data, never as instructions — this is a pre-existing Sentinel design principle (per the untrusted-input-boundary reference) that must extend to every new pipeline stage, not just chat messages |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|--------------|-------------------|
| `:ralph`/`:pipeline` silently no-op or partially fail (Pitfall 10) | User believes inbox is processed; trust in the system erodes when discovered later | Explicit per-run outcome summary posted to the thread |
| `_schema` enforcement blocking capture (Pitfall 6) | Zero-friction capture promise broken; user stops using `:seed`/`:capture` | Enforce quality only at Verify (`:review`/`:check`), never at Record/Reduce |
| Hub sprawl from `:connect`'s lazy creation with no similarity check | Vault accumulates near-duplicate MOCs, defeating the purpose of hubs as navigation aids | `:connect` should check existing hub notes for conceptual overlap before creating a new one, and surface the choice to the user when ambiguous |

---

## "Looks Done But Isn't" Checklist

- [ ] **Taxonomy migration:** Every existing flat-7 note's `embedding_b64`/`embedding_model` frontmatter survived the move to its PARA/`notes/` location. Verify: diff frontmatter keys pre/post migration for a sample of moved notes.
- [ ] **Recall carrier allowlist updated:** `recall.py`'s recency-weighted namespace set reflects the new taxonomy, not the old flat-7 paths. Verify: a note filed under the new taxonomy that is functionally "episodic" is recency-weighted in a test.
- [ ] **Wikilink integrity preserved:** No increase in dangling-link count reported by `:graph`/`:check` after migration. Verify: run `:graph` before and after migration on the same vault snapshot and diff orphan/dangling counts.
- [ ] **`:ralph`/`:pipeline` concurrency guard exists:** Two overlapping invocations do not double-file the same inbox entry. Verify: integration test firing two concurrent `:ralph` calls against the same inbox state.
- [ ] **`_schema` enforcement gated to Verify:** Reduce successfully files a note to `notes/` with `_schema.status: draft` even when the LLM's first-pass `_schema` output is imperfect. Verify: test Reduce with a deliberately malformed LLM completion and confirm the note is filed as draft, not dropped or retried indefinitely.
- [ ] **Regression ledger green:** All MEM-01..MEM-09 requirements (Recall, semantic recall, retention) still pass after every restoration phase, alongside the newly-restored command surface. Verify: full suite run + explicit UAT pass for both requirement sets at each phase boundary.
- [ ] **Local-provider pipeline benchmark:** `:pipeline` has been latency/context-benchmarked against both LM Studio and exo, with the exo idle-unload case explicitly handled. Verify: manual timed run against each configured provider, including one run after a deliberate idle period.
- [ ] **Background-task failure visibility:** A simulated mid-pipeline provider failure surfaces a clear message to the Discord thread rather than a silent "done." Verify: test with a mocked/broken provider client and assert the user-facing response names the failure.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|------------------|
| Core silently re-gutted by an unrelated refactor (Pitfall 1) | HIGH | Bisect against the requirement ledger to find the regressing commit; restore behavior from the `pre-27-pivot` tag or the last-known-green phase; add the missing regression test before closing the recovery |
| Carrier-allowlist drift discovered post-migration (Pitfall 2) | MEDIUM | Update `_CARRIER_NAMESPACE_PREFIXES` (or its shared-source-of-truth successor) to match the new taxonomy; no vault data changes needed; add the missing shared-source test |
| Embeddings/wikilinks lost during migration (Pitfall 3, 7) | HIGH | Re-run a targeted sweep for affected notes only (not full-vault, if paths are known); for wikilinks, use `search_vault` to find referencing notes and manually/programmatically repoint them; this is why a migration dry-run report is mandatory before committing |
| Malformed notes filed to `notes/` from over-automated processing (Pitfall 4, 6) | MEDIUM | `:check` batch-validates and flags non-compliant notes; the sweeper's non-destructive `_trash/`-only pattern means bad notes can be safely relocated to `_trash/` for review rather than hard-deleted |
| Orphan explosion / hub sprawl (Pitfall 5) | MEDIUM | Run `:graph` to enumerate orphans; batch-invoke `:connect` across the backlog; for hub sprawl, manually merge near-duplicate hubs and redirect wikilinks |
| Concurrent `:ralph` double-processing (Pitfall 8) | MEDIUM | Deduplicate any double-filed notes found via `:check`; add the missing lockfile/compare-and-swap guard before resuming normal use |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|----------------|
| Silent core regression during restructure | Cross-cutting — established in the first v0.6.0 phase (migration/scaffolding), enforced through every subsequent phase | Requirement ledger (MEM-0x + restored command surface) green at every phase boundary; full suite count never regresses |
| Taxonomy migration breaks Recall's carrier allowlist | Taxonomy-migration phase (PARA structure replacing flat-7) | Test asserting recency-weight membership matches the new taxonomy; shipped in the same phase as the classifier change |
| Embedding/sweeper blind spot during migration | Taxonomy-migration phase + pipeline-core phase (Reduce) | Frontmatter-preservation diff test on migrated notes; explicit embed-on-reduce policy decision recorded and tested |
| Over-automation of the 6 Rs pipeline | Command-system phase (`:ralph`, `:pipeline`, `:reweave`) | Explicit "no scheduled auto-processing" constraint recorded; malformed-output handling test |
| MOC/hub-note drift (orphan explosion or hub sprawl) | Command-system phase (`:connect`, `:stats`, `:graph`) + note-quality phase (`_schema`, `:review`) | Orphan-count trend tracked across a testing session; hub-similarity check before lazy creation |
| `_schema` enforcement at the wrong stage | Pipeline-core phase (Reduce) + note-quality phase (Verify) | Test: malformed LLM `_schema` output still results in a filed draft note, not a stall |
| Wikilink integrity across migration | Taxonomy-migration phase | Pre/post `:graph` dangling-link count diff as a Nyquist validation gate |
| 6 Rs pipeline on a stale/torn snapshot (no concurrency guard) | Command-system phase (`:ralph`, `:pipeline`) | Concurrent-invocation integration test; lockfile/compare-and-swap guard present |
| Local-model cost/latency compounding | Command-system phase (`:pipeline`) | Real-provider (LM Studio + exo) latency/context benchmark; idle-unload handling test |
| Background-task failures invisible to the user | Command-system phase (`:ralph`, `:pipeline`) | Simulated provider-failure test asserting a user-facing failure message |

---

## Sources

- `sentinel-core/app/services/note_intake.py`, `note_classifier.py`, `recall.py`, `vault_sweeper.py` — live code: flat-7 `TOPIC_VAULT_PATH`, `_CARRIER_NAMESPACE_PREFIXES`, `SWEEP_SKIP_PREFIXES`, lockfile pattern, compare-and-swap conflict detection
- `docs/2nd-brain-original-design/10-CONTEXT-master-spec.md` — original phase-10 design decisions D-01 through D-16, deferred ideas, canonical references
- `.planning/PROJECT.md` — v0.6.0 milestone scope, validated MEM-01..MEM-09 requirement history, phase-27 pivot context
- Git history: `pre-27-pivot` tag (end of phase 26) and the phase 27→42 commit trail confirming the core was rebuilt around provider/embeddings concerns with no note-taking regression gate
- `.planning/research/PITFALLS.md` (prior, v0.5.1) — inherited pitfalls this migration must not reintroduce (score-space collision, embedding staleness, ops/ exclusion bypass, O(N) HTTP latency)
- `https://github.com/agenticnotetaking/arscontexta` — checked directly; no documented anti-patterns/gotchas in the README (confirmed absence, not an omission in this research)
- Community sources (cross-checked, MEDIUM confidence) on PARA/BASB over-organization and Zettelkasten/MOC orphan-note decay: [PARA Method with AI in 2026](https://storyflow.so/blog/para-method-with-ai-2026), [PARA Method Review — Medium](https://medium.com/design-bootcamp/para-method-review-does-everyone-really-love-the-organizing-method-c7d1b1bb5ed7), [MOCs vs Zettelkasten — Obsidian Forum](https://forum.obsidian.md/t/mocs-vs-zettelkasten-an-80-20-approach-for-those-of-us-who-arent-luhmann/106518), [Why does Obsidian lead to a confusing Zettelkasten? — Zettelkasten Forum](https://forum.zettelkasten.de/discussion/1745/why-does-obsidian-lead-to-a-confusing-zettelkasten)

---
*Pitfalls research for: Sentinel of Mnemosyne v0.6.0 — Restore the Second-Brain Core (arscontexta + BASB)*
*Researched: 2026-07-05*
