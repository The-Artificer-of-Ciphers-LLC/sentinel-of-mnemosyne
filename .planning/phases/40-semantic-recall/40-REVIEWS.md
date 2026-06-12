---
phase: 40
round: 3
reviewers: [codex, lm_studio]
reviewed_at: 2026-06-12T00:34:52Z
plans_reviewed: [40-04-PLAN.md, 40-05-PLAN.md, 40-06-PLAN.md, 40-07-PLAN.md]
convergence: "narrowing split — Codex: HIGH/not-converged (1 residual: permissive run_sweep default); LM Studio: LOW/converged. Down from 2 HIGH in round 2."
note: "claude skipped (self CLI); gemini/coderabbit/opencode/qwen/cursor/antigravity/ollama/llama_cpp not installed"
---

# Cross-AI Plan Review — Phase 40 (Gap Closure) — Round 3

Final convergence check over round-2-revised 40-04/05/06/07. Shipped 40-01..03 frozen.

## Codex Review

## Summary

`40-05`, `40-06`, and `40-07` are materially tightened and look executable. `40-04` is much better than round 2, and the stale-decision bug inside `run_sweep` is addressed in the plan text.

I do **not** think the set is converged yet. There is still one **HIGH** gap on the original failure class: `run_sweep` keeps a permissive `model_loaded: bool = True` fallback, and the plan does not close or prove away every direct caller. That means the new fail-closed probe can still be bypassed by any missed/current/future caller that invokes `run_sweep(..., model_loaded=True)` without `safe_to_mutate`. For this incident class, that is still too much residual risk.

## Round-2 Verification

- **A — RESOLVED**: The revised 40-04 text now requires `safe_to_mutate()` immediately before each `relocate` / `move_to_trash` in all three destructive branches, plus a flip-to-false mid-sweep test.
- **B — PARTIAL**: The new `probe_classifier_model_ready()` itself is correctly fail-closed, but `run_sweep` still allows a boolean fallback path that can bypass that probe unless all callers are exhaustively locked down.
- **C — RESOLVED**: 40-04 now explicitly suppresses classification frontmatter write-back on unsafe runs and requires byte-identical-note assertions.
- **D — RESOLVED**: 40-07 removes the duplicate literal approach and makes `RecallConfig.index_path` derive from the single index-path constant, with case-insensitive extension handling.
- **E — RESOLVED**: 40-06 now defines two audit modes, makes `--inventory` strongly recommended, enumerates every protected namespace, and clearly marks missing `LIVE_TEST=1` as a no-audit skip.
- **F — RESOLVED**: 40-05 records the protected-set decision explicitly and requires an explicit literal tuple default.

## New Concerns

- **HIGH**: `40-04` keeps `run_sweep(..., model_loaded: bool = True)` as a live fallback. Without either removing that fallback for destructive sweeps or proving all call sites are routed through `safe_to_mutate`, the degraded-classifier guard is not closed by construction.
- **MEDIUM**: `40-06`’s built-in canonical inventory can drift from reality unless the manifest path is used consistently; that is acceptable operationally, but it is still weaker than a generated inventory source.
- **LOW**: `40-05` destination protection will also block relocate-based restores into protected namespaces; the operator restore path should be documented explicitly as write/copy, not relocate.

## Risk Assessment

Overall risk: **HIGH**

Verdict: **NOT CONVERGED**

To converge, I would require one of these in `40-04`:

1. Remove the boolean fallback for destructive execution entirely, or  
2. Make `safe_to_mutate` mandatory for non-dry-run `run_sweep`, or  
3. Add an explicit repo-wide callsite lock proving every production caller passes the fail-closed probe and no direct bypass remains.

Until that is closed, there is still a real path to destructive moves on degraded model state.

---

## LM Studio Review

*(model: qwen3.6-35b-a3b — local, 64k context)*



# Cross-AI Plan Review — ROUND 3 (Final Convergence Check)

