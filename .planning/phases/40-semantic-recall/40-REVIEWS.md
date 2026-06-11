---
phase: 40
round: 2
reviewers: [codex, lm_studio]
reviewed_at: 2026-06-11T23:50:55Z
plans_reviewed: [40-04-PLAN.md, 40-05-PLAN.md, 40-06-PLAN.md, 40-07-PLAN.md]
convergence: "split — Codex: HIGH/not-converged; LM Studio: LOW/converged (divergence isolated to 40-04)"
note: "claude skipped (self CLI); gemini/coderabbit/opencode/qwen/cursor/antigravity/ollama/llama_cpp not installed"
---

# Cross-AI Plan Review — Phase 40 (Gap Closure) — Round 2

Convergence pass over the revised plans **40-04/05/06/07** (which incorporated round 1's 10 concerns). Shipped 40-01..03 frozen.

## Codex Review

## 40-04
**Summary**

Round-1 improved this plan substantially, but it is **not converged** and I do **not** consider it safe to execute as written. The two biggest gaps are both in the new safety guard: it is only evaluated once per sweep, not before each destructive action, and the proposed “classifier readiness” half is not actually checking the classifier’s real readiness path.

**Round-1 verification**

| Concern | Status | Why |
|---|---|---|
| 1. Runtime safe-to-mutate probe | **PARTIAL** | The probe moved inside `run_sweep`, but the action text says it is evaluated once after lock acquisition and “re-evaluate is not required mid-loop”; that is not “before every destructive step.” |
| 2. Degraded-index correctness | **RESOLVED** | The revised `_emit_embedding_index` contract now explicitly forbids persisting a new `content_hash` without a fresh vector. |
| 3. Sweeper exception ownership | **RESOLVED** | 40-04 now clearly owns catch-and-continue for `ProtectedPathError` across noise, relocate, and dedup branches. |
| 4. Admin endpoint bypass | **PARTIAL** | The admin path now passes a probe, but the specified probe does not actually prove classifier readiness, so bypass risk is reduced, not closed. |
| 8. 40-04↔40-05 relationship | **RESOLVED** | Ownership is now clean: 05 raises, 04 catches, no planned file overlap. |

**New concerns**

- **[HIGH]** The plan does **not** evaluate the guard before every destructive step. It explicitly evaluates once per run, then proceeds through later relocations/trash moves on that stale decision.
- **[HIGH]** The proposed probe in `routes/note.py` is the wrong readiness signal. `note_classifier` uses the **structured** model-selection path, not a generic “chat model resolvable” check, and `select_model()` can return a default even when no suitable model is loaded. That means the sweep can still mutate on degraded classifier output.
- **[MEDIUM]** The plan preserves classification write-back during unsafe runs. That is non-destructive, but it means degraded classifier output can still be persisted into note frontmatter, which may create later operator confusion even if files are not moved.

**Suggestions**

- Evaluate `safe_to_mutate()` immediately before each live `move_to_trash` / `relocate`, not once per sweep.
- Bind the probe to the classifier’s actual readiness path: the model kind used by `classify_note`, with a “loaded and selectable” check that fails closed.
- If the run is unsafe, consider also suppressing classification frontmatter updates, not just moves.

**Risk assessment**

**HIGH.** Not converged. The core safety claim is still weaker than the incident requires.

---

## 40-05
**Summary**

This revision addresses the round-1 protection concerns well. As a primitive-level vault guard, it is **safe to execute** and is close to converged.

**Round-1 verification**

| Concern | Status | Why |
|---|---|---|
| 5. Protected set not sentinel-only | **RESOLVED** | The plan now forces an explicit enumerated set and names `sentinel/`, `self/`, and `security/` unless code review justifies narrower scope. |
| 6. No destination protection | **RESOLVED** | `relocate()` now guards both `src` and `dst`. |
| 7. `app/errors.py` + brittle grep | **RESOLVED** | `app/errors.py` is in `files_modified`, and the acceptance criteria are behavior-first. |
| 8. 40-04↔40-05 relationship | **RESOLVED** | The split is clean and defensible: this plan raises, 40-04 handles continuation. |

**New concerns**

- **[LOW]** The fallback “ship `sentinel/`-only if `self/` / `security/` aren’t truly critical” is reasonable, but the summary must record that decision explicitly. Otherwise the plan could regress back into an implicit protected-set argument.

**Suggestions**

- Prefer making the default enumerated set explicit in code even if one namespace is later removed by decision, so the review artifact stays unambiguous.

**Risk assessment**

**LOW.** Converged in substance.

---

## 40-06
**Summary**

This is much better than the provenance-only draft. It now adds the missing second audit mode and concrete operator workflow. I would call it **useful but not exhaustive**. Safe to execute, but not a perfect blast-radius guarantee.

**Round-1 verification**

| Concern | Status | Why |
|---|---|---|
| 9. Blast-radius audit only on `original_path` provenance | **PARTIAL** | The second mode, `--since`, and `--dry-run` are present, and `learning/persona/` is explicitly scanned. But without an inventory manifest the fallback mode is still heuristic-heavy. |

**New concerns**

- **[MEDIUM]** The inventory mode, without `--inventory`, is still mostly persona-focused heuristics plus presence checks. It will catch the known incident shape, but it is not a full namespace-policy diff for all protected content moved without provenance.
- **[LOW]** The plan says `--dry-run` even though the script is read-only either way. That is harmless, but the help text should make clear that `--dry-run` is an affirmation flag, not a mode switch.

**Suggestions**

- Treat `--inventory` as strongly recommended in the operator instructions, not optional nicety.
- Make the default namespace-policy scan enumerate every protected namespace and expected canonical files, not just `sentinel/persona.md`.

**Risk assessment**

**MEDIUM.** Probably good enough for operator recovery, but not fully converged as a comprehensive forensic audit.

---

## 40-07
**Summary**

This revision cleanly fixes the buried `.json`/`.md` fallback problem. It is **safe to execute** and effectively converged.

**Round-1 verification**

| Concern | Status | Why |
|---|---|---|
| 10. `.json`→`.md` fallback buried / dual-constant risk | **RESOLVED** | The fallback is now its own plan, with equality lock plus end-to-end round-trip tests for both extensions. |

**New concerns**

- **[MEDIUM]** The plan allows either “real shared constant import” or “duplicate literals plus assertion.” Only the first is truly single-source. The second is safer than today, but still not as strong as the plan objective claims.

**Suggestions**

- Make `RecallConfig.index_path` derive from `EMBEDDING_INDEX_PATH` directly. Do not settle for two literals plus a test.

**Risk assessment**

**LOW.** Converged if implemented with a real shared constant.

---

## Round-1 Verification Matrix
| Concern | Status | Why |
|---|---|---|
| 1 | **PARTIAL** | Probe is inside `run_sweep`, but only once per run, and the planned readiness signal is not the classifier’s real readiness path. |
| 2 | **RESOLVED** | New `_emit_embedding_index` contract closes the stale-vector/new-hash corruption hole. |
| 3 | **RESOLVED** | 40-04 now explicitly owns catch-and-continue across all destructive branches. |
| 4 | **PARTIAL** | Admin path passes a probe, but probe quality is insufficient, so bypass is not fully closed. |
| 5 | **RESOLVED** | Protected namespaces are now explicitly enumerated. |
| 6 | **RESOLVED** | Destination protection is now included. |
| 7 | **RESOLVED** | `app/errors.py` is included and grep-only criteria were replaced with behavior checks. |
| 8 | **RESOLVED** | Clear cross-plan contract: 05 raises, 04 catches. |
| 9 | **PARTIAL** | Second audit mode exists, but manifest-less inventory mode is still heuristic rather than comprehensive. |
| 10 | **RESOLVED** | Fallback is now atomic, tested, and separated into 40-07. |

## Overall
**Risk assessment: HIGH.**  
I do **not** consider the set **converged** yet, because 40-04 still leaves a real path to destructive mutation on degraded classifier state. That was the production-down class of failure, so I would not wave this through until the guard is both:

1. checked at the point of each destructive move, and  
2. wired to the classifier’s actual readiness mechanism, not a chat-model proxy.

---

## LM Studio Review

*(model: qwen3.6-35b-a3b — local, 64k context, no external egress)*



# Cross-AI Plan Review — ROUND 2 (Convergence)

## 1. Summary
The revised plans (40-04, 40-05, 40-06, 40-07) directly and correctly address the root cause of the Phase 40 UAT blocker: a destructive full sweep running during startup, combined with missing model readiness checks and an unprotected `sentinel/` namespace. The fixes introduce a runtime safety probe, a primitive-level vault guard, proper exception handling, and a two-mode blast-radius audit. Dependency chains are correctly sequenced (04/05 → 06; 04 → 07 → 06), file overlap is eliminated, and acceptance criteria are behavioral rather than grep-dependent. All Round-1 concerns are resolved. The plans are safe to execute, and the phase has **converged**.

---

## 2. Round-1 Verification

| # | Concern | Status | Why |
|---|---------|--------|-----|
| 1 | [HIGH] Static `model_loaded` boolean → runtime probe | **RESOLVED** | 40-04 Task 2 replaces the boolean with an injectable `safe_to_mutate` callable evaluated *inside* `run_sweep` before destructive steps. Broadened to embedding + classifier readiness. |
| 2 | [HIGH] Degraded-index correctness | **RESOLVED** | 40-04 Task 2 explicitly modifies `_emit_embedding_index` carry-forward logic to forbid persisting a new `content_hash` without a fresh vector. Tests cover both carry-forward and `stale: true` marking. |
| 3 | [HIGH] Cross-plan ownership hole on exception handling | **RESOLVED** | 40-04 Task 2 explicitly OWNS catch-and-continue for all three destructive branches (noise, relocate, dedup). Tests prove `ProtectedPathError` is recorded and the sweep continues. |
| 4 | [MED] Admin sweep endpoint could bypass guard | **RESOLVED** | 40-04 Task 3 wires `start_sweep` to pass a runtime probe. Dry-run is correctly exempted (writes nothing). Tests prove probe-False admin paths perform zero moves. |
| 5 | [MED] Protected set implicitly `sentinel/`-only | **RESOLVED** | 40-05 Task 1 explicitly enumerates `sentinel/`, `self/`, `security/` in `Settings.protected_namespaces`. Parametrized tests assert the full enumeration. |
| 6 | [MED] No destination protection | **RESOLVED** | 40-05 Task 2 adds `is_protected_path(dst)` as the first statement in `relocate`. Tests prove destination refusal and zero writes under protected namespaces. |
| 7 | [LOW] `app/errors.py` missing; brittle grep criteria | **RESOLVED** | 40-05 explicitly lists `app/errors.py` in `files_modified`. Acceptance criteria use behavior/spy assertions, not grep counts. |
| 8 | 40-04↔40-05 relationship | **RESOLVED** | 40-05 raises `ProtectedPathError` in `vault.py`; 40-04 catches it in `vault_sweeper.py`. `files_modified` lists are disjoint. Tests are split appropriately. |
| 9 | [HIGH/MED] Blast-radius audit keyed only on provenance | **RESOLVED** | 40-06 Task 1 implements a second inventory/namespace-policy mode that scans target namespaces (e.g., `learning/persona/`) for persona-like files and missing protected files, filtering by `--since`. |
| 10 | [MED] `.json`→`.md` fallback buried in checkpoint | **RESOLVED** | 40-07 extracts the fallback into an atomic plan. Single-sources the path, asserts equality, adds extension-aware encode/decode, and proves both-extensions round-trip. 40-06 correctly depends on it. |

---

## 3. New Concerns

* **[MED] Single-evaluation probe limitation (40-04 Task 2):** The `safe_to_mutate` probe is evaluated *once* after lock acquisition, not per-note. If the embedding/classifier models load asynchronously during the sweep, notes processed later won't get a second chance to move. This is an intentional fail-safe trade-off (safety over throughput), but must be documented so operators understand why mid-sweep model loading won't trigger late moves.
* **[LOW] Case-sensitivity on extension check (40-07 Task 1):** `_encode_index_body` and `_decode_index_body` use `path.endswith(".md")`. This will silently fail for `.MD`, `.Json`, or operator-renamed variants. While `.json` is the default, live vault state or future config changes could trigger edge cases.
* **[MED] Deterministic choice for degraded-index carry-forward (40-04 Task 2):** The plan says the implementation will either (i) carry the old entry forward unchanged, or (ii) mark it `stale: true`. The plan does not mandate which path is chosen. If the implementation randomly or conditionally picks between them without a deterministic rule, tests may flake or behavior may drift across deployments.
* **[LOW] Blast-radius script safety gate (40-06 Task 1):** The script requires `LIVE_TEST=1` to execute. If run without it, it silently does nothing. This is a safety feature, but operators must be explicitly warned in the SUMMARY that omitting the flag yields no audit, not a clean pass.

---

## 4. Suggestions

1. **Make the degraded-index carry-forward deterministic:** Explicitly choose one path (prefer `stale: true` marker to preserve the new `content_hash` so the index doesn't silently drift, or explicitly document the choice). Update the plan to state the deterministic rule so tests are stable and behavior is reproducible.
2. **Add case-insensitive extension check in 40-07:** Change `path.endswith(".md")` to `path.lower().endswith(".md")` in both `_encode_index_body` and `_decode_index_body` to handle case variations gracefully without breaking the `.json` default.
3. **Document the single-evaluation probe trade-off:** Add a brief comment/docstring in 40-04 Task 2 explaining why the probe is evaluated once at loop start (performance, simplicity, fail-safe design) and that mid-sweep model loading will not retroactively enable moves for already-processed notes.
4. **Explicitly warn about `LIVE_TEST` in 40-06 SUMMARY:** State clearly that running the blast-radius script without `LIVE_TEST=1` is a no-op and does not indicate a clean vault.

---

## 5. Risk Assessment

**Overall Risk: LOW**

**Justification:**
The revisions directly neutralize the production-down root cause by decoupling startup from destructive logic, enforcing a runtime readiness probe, hardening the vault primitive with source+destination guards, and ensuring all destructive branches safely continue on protected-path refusals. The dependency graph is correctly sequenced, file overlap is eliminated, and acceptance criteria are behavioral. The 4 shipped success criteria are explicitly preserved and regression-locked. The new concerns are LOW/MED, do not introduce new attack surfaces or data-corruption paths, and are easily mitigated with the suggested adjustments.

**Convergence: YES** — All Round-1 HIGH concerns are resolved. No remaining HIGH concerns exist. The plans are safe to execute and meet the convergence threshold.

---

## Consensus Summary — Round 2

**Convergence verdict: NOT CONVERGED (split).** Codex rates the set **HIGH / not safe to execute as-is**; LM Studio rates it **LOW / converged**. The disagreement is isolated to **40-04**. Because this phase exists specifically to stop destructive moves on degraded model state, the conservative reading governs: one more targeted pass on 40-04 is warranted before execution.

### Where both reviewers AGREE
- **40-05 — converged (LOW).** Protected set enumerated (`sentinel/` + `self/` + `security/`), destination protection added, `app/errors.py` in `files_modified`, behavior-first criteria. *Minor:* record the "ship sentinel/-only if self//security/ aren't truly boot-critical" fallback as an explicit decision so it can't silently regress.
- **40-07 — converged only if a REAL shared constant.** Both flag that the plan permits "duplicate literals + equality-test" as an alternative to importing one shared `EMBEDDING_INDEX_PATH`. Tighten the plan to mandate `RecallConfig.index_path` *derives from* `EMBEDDING_INDEX_PATH` (single source), not two literals guarded by a test. (LM Studio also: make the `.md`/`.json` extension check case-insensitive.)
- **40-06 — improved but not exhaustive (MED).** The second audit mode is heuristic without a manifest. Codex: make `--inventory` strongly recommended and have the namespace-policy scan enumerate *every* protected namespace's canonical files, not just `sentinel/persona.md`. LM Studio: the SUMMARY must warn that running without `LIVE_TEST=1` is a silent no-op, not a clean-vault result.
- **Round-1 concerns 2, 3, 5, 6, 7, 8, 10 → RESOLVED by both.** Concern 9 → improved (PARTIAL/RESOLVED).

### The blocking divergence — 40-04 (concerns 1 & 4)
- **Codex [HIGH] — guard not evaluated per destructive step.** `safe_to_mutate()` is evaluated once after lock acquisition ("re-evaluate not required mid-loop"); later relocate/trash moves then proceed on that stale decision. *Fix:* evaluate immediately before each live `relocate`/`move_to_trash` (or add a mid-sweep re-check and document why once-at-start suffices).
- **Codex [HIGH] — wrong readiness signal (the sharper issue).** The `routes/note.py` probe checks a generic "chat model resolvable," but `note_classifier` uses the **structured model-selection path**, and `select_model()` can return a default even when no suitable model is loaded — so the probe can return TRUE on a degraded classifier and the guard is bypassed at its source. *Fix:* bind the probe to the classifier's actual readiness (the model kind `classify_note` uses), "loaded and selectable," **fail-closed**.
- **Codex [MED] — degraded frontmatter write-back.** Classification frontmatter is still written on unsafe runs; non-destructive, but persists degraded output. *Fix:* suppress classification writes on unsafe runs too.
- **LM Studio's counter-position:** it reads evaluate-once as an intentional fail-safe (cold model at start → FALSE → whole sweep skips), which correctly handles the *literal* boot incident, and rates the residue MED/acceptable. This is valid for the exact incident but does **not** address Codex's two cases (mid-sweep degradation; a probe that falsely reports "ready").
- **Adjudication:** Codex's concern 4/#2 (wrong readiness signal) is decisive — if the probe can return TRUE on a degraded classifier, the entire guard is moot regardless of how often it's evaluated. That alone keeps the set from converging.

### Recommended next step
Targeted replan of 40-04 (the other three plans need only the small tightenings above):
```
/gsd-plan-phase 40 --reviews
```
fold in: (1) per-destructive-step probe evaluation, (2) classifier-real-readiness fail-closed probe, (3) suppress frontmatter writes on unsafe runs, (4) 40-07 single shared constant + case-insensitive extension, (5) 40-06 `--inventory`/`LIVE_TEST` emphasis, (6) 40-05 record the fallback decision. Then re-run `/gsd-review --phase 40 --all` to confirm convergence (or use `/gsd-plan-review-convergence` to loop automatically until no HIGH concerns remain).

**Overall (conservative consensus): MEDIUM–HIGH risk, not converged — one more 40-04 pass before execute.**
