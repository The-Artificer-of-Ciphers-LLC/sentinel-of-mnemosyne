---
phase: 40
reviewers: [codex, lm_studio]
reviewed_at: 2026-06-11T21:30:15Z
plans_reviewed: [40-04-PLAN.md, 40-05-PLAN.md, 40-06-PLAN.md]
note: "claude skipped (self CLI); gemini/coderabbit/opencode/qwen/cursor/antigravity/ollama/llama_cpp not installed"
---

# Cross-AI Plan Review — Phase 40 (Gap Closure)

Plans under review: **40-04, 40-05, 40-06** (the gap-closure plans closing the UAT startup-sweep blocker). Shipped plans 40-01..03 were supplied as frozen context only.

## Codex Review

## Summary

These three plans are directionally correct and probably close the immediate production-down incident: `40-04` removes the destructive startup path, `40-05` adds the right defense-in-depth guard at the Vault move primitives, and `40-06` adds the missing live-environment audit and re-verification. The main reason I would not call them fully safe yet is that the definition of “degraded” in `40-04` is too narrow and the degraded-index semantics are underspecified: the plan currently treats embedding availability as the sole trust signal for destructive moves, but the incident was fundamentally “bad model output drove file moves,” which is broader than “embedding model unavailable.” There is also a coordination gap between `40-04` and `40-05` around who owns sweeper-side exception handling and an audit-script completeness gap for collateral damage that did not retain provenance.

## Strengths

- `40-04` correctly attacks the root cause instead of papering over symptoms: boot should call an index-only routine, not `run_sweep`.
- `40-04` reuses `_emit_embedding_index` rather than inventing a second index-writing path, which lowers regression risk against MEM-05.
- `40-04` explicitly locks the boot path with a regression test that proves `initialize_startup` does not call `run_sweep`.
- `40-05` places protection at the lowest useful layer for this incident: `Vault.relocate` and `Vault.move_to_trash`, which is the right place to cover manual sweep, force-reclassify, and future callers.
- `40-05` correctly separates “skip-prefix” from “never movable,” which fixes the conceptual bug that caused `sentinel/` to be treated like ordinary content.
- `40-06` is appropriately non-autonomous and acknowledges that live-vault verification is required for the `.json` path and blast-radius audit.
- Wave ordering is mostly sane: fix the code path and primitive guard first, then re-run live UAT.

## Concerns

- `[HIGH]` `40-04` defines “degraded” too narrowly. It gates destructive behavior on `model_loaded` / embedder failure, but the destructive decisions come from classification and relocation logic, not just embedding generation. If the classifier degrades independently while embeddings are “available,” the same class of incident can still happen.
- `[HIGH]` The degraded full-sweep index behavior is underspecified and potentially wrong. `40-04` says degraded `run_sweep` should still emit index bookkeeping while skipping fresh vectors. If note content changed during that run, the plan does not state whether `content_hash` stays old or gets updated. Updating `content_hash` without a fresh vector would silently mark stale embeddings as current and can break MEM-05 correctness.
- `[HIGH]` `40-05` assumes existing sweeper branches safely catch `ProtectedPathError`, but the plan itself admits the noise-to-trash branch may not. Since `40-05` refuses to edit `vault_sweeper.py`, the integration guarantee is not self-contained. That is a cross-plan ownership hole.
- `[MEDIUM]` `40-05` protects only source paths. A future caller could still relocate arbitrary content into `sentinel/`, which does not recreate this exact incident but does violate namespace integrity.
- `[MEDIUM]` `40-05` defaults protection to only `sentinel/`, while the incident writeup refers to “other operator-critical paths” as possible scope. The plan has configurability, but it does not force the project to enumerate the full protected set before shipping.
- `[MEDIUM]` `40-06`’s blast-radius audit can miss damage if provenance was not written, was later overwritten, or if a note was deleted instead of relocated. It is good for “what still carries `original_path`,” not a complete forensic reconstruction.
- `[MEDIUM]` `40-06` says it will list “all other relocations in the incident window,” but the task description does not actually define or implement incident-window filtering logic.
- `[MEDIUM]` The `.json` rejection fallback in `40-06` is not really a verification step; it is a new code change affecting index path constants in at least two modules. That fallback deserves its own explicit micro-plan or at least declared file ownership and regression checks.
- `[LOW]` `40-05` frontmatter changes include `app/errors.py`, but that file is missing from `files_modified`. That is a plan hygiene issue, not a design flaw.
- `[LOW]` Some acceptance criteria rely on `grep` patterns that are brittle and weaker than behavior tests, especially `grep -c "run_sweep" == 0` in `composition.py`.