## 1. Summary
The revised plans directly and surgically address every Round-2 concern. The fixes are not nominal; they are structurally enforced in the control flow, explicitly tested against the exact failure modes, and documented to prevent silent regression. The core failure class (destructive file moves on degraded model state / stale guard decisions) is closed by:
- Replacing the "evaluate once per sweep" pattern with a per-move `_is_safe()` helper that re-evaluates the probe immediately before every `relocate`/`move_to_trash`.
- Binding the probe to the classifier's actual readiness path, explicitly passing `default=None` and hard-gating on `_score("structured", id) > 0` to reject defaulted/last-resort selections.
- Suppressing classification frontmatter write-back on unsafe runs and enforcing a deterministic degraded-index invariant (`stale: true`).
- Eliminating duplicate index-path literals by construction, making the `.json`→`.md` fallback a single-constant flip with case-insensitive fenced-JSON round-trip tests.
- Explicitly enumerating the protected set, documenting the scope decision, and hardening the audit script's no-op behavior.

The plans are ready for execution. No structural gaps remain that would allow a destructive move on a degraded model state.

---

## 2. Round-2 Verification (A–F)

| Concern | Status | Why (Verification) |
|:---|:---:|:---|
| **A. Guard evaluated ONCE per sweep, stale decision** | **RESOLVED** | Task 3 (40-04) explicitly replaces the single-check pattern with a local `async def _is_safe()` that calls `await safe_to_mutate()` **immediately before every** `client.relocate` / `client.move_to_trash` in all three branches. The test injects a stateful coroutine that returns `True` then flips to `False` mid-sweep, asserting that moves stop at the flip point. The stale-decision path is structurally closed. |
| **B. Probe was a generic "chat model" proxy; `select_model()` returns DEFAULT, falsely reporting "ready"** | **RESOLVED** | Task 2 (40-04) explicitly passes `default=None` to `select_model("structured", ...)` so rules 3/5 cannot fire, and adds a hard guard: `if _score("structured", returned_id) <= 0: return False`. A defaulted or last-resort model that lacks function-calling scores `0`, causing the probe to return `False`. Tests cover empty list, non-scored loaded model, and HTTP failure. The false-ready path is closed. |
| **C. Degraded classifier output written to frontmatter on unsafe runs** | **RESOLVED** | Task 3(b) gates step-3 frontmatter write-back on the exact same per-note `_is_safe()` result. When unsafe, `write_note` is skipped entirely. Tests assert `report.topic_moves == 0`, `report.noise_moved == 0`, and every input note remains byte-identical. Degraded output is never persisted. |
| **D. 40-07 allowed "duplicate literals + assertion" for index path** | **RESOLVED** | Task 1 (40-07) explicitly forbids the duplicate-literal alternative. `RecallConfig.index_path` now defaults to the imported `EMBEDDING_INDEX_PATH`. The literal string exists in exactly one module. Case-insensitive extension checking (`path.lower().endswith(".md")`) is implemented. Single-source-of-truth is enforced by construction, not just assertion. |
| **E. 40-06 inventory mode heuristic / `--inventory` optional / LIVE_TEST no-op unclear** | **RESOLVED** | Task 1 (40-06) enforces a prominent docstring + distinct exit/banner stating that running without `LIVE_TEST=1` performs **NO audit** and is **NOT a clean-vault result**. `--inventory` is strongly recommended, with a fallback per-namespace canonical map. `--dry-run` is explicitly documented as an affirmation flag (read-only regardless). Operator misinterpretation risk is eliminated. |
| **F. 40-05 protected set was implicit** | **RESOLVED** | Task 1 (40-05) mandates an explicit literal tuple default (`("sentinel/", "self/", "security/")`) and requires the final shipped scope + rationale to be recorded in the 40-05 SUMMARY. Implicit regression is structurally prevented by code + documentation. |

---

## 3. New Concerns (Post-Review)

| Concern | Severity | Notes |
|:---|:---:|:---|
| **Lazy import fallback for `ProtectedPathError` (40-04 Task 3)** | LOW | If 40-05 hasn't merged in an isolated run, the plan falls back to catching broad `Exception`. This is safe but requires strict CI merge ordering (40-05 before 40-04, or explicit `depends_on` gating). Not a convergence blocker. |
| **`stale: true` index schema extension (40-04 Task 3)** | LOW | Introducing a new `stale` field to the index JSON requires the recall loader to explicitly skip `stale: true` entries. The plan notes the invariant but doesn't show the recall-side consumer update. A one-line recall loader update is needed, but it doesn't break convergence. |
| **Per-move probe overhead** | LOW | Re-evaluating `probe_classifier_model_ready` (which hits `/v1/models` and runs `select_model`) before every note move adds lightweight HTTP latency. Acceptable trade-off for fail-closed safety. |

