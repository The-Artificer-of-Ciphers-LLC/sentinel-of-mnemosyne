---
phase: 21
slug: production-recovery-security-pipeline-discord
status: ready
created: 2026-04-11
gap_closure: true
gaps_closed: [GAP-01, GAP-02]
audit_source: v0.1-v0.4-MILESTONE-AUDIT.md
---

# Phase 21 Context: Production Recovery — Security Pipeline + Discord

## Phase Goal

Restore the production system to a working state. Phase 10-03 commit `6cfb0d3` deleted `injection_filter.py` and `output_scanner.py` and stripped all wiring from `main.py`, causing every `POST /message` request to crash with `AttributeError: 'State' object has no attribute 'injection_filter'`. Separately, the Discord container include has been commented out for the third time.

After this phase: `POST /message` succeeds end-to-end, E2E flows 1–3 and 5–6 are operational, and Discord is available via `docker compose up`.

---

## Source

Gaps GAP-01 and GAP-02 from `.planning/v0.1-v0.4-MILESTONE-AUDIT.md` (audited 2026-04-11).

---

## Root Cause (GAP-01)

Phase 10-03 commit `6cfb0d3` (`feat(10-03): replace get_user_context() with asyncio.gather() 5-file parallel read`) deleted:
- `sentinel-core/app/services/injection_filter.py`
- `sentinel-core/app/services/output_scanner.py`
- `tests/unit/test_injection_filter.py`
- `tests/unit/test_output_scanner.py`

And stripped all `InjectionFilter`/`OutputScanner` imports and `app.state` assignments from `main.py`. `message.py` was not updated — it still references `request.app.state.injection_filter` at line 79 and `request.app.state.output_scanner` at lines 188–189. Tests pass because `conftest.py` `default_app_state` fixture stubs both objects into `app.state` before each test.

## Root Cause (GAP-02)

`docker-compose.yml` line 10 is `#   - path: interfaces/discord/compose.yml`. This is the third time this line has been commented across phases (Phase 06 fixed it, then Phase 10 work re-commented it again).

---

## Decisions

### D-01: Restore injection_filter.py from git history

Restore `sentinel-core/app/services/injection_filter.py` from commit `c6f4753` (the last known-good commit before the deletion):

```bash
git show c6f4753:sentinel-core/app/services/injection_filter.py > sentinel-core/app/services/injection_filter.py
```

If `c6f4753` does not contain the file, use `git log --all --diff-filter=D -- sentinel-core/app/services/injection_filter.py` to find the last commit before deletion, then restore.

### D-02: Restore output_scanner.py from git history

Same approach as D-01 for `sentinel-core/app/services/output_scanner.py`.

### D-03: Restore test files from git history

Restore both deleted test files:
- `tests/unit/test_injection_filter.py`
- `tests/unit/test_output_scanner.py`

### D-04: Re-wire InjectionFilter + OutputScanner in main.py lifespan

Re-add to `sentinel-core/app/main.py`:
1. Import `InjectionFilter` from `app.services.injection_filter`
2. Import `OutputScanner` from `app.services.output_scanner`
3. In the lifespan context manager, instantiate both and assign to `app.state.injection_filter` and `app.state.output_scanner`

Do NOT modify `message.py` — it already references these correctly; the issue is only in `main.py`.

### D-05: Uncomment Discord include in docker-compose.yml

Change line 10 of `docker-compose.yml` from:
```yaml
#   - path: interfaces/discord/compose.yml
```
to:
```yaml
  - path: interfaces/discord/compose.yml  # DO NOT COMMENT — restored 3x, required for Discord interface
```

The inline comment is a signal to future agents and developers that this line is load-bearing.

### D-06: Run full test suite to verify no regressions

After all four service files are restored and `main.py` re-wired, run `pytest` from `sentinel-core/` to confirm all existing tests pass. The test count should increase (restored test files add coverage back).

---

## Affected Requirements

| Requirement | Description | Expected After |
|-------------|-------------|----------------|
| CORE-03 | POST /message returns ResponseEnvelope | ✅ SATISFIED |
| SEC-01 | InjectionFilter strips injection | ✅ SATISFIED |
| SEC-02 | OutputScanner blocks leaked credentials/PII | ✅ SATISFIED |
| IFACE-02 | Discord bot container operational | ✅ SATISFIED |
| IFACE-03 | Discord slash commands deferred responses | ✅ SATISFIED |
| IFACE-04 | Discord multi-turn threads | ✅ SATISFIED |

## E2E Flows Restored

| Flow | Restored By |
|------|-------------|
| 1: curl → POST /message → Pi → LM Studio → response | D-01..D-05 |
| 2: Obsidian context → inject → Pi → session write | D-01..D-05 |
| 3: Discord /sentask → bot → Core → Pi → thread reply | D-05 + flows 1/2 |
| 5: user input → InjectionFilter → Pi → OutputScanner → response | D-01..D-05 |
| 6: Session-start → asyncio.gather self/ reads → context inject | D-01..D-05 |

---

## Artifacts to Modify

| File | Change |
|------|--------|
| `sentinel-core/app/services/injection_filter.py` | Restore from git history |
| `sentinel-core/app/services/output_scanner.py` | Restore from git history |
| `tests/unit/test_injection_filter.py` | Restore from git history |
| `tests/unit/test_output_scanner.py` | Restore from git history |
| `sentinel-core/app/main.py` | Re-add imports + app.state assignments in lifespan |
| `docker-compose.yml` | Uncomment Discord include, add danger comment |

---

## Out of Scope

- Modifying `message.py` (already correct)
- Modifying `conftest.py` test fixtures (they correctly stub; this is fine)
- Changing any injection filter or output scanner logic (restore exactly, no improvements)
- Phase 24 pentest agent wiring (separate phase)
