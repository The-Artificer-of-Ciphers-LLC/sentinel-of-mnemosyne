---
phase: 25
slug: v0-40-pre-beta-refactoring-eliminate-duplicates-complete-stu
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-11
---

# Phase 25 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (sentinel-core) + vitest 2.x (pi-harness) |
| **Config file** | `sentinel-core/pyproject.toml` ([tool.pytest.ini_options]) / `pi-harness/vitest.config.ts` |
| **Quick run command** | `cd sentinel-core && python -m pytest -x -q` |
| **Full suite command** | `cd sentinel-core && python -m pytest && cd ../pi-harness && npx vitest run` |
| **Estimated runtime** | ~30 seconds (pytest ~25s, vitest ~5s) |

---

## Sampling Rate

- **After every task commit:** Run `cd sentinel-core && python -m pytest -x -q`
- **After every plan wave:** Run full suite (pytest + vitest)
- **Before `/gsd-verify-work`:** Full suite must be green; `docker compose config` must succeed with no warnings
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

*To be filled in by gsd-planner during plan creation. Each plan's tasks must populate this table.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 25-01-xx | 01 | 1 | (Phase 24 D-01) | — | N/A | integration | `docker compose config` | ✅ | ⬜ pending |
| 25-04-xx | 04 | 1 | DUP-03/RD-03 | — | N/A | unit | `cd sentinel-core && python -m pytest tests/test_litellm_provider.py tests/test_pi_adapter.py -x -q` | ❌ W0 | ⬜ pending |
| 25-05-xx | 05 | 1 | DUP-01/RD-01 | — | N/A | unit | `cd sentinel-core && python -m pytest && cd ../shared && python -m pytest` | ❌ W0 | ⬜ pending |
| 25-06-xx | 06 | 1 | STUB-03/RD-07 | T-25-01 | InjectionFilter catches all 30+ jailbreak prompts | security | `cd security && python -m pytest pentest/jailbreak_baseline.py -v` | ❌ W0 | ⬜ pending |
| 25-07-xx | 07 | 1 | CONTRA-01–04/RD-10 | — | Docs match code | manual | grep-based checks from acceptance criteria §10 | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `sentinel-core/tests/test_status.py` — stub tests for GET /status and GET /context/{user_id} (RD-05)
- [ ] `shared/tests/test_sentinel_client.py` — stub tests for SentinelCoreClient (RD-01)
- [ ] `interfaces/discord/tests/__init__.py` + `test_thread_persistence.py` — moved+rewritten from sentinel-core/tests/ (RD-09)
- [ ] `interfaces/discord/tests/test_subcommands.py` — stub tests for subcommand routing (§9 requirement)
- [ ] `interfaces/imessage/tests/__init__.py` + `test_bridge.py` — new test file for bridge.py (RD-08, §9)
- [ ] `security/pentest/jailbreak_baseline.py` — 30+ jailbreak prompt stubs against InjectionFilter (RD-07)

*All must exist (even as stubs) before the relevant implementation tasks run.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `docker compose config` reports no warnings | Success Criterion 5 | Compose validation requires Docker daemon | Run `docker compose config` and confirm exit 0, no warnings |
| `sentinel.sh --discord up -d` starts exactly 3 services | Success Criterion 9 | Requires Docker + running environment | `./sentinel.sh --discord up -d && docker compose ps` |
| Full Disk Access error message displayed for iMessage | RD-08 D-05 | Cannot unit-test macOS SIP protection in CI | Manually revoke Full Disk Access from Terminal, run bridge.py, confirm helpful error |
| Cross-session memory still works after envelope expansion | CONTRA-01 D-03 | Requires live LM Studio | Send a message, check session written, send second referencing first |

---

## Acceptance Criteria Checklist (from V040-REFACTORING-DIRECTIVE.md §10)

These must ALL be true before phase ships:

- [ ] `grep -rn "def call_core" interfaces/` → 0 results
- [ ] `grep -rn "NotImplementedError" sentinel-core/app/` → 0 results
- [ ] `cd sentinel-core && pytest` exits 0
- [ ] `cd pi-harness && npx vitest run` exits 0
- [ ] All test files in §9 exist and pass
- [ ] `docker compose config` succeeds, no warnings
- [ ] `security/pentest/jailbreak_baseline.py` passes
- [ ] `security/JAILBREAK-BASELINE.md` exists
- [ ] SEC-04 checkbox checked in `.planning/REQUIREMENTS.md`
- [ ] All CONTRA-01–04 resolved (docs match code)
- [ ] Route registry: 4 routes in sentinel-core, 3 in pi-harness
- [ ] `shared/sentinel_client.py` exists, imported by both interfaces
- [ ] All 10 RD directives implemented per §5

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
