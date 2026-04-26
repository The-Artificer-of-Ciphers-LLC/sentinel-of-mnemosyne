---
phase: 36
slug: foundry-npc-pull-import
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-26
---

# Phase 36 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `modules/pathfinder/pyproject.toml` `[tool.pytest.ini_options]` `asyncio_mode = "auto"` |
| **Quick run command** | `cd modules/pathfinder && python -m pytest tests/test_npcs.py -x -q` |
| **Full suite command** | `cd modules/pathfinder && python -m pytest tests/ -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd modules/pathfinder && python -m pytest tests/test_npcs.py -x -q`
- **After every plan wave:** Run `cd modules/pathfinder && python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green + manual Foundry import smoke test
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 36-01-01 | 01 | 0 | FVT-04a..f | T-CORS / T-PATH | slug sanitized; GET in CORS allow_methods | unit | `pytest tests/test_npcs.py -x -q` | ❌ W0 | ⬜ pending |
| 36-01-02 | 01 | 1 | FVT-04a,b,c | — | list returns [] on Obsidian error (not 503) | unit | `pytest tests/test_npcs.py::test_list_npcs_success tests/test_npcs.py::test_list_npcs_empty tests/test_npcs.py::test_list_npcs_obsidian_down -x` | ❌ W0 | ⬜ pending |
| 36-01-03 | 01 | 1 | FVT-04d,e,f | T-PATH | 404 on missing slug; 400 on path-traversal slug | unit | `pytest tests/test_npcs.py::test_get_foundry_actor_success tests/test_npcs.py::test_get_foundry_actor_not_found tests/test_npcs.py::test_get_foundry_actor_invalid_slug -x` | ❌ W0 | ⬜ pending |
| 36-02-01 | 02 | 2 | FVT-04g | — | Button visible in actor directory header | manual | Load module in Foundry; verify "Import from Sentinel" button in header | n/a | ⬜ pending |
| 36-02-02 | 02 | 2 | FVT-04h | — | Full import flow: select → preview → actor created | manual | Live Foundry end-to-end import test | n/a | ⬜ pending |
| 36-02-03 | 02 | 2 | FVT-04i | — | Duplicate confirm → overwrite updates existing actor | manual | Live Foundry duplicate handling test | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_npcs.py` — 6 unit tests covering FVT-04a through FVT-04f (list endpoint + actor endpoint + error paths)
- [ ] No new `conftest.py` changes needed — existing mock pattern (patch `app.routes.npcs.obsidian`, `httpx.ASGITransport`) applies directly

*Existing infrastructure (pytest-asyncio, conftest.py fixtures) covers all infrastructure needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| "Import from Sentinel" button visible in actor directory | FVT-04g | Requires live Foundry VTT runtime; no testable DOM layer outside browser | Load updated module in Foundry, open Actors tab, verify button in header |
| Full import flow: select NPC → preview → Import → Actor in world | FVT-04h | Requires live Foundry + live Sentinel stack | Run `/clear`, open Actors, click Import button, select NPC, confirm actor created |
| Duplicate handling confirm dialog | FVT-04i | Requires live Foundry with existing actor of same name | Create actor "Varek", re-import; confirm "Overwrite?" dialog appears; test Yes/No paths |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
