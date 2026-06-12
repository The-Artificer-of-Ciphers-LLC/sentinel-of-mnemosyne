---
phase: 40
round: 4
reviewers: [codex, lm_studio]
reviewed_at: 2026-06-12T00:57:37Z
plans_reviewed: [40-04-PLAN.md, 40-05-PLAN.md, 40-06-PLAN.md, 40-07-PLAN.md]
convergence: "CONVERGED — both reviewers LOW risk, no remaining HIGH. Trajectory: r2 2×HIGH → r3 1×HIGH → r4 0×HIGH."
note: "claude skipped (self CLI); gemini/coderabbit/opencode/qwen/cursor/antigravity/ollama/llama_cpp not installed"
---

# Cross-AI Plan Review — Phase 40 (Gap Closure) — Round 4 (CONVERGED)

Final convergence confirmation over 40-04/05/06/07. Shipped 40-01..03 frozen.

## Codex Review

## Summary

The round-3 fixes are real and complete **by construction**.

For **G**, `40-04` no longer relies on caller discipline. The destructive gate moves from a permissive boolean to `safe_to_mutate: Callable[...] | None = None`, and the plan explicitly makes `None` fail closed inside `run_sweep`. Combined with the required test for `dry_run=False` + no probe => zero moves, and the startup/admin rewiring, that closes the original bypass class.

For **H**, `40-07` completes the degraded-index contract on the reader side. `40-04` introduces `stale: true`; `40-07` explicitly makes `SemanticRecall` skip `entry.get("stale")` before decode/score, with the right tests. That closes the stale-vector-at-query-time correctness gap.

Safe to execute: **yes**.

## Verification

- **G — RESOLVED**: destructive `run_sweep` is fail-closed with no probe, the permissive `model_loaded: bool = True` path is explicitly removed from `run_sweep`, startup no longer calls `run_sweep`, and the live admin path must supply the runtime probe.
- **H — RESOLVED**: `SemanticRecall.search` now skips `stale: true` entries before decode/score, with tests for stale-skipped, non-stale-unaffected, and all-stale-empty.

Earlier items re-check:

- **A — RESOLVED**: probe is re-evaluated immediately before each destructive move, with a flip-to-false mid-sweep test.
- **B — RESOLVED**: readiness probe is tied to the real structured-selection path and fails closed on defaulted/non-scored selections.
- **C — RESOLVED**: unsafe runs suppress classification frontmatter write-back; degraded classifier output is not persisted.
- **D — RESOLVED**: index path is single-sourced from `EMBEDDING_INDEX_PATH`; no duplicate literal approach remains.
- **E — RESOLVED**: 40-06 makes the inventory manifest authoritative and clearly warns that unarmed `LIVE_TEST` means no audit, not a clean result.
- **F — RESOLVED**: protected namespaces are explicitly enumerated and the scope decision is required in the summary.
- **Restore note — RESOLVED**: 40-05 explicitly records restore-via-write/copy, not relocate.

## New concerns

No real remaining **HIGH** concerns on this failure class.

No material regression risk is introduced against the 4 shipped Phase-40 success criteria. The plans preserve:
- sidecar-based semantic recall
- embedding-model mismatch skip
- RRF merge
- existing RetrievalStrategy seam

## Risk Assessment

Overall risk: **LOW**

Verdict: **CONVERGED**

---

## LM Studio Review

*(model: qwen3.6-35b-a3b — local, 64k context)*



## Summary
The round-3 fixes for **G** (permissive default bypass) and **H** (stale embedding correctness) are **closed by construction** in the submitted plans. The signature change on `run_sweep` forces probe injection, the `_is_safe()` helper explicitly handles `None` by returning `False`, and all call paths (startup, admin) are explicitly wired or tested against the fail-closed default. The reader-side completion of the degraded-index invariant correctly skips `stale: true` entries early in the candidate loop, handles missing keys safely, and preserves healthy behavior. Earlier-resolved items (A–F) remain structurally intact, with clean cross-plan scoping and explicit dependency ordering (`40-04 → 40-07 → 40-06`). No HIGH concerns remain on the failure classes that triggered the UAT blocker.

