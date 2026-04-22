---
phase: 29
slug: npc-crud-obsidian-persistence
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-22
---

# Phase 29 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `modules/pathfinder/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd modules/pathfinder && python -m pytest tests/ -x -q` |
| **Full suite command** | `cd modules/pathfinder && python -m pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds |

`asyncio_mode = "auto"` already set in pyproject.toml — no additional config needed.

---

## Sampling Rate

- **After every task commit:** Run `cd modules/pathfinder && python -m pytest tests/ -x -q`
- **After every plan wave:** Run `cd modules/pathfinder && python -m pytest tests/ -v && cd interfaces/discord && python -m pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 29-01-01 | 01 | 1 | NPC-01 | T-29-03 | slugify() strips path traversal chars | unit | `pytest tests/test_npc.py::test_npc_create_success -x` | ❌ W0 | ⬜ pending |
| 29-01-02 | 01 | 1 | NPC-01 | — | 409 on collision, no overwrite | unit | `pytest tests/test_npc.py::test_npc_create_collision -x` | ❌ W0 | ⬜ pending |
| 29-02-01 | 02 | 1 | NPC-02 | T-29-02 | JSON parse failure = safe error | unit | `pytest tests/test_npc.py::test_npc_update_identity_fields -x` | ❌ W0 | ⬜ pending |
| 29-03-01 | 03 | 1 | NPC-03 | — | N/A | unit | `pytest tests/test_npc.py::test_npc_show_returns_fields -x` | ❌ W0 | ⬜ pending |
| 29-03-02 | 03 | 1 | NPC-03 | — | 404 propagated correctly | unit | `pytest tests/test_npc.py::test_npc_show_not_found -x` | ❌ W0 | ⬜ pending |
| 29-04-01 | 04 | 2 | NPC-04 | — | Closed enum rejects invalid types | unit | `pytest tests/test_npc.py::test_npc_relate_valid -x` | ❌ W0 | ⬜ pending |
| 29-04-02 | 04 | 2 | NPC-04 | — | 422 for invalid relation type | unit | `pytest tests/test_npc.py::test_npc_relate_invalid_type -x` | ❌ W0 | ⬜ pending |
| 29-05-01 | 05 | 2 | NPC-05 | T-29-04 | Timeout + size limit on attachment | unit | `pytest tests/test_npc.py::test_npc_import_basic -x` | ❌ W0 | ⬜ pending |
| 29-05-02 | 05 | 2 | NPC-05 | — | Collision NPCs skipped + reported | unit | `pytest tests/test_npc.py::test_npc_import_collision_skipped -x` | ❌ W0 | ⬜ pending |
| 29-06-01 | 06 | 1 | (bot) | T-29-05 | X-Sentinel-Key forwarded to module | unit | `pytest interfaces/discord/tests/test_subcommands.py::test_pf_dispatch_create -x` | ❌ W0 | ⬜ pending |
| 29-06-02 | 06 | 1 | (bot) | — | Error embed on invalid relation type | unit | `pytest interfaces/discord/tests/test_subcommands.py::test_pf_dispatch_relate_invalid -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `modules/pathfinder/tests/test_npc.py` — stubs for NPC-01 through NPC-05 (all test functions above, parametrized with mocked Obsidian + LiteLLM clients)
- [ ] `interfaces/discord/tests/test_subcommands.py` — add `test_pf_dispatch_*` cases (file exists, extend it)
- [ ] Framework: already configured — no install needed (`asyncio_mode = "auto"` confirmed in pyproject.toml)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Discord attachment receipt (`on_message`) | NPC-05 | Discord API cannot be mocked reliably in unit tests without a live bot token | Upload a Foundry JSON file as a reply to a `/sen` thread; verify summary embed appears |
| Obsidian note visible in vault | NPC-01 | Requires live Obsidian REST API | Run `:pf npc create` end-to-end; open Obsidian, confirm note at `mnemosyne/pf2e/npcs/{slug}.md` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
