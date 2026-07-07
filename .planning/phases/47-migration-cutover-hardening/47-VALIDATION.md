---
phase: 47
slug: migration-cutover-hardening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-06
---

# Phase 47 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (two separate venvs — `sentinel-core` and `interfaces/discord`) |
| **Config file** | `sentinel-core/pytest.ini` / `interfaces/discord/pytest.ini` (existing) |
| **Quick run command** | `cd sentinel-core && .venv/bin/python -m pytest tests/test_pipeline_orchestrator.py tests/test_vault_sweeper.py tests/test_graph_analysis.py tests/test_links_sidecar_index.py -q` |
| **Full suite command** | `cd sentinel-core && .venv/bin/python -m pytest tests/ -q` (590 collected) **AND** `cd interfaces/discord && .venv/bin/python -m pytest tests/ -q` (326 collected) — both venvs; there is no single combined command |
| **Estimated runtime** | ~60–120 seconds (full, both venvs) |

---

## Sampling Rate

- **After every task commit:** Run the quick-run command (pipeline / sweeper / graph / links-sidecar subset)
- **After every plan wave:** Run the full suite command (both venvs)
- **Before `/gsd-verify-work`:** Full suite green (both venvs) **and** the v0.6.0 regression ledger check-in row appended
- **Max feedback latency:** ~120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 47-01-01 | 01 | 1 | MIG-01 | — | Every flat-7 note lands under `notes/` (Reduce) or `ops/` (direct) with `_schema` + ≥1 wikilink; none grandfathered | integration | `cd sentinel-core && .venv/bin/python -m pytest tests/test_migration_orchestrator.py::test_full_backfill_no_grandfathering -x` | ❌ W0 | ⬜ pending |
| 47-01-02 | 01 | 1 | MIG-02 | T-47-03 | Embedding sidecar key patched with the move (not orphaned); pre/post `:graph` orphan diff = 0 new (notes/); ops-bound backlink-scan diff = 0 new dangling | integration | `cd sentinel-core && .venv/bin/python -m pytest tests/test_migration_orchestrator.py::test_embedding_and_wikilink_preservation -x` | ❌ W0 | ⬜ pending |
| 47-02-01 | 02 | 1 | MIG-02 / D-02 | T-47-02 | Atomic rollback replays the recorded inverse of every REST op on hard failure — vault returns to exact pre-migration state | integration | `cd sentinel-core && .venv/bin/python -m pytest tests/test_migration_rollback_ledger.py -x` | ❌ W0 | ⬜ pending |
| 47-03-01 | 03 | 2 | MIG-03 | — | v0.6.0 regression ledger MEM-01..09 rows still green; a Phase-47 boundary check-in row is appended | artifact + suite | `grep -q 'MEM-09' .planning/v0.6.0-REGRESSION-LEDGER.md && cd sentinel-core && .venv/bin/python -m pytest tests/ -k "mem0 or recall or recency" -q` | ✅ MEM-0x tests; ❌ ledger append is a plan task | ⬜ pending |
| 47-03-02 | 03 | 2 | MIG-04 | — | Full sentinel-core (590) + discord (326) suites stay green post-migration; no shrinking count | full suite | `cd sentinel-core && .venv/bin/python -m pytest tests/ -q` AND `cd interfaces/discord && .venv/bin/python -m pytest tests/ -q` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Task IDs are indicative — the planner owns final plan/wave/task numbering.*

---

## Wave 0 Requirements

- [ ] `sentinel-core/tests/test_migration_orchestrator.py` — MIG-01, MIG-02 (backfill correctness, embedding sidecar-key + wikilink preservation, rollback-on-failure)
- [ ] `sentinel-core/tests/test_migration_rollback_ledger.py` — D-02/D-02a (atomic rollback replays the recorded inverse of every op)
- [ ] `sentinel-core/tests/test_migration_routes.py` — the new admin-gated `:migrate` route shape (mirror `test_note_routes.py` sweep-route tests)
- [ ] A dedicated **ops-bound backlink pre/post scan helper** + its test — no existing module covers `ops/`-scoped wikilink checking; `graph_analysis`/`links_sidecar_index` are `notes/`-scoped **by design and must NOT be widened** (single-purpose scope). Write a small new scan function instead.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Obsidian `[[wikilink]]` survives a real cross-directory move (title-based resolution) | MIG-02 / D-03 | Sentinel's own `:graph` cannot prove the *live Obsidian app* still resolves the link — it only reads the links sidecar | Against the real vault: move one note via REST keeping its title, open Obsidian, confirm an inbound `[[link]]` still resolves; then re-run `:graph` and confirm dangling count unchanged |
| Physical flat-7 directory names (`reference/` vs `references/`, etc.) | MIG-01 | Vault is REST-only, no local mount — actual dir names unconfirmed at plan time | Resolve empirically in the `:migrate --dry-run` probe before any writes; dry-run must list the real source dirs it found |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