## Suggestions

- Expand `40-04`’s trust model from “embeddings unavailable” to “unsafe to mutate.” Make the guard hinge on every prerequisite for trustworthy destructive classification, not just the embedding model. If the classifier has its own readiness/probe signal, use it too.
- Specify degraded index invariants explicitly. In a degraded run, either:
  - do not rewrite index entries for changed notes at all, or
  - mark entries as stale in a way that prevents them from being treated as fresh.
  What must not happen is “new `content_hash`, old vector.”
- Move the sweeper-side `ProtectedPathError` handling into `40-04`, or make `40-05` formally depend on `40-04` for its integration test. Right now the boundary is fuzzy.
- Add a test that a full sweep with a healthy classifier but `ProtectedPathError` on `sentinel/persona.md` continues processing other notes and records a clear error, rather than aborting the whole run.
- Consider guarding destinations into protected namespaces as well, or at minimum add a deliberate decision note saying destination protection is intentionally out of scope.
- Before shipping `40-05`, explicitly enumerate the default protected namespaces required for boot-critical operation. If `sentinel/` is the only one, state that clearly; if not, bake the others into defaults now.
- Strengthen `40-06` by adding a second audit mode that compares current vault paths against a known-good inventory or namespace policy, because provenance-only scanning is not complete forensics.
- If the `.json` path might fail live, spin that fallback into a tiny explicit follow-up plan with tests, rather than burying a production behavior change inside a human checkpoint.

## Risk Assessment

**MEDIUM**

The plans are good enough to likely stop the exact startup crash-loop and prevent `sentinel/persona.md` from being moved again, which is the most important outcome. The residual risk is not trivial, though: the degraded-state model is still too optimistic, the stale-index behavior under degraded sweeps is not nailed down, and the cross-plan exception-handling ownership is muddy. I would approve these plans only after tightening those points, because otherwise they close the observed incident but still leave room for adjacent data-loss or silent recall-correctness regressions.

---

## LM Studio Review

*(model: qwen3.6-35b-a3b — local, no external egress)*



# Cross-AI Plan Review: Phase 40 Gap Closure (40-04, 40-05, 40-06)

## Summary
The three plans form a coherent, defense-in-depth strategy to close the Phase 40 UAT blocker. 40-04 correctly isolates the startup path to an index-only routine and introduces a degradation abort guard, while 40-05 enforces namespace protection at the lowest I/O primitive (Vault seam), ensuring no caller can move `sentinel/` files. 40-06 provides a necessary operator-facing audit and live verification checkpoint. Collectively, they address the root cause (destructive sweep on boot), add systemic safeguards, and verify recovery without regressing the four shipped success criteria. The wave dependency (40-04/05 parallel, 40-06 gated) and file ownership separation are clean. However, operational gaps around dynamic model state, blast-radius blind spots, and cross-plan handoffs prevent a LOW risk rating.

---

## Strengths
- **Defense-in-depth architecture:** 40-04 stops the destructive path at the orchestration level (startup/degradation), while 40-05 enforces protection at the I/O primitive (`relocate`/`move_to_trash`). This covers both current and future callers, satisfying the "never relocate `sentinel/`" requirement regardless of entry point.
- **Strict regression locking:** All plans explicitly preserve the 4 shipped criteria. 40-04 reuses `_emit_embedding_index` verbatim; 40-05 only adds guards; 40-06 is verification. No existing retrieval logic, RRF merge, or sidecar index contract is touched.
- **Clean wave dependency & file ownership:** 40-04 and 40-05 run in parallel (wave 1) with zero file overlap (`vault_sweeper.py`/`composition.py` vs `vault.py`/`config.py`). 40-06 correctly gates on both (wave 2). This enables safe parallel implementation and reduces merge conflict risk.
- **Threat modeling alignment:** STRIDE registers correctly identify boot→vault and degraded-output boundaries, with mitigations explicitly mapped to acceptance criteria. The `acquire_sweep_lock` reuse in 40-04 prevents concurrent index-vs-sweep races.

