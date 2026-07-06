# Project Research Summary

**Project:** Sentinel of Mnemosyne
**Domain:** Agentic note-taking / personal knowledge management engine (arscontexta + Building a Second Brain), fused into an existing FastAPI/Discord/Obsidian-REST/LiteLLM assistant
**Researched:** 2026-07-05
**Confidence:** MEDIUM-HIGH

## Executive Summary

v0.6.0 rebuilds the arscontexta+BASB note-taking core that the phase-27 "Path B" pivot unintentionally gutted -- three-space vault (self/notes/ops/inbox/templates/), PARA taxonomy, the 6 Rs pipeline (Record to Reduce to Reflect to Reweave to Verify to Rethink), _schema/claim-titles/wikilinks, MOC/hub notes, and the 27-command surface -- built on top of, not instead of, the post-phase-39 architecture (Recall module, semantic recall, embeddings-through-Sentinel, Pathfinder). All four researchers converged independently on the same core finding: the Discord command surface is already routed (command_router.py/bot.py dispatch all 27 commands today), so the actual gap is not "wire up the commands" but build the 6 Rs pipeline as real backend orchestration. Today :ralph/:pipeline/:reweave are single fixed-text prompts (_SUBCOMMAND_PROMPTS) sent through call_core() to one ai_provider.complete() call -- no tool-calling, no vault mutation loop, no per-phase context isolation. The Discord reply looks like a completed pipeline run while the vault is untouched. Recognizing this distinction (routing vs. orchestration) is the single most important reframe for phase sequencing.

