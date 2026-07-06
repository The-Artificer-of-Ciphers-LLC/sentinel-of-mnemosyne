---
phase: 46
slug: 6-rs-pipeline-orchestrator
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-06
---

# Phase 46 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Detailed per-task map is filled by the planner / nyquist-auditor from RESEARCH.md's `## Validation Architecture`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | sentinel-core/pyproject.toml |
| **Quick run command** | `cd sentinel-core && .venv/bin/python -m pytest tests/test_pipeline_orchestrator.py tests/test_six_rs_*.py -q` |
| **Full suite command** | `cd sentinel-core && .venv/bin/python -m pytest tests/` |
| **Estimated runtime** | ~30–60 seconds (full core suite) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command (new pipeline/six_rs tests)
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green (550+ passing baseline maintained)
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-T1 six_rs RED stubs | 46-01 | 0 | PIPE-02,04,05,07 | T-46-TST | RED stubs never shadow real modules | scaffold | `cd sentinel-core && .venv/bin/python -m pytest tests/test_six_rs_*.py --collect-only -q` | ❌ W0 | ⬜ pending |
| 01-T2 orch/route/store RED stubs | 46-01 | 0 | PIPE-02,03,06 | T-46-TST | lock-before-inbox-read encoded | scaffold | `cd sentinel-core && .venv/bin/python -m pytest tests/test_pipeline_orchestrator.py tests/test_pipeline_status_store.py tests/test_pipeline_routes.py --collect-only -q` | ❌ W0 | ⬜ pending |
| 01-T3 suite collection gate | 46-01 | 0 | PIPE-02..07 | T-46-TST | 550+ baseline stays green | scaffold | `cd sentinel-core && .venv/bin/python -m pytest tests/ --collect-only -q` | ❌ W0 | ⬜ pending |
| 02-T1 shared resolver | 46-02 | 1 | PIPE-02,04,05 | T-46-DRIFT | one resolver, no drift | unit | `cd sentinel-core && .venv/bin/python -c "from app.services.model_resolution import resolve_structured_model"` | ❌ W0 | ⬜ pending |
| 02-T2 note_classifier refactor | 46-02 | 1 | PIPE-02 | T-46-DRIFT | zero behavior change | unit | `cd sentinel-core && .venv/bin/python -m pytest tests/test_note_classifier.py -q` | ✅ | ⬜ pending |
| 03-T1 inbox retry_count | 46-03 | 1 | PIPE-01,07 | T-46-RETRY,T-46-PARSE | bounded retry; safe parse; capture unchanged | unit | `cd sentinel-core && .venv/bin/python -m pytest tests/test_inbox.py -q` | ✅ | ⬜ pending |
| 03-T2 pipeline_status_store | 46-03 | 1 | PIPE-06 | — | duck-typed report round-trip | unit | `cd sentinel-core && .venv/bin/python -m pytest tests/test_pipeline_status_store.py -q` | ❌ W0 | ⬜ pending |
| 04-T1 six_rs/reduce | 46-04 | 2 | PIPE-02 | T-46-INJECT,T-46-BADOUT | draft-on-malformed; DATA-only prompt | unit | `cd sentinel-core && .venv/bin/python -m pytest tests/test_six_rs_reduce.py -q` | ❌ W0 | ⬜ pending |
| 04-T2 six_rs/verify | 46-04 | 2 | PIPE-07 | T-46-RETRY | reuse check_note_compliance; named cap | unit | `cd sentinel-core && .venv/bin/python -m pytest tests/test_six_rs_verify.py -q` | ❌ W0 | ⬜ pending |
| 05-T1 six_rs/reflect | 46-05 | 2 | PIPE-02 | T-46-03,T-46-INJECT | embedding-first; no self/ links | unit | `cd sentinel-core && .venv/bin/python -m pytest tests/test_six_rs_reflect.py -q` | ❌ W0 | ⬜ pending |
| 05-T2 six_rs/reweave | 46-05 | 2 | PIPE-04 | T-46-CORRUPT | append-only idempotent; schema preserved | unit | `cd sentinel-core && .venv/bin/python -m pytest tests/test_six_rs_reweave.py -q` | ❌ W0 | ⬜ pending |
| 05-T3 six_rs/rethink | 46-05 | 2 | PIPE-05 | T-46-INJECT | tolerant of absent tensions; KEEP fallback | unit | `cd sentinel-core && .venv/bin/python -m pytest tests/test_six_rs_rethink.py -q` | ❌ W0 | ⬜ pending |
| 06-T1 orchestrator run() | 46-06 | 3 | PIPE-02,03,04,05,07 | T-46-04,T-46-05,T-46-RETRY | shared lock first; Verify-gate; loop isolation | integration | `cd sentinel-core && .venv/bin/python -m pytest tests/test_pipeline_orchestrator.py -q` | ❌ W0 | ⬜ pending |
| 06-T2 start_pipeline | 46-06 | 3 | PIPE-06 | T-46-04 | async ack; blocked/error states | integration | `cd sentinel-core && .venv/bin/python -m pytest tests/test_pipeline_orchestrator.py tests/test_pipeline_status_store.py -q` | ❌ W0 | ⬜ pending |
| 06-T3 route + registration | 46-06 | 3 | PIPE-06 | T-46-01 | imported admin gate; 422 bad mode | integration | `cd sentinel-core && .venv/bin/python -m pytest tests/test_pipeline_routes.py -q` | ❌ W0 | ⬜ pending |
| 07-T1 discord RED tests | 46-07 | 4 | PIPE-02,03,04,05,06 | T-46-01-IFACE | branch coverage incl refactor→rethink | integration | `cd interfaces/discord && .venv/bin/python -m pytest tests/test_core_gateway.py tests/test_command_router_module.py --collect-only -q` | ❌ W0 | ⬜ pending |
| 07-T2 gateway + router branch | 46-07 | 4 | PIPE-02,03,04,05,06 | T-46-01-IFACE,T-46-LEAK | admin gate; bounded status format | integration | `cd interfaces/discord && .venv/bin/python -m pytest tests/test_core_gateway.py tests/test_command_router_module.py -q` | ❌ W0 | ⬜ pending |
| 07-T3 bot.py rewire | 46-07 | 4 | PIPE-02,03,04,05 | T-46-04-IFACE | dead prompts removed; concurrency msg | integration | `cd interfaces/discord && .venv/bin/python -m pytest tests/ -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_pipeline_orchestrator.py` — RED stubs for the orchestrator (mode dispatch, shared-lock guard, PipelineReport counts)
- [ ] `tests/test_six_rs_reduce.py` / `_reflect.py` / `_reweave.py` / `_verify.py` / `_rethink.py` — per-phase stage stubs
- [ ] FakeVault fixtures — mirror existing `test_vault_sweeper` / `test_note_classifier` conftest patterns
- [ ] pytest already installed (sentinel-core `.venv`) — no framework install needed

*Planner to finalize against RESEARCH.md's validation architecture.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live `:ralph`/`:pipeline` run mutates the real Obsidian vault (writes `notes/` with `_schema`, updates MOC) | PIPE-02, PIPE-03 | Requires live Obsidian REST + LM Studio; not exercised by FakeVault unit tests | Run `:ralph` in Discord after seeding `inbox/`; confirm `notes/{slug}.md` appears with a trailing `_schema` block + wikilink and the MOC hub is updated |
| Async run status is pollable and reports real per-phase counts | PIPE-06 | End-to-end Discord + background task timing | Start a pipeline, poll `:pipeline` status; confirm counts advance and a final success/partial/failure outcome is reported |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (18/18 tasks)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (46-01 creates every core test file; 46-07 T1 creates the discord RED tests)
- [x] No watch-mode flags (all commands are one-shot `pytest ... -q` / `--collect-only`)
- [x] Feedback latency < 60s (quick per-module runs; full core suite ~30–60s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planner-approved (Wave 0 RED scaffolds pending execution)