---

## 4. Risk Assessment
- **Overall Risk:** **LOW**
- **Regression Risk:** Negligible. All plans explicitly lock the 4 shipped Phase-40 success criteria via regression tests. The changes are surgical: adding a probe, rewiring startup, adding a vault-seam guard, adding a read-only audit script, and deriving a constant.
- **Cross-Plan Dependencies:** Explicitly managed via `depends_on` chains and lazy imports. 40-04 owns the sweeper-side catch; 40-05 owns the primitive guard; 40-06 owns the audit script; 40-07 owns the index path derivation. No circular or unresolvable dependencies exist.
- **Failure Class Closure:** The exact failure path (degraded model → false-ready probe → stale guard → destructive move) is closed at every layer: startup (index-only), runtime (per-move re-evaluation), probe (fail-closed classifier readiness), and primitive (protected-namespace refusal).

---

## 5. Verdict
**CONVERGED**

The Round-2 fixes are real, structurally enforced, and fully tested against the exact failure modes. There are **no remaining HIGH concerns** on the destructive-vault-move-on-degraded-state failure class. The plans meet the convergence bar and are safe to execute.

---

## Consensus Summary — Round 3

**Convergence verdict: NOT CONVERGED (narrowing split).** LM Studio → LOW/CONVERGED; Codex → HIGH/NOT-CONVERGED on a single residual. The divergence narrowed from round 2 (2 HIGH → 1 HIGH), and the remaining item is a *secure-by-default hardening*, not a functional bypass bug. Both reviewers agree round-2 items **A, C, D, E, F are RESOLVED** (B: LM Studio RESOLVED, Codex PARTIAL for the reason below).

### The one remaining HIGH (Codex) — worth closing
**`run_sweep(..., model_loaded: bool = True)` keeps a permissive default.** The new `probe_classifier_model_ready()` is itself correctly fail-closed, but the destructive sweep still trusts a caller-supplied boolean that defaults to `True`. Any missed/current/future caller invoking `run_sweep(model_loaded=True)` without the `safe_to_mutate` probe bypasses the guard by construction. The original incident *was* a caller reaching the destructive path, so relying on callers to opt into safety is the same fragility class. **Close it via any one of:**
1. remove the boolean fallback for destructive (non-dry-run) execution entirely; or
2. make `safe_to_mutate` **mandatory** for non-dry-run `run_sweep` (no permissive default); or
3. add an explicit repo-wide call-site lock proving every production caller passes the fail-closed probe and no direct bypass remains.

### Also fold in
- **[correctness, MEM-05] Recall must skip `stale: true` entries.** 40-04's degraded-index invariant marks entries `stale: true`, but the plans don't show the recall-side loader (`SemanticRecall`) *skipping* them — without that one-line consumer update + test, a stale embedding can still be read at query time. (Raised by LM Studio; it completes round-1 concern 2.)
- **[Codex MED] 40-06 canonical inventory can drift** from reality unless the `--inventory` manifest is the authority — prefer the generated/manifest source over a hard-coded canonical map.
- **[Codex LOW] 40-05 destination protection blocks relocate-based restores** into protected namespaces — document the operator restore path as write/copy, not relocate.
- **[LM Studio LOW] Merge-order / lazy-import**: 40-04's broad-`Exception` fallback when 40-05's `ProtectedPathError` isn't present relies on 40-05 landing first; the `depends_on`/wave ordering covers this, just confirm it in execution.

### Where it stands
Risk (conservative consensus): **MEDIUM** (down from MEDIUM–HIGH). The known callers are already locked (startup is index-only; the admin endpoint is probe-gated), so the residual is a latent-bypass hardening rather than a live hole — but on this failure class it's cheap and worth closing by construction.

### Recommendation
This is a small, well-specified final pass. Either:
- `/gsd-plan-phase 40 --reviews` once more to (a) make the probe mandatory / drop the permissive `run_sweep` default and (b) add the recall `stale`-skip + test, then a final `/gsd-review` to confirm — **recommended; this should be the last loop**; or
- accept Codex's residual as a documented hardening item and `/gsd-execute-phase 40` now, since the known destructive callers are already gated.

The replan↔review loop has earned its keep — it caught a real guard bypass in round 2 and a latent one in round 3. We are clearly at the tail; one more targeted pass should converge it.