## Verification
| Item | Status | Reason |
|------|--------|--------|
| **G (HIGH)** | **RESOLVED** | The permissive `model_loaded: bool = True` default is explicitly removed. `run_sweep` now takes `safe_to_mutate: Callable[[], Awaitable[bool]] | None = None`. The local `_is_safe()` helper returns `False` when `safe_to_mutate is None`. A destructive run with no probe performs zero moves. All call sites (startup → `rebuild_embedding_index`; admin → `start_sweep` → `run_sweep`) are explicitly wired or tested against the fail-closed default. The bypass is closed by construction, not by caller discipline. |
| **H (Correctness)** | **RESOLVED** | `SemanticRecall.search` now checks `entry.get("stale")` early in the candidate loop, before decode/cosine scoring. Missing keys are safely falsy (proceeds normally). `stale: true` entries are skipped. All-stale degrades to `[]` cleanly. The reader-side completion of 40-04's degraded-index invariant is correctly scoped to `recall.py` (single-owner) and does not regress healthy recall behavior. |
| **A (Per-move re-eval)** | **INTACT** | 40-04 Task 3 explicitly re-evaluates `_is_safe()` before *each* destructive move. A probe that flips `False` mid-sweep stops all subsequent moves. |
| **B (Classifier readiness)** | **INTACT** | 40-04 Task 2 adds `probe_classifier_model_ready()` mirroring the structured `select_model` path. Fails closed on defaulted/non-scored selections. Admin probe ANDs this with embedding readiness. |
| **C (Frontmatter suppression)** | **INTACT** | 40-04 Task 3 gates step-3 classification write-back on the same per-note `_is_safe()` result. Degraded output is never persisted on unsafe runs. |
| **D (Single index path)** | **INTACT** | 40-07 Task 1 derives `RecallConfig.index_path` from `EMBEDDING_INDEX_PATH`. No duplicate literal. Equality guard + grep assertion prevent future divergence. |
| **E (40-06 inventory/LIVE_TEST)** | **INTACT** | 40-06 is a separate, read-only audit script. It depends on 40-04/05/07 but does not modify core logic. LIVE_TEST no-op warning and manifest-authoritative scanning are correctly scoped. |
| **F (40-05 protected set)** | **INTACT** | 40-05 adds `ProtectedPathError` and source/destination guards on `relocate`/`move_to_trash`. 40-04 explicitly catches it and continues. No file overlap; defense-in-depth holds. |

## New Concerns
- **LOW: Probe latency on long sweeps.** The fail-closed probe queries `/v1/models` (or `/api/v0/models`) before *every* destructive move. On a vault with thousands of notes, this could introduce noticeable latency or trigger API rate limits during a live sweep. This is a performance trade-off for safety, not a correctness failure. Mitigation: cache the probe result for the duration of a single sweep run, or document the expected latency budget. Does not block convergence.

## Risk Assessment
- **Safety/Correctness:** HIGH confidence. Both failure classes (bypass via permissive default, stale embedding leakage) are structurally closed. The fail-closed default, per-move re-evaluation, and early stale-skip are provably enforced by the signature change and loop placement.
- **Regression:** LOW. Cross-plan file scoping is explicit. Dependencies (`40-04 → 40-07 → 40-06`) are respected. Shipped success criteria (RetrievalStrategy seam, sidecar reads, model-mismatch skip, RRF merge) are untouched.
- **Operational:** LOW (probe latency on long sweeps, noted above).

## CONVERGED
The round-3 fixes for G and H hold by construction. No remaining HIGH concern exists on the failure classes that caused the production-down blocker. All call paths are explicitly wired or fail-closed. The degraded-index invariant is fully closed on the reader side. Earlier-resolved items (A–F) remain intact. **Safe to execute.**

---

## Consensus Summary — Round 4

**Convergence verdict: CONVERGED ✓** — both reviewers independently rate the set **LOW risk** with **no remaining HIGH concern** on the production-down failure class.

- **G [HIGH, round-3 residual] — RESOLVED by construction (both).** The permissive `model_loaded: bool = True` default is removed; `run_sweep` takes `safe_to_mutate: Callable | None = None` and `_is_safe()` fails closed (returns False) when the probe is None → a destructive sweep with no probe performs zero moves. Bypass closed by construction, not caller discipline.
- **H [correctness/MEM-05] — RESOLVED (both).** `SemanticRecall` skips `stale: true` entries before decode/score; recall.py single-owner; tests cover stale-skip / non-stale / all-stale→[].
- **A–F — intact, no regression (both).** Per-move probe eval, classifier fail-closed readiness, frontmatter suppression on unsafe runs, single index-path constant, 40-06 inventory/LIVE_TEST, 40-05 explicit protected set + write/copy restore note. The 4 shipped success criteria (RetrievalStrategy seam, sidecar reads, embedding_model-mismatch skip, RRF k≈60) are untouched.

### Only outstanding note — LOW, non-blocking (LM Studio)
The fail-closed probe queries `/v1/models` before *every* destructive move; on a large live sweep that's potential latency / rate-limit pressure. **Optional** execution-time mitigation: cache the model-list lookup briefly (keeping the per-move readiness *decision* intact), or document the latency budget. Does **not** block convergence or execution — track as a perf follow-up if a real sweep proves slow.

### Verdict
The 3-round replan↔review loop is complete. It caught a real guard bypass (round 2), a latent secure-by-default bypass (round 3), and a reader-side correctness gap (round 3) — all now closed. **Plans are safe to execute.**

Next: `/gsd-execute-phase 40` (waves 1–2 autonomous; 40-06 pauses for the live-vault operator checkpoint).
