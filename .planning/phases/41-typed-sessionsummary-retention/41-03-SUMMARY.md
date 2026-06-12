---
phase: 41-typed-sessionsummary-retention
plan: "03"
subsystem: sentinel-core/config + sentinel-core/composition
tags: [tdd, config, retention-policy, composition-root, env-override, mem-06]
dependency_graph:
  requires:
    - 41-01 (RetentionPolicy frozen dataclass in app/services/recall.py)
  provides:
    - Settings.retention_hot_limit (env: RETENTION_HOT_LIMIT, default 3)
    - Settings.retention_hot_window_days (env: RETENTION_HOT_WINDOW_DAYS, default 2)
    - RetentionPolicy constructed from settings and injected into Recall at composition root
  affects:
    - sentinel-core/app/config.py
    - sentinel-core/app/composition.py
    - sentinel-core/tests/test_config.py
tech_stack:
  added: []
  patterns:
    - env-overridable Settings field (mirrors sweep_skip_prefixes / protected_namespaces idiom)
    - composition-root dependency injection (mirrors RecallConfig() construction pattern)
    - TDD RED→GREEN with monkeypatch.setenv for env-override behavioral tests
key_files:
  created:
    - sentinel-core/tests/test_config.py
  modified:
    - sentinel-core/app/config.py
    - sentinel-core/app/composition.py
decisions:
  - "retention_hot_limit and retention_hot_window_days added beside sweep_skip_prefixes/protected_namespaces — same env-override idiom, same inline-doc style"
  - "RetentionPolicy injected as a separate object into Recall (NOT threaded through RecallConfig) — OQ3 resolution"
  - "policy=_policy passed unconditionally in composition.py — between-wave state where Recall.__init__ does not yet accept it (Plan 04, Wave 3, adds the constructor parameter)"
  - "T-41-06: negative env value degrades gracefully to empty-slice (never unbounded read); explicit lower-bound clamp is a candidate follow-up but not required at ASVS L1 for this operator-controlled env"
metrics:
  duration: "102s (~2 min)"
  completed: "2026-06-12"
  tasks_completed: 2
  files_modified: 3
---

# Phase 41 Plan 03: Env-Overridable RetentionPolicy Wiring Summary

**One-liner:** `Settings.retention_hot_limit` / `Settings.retention_hot_window_days` added as env-overridable knobs and wired into a `RetentionPolicy` injected at the `Recall` composition root, making MEM-06 operator-tunable without a redeploy.

## What Was Built

### `sentinel-core/app/config.py`

Two new `Settings` fields added beside `sweep_skip_prefixes` and `protected_namespaces`, mirroring their idiom exactly:

```python
retention_hot_limit: int = 3          # env: RETENTION_HOT_LIMIT
retention_hot_window_days: int = 2    # env: RETENTION_HOT_WINDOW_DAYS
```

Defaults (3 / 2) preserve the current "today+yesterday, top-3 sessions" behavior shipped in Plan 41-01. pydantic-settings auto-maps the uppercased field name to the env var — no alias needed. Inline doc comment notes the MEM-06 D-04 context and T-41-06 degradation behavior.

### `sentinel-core/app/composition.py`

- `RetentionPolicy` added to the `from app.services.recall import ...` line.
- In the `if recall is None:` block, after `_config = RecallConfig()`:
  ```python
  _policy = RetentionPolicy(
      hot_limit=settings.retention_hot_limit,
      hot_window_days=settings.retention_hot_window_days,
  )
  ```
- `Recall(...)` call extended with `policy=_policy` unconditionally.
- `settings` was already in scope — no additional config reads added.

**Wave-ordering note:** `Recall.__init__` does not yet accept a `policy=` parameter; Plan 04 (Wave 3, `depends_on` 41-03) adds the constructor parameter before the next full-app integration check (Plan 05's phase gate). This plan ships the call site now as the single intended between-wave state per the lockstep.

### `sentinel-core/tests/test_config.py`

Two new behavioral tests:

- `test_retention_defaults` — constructs `Settings()` with both env vars deleted (`monkeypatch.delenv`), asserts `retention_hot_limit == 3` and `retention_hot_window_days == 2`.
- `test_retention_env_override` — sets `RETENTION_HOT_LIMIT=5` / `RETENTION_HOT_WINDOW_DAYS=4`, constructs a fresh `Settings()`, asserts values are `5` and `4` AND `isinstance(..., int)` (type coercion verified, not just equality).

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (`test(41-03)`) | 5fb5262 | PASS |
| GREEN (`feat(41-03)` config) | 1de8474 | PASS |

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | RED→GREEN — env-overridable retention Settings fields | 5fb5262 (RED), 1de8474 (GREEN) | tests/test_config.py, app/config.py |
| 2 | Wire RetentionPolicy from settings into composition root | 6462ca2 | app/composition.py |

## Verification Evidence

```
cd sentinel-core && uv run pytest tests/test_config.py -k retention -x -q
..
2 passed in 0.08s
```

```
cd sentinel-core && PYTHONPATH="../shared:." uv run python -c \
  "import app.composition; from app.services.recall import RetentionPolicy; print(RetentionPolicy(hot_limit=1, hot_window_days=1))"
RetentionPolicy(hot_limit=1, hot_window_days=1)
```

## Deviations from Plan

None — plan executed exactly as written. The PYTHONPATH requirement (`../shared:.`) for the import verify is the same runtime context used by all sentinel-core test runs (not a deviation, just an operational note).

## Known Stubs

None. Both Settings fields have real defaults and real env-override wiring. The composition root constructs a real `RetentionPolicy` from them. No placeholder values or TODO comments.

## Threat Flags

None. No new network endpoints or auth paths introduced. The env-trust surface (T-41-06) is documented in the plan threat model: negative env values degrade to empty-slice behavior (fewer sessions, never unbounded read); the operator controls this env on a local-network single-operator deployment (CLAUDE.md constraint).

## Self-Check: PASSED

- `sentinel-core/tests/test_config.py` — EXISTS, contains `test_retention_defaults` and `test_retention_env_override`, both call `Settings()` and assert field values
- `sentinel-core/app/config.py` — EXISTS, contains `retention_hot_window_days` (checked by plan artifact)
- `sentinel-core/app/composition.py` — EXISTS, contains `RetentionPolicy` import and `policy=_policy` wiring
- Commit `5fb5262` — EXISTS (RED)
- Commit `1de8474` — EXISTS (GREEN)
- Commit `6462ca2` — EXISTS (Task 2)
- `uv run pytest tests/test_config.py -k retention -x -q` — 2 passed
- `import app.composition; RetentionPolicy(hot_limit=1, hot_window_days=1)` — prints correctly
