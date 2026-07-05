---
phase: 42
slug: first-class-exo-provider
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-05
---

# Phase 42 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (both `sentinel-core` and `modules/pathfinder`) |
| **Config file** | `sentinel-core/pyproject.toml`, `modules/pathfinder/pyproject.toml` |
| **Quick run command** | `pytest -q` (in the changed service dir) |
| **Full suite command** | `pytest` in `sentinel-core/` and `modules/pathfinder/` |
| **Estimated runtime** | ~30–60 seconds per service |

---

## Sampling Rate

- **After every task commit:** Run `pytest -q` in the changed service
- **After every plan wave:** Run the full suite in both affected services
- **Before `/gsd-verify-work`:** Full suite must be green in both services
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

> Populated by the planner/executor per task. Anchors: ROADMAP Phase 42 success criteria (1–6) + CONTEXT decisions D-01…D-10.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 42-01-01 | 01 | 1 | SC-1 (openai_compatible) | — | provider selection is table-driven; unknown `ai_provider` errors, never silent-fallthrough | unit | `pytest -q sentinel-core/tests` | ❌ W0 | ⬜ pending |
| 42-0X-XX | — | — | SC-3 (fallback) / SC-4 (NotFound) | — | 404/NotFoundError triggers fallback; both-down → ProviderUnavailableError | unit | `pytest -q` | ❌ W0 | ⬜ pending |
| 42-0X-XX | — | — | SC-4 (/state discovery) | — | zero instances → fallback-or-clear-error, never guess catalog[0] | unit | `pytest -q` | ❌ W0 | ⬜ pending |
| 42-0X-XX | — | — | SC-2 (LM Studio regression) | — | LM Studio chat path unchanged after migration to openai_compatible | unit | `pytest -q` | ✅ (existing) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> Tests are embedded per-task (test-first via tdd="true") rather than pre-staged in a separate Wave 0 plan — no standalone Wave 0 needed.

- [ ] `sentinel-core/tests/test_provider_router.py` — fallback + NotFound-trigger cases (extend if exists)
- [ ] `sentinel-core/tests/test_model_selector.py` — /state discovery + zero-instance cases (extend the exo-model-notfound-502 tests)
- [ ] `sentinel-core/tests/` — openai_compatible provider-map assembly + unknown-provider error
- [ ] pf2e→core chat handoff: core completion-endpoint test + pf2e client call-site tests

*If existing infrastructure covers a requirement, mark it ✅ (existing) rather than adding a Wave 0 stub.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| End-to-end chat through exo via core | SC (integration) | Requires a live exo instance with a loaded model | Load a model in exo; `curl` core `/message` (or the new completion endpoint); expect 200 with real reply |
| exo `GET /state` shape | SC-4 | exo wire format confirmed live, not just from Pydantic source | `curl http://localhost:52415/state`; confirm `instances` / model-id path used by discovery |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-05 (plan-check passed)
