---
phase: 30
slug: npc-outputs
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-23
---

# Phase 30 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`asyncio_mode = "auto"`) |
| **Config file** | `modules/pathfinder/pyproject.toml` |
| **Quick run command** | `cd modules/pathfinder && python -m pytest tests/test_npc.py -x -q` |
| **Full suite command** | `cd modules/pathfinder && python -m pytest tests/ -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd modules/pathfinder && python -m pytest tests/test_npc.py -x -q`
- **After every plan wave:** Run `cd modules/pathfinder && python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 30-01-01 | 01 | 1 | OUT-01–OUT-04 | T-30-01-02 | `generate_mj_description` truncates personality/backstory to 200 chars, strips newlines before LLM call | unit | `cd modules/pathfinder && python -c "from app.llm import generate_mj_description, build_mj_prompt; print('ok')"` | ❌ W0 | ⬜ pending |
| 30-01-02 | 01 | 1 | OUT-01–OUT-04 | T-30-01-01 | `build_npc_pdf` uses `buffer.getvalue()` not `buffer.read()` | unit | `cd modules/pathfinder && grep -c "buffer.getvalue()" app/pdf.py` | ❌ W0 | ⬜ pending |
| 30-01-03 | 01 | 1 | OUT-01 | — | N/A | unit | `cd modules/pathfinder && python -m pytest tests/test_npc.py::test_npc_export_foundry_success -x` | ❌ W0 | ⬜ pending |
| 30-01-04 | 01 | 1 | OUT-01 | — | N/A | unit | `cd modules/pathfinder && python -m pytest tests/test_npc.py::test_npc_export_foundry_not_found -x` | ❌ W0 | ⬜ pending |
| 30-01-05 | 01 | 1 | OUT-01 | — | Zero-value defaults when no stats block (D-05) | unit | `cd modules/pathfinder && python -m pytest tests/test_npc.py::test_npc_export_foundry_no_stats -x` | ❌ W0 | ⬜ pending |
| 30-01-06 | 01 | 1 | OUT-02 | — | N/A | unit | `cd modules/pathfinder && python -m pytest tests/test_npc.py::test_npc_token_success -x` | ❌ W0 | ⬜ pending |
| 30-01-07 | 01 | 1 | OUT-02 | — | Fixed template enforces `--ar 1:1` and `--no text` (D-09) | unit | `cd modules/pathfinder && python -m pytest tests/test_npc.py::test_npc_token_template_structure -x` | ❌ W0 | ⬜ pending |
| 30-01-08 | 01 | 1 | OUT-03 | — | N/A | unit | `cd modules/pathfinder && python -m pytest tests/test_npc.py::test_npc_stat_success -x` | ❌ W0 | ⬜ pending |
| 30-01-09 | 01 | 1 | OUT-03 | — | Empty stats dict when no stats block (D-16) | unit | `cd modules/pathfinder && python -m pytest tests/test_npc.py::test_npc_stat_no_stats -x` | ❌ W0 | ⬜ pending |
| 30-01-10 | 01 | 1 | OUT-04 | — | PDF bytes start with `%PDF` (Pitfall 6: `.getvalue()` not `.read()`) | unit | `cd modules/pathfinder && python -m pytest tests/test_npc.py::test_npc_pdf_success -x` | ❌ W0 | ⬜ pending |
| 30-01-11 | 01 | 1 | OUT-04 | — | PDF with header-only when no stats block (D-20) | unit | `cd modules/pathfinder && python -m pytest tests/test_npc.py::test_npc_pdf_no_stats -x` | ❌ W0 | ⬜ pending |
| 30-02-01 | 02 | 2 | OUT-01–OUT-04 | T-30-02-01 | `NPCOutputRequest` applies `_validate_npc_name()` validator | unit | `cd modules/pathfinder && python -m pytest tests/test_npc.py -k "export_foundry or npc_token or npc_stat or npc_pdf" -q` | ❌ W0 | ⬜ pending |
| 30-02-02 | 02 | 2 | OUT-01–OUT-04 | — | REGISTRATION_PAYLOAD contains all 10 routes | unit | `cd modules/pathfinder && python -c "from app.main import REGISTRATION_PAYLOAD; assert len(REGISTRATION_PAYLOAD['routes']) == 10; print('ok')"` | ✅ | ⬜ pending |
| 30-03-01 | 03 | 3 | OUT-01–OUT-04 | — | N/A | manual | Trigger each slash command in Discord and confirm correct response shape | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `modules/pathfinder/tests/test_npc.py` — append nine OUT-01–OUT-04 test stubs (Plan 30-01 Task 2)
- [ ] `modules/pathfinder/app/pdf.py` — new module with `build_npc_pdf`; must exist before test imports work (Plan 30-01 Task 1)
- [ ] `modules/pathfinder/app/llm.py` — add `generate_mj_description` and `build_mj_prompt` (Plan 30-01 Task 1)
- [ ] `modules/pathfinder/pyproject.toml` — add `reportlab>=4.4.0` (Plan 30-01 Task 2)

Wave 0 is complete when: `cd modules/pathfinder && python -m pytest tests/test_npc.py -k "export_foundry or npc_token or npc_stat or npc_pdf" -q 2>&1 | grep -E "(ERROR|FAILED|passed|failed)"` shows 9 test functions present (failing RED is expected).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Discord `/npc export-foundry` attaches `.json` file to message | OUT-01 | Requires live Discord session and running module stack | Trigger command, confirm file attachment downloads and opens as valid JSON |
| Discord `/npc token` response text is usable in Midjourney | OUT-02 | Midjourney prompt quality is subjective; no bot API | Copy prompt from Discord response into Midjourney `/imagine`, confirm image generates |
| Discord `/npc stat` embed renders with correct field layout | OUT-03 | Discord embed rendering requires live client | Confirm embed shows AC, HP, saves in expected field order |
| Discord `/npc pdf` attaches valid PDF | OUT-04 | Requires live Discord session | Open attached PDF, confirm name/level/stats render correctly |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
