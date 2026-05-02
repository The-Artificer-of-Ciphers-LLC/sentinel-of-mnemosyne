---
quick_id: 260502-ect
slug: add-qwen3-qwen3-5-qwen3-5-moe-qwen3-moe-
date: 2026-05-02
status: planned
---

# Silence pre-existing Qwen3 arch warning in model_profiles

Came out of `/diagnose` on the running sentinel-core container. LM Studio reports the active chat model `qwen3.6-35b-a3b` with `arch: qwen3_5_moe` — that key is not in `FAMILY_PROFILES`, so the primary lookup misses and falls through to substring match on model_id. The fallback finds `"qwen"` → returns `qwen2` profile (correct ChatML stop tokens). The warning is a primary-path miss, not a behavior bug.

The smoke test in the rebuild verification earlier this session (`POST /message` round-trip) confirmed the model terminates cleanly with `qwen2`-profile stop tokens, so this fix does not change behavior — it adds the missing arch keys so the primary lookup succeeds without the warning.

## Decisions (locked)

- Per Qwen team docs and empirical evidence (current container's smoke test response terminated cleanly), Qwen3 family uses identical ChatML stop tokens (`<|im_end|>`, `<|endoftext|>`) as Qwen2/2.5. Alias to existing `qwen2` profile, do not create a separate ModelProfile.
- Cover four arch strings observed/likely from LM Studio: `qwen3`, `qwen3_5`, `qwen3_5_moe` (the one currently firing the warning), `qwen3_moe`.
- Add one substring pattern `("qwen3", "qwen2")` before the bare `("qwen", "qwen2")` entry to future-proof against new Qwen3 model_ids.
- Regression test asserts `get_profile` (or its arch-mapping path) returns the qwen2 profile for `arch=qwen3_5_moe` AND emits no warning at WARNING level.

## Files modified

### Edit
- `shared/sentinel_shared/model_profiles.py` — add 4 alias lines after line 111 (existing alias block); add `("qwen3", "qwen2")` substring pattern before the existing `("qwen", "qwen2")` line.

### Create
- `shared/tests/test_model_profiles.py` (or add to existing `shared/tests/test_*.py` if a model-profiles test file exists — verify first; if not, create new) — 2-3 behavioral tests:
  1. `test_qwen3_5_moe_arch_returns_qwen2_profile` — call the arch-lookup directly (whatever the public seam is), assert returned profile matches the `qwen2` ModelProfile.
  2. `test_qwen3_5_moe_arch_does_not_warn` — use `caplog` at WARNING level around the lookup, assert no `arch '... ' not in FAMILY_PROFILES` warnings emitted.
  3. `test_qwen3_substring_pattern_matches_qwen3_only_models` — call the substring path with `model_id="qwen3-future-variant"`, assert returns `qwen2` profile.

## Tasks

1. **Add the four alias lines + the substring pattern + regression tests, all in one atomic commit.** (~6 LOC change in model_profiles.py + ~30 LOC of tests.)

## Verification

- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q` → 254 baseline + 3 new = 257 passed.
- New tests in `shared/tests/test_model_profiles.py` pass (verify they were actually run, not silently skipped).
- `cd sentinel-core && uvx ruff check .` → 0 errors.
- After rebuild + bounce: startup logs do NOT contain `arch 'qwen3_5_moe' not in FAMILY_PROFILES`. (Optional sanity check; not required for commit.)

## Guardrails

- **Spec-Conflict Guardrail.** Behavior preserved — qwen3 stop sequences identical to qwen2 (verified empirically by clean smoke-test termination earlier this session). No shipped-feature regression.
- **Test-Rewrite Ban.** No existing tests rewritten; only additions.
- **Behavioral-Test-Only Rule.** New tests call the function under test and assert observable result (returned ModelProfile equality + log-record absence).
- **AI Deferral Ban.** Single task, ships in one commit.

Direct to main per project override.