The recommended approach requires zero new runtime dependencies -- every capability (footer _schema block parsing, wikilink regex extraction, graph metrics, a links-index sidecar, background pipeline orchestration) is achievable by extending patterns already present in sentinel-core/app/ (markdown_frontmatter.py, embedding_sidecar_index.py, task_runner.py, note_classifier.py's structured-output pattern) using dependencies already pinned (PyYAML, pydantic, stdlib). The 6 Rs pipeline should be implemented as a six_rs/ package of independent, structured-completion phases (mirroring note_classifier.classify_note()) driven by a new pipeline_orchestrator.py scheduled via the existing AsyncioTaskRunner seam -- architecturally cloned from the proven vault_sweeper.py/sweep_status_store.py background-task template, never inlined into MessageProcessor. PARA taxonomy replacing the flat-7 classifier is a breaking change, not an addition: learning/reference content routes to inbox/ for Reduce instead of directly to flat category folders, while journal/accomplishment/observation keep directory filing but move under ops/ subdirectories. notes/ itself stays flat (no topic subfolders) -- MOC/wikilink navigation replaces directory-based organization.

The dominant risk is repeating the exact failure that created this milestone: the core was gutted at phase 27 via a refactor scoped around an unrelated concern (Pi-harness removal), with no regression contract to catch the silent loss. v0.6.0 must carry a MEM-0x + restored-command-surface regression ledger checked at every phase boundary -- not just at milestone close. Two further code-grounded, silent-regression traps were found by direct inspection: recall.py's _CARRIER_NAMESPACE_PREFIXES hardcodes flat-7 paths as a second, independently-maintained copy of the taxonomy map -- migrating the taxonomy without updating this allowlist silently degrades recency weighting with zero test failures; and vault_sweeper.py's SWEEP_SKIP_PREFIXES never embeds inbox/, which is fine today but becomes a recall blind-spot once inbox/ is a first-class, longer-lived pipeline staging area. Both must be fixed in the same phase that introduces the taxonomy change, not deferred.

## Key Findings

### Recommended Stack

Zero new dependencies. Extend app/markdown_frontmatter.py with symmetric split_footer_schema()/join_footer_schema() functions (footer fence, not header -- arscontexta's _schema block sits at the end of the note, structurally distinct from existing leading YAML frontmatter). Add a small wikilinks.py module (compiled regex, same style as _FRONTMATTER_RE) and a NoteSchema pydantic model for :review/:check validation. Persist a links/graph sidecar (ops/sweeps/links-index.json) using the exact JSON-in-markdown-fence pattern already established by embedding_sidecar_index.py, computed in the same sweep pass that already computes embeddings. Graph metrics (orphans, backlinks, density) are hand-rolled dict/set/Counter operations over that sidecar -- explicitly rejecting networkx/obsidiantools as unwarranted dependency surface for personal-vault scale. The 6 Rs pipeline is prompt-driven AI reasoning through the existing litellm/LM Studio path, orchestrated via the existing AsyncioTaskRunner.schedule() seam -- explicitly rejecting APScheduler/Celery/RQ (no periodic/distributed requirement) and any anthropic/Claude SDK call (hard constraint: local-model-only processing path).

**Core technologies:**
- PyYAML (existing pin) -- parse/emit the new footer _schema fence, symmetric to existing frontmatter handling
- pydantic (existing pin) -- NoteSchema validation backing :review/:check
- stdlib re/json/asyncio -- wikilink extraction, links-index sidecar, pipeline orchestration
- Existing AsyncioTaskRunner/TaskRunner seam -- background execution for :ralph/:pipeline/:reweave, cloned from the sweeper's proven shape
- litellm (existing) -- 6 Rs stage completions via the existing LM Studio/local-model provider path only

### Expected Features

**Must have (table stakes):** three-space vault structure (self/notes/ops/inbox/templates/) with migration from core/; session-start reading pattern (self/*.md, ops/reminders.md) -- largely already implemented via RecallConfig.self_paths; PARA taxonomy replacing flat-7 (/note/classify and /vault/sweep re-specified -- a breaking change, not layered addition); _schema block + claim-title + wikilink note-quality standard with :review/:check; Record to Reduce to Reflect (6 Rs stages 1-3) via :capture/:seed/:ralph; MOC/hub notes created lazily via :connect; core command subset (:capture :seed :ralph :pipeline :connect :review :check :stats :graph :help); non-destructive writes preserved (_trash/ relocation only, never hard-delete).

**Should have (differentiators):** Reweave (backward-pass note revision -- BASB's Distill phase, depends on a populated graph existing first); operational learning loop (ops/observations/, ops/tensions/ to threshold-triggered :rethink); :graph/:stats vault health analytics (orphans, link density, dangling links); reuse of the existing SemanticRecall embedding index for :connect/:reweave candidate-finding (genuine head start -- flag explicitly so planning doesn't reinvent retrieval); task-stack (:tasks/:next).

**Defer (v2+):** true fresh-context-per-phase orchestration (separate sequential call_core() calls per 6 Rs stage) unless D-13's single-prompt approach shows measurable quality degradation; plugin-tier meta-commands (:plugin:health, :plugin:architect, etc.); vault-wide backfill of pre-milestone notes to the new _schema standard (grandfather-vs-backfill decision explicitly unresolved -- flag for requirements); multi-domain extension.

**Anti-features (do not build):** literal port of arscontexta's Claude Code hooks (SessionStart/PostToolUse/git-auto-commit -- Sentinel has no filesystem-hook or subagent runtime); scheduled/cron vault reorganization (violates BASB's just-in-time organization principle); auto-running :pipeline on every message without being asked; PARA subfolders inside notes/ (violates the flat-namespace invariant); auto-updating self/identity.md from inferred behavior without confirmation; indexing Sentinel's own generated replies as graph content; over-retrieval (exhaustive scan-and-dump) during :connect/:reweave candidate search.

### Architecture Approach

The command-routing layer needs no rework -- :capture/:seed/:note/:inbox/:vault-sweep/:pf stay unchanged. The pipeline-shaped commands (:ralph/:pipeline/:reweave/:check/:rethink/:graph/:stats/:review/:connect) swap from call_core(fixed_prompt) to new dedicated endpoints backed by real orchestration. POST /message/MessageProcessor stays deliberately untouched -- the pipeline is a background task, not a chat turn, avoiding the exact layering mistake ADR-0003 already rejected for Recall.

**Major components:**
1. pipeline_orchestrator.py + pipeline_status_store.py (new) -- background 6 Rs orchestration, cloned from vault_sweeper.run_sweep/sweep_status_store.py's proven admin-gated, pollable-status shape
2. six_rs/{reduce,reflect,reweave,verify,rethink}.py (new package) -- independent structured-completion calls per phase, mirroring note_classifier.py's model-resolution + JSON-schema-constrained completion pattern; each phase gets only minimal context, never the full conversational Hot/Warm tier
3. note_schema.py, graph_analysis.py, moc_maintenance.py (new) -- trailing _schema block parse/validate, orphan/backlink/density computation over the links-index sidecar, lazy hub create/append with bidirectional wikilinks -- hub-matching reuses the existing embedding sidecar (SemanticRecall machinery) before falling back to a fresh LLM call
4. note_classifier.py/vault_sweep_plan.py/vault_sweeper.py (modified) -- taxonomy routing splits notes-bound (to inbox/ for Reduce) vs. ops-bound (to ops/{journal,accomplishments}/); topic-dir relocation for notes-bound content retired

### Critical Pitfalls

1. **Silent core regression during restructure (repeating phase-27)** -- enumerate the pre-27 command surface and MEM-01..MEM-09 as two parallel requirement ledgers; every phase must gate on both staying green, plus a standing full-suite regression run, not just at milestone close.
2. **Taxonomy migration silently breaks Recall's carrier allowlist** -- recall.py's _CARRIER_NAMESPACE_PREFIXES is a hand-maintained second copy of the taxonomy map; migrating without updating it degrades recency weighting with zero test failures. Must ship in the same phase as the classifier change, ideally as a single shared source of truth.
3. **Embedding/sweeper blind spot during pipeline migration** -- inbox/ is never embedded (SWEEP_SKIP_PREFIXES), which is correct today but becomes a recall blind-spot once inbox/ is a longer-lived staging area; migration moves must preserve embedding_b64/embedding_model frontmatter (rename, not delete+recreate) or trigger a costly full-vault re-embed.
4. **Over-automation of the 6 Rs pipeline against a bounded local model** -- keep :ralph/:pipeline strictly user-invoked in this milestone; never gate Reduce's success on passing the same validation bar :review uses -- file as _schema.status: draft and let Verify catch imperfection, don't stall the pipeline.
5. **Wikilink integrity breaks across the taxonomy migration** -- a naive write-new-path+delete migration silently orphans every [[wikilink]] referencing the old path; must verify empirically whether wikilinks are title- or path-keyed before assuming risk, and treat pre/post :graph dangling-link count as a Nyquist validation gate.

## Implications for Roadmap

All four researchers converge on the same four-phase build order, driven by hard dependency edges (schema/graph needs the taxonomy decided first; the pipeline needs schema+graph to validate/connect against).

### Phase A: Vault Namespace + Taxonomy Foundation
**Rationale:** Everything downstream (PARA, _schema, MOCs, session-start reads) assumes the self/notes/ops/inbox/templates structure and taxonomy routing already exist. This is the correct, lowest-risk starting point -- it changes a routing table and directory conventions, not core retrieval behavior.
**Delivers:** notes//templates/ namespaces (lazy-create per existing D-14 pattern); note_classifier.TOPIC_VAULT_PATH split into notes-bound (to inbox/) vs. ops-bound (to ops/{journal,accomplishments}/); narrowed vault_sweep_plan.py/vault_sweeper.py topic-dir move scope; PROTECTED_NAMESPACES and RecallConfig.exclude_prefixes gain templates/ (confirm notes/ stays un-excluded); a one-time, reviewable migration of existing flat-7 content.
**Addresses:** three-space vault, PARA taxonomy replacing flat-7 (FEATURES.md P1 items).
**Avoids:** Pitfall 2 (carrier-allowlist drift -- must ship the recall.py update in this same phase), Pitfall 3 (embedding/wikilink preservation during migration), Pitfall 7 (wikilink integrity across migration).

### Phase B: Note-Quality Schema + Graph Analysis (additive, read-mostly)
**Rationale:** Read/analysis endpoints with no chat-path coupling -- safe to build once notes/+templates/ exist and taxonomy routing is decided, without waiting on the pipeline orchestrator.
**Delivers:** note_schema.py (trailing _schema: parse/validate), graph_analysis.py (orphans/triangles/density/hub membership), moc_maintenance.py (lazy hub create/append); :review, :check, :graph, :stats, :connect swap from fixed-prompt call_core() to real structured endpoints.
**Uses:** the links-index sidecar pattern from STACK.md (mirrors embedding_sidecar_index.py); reuses SemanticRecall's embedding infrastructure for hub-candidate matching before falling back to an LLM call (Architecture Pattern 4).
**Implements:** the note-quality standard (_schema+claim-title+wikilinks) and MOC/hub navigation layer from FEATURES.md.

### Phase C: 6 Rs Pipeline Orchestrator (highest complexity)
**Rationale:** This is the actual "restore the core" work -- the gap every researcher flagged as the real missing capability, not the already-routed command surface. Requires Phase A's taxonomy decision (what counts as an inbox entry destined for Reduce) and Phase B's schema/graph (Verify and Reflect depend on them).
**Delivers:** pipeline_orchestrator.py + pipeline_status_store.py (cloned from the sweeper's proven background-task shape); six_rs/{reduce,reflect,reweave,verify,rethink}.py as independent structured completions; POST /vault/pipeline/start / GET /vault/pipeline/status (admin-gated, mirrors /vault/sweep/*); :ralph/:pipeline/:reweave/:rethink swap to these new endpoints; a concurrency guard (lockfile or compare-and-swap, mirroring the sweeper's/NoteIntake's existing patterns) and explicit success/partial/failure reporting back to Discord (not fire-and-forget).
**Addresses:** Record to Reduce to Reflect to Reweave to Verify to Rethink (all 6 Rs stages), the pipeline's actual note-organizing output.
**Avoids:** Pitfall 4 (over-automation/unattended triggers -- keep strictly user-invoked), Pitfall 5 (orphan explosion -- make :ralph refuse to mark "processed" without a successful Reflect), Pitfall 6 (_schema enforcement at the wrong stage -- file as draft, don't block Reduce on Verify-grade validation), Pitfall 8 (concurrency -- no double-processing), Pitfall 9 (local-model cost/latency compounding -- benchmark against the real configured provider, including exo's idle-unload behavior, before committing to a single-completion :pipeline), Pitfall 10 (silent background-task failure -- must report actual outcome, deviating from the session-summary fire-and-forget pattern).

### Phase D: Migration Completion + Cutover Hardening
**Rationale:** Full-vault migration and retirement of dead directory-routing code should only happen once A-C are validated against real Discord traffic -- doing it earlier risks a destructive migration against a still-shifting taxonomy.
**Delivers:** completion of remaining flat-7 content migration; removal of now-dead directory-routing code paths; USER-GUIDE.md/README.md updates reflecting the new background-task UX for pipeline commands; full regression + live UAT pass.
**Addresses:** the grandfather-vs-backfill decision for pre-milestone notes (FEATURES.md open question), final cutover.

### Phase Ordering Rationale

- **A gates B, B gates C** -- pure dependency: graph_analysis.py's code can be unit-tested against FakeVault fixtures without waiting for real pipeline output, but nothing meaningful exists in notes/ until A's taxonomy routing and, eventually, C's Reduce phase populate it. six_rs.reflect needs B's graph_analysis/moc_maintenance; six_rs.verify needs B's note_schema.
- **Reweave/:rethink/:refactor are correctly late** -- nothing to reweave, rethink, or refactor against on an empty or freshly-migrated vault; these depend on Reduce+Reflect already populating a non-trivial graph.
- **This order directly avoids the phase-27 anti-pattern**: each phase's scope is narrow and explicit (taxonomy OR schema/graph OR orchestrator OR migration), so a regression ledger can attribute any MEM-0x or command-surface breakage to a specific phase rather than discovering it silently, months later, the way phase 27's Pi-harness removal did.
- **Phase C should be feature-flagged/left unwired in Discord until its own regression pass is green** -- it is the highest-complexity, most-new-code phase and the one most likely to need iteration before user-facing exposure.

### Research Flags

Needs deeper research during planning:
- **Phase C (6 Rs pipeline orchestrator):** the single-prompt-vs-per-stage-isolation tradeoff (D-13 cheap approach vs. true fresh-context-per-phase) needs a real local-model latency/context benchmark against both configured providers (LM Studio and exo) before locking the design -- recommend starting with the single-prompt approach and validating quality before adding per-stage isolation.
- **Phase A (migration):** wikilink title-vs-path-keying needs an empirical check against the live Obsidian vault before finalizing the migration approach (rename vs. copy+relink).

Phases with standard, well-documented patterns (skip --research-phase):
- **Phase B:** directly clones embedding_sidecar_index.py's JSON-sidecar pattern and note_classifier.py's structured-completion pattern; no novel technology.
- **Phase D:** migration completion and doc updates follow the non-destructive _trash/-only pattern already established.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Existing-code claims verified by direct read of sentinel-core/app/; arscontexta claims verified via raw GitHub file fetch but tool-classified LOW-confidence source -- cross-check against the live upstream repo before implementation |
| Features | MEDIUM-HIGH | Primary-source repo content (README, three-spaces.md, kernel.yaml) for arscontexta mechanics is HIGH confidence; BASB/PARA framing is well-established public methodology (MEDIUM); Sentinel-specific constraints sourced from PROJECT.md and the recovered phase-10 master spec (HIGH) |
| Architecture | HIGH/MEDIUM | HIGH for current-codebase findings (production source, ADRs, phase-10 spec); MEDIUM for arscontexta upstream pattern citations (single WebFetch pass, not independently cross-verified) |
| Pitfalls | HIGH/MEDIUM | HIGH for integration-specific pitfalls (grounded in live code and git history including the pre-27-pivot tag); MEDIUM for general second-brain/Zettelkasten domain patterns, triangulated from adjacent-methodology community sources |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Grandfather vs. backfill existing flat-7 notes to the _schema standard** -- not resolved by research; requirements/planning must decide whether pre-milestone notes are retroactively brought up to standard via a batch :check/:review pass, or grandfathered with the new standard applying only going forward.
- **:ralph/:pipeline orchestration depth** -- single-prompt (D-13, cheap, current design) vs. true per-stage isolated call_core() calls (faithful to arscontexta's "fresh context per phase" principle, costlier). Recommend starting with the former for MVP and treating per-stage isolation as a differentiator to add once quality gaps are observed in production use.
- **Title-keyed vs. path-keyed wikilinks** -- Obsidian's wikilink resolution behavior against this specific vault needs an empirical check before finalizing the migration/rename strategy; assuming REST semantics without verification risks silently breaking cross-references.
- **Local-model pipeline cost/latency** -- no real benchmark exists yet for a single-completion :pipeline run against either configured provider (LM Studio, exo); exo's idle-unload/404 behavior in particular needs explicit handling, not silent failure. Must be benchmarked as part of Phase C's own verification, using the existing provider-registry (phase 42) work.

## Sources

### Primary (HIGH confidence)
- Direct reads of production source: sentinel-core/app/vault.py, app/services/message_processing.py, app/services/recall.py, app/services/note_classifier.py, app/services/vault_sweep_plan.py, app/services/vault_sweeper.py, app/services/task_runner.py, app/services/note_sweep_runner.py, app/services/sweep_status_store.py, app/services/embedding_sidecar_index.py, app/routes/note.py, app/markdown_frontmatter.py, interfaces/discord/command_router.py, interfaces/discord/bot.py
- docs/2nd-brain-original-design/10-CONTEXT-master-spec.md -- recovered phase-10 master spec (D-01 through D-16)
- .planning/PROJECT.md, CONTEXT.md, docs/adr/0001-0006 -- current milestone scope, validated MEM-01..MEM-09 history, architectural precedent
- Git history: pre-27-pivot tag and the phase 27-43 commit trail confirming the core was rebuilt around provider/embeddings concerns with no note-taking regression gate
- https://raw.githubusercontent.com/agenticnotetaking/arscontexta/main/README.md, reference/three-spaces.md, reference/kernel.yaml -- direct repository fetch (not summarized)

### Secondary (MEDIUM confidence)
- /yaml/pyyaml, /networkx/networkx (Context7) -- version/API confirmation and "rejected as overkill" grounding
- WebFetch digest of github.com/agenticnotetaking/arscontexta general repo overview
- Web search on Tiago Forte's Building a Second Brain (PARA/CODE framework, just-in-time organization principle)
- Community sources on PARA/BASB over-organization and Zettelkasten/MOC orphan decay (Obsidian Forum, Zettelkasten Forum, Medium)

### Tertiary (LOW confidence)
- WebFetch of agenticnotetaking/arscontexta (tool-classified LOW by the harness despite being a direct primary-source fetch) -- cross-check against the live repo before implementation, per STACK.md's own flag
- python-frontmatter, obsidiantools (WebSearch) -- used only to identify and reject alternatives

---
*Research completed: 2026-07-05*
*Ready for roadmap: yes*
