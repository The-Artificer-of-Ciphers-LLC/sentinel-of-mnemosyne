---
phase: 48
slug: module-scaffold-shared-vault-client
status: ready
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-08
---

# Phase 48 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Populated from the real per-task `<automated>` commands in 48-01..48-05.

---

## Test Infrastructure

This phase spans **four separate pytest venvs** (one per package). All use `pytest` with
`pytest-asyncio` in `asyncio_mode = "auto"`.

| Venv | Framework | Config file | Full-suite command | Baseline |
|------|-----------|-------------|--------------------|----------|
| `sentinel-core` | pytest 7.x + asyncio | `sentinel-core/pyproject.toml` | `cd sentinel-core && .venv/bin/python -m pytest -q` | ~605 (unchanged this phase) |
| `modules/pathfinder` (pf2e) | pytest + asyncio (`asyncio_mode=auto`) | `modules/pathfinder/pyproject.toml` | `cd modules/pathfinder && .venv/bin/python -m pytest -q` | ~405 (client body swapped only) |
| `shared` (`sentinel_shared`) | pytest | `shared/pyproject.toml` | `cd shared && .venv/bin/python -m pytest -q` | ~35 baseline + 2 new files |
| `modules/music` | pytest + asyncio (`asyncio_mode=auto`) | `modules/music/pyproject.toml` (created in Plan 03) | `cd modules/music && .venv/bin/python -m pytest -q` | new this phase |

- **Quick command (per task):** the task's own targeted `<automated>` command (one test file / import / grep) — see the Per-Task Verification Map. ~2–8s.
- **Full command (per wave / pre-verify):** the owning venv's whole `pytest -q`; the phase gate (Plan 05, Task 1) runs all four venvs together. ~60–90s (dominated by `sentinel-core` ~605).

---

## Sampling Rate

- **After every task commit:** Run that task's `<automated>` quick command (its per-file pytest / import / grep). Max latency ~10s.
- **After every plan / wave:** Run the owning venv's full suite (`pytest -q`). Max latency ~90s.
- **Before `/gsd-verify-work`:** The consolidated **four-venv** gate (Plan 05, Task 1) must be green — `sentinel-core` and `modules/pathfinder` show ZERO regression; `shared` + `modules/music` include the new tests.
- **Max feedback latency:** quick ≤ 10s · full four-venv ≤ 90s.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 48-01-01 | 01 | 1 | MUS-05 | — | Orphan rule vendored once (no per-module drift); full-path target does NOT resolve to a bare stem | unit (TDD) | `cd shared && .venv/bin/python -m pytest -q tests/test_graph_check.py` | ❌ in-task (TDD) | ⬜ pending |
| 48-01-02 | 01 | 1 | XMOD-01 | T-48-01, T-48-02 | Bearer token set/omitted but never logged; verbatim behavior lift (120s `put_note` timeout, safe-degrade) | unit (TDD) | `cd shared && .venv/bin/python -m pytest -q tests/test_obsidian.py` | ❌ in-task (TDD) | ⬜ pending |
| 48-02-01 | 02 | 2 | XMOD-01 | T-48-04 | MRO resolves construction to `ObsidianClientCore` (auth-header init preserved; no mixin `__init__`) | unit + grep | `grep -c "async def get_note" modules/pathfinder/app/obsidian.py` (→ 0) · `cd modules/pathfinder && .venv/bin/python -c "from app.obsidian import ObsidianClient; assert 'ObsidianClientCore' in [b.__name__ for b in ObsidianClient.__mro__]"` | ✅ (pf2e venv) | ⬜ pending |
| 48-02-02 | 02 | 2 | XMOD-01 | T-48-03 | No write/auth drift — full pf2e suite green with no test edits (D-06) | regression | `cd modules/pathfinder && .venv/bin/python -m pytest -q` | ✅ (existing ~405) | ⬜ pending |
| 48-03-01 | 03 | 2 | MUS-01 | T-48-06 | Registration key via Docker `secrets:` file, not plaintext `environment:` | config/smoke | `cd modules/music && docker compose config >/dev/null 2>&1 || true; test -f pyproject.toml && test -f Dockerfile && test -f compose.yml && .venv/bin/python -c "import fastapi, pydantic_settings, httpx"` · `grep -c "modules/music/compose.yml" docker-compose.yml` | ⚙️ W2 (creates music venv) | ⬜ pending |
| 48-03-02 | 03 | 2 | MUS-01, MUS-02 | T-48-05, T-48-07 | `X-Sentinel-Key` on register/heartbeat; core-only client never imports Core's Vault (MUS-02 grep empty) | unit/import | `cd modules/music && .venv/bin/python -c "from app.main import app, REGISTRATION_PAYLOAD, _register_with_retry, _registration_heartbeat; assert REGISTRATION_PAYLOAD['name']=='music' and [r['path'] for r in REGISTRATION_PAYLOAD['routes']]==['healthz']"` · `cd modules/music && .venv/bin/python -c "from fastapi.testclient import TestClient; from app.main import app; r=TestClient(app).get('/healthz'); assert r.status_code==200 and r.json().get('module')=='music', r.text"` | ⚙️ W2 (music venv) | ⬜ pending |
| 48-03-03 | 03 | 2 | MUS-01 | T-48-05 | Registration retry/backoff proven; `SystemExit(1)` after 5 failures; posted json == `REGISTRATION_PAYLOAD` | unit | `cd modules/music && .venv/bin/python -m pytest -q` | ⚙️ W2 (music venv) | ⬜ pending |
| 48-04-01 | 04 | 3 | MUS-05, MUS-02 | T-48-10 | Zero-orphan + `_schema` proven via vendored rule; seed writes only through module client (no Core Vault import) | unit (pure, TDD) | `cd modules/music && .venv/bin/python -m pytest -q tests/test_music_vault_seed.py` | ⚙️ W2 (music venv) | ⬜ pending |
| 48-04-02 | 04 | 3 | MUS-01 | T-48-08, T-48-09 | Override generated from Core defaults + `music/`; drift guard keeps `security/`/`self/`/`pf2e/` protected; lands atomically with the seed writer (D-13) | unit/drift + git | `cd sentinel-core && .venv/bin/python -m pytest -q tests/test_env_override_matches_core_defaults.py` · `cd modules/music && .venv/bin/python scripts/gen_sweep_protection_env.py | grep -c "music/"` | ✅ (core venv) / ⚙️ W2 | ⬜ pending |
| 48-05-01 | 05 | 4 | MUS-01, MUS-02, MUS-05 | — | Zero cross-suite regression from the shared-client cutover across all four venvs | regression (4 venvs) | `cd sentinel-core && .venv/bin/python -m pytest -q` · `cd modules/pathfinder && .venv/bin/python -m pytest -q` · `cd shared && .venv/bin/python -m pytest -q` · `cd modules/music && .venv/bin/python -m pytest -q` | ✅ / ⚙️ W2 (music) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**File-Exists legend:** ✅ = the venv/suite pre-exists at phase start and the verify runs immediately · ❌ in-task (TDD) = the test file is authored inside its own task's RED step on an existing venv (no external Wave 0 blocker) · ⚙️ W2 = requires `modules/music/.venv`, created by **48-03-01 (Wave 2)** before any music-venv verify runs (satisfied by the wave/dependency ordering).