---

## Concerns
- **HIGH: Static degradation guard & race condition on first boot**  
  `graph.embedding_model_loaded` is evaluated once at boot. If the embedding model loads asynchronously, hot-swaps, or becomes available mid-session, the static flag won't update. A manually triggered full sweep after boot could still run destructively if the model loads between guard evaluation and execution. The plan assumes a static boolean but doesn't handle dynamic state changes or mid-sweep model availability shifts.

- **HIGH: Blast-radius audit misses "orphaned" notes**  
  The audit script relies on `original_path` frontmatter. If the bad sweep occurred before provenance was written, or if the vault was partially rolled back to v0.50.3 (which doesn't write this frontmatter), relocated files may lack this tag. The script will miss notes that were moved to `learning/persona/` (or elsewhere) without provenance, leaving residual blast radius undetected.

- **MEDIUM: Unverified try/except wrapping in `run_sweep`**  
  40-05 assumes existing `run_sweep` branches wrap `client.relocate`/`client.move_to_trash` in try/except. If a branch (e.g., noise→trash) lacks this, `ProtectedPathError` will crash the sweep instead of recording it in `report.errors`. The plan defers this to 40-04's summary, creating a cross-plan handoff risk that could leave a crash path unpatched.

- **MEDIUM: Admin endpoint wiring gap**  
  40-04 mentions "full sweep callers default `model_loaded=True`" but doesn't explicitly detail wiring the admin endpoint (`POST /vault/sweep/start` or similar) to pass the new parameter. If the admin endpoint bypasses the guard or defaults incorrectly, it remains a vector for destructive moves under manual override.

- **LOW: `.json` vs `.md` fallback constant sync**  
  40-06 notes a one-line change to `EMBEDDING_INDEX_PATH` and `RecallConfig.index_path`. If the REST API rejects `.json`, both constants must be updated atomically during redeploy, or recall will fail to read the index. The plan should explicitly track this dual-update as a single atomic step.

---

## Suggestions
- **Dynamic model probe in 40-04:** Replace the static `model_loaded` flag with a runtime probe (e.g., `probe_embedding_model_loaded()`) called *inside* `run_sweep` and `rebuild_embedding_index` before any destructive step. Document the operational constraint if static is retained (e.g., "model must be loaded before first boot").
- **Orphaned-note detection in 40-06:** Enhance the blast-radius script to scan `learning/persona/` (and other namespaces) for files matching `sentinel/` naming patterns or containing persona-like frontmatter, flagging them as potential orphaned relocations even without `original_path`. Add a `--dry-run` mode for safe testing.
- **Explicit try/except audit in 40-05:** Instead of deferring, explicitly verify and patch any `run_sweep` branch that lacks a try/except around `client.relocate`/`client.move_to_trash` to ensure `ProtectedPathError` is caught and recorded in `report.errors`. Add a test case for this.
- **Admin endpoint wiring:** Explicitly wire the admin sweep endpoint to pass `model_loaded=probe()` (or `True` by default) in 40-04, or defer it to a clearly marked follow-up with a risk assessment and operational runbook.
- **Atomic fallback update in 40-06:** Bundle the `.json` → `.md` constant change into a single atomic commit/PR with the 40-04/40-05 fixes to prevent a window where the sweeper writes `.json` but recall reads `.md` (or vice versa). Document the exact file paths and line numbers for the operator.

---

## Risk Assessment
**Overall Risk: MEDIUM**

**Justification:**  
The plans are structurally sound and correctly isolate the blocker. The defense-in-depth approach (boot path isolation + primitive-level guard) strongly mitigates data-loss risk, and regression risk to the 4 shipped criteria remains LOW. However, the static degradation guard, potential admin endpoint wiring gap, and blast-radius audit blind spots introduce operational risks that could leave residual vault corruption or allow destructive sweeps under specific conditions. These are manageable with the suggested enhancements but prevent a LOW rating. The wave ordering is correct, file ownership is clean, and the threat model aligns with the mitigations. With the HIGH/MEDIUM concerns addressed, the plans will safely close the incident without regressing shipped functionality.

---

## Consensus Summary

Two independent reviewers (Codex/GPT and a local Qwen3.6-35B) converged on the same picture: the three plans are **directionally correct and likely stop the exact crash-loop**, but carry residual data-loss / recall-correctness risk until a few points are tightened. **Overall risk (consensus): MEDIUM.**

### Agreed Strengths
- **Root-cause fix, not symptom patch** — 40-04 makes boot call an index-only routine instead of the destructive `run_sweep`.
- **Defense-in-depth** — orchestration-level guard (40-04) *plus* protection at the lowest I/O primitive (40-05 `Vault.relocate`/`move_to_trash`), which covers manual sweep, force-reclassify, and future callers.
- **Strict regression locking** — the 4 shipped success criteria are preserved; 40-04 reuses `_emit_embedding_index`; no retrieval / RRF / sidecar-contract code is touched.
- **Clean wave & file ownership** — 40-04 ∥ 40-05 with zero file overlap; 40-06 correctly gated on both and correctly `autonomous: false` for live-vault work.

### Agreed Concerns (raised by BOTH — highest priority)
1. **[HIGH] Degradation guard is too narrow and too static.** Gating destructive moves only on embedding `model_loaded`, evaluated once at boot, misses (a) bad *classifier* output (the moves are classifier-driven, not just embedding-driven) and (b) async / mid-session model load. **Fix:** probe model/classifier readiness at runtime *inside* `run_sweep` before any destructive step; broaden the signal from "embeddings unavailable" to "unsafe to mutate."
2. **[HIGH] Cross-plan ownership hole on sweeper exception handling.** 40-05 assumes `run_sweep` branches catch `ProtectedPathError`, but 40-05 refuses to edit `vault_sweeper.py` and the noise→trash branch may be unwrapped → an uncaught `ProtectedPathError` would crash the whole sweep. **Fix:** move the sweeper-side handling into 40-04 (or make 40-05 formally depend on it) and add a test that a sweep hitting a protected path keeps processing other notes and records the error.
3. **[HIGH/MED] Blast-radius audit is blind to provenance-less damage.** It keys on `original_path` frontmatter; files moved before provenance was written, after the v0.50.3 rollback, or deleted-not-moved are missed. **Fix:** add a second audit mode comparing the live vault against a known-good inventory / namespace policy, and scan target namespaces (e.g. `learning/persona/`) for persona-like files.
4. **[MED] The `.json`→`.md` fallback is a real production code change** (two constants in two modules) buried inside a human checkpoint. **Fix:** pull it into its own small follow-up plan with tests; treat the dual-constant update as one atomic change.

### Divergent Views (single reviewer — worth investigating)
- **Codex only [HIGH]:** degraded-sweep *index invariant* — if a degraded run rewrites `content_hash` without a fresh vector, stale embeddings get marked current → MEM-05 recall-correctness risk. Specify: in a degraded run, do NOT rewrite index entries for changed notes (or mark them stale).
- **Codex only [MED]:** only *source* paths are protected — a caller could still relocate content *into* `sentinel/` (destination protection); and the default protected set should enumerate the "other operator-critical paths" now, not just `sentinel/`.
- **Codex only [LOW]:** `app/errors.py` is absent from 40-05 `files_modified`; some `grep`-based acceptance criteria (e.g. `run_sweep` count == 0) are brittle vs behavior tests.
- **LM Studio only [MED]:** admin sweep endpoint wiring — ensure `POST /vault/sweep/start` passes `model_loaded`(probe) and cannot bypass the guard.

### Recommended next step
The four agreed concerns are concrete and plan-level. To fold them in:

```
/gsd-plan-phase 40 --reviews
```

Concerns 1–2 (the two HIGH cross-cutting items) are worth resolving before executing Wave 1; concern 3 (audit completeness) before running 40-06's live audit; concern 4 can become a follow-up plan.