---

## Wave 0 Requirements

**No dedicated Wave 0 test-scaffold plan is required.**

- Three of the four venvs already exist with pytest configured — **existing infrastructure covers** the `sentinel-core`, `modules/pathfinder`, and `shared` suites (including the Core-side drift test in 48-04-02 and the Core/pf2e/shared regression runs in 48-05-01).
- The fourth venv, `modules/music/.venv`, is created by **48-03-01 (Wave 2, Task 1)** (`uv sync`, else `python -m venv .venv && .venv/bin/pip install -e .[dev]`). Every music-venv verify runs strictly after it: 48-03-02/03 (same plan, later tasks), 48-04-* (Wave 3), 48-05 (Wave 4). The wave/dependency graph enforces this ordering, so no pre-phase Wave 0 is needed.
- All per-task test files are authored within their own tasks: TDD RED step for `test_graph_check.py`, `test_obsidian.py`, `test_music_vault_seed.py`; standard authoring for `test_registration.py`, `test_healthz.py`, `test_env_override_matches_core_defaults.py`. None are left MISSING.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live-Docker smoke — music module registers on the live stack, `/healthz` returns 200 via the Core proxy, the 4-note `music/` hub-mesh is present in the live vault, and a real sweep leaves it intact (Plan 05, Task 2 · threats T-48-11/T-48-12) | MUS-01, MUS-05 | Live Docker stack + live Obsidian vault + a real `:vault-sweep` are integration facts that mocked unit tests (mocked registration, pure orphan check) cannot establish; must run from the deploy checkout holding `secrets/` + `.env` | 1) Apply the generated override to the deploy `.env` BEFORE first write (`python3 modules/music/scripts/gen_sweep_protection_env.py >> .env`; confirm `security/`/`self/`/`pf2e/`/`music/` all present in `SWEEP_SKIP_PREFIXES`). 2) `docker compose --profile music up -d`; confirm `music-module` running (probe port with `lsof`, not `/dev/tcp`). 3) `curl -sf -H "X-Sentinel-Key: $SENTINEL_API_KEY" http://localhost:8000/modules` lists `music`; restart core and re-check within ~30s (heartbeat re-register). 4) `curl -sf http://localhost:8000/modules/music/healthz` → 200 `{"status":"ok","module":"music"}`. 5) Confirm the 4 hub-mesh notes exist in the vault. 6) Trigger `:vault-sweep`; confirm NONE of the four `music/` notes were relocated to `_trash/`. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none MISSING; existing infra + Wave-2 music venv covers all)
- [x] No watch-mode flags
- [x] Feedback latency < 90s (quick ≤ 10s · full four-venv ≤ 90s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-08
