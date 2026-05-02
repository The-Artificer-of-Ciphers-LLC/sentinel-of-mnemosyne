---
quick_id: 260502-cky
slug: vault-capability-seam-introduce-vault-pr
date: 2026-05-02
status: planned
---

# Vault Capability Seam — Introduce `Vault` Protocol + `ObsidianVault` Adapter

## Description

Introduce the **Vault** capability seam: a single module `app/vault.py` holding a `Vault` Protocol plus a concrete `ObsidianVault` adapter that replaces today's `ObsidianClient`. The seam absorbs (a) the inline persona probe currently in `main.py` lifespan, (b) the trash/relocate/lockfile orchestration currently in `vault_sweeper.py`, and (c) the loose HTTP primitives. A dict-backed `FakeVault` lives in `tests/fakes/vault.py` for tests. `app.state.obsidian_client` is renamed to `app.state.vault` everywhere. ADR-0001's startup contract is preserved end-to-end via a new `VaultUnreachableError` typed exception and a `read_persona() -> str | None` capability that distinguishes "vault reachable, file 404" from "vault unreachable".

## Decisions (locked)

| Q | Pick | Meaning |
|---|------|---------|
| Q1 | (a) Wide surface | Vault owns capability methods AND primitives. One seam, one mock target. |
| Q2 | (b) Protocol + adapter | `Vault` is a `typing.Protocol`; `ObsidianVault` is the concrete adapter. Tests use `FakeVault`. |
| Q3 | (a) Typed exceptions | `read_persona() -> str \| None`; raises `VaultUnreachableError` on transport failure. Pairs with existing `ContextLengthError`/`EmbeddingModelUnavailable`/`ProviderUnavailableError` pattern. |
| Q4 | (a) Single file | Both Protocol AND `ObsidianVault` live in `app/vault.py`. Breaks the `app/clients/` convention — operator pre-authorized. |
| Q5 | OK as proposed | Capability list approved (see below). |
| Q6 | (a) FakeVault dict-backed | In-memory dict-backed full Protocol implementation, ~150 LOC, in `tests/fakes/vault.py`. |

### ADR-0001 startup contract — MUST be preserved end-to-end

- Vault reachable + `sentinel/persona.md` 404 → hard fail at startup (RuntimeError raised by lifespan)
- Vault unreachable at startup → continue with hardcoded `_FALLBACK_PERSONA`
- Per-request: persona read fails → fallback + warning, never 503

Post-refactor implementation:
- `vault.read_persona()` returns `str | None`. `None` = vault reachable, file 404.
- `vault.read_persona()` raises `VaultUnreachableError` on transport failure (timeout, connection error, 5xx).
- Lifespan:
  - returns `None` → raise `RuntimeError` (ADR-0001 hard-fail branch)
  - raises `VaultUnreachableError` → log warning + continue (graceful-degrade branch)
  - returns `str` → log success
- `MessageProcessor._append_hot_tier`: per-request read; on `None` or `VaultUnreachableError` → `_FALLBACK_PERSONA`.

**No behavior change at the contract level. Only the implementation site moves.**

## Locked Vault capability list

| Method | Replaces | Notes |
|---|---|---|
| `read_persona() -> str \| None` | `main.py:194-217` inline probe | New. Raises `VaultUnreachableError` on transport failure. |
| `get_user_context(user_id) -> str \| None` | `ObsidianClient.get_user_context` | Verbatim. Used by `test_auth.py`, `test_message.py`. Preserves existing call sites. |
| `read_self_context(path) -> str` | `ObsidianClient.read_self_context` | Verbatim. |
| `read_recent_sessions(user_id, limit) -> list[str]` | `ObsidianClient.get_recent_sessions` | Verbatim. |
| `write_session_summary(path, content) -> None` | `ObsidianClient.write_session_summary` | Swallow-on-failure semantics preserved (commit `7601883`). |
| `find(query) -> list[dict]` | `ObsidianClient.search_vault` | Renamed. |
| `move_to_trash(path, when: datetime) -> str` | `vault_sweeper.move_to_trash` | Returns trash path. |
| `relocate(src, dst) -> None` | `vault_sweeper.move_to_topic_folder` | |
| `acquire_sweep_lock(now) -> bool` / `release_sweep_lock() -> None` | `vault_sweeper.acquire_lock` / `release_lock` | Lockfile is in vault → Vault concern. |
| `list_under(prefix) -> list[str]` | `ObsidianClient.list_directory` | Renamed for domain clarity. |
| `read_note(path)` / `write_note(path, body)` / `delete_note(path)` / `patch_append(path, body)` | unchanged primitives | Verbatim. |
| `check_health() -> bool` | `ObsidianClient.check_health` | Verbatim. |

## Files modified

### Create
- `sentinel-core/app/vault.py` — `Vault` Protocol + `ObsidianVault` adapter + `VaultUnreachableError`.
- `sentinel-core/tests/fakes/__init__.py` — package marker.
- `sentinel-core/tests/fakes/vault.py` — `FakeVault` dict-backed Protocol implementation (~150 LOC).
- `docs/adr/0002-vault-seam-location.md` — records the convention break for Q4(a) (Vault Protocol + adapter live in `app/vault.py`, not `app/clients/`).

### Edit
- `sentinel-core/app/main.py` — lifespan replaces inline probe (lines 194-217) with `vault.read_persona()` + typed-exception branching; `app.state.obsidian_client` → `app.state.vault` at every reference (line 180 construction, line 185 setter, line 187 health probe, line 242 processor wiring, line 332 status check, plus the import on line 26).
- `sentinel-core/app/services/vault_sweeper.py` — `run_sweep` calls `vault.move_to_trash` / `vault.relocate` / `vault.acquire_sweep_lock` / `vault.release_sweep_lock`. Helpers `is_in_topic_dir` and `propose_topic_move` stay (decision logic).
- `sentinel-core/app/services/message_processing.py` — `_append_hot_tier` uses `vault` (renamed parameter / attribute access).
- `sentinel-core/app/routes/note.py` — `request.app.state.obsidian_client` → `request.app.state.vault`.
- `sentinel-core/app/routes/message.py` — background-task `obsidian.write_session_summary` → `vault.write_session_summary`.
- `sentinel-core/app/routes/status.py` — both `request.app.state.obsidian_client` references (lines 13, 40) → `request.app.state.vault`.
- `sentinel-core/scripts/trash_vault_root_junk.py` — `from app.clients.obsidian import ObsidianClient` → `from app.vault import ObsidianVault`; update construction site accordingly.
- `sentinel-core/tests/test_message.py` — autouse fixture: `MagicMock(obsidian)` → `FakeVault`; rename `app.state.obsidian_client` → `app.state.vault`.
- `sentinel-core/tests/test_auth.py` — fixture/setup uses `FakeVault`; rename `app.state.obsidian_client` → `app.state.vault` at lines 52, 67, 70, 97; `get_user_context` calls preserved verbatim.
- `sentinel-core/tests/test_cors.py` — rename `app.state.obsidian_client` → `app.state.vault` at line 21.
- `sentinel-core/tests/test_integration_obsidian_llm.py` — replace `app.state.obsidian_client = mock_obsidian` with `app.state.vault = fake_vault`; the 8 hits cover `search_vault`/`get_recent_sessions`/`read_self_context` mocks → migrate to `FakeVault` pre-population (search_vault → find).
- `sentinel-core/tests/test_vault_sweeper.py` — `MagicMock(spec=ObsidianClient)` → `FakeVault`.
- `CLAUDE.md`, `README.md` (sentinel-core or root, wherever operator setup is documented) — `ObsidianClient` references → `Vault` / `ObsidianVault`.

### Rename
- `sentinel-core/tests/test_obsidian_client.py` → `sentinel-core/tests/test_obsidian_vault.py`. Inside: `ObsidianClient` → `ObsidianVault`, `search_vault` → `find`, `list_directory` → `list_under`.

### Delete
- `sentinel-core/app/clients/obsidian.py` — deleted in task 5 after the shim is no longer needed.

## Tasks

Six atomic commits, in order. Each commit must leave the tree green (`pytest -q` and `ruff check .` both pass).

---

### Task 1 — Create `app/vault.py` with Protocol + `ObsidianVault` (wholesale rename of `ObsidianClient`)

**Files:** `sentinel-core/app/vault.py` (new), `sentinel-core/app/clients/obsidian.py` (replace with shim).

**Action:**
- Create `app/vault.py`. Move the entire `ObsidianClient` class body verbatim from `app/clients/obsidian.py` into `app/vault.py` as `class ObsidianVault`.
- Rename methods inside `ObsidianVault`: `search_vault` → `find`, `list_directory` → `list_under`. (Method bodies unchanged.) `get_user_context` keeps its name.
- Define `class Vault(typing.Protocol):` covering every current method on `ObsidianVault` (use the locked capability list above for the full surface — `read_persona` and the sweep methods come in tasks 2–3, so omit them here; this protocol expands across tasks). `get_user_context` is part of this initial Protocol surface.
- Add `class VaultUnreachableError(Exception): pass`.
- Replace `app/clients/obsidian.py` with a transitional shim — use a thin subclass that re-exposes the legacy method names without polluting `ObsidianVault` itself:
  ```python
  # app/clients/obsidian.py — backwards-compat shim, deleted in task 5
  from app.vault import ObsidianVault, VaultUnreachableError  # noqa: F401

  class ObsidianClient(ObsidianVault):
      """Deprecated alias. Use app.vault.ObsidianVault instead."""
      search_vault = ObsidianVault.find
      list_directory = ObsidianVault.list_under

  __all__ = ["ObsidianClient"]
  ```
  This keeps `ObsidianVault` clean (no legacy method aliases live on it) while existing call sites against `ObsidianClient` continue to work for the duration of the transition window. The shim file is deleted in task 5.

**Verify:**
- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q` → all existing 243 tests pass with no source-call-site changes.
- `cd sentinel-core && uvx ruff check .` → 0 errors.

**Done:**
- `app/vault.py` exists with `Vault` Protocol, `ObsidianVault` class, `VaultUnreachableError`.
- All existing call sites still work via the shim.

---

### Task 2 — Add `read_persona()` capability + absorb lifespan inline probe

**Files:** `sentinel-core/app/vault.py`, `sentinel-core/app/main.py`, `sentinel-core/tests/test_obsidian_client.py` (still named this; renamed in task 5).

**Action:**
- On `ObsidianVault`, add `async def read_persona(self) -> str | None`:
  - GET `/vault/sentinel/persona.md`.
  - 200 → return body string.
  - 404 → return `None`.
  - timeout / connection error / 5xx → raise `VaultUnreachableError` (chain original via `from`).
- Add `read_persona` to the `Vault` Protocol.
- In `main.py` lifespan, replace the inline probe at lines ~194-217 with:
  ```python
  try:
      persona = await vault.read_persona()
      if persona is None:
          raise RuntimeError(
              "Vault reachable but sentinel/persona.md not found — "
              "ADR-0001 hard-fail: refusing to start without persona contract."
          )
      logger.info("Persona loaded from vault (%d chars)", len(persona))
      app.state.persona = persona
  except VaultUnreachableError as e:
      logger.warning("Vault unreachable at startup; using fallback persona: %s", e)
      app.state.persona = _FALLBACK_PERSONA
  ```
  (Adjust to match the existing `app.state` attribute used for persona — preserve current attribute name.)
- Add three behavioral tests for `read_persona()` in `test_obsidian_client.py`:
  1. 200 with body → returns the string.
  2. 404 → returns `None`.
  3. Transport failure (mock `httpx.ConnectError` or timeout) → raises `VaultUnreachableError`.
  Each test calls `await vault.read_persona()` and asserts the observable result/exception. No source-grep, no mock-call-shape-only assertions.

**Verify:**
- `pytest -q` → all pass, including 3 new persona tests.
- `ruff check .` → clean.
- Manual sanity: lifespan no longer references `httpx` directly for the persona probe; the inline 24-line block is gone.

**Done:**
- `vault.read_persona()` exists and is exercised by lifespan.
- ADR-0001 contract paths (vault-up+404 hard-fail, vault-down graceful-degrade, vault-up+200 success) are all covered by tests.

---

### Task 3 — Add sweep capabilities to `ObsidianVault`; rewire `vault_sweeper`

**Files:** `sentinel-core/app/vault.py`, `sentinel-core/app/services/vault_sweeper.py`, `sentinel-core/tests/test_vault_sweeper.py` (test additions only; full FakeVault swap is task 4).

**Action:**
- Move method bodies from `vault_sweeper.py` into `ObsidianVault`:
  - `move_to_trash(path, when: datetime) -> str` (vault_sweeper lines 271–315) — returns trash path.
  - `relocate(src, dst) -> None` (lines 332–393, body of `move_to_topic_folder`).
  - `acquire_sweep_lock(now) -> bool` (lines 416–440).
  - `release_sweep_lock() -> None` (lines 440–450).
- Add all four to the `Vault` Protocol.
- Helpers `is_in_topic_dir` and `propose_topic_move` stay in `vault_sweeper.py` — they are decision logic, not Vault primitives.
- Update `vault_sweeper.run_sweep` (and its callers inside the module) to call `vault.move_to_trash(...)`, `vault.relocate(...)`, `vault.acquire_sweep_lock(...)`, `vault.release_sweep_lock(...)` against the injected vault. The sweeper's signature accepts the Vault (existing parameter renamed if needed).
- Add direct behavioral tests against `ObsidianVault` for each new method. **Each test must assert observable state mutations**, not just request shape:
  - `move_to_trash(src, when)`: after the call, `vault.read_note(src)` returns `""` (source gone) AND `vault.read_note(dst_returned_by_call)` returns the original body.
  - `relocate(src, dst)`: after the call, `vault.read_note(src)` returns `""` AND `vault.read_note(dst)` returns the original body.
  - `acquire_sweep_lock(now)`: returns `True` on first call; second call returns `False`; after `release_sweep_lock()`, next `acquire_sweep_lock` returns `True`.
  - Transport errors raise `VaultUnreachableError`.
  Mock the HTTP layer for `ObsidianVault` direct tests; assertions are on observable post-state. (FakeVault makes the same patterns trivial to test in higher-level sweeper tests.) Do not weaken existing sweeper tests.

**Verify:**
- `pytest -q` → all sweeper tests pass + new direct Vault tests pass.
- `ruff check .` → clean.
- `rg -n "def (move_to_trash|move_to_topic_folder|acquire_lock|release_lock)" sentinel-core/app/services/vault_sweeper.py` → 0 matches (bodies migrated).

**Done:**
- Sweep primitives live on `ObsidianVault`.
- `vault_sweeper.py` retains only decision logic (`is_in_topic_dir`, `propose_topic_move`, `run_sweep` orchestration).

---

### Task 4 — Build `FakeVault` and migrate `test_vault_sweeper.py`

**Files:** `sentinel-core/tests/fakes/__init__.py` (new), `sentinel-core/tests/fakes/vault.py` (new), `sentinel-core/tests/test_vault_sweeper.py` (fixture swap).

**Action:**
- Create `tests/fakes/__init__.py`.
- Create `tests/fakes/vault.py` with `class FakeVault:` implementing the full `Vault` Protocol against `dict[str, str]` (path → body) and `dict[str, dict]` (path → frontmatter). ~150 LOC.
  - `read_note` / `write_note` / `delete_note` / `patch_append` mutate the dict.
  - `find(query)` does a substring scan over bodies.
  - `list_under(prefix)` filters keys.
  - `read_persona()` returns `self._notes.get("sentinel/persona.md")` (None on miss). A `raise_unreachable: bool` flag flips it into the `VaultUnreachableError` branch for tests.
  - `get_user_context(user_id)` returns `self._notes.get("self/identity.md")` (None on miss) — single-user system per D-01.
  - `move_to_trash(path, when)` moves the entry to `Trash/{when:%Y-%m-%d}/{basename}` and returns the new key.
  - `relocate(src, dst)` re-keys the entry.
  - `acquire_sweep_lock(now)` / `release_sweep_lock()` flip a bool flag (with stale-detection mirroring the real lockfile semantics if any test relies on it).
  - `read_self_context`, `read_recent_sessions`, `write_session_summary`, `check_health` — minimal dict-backed behavior.
- In `test_vault_sweeper.py`, replace `MagicMock(spec=ObsidianClient)` instantiation in fixtures with `FakeVault()`. Assertions and call paths remain identical (per Test-Rewrite Ban "fixture-wiring refactor" allowance).
- Commit body documents: "Fixture-wiring refactor under Test-Rewrite Ban allowed list — assertions and call paths preserved; only the test double's implementation changed (MagicMock → FakeVault)."

**Verify:**
- `pytest -q tests/test_vault_sweeper.py` → all pass.
- `pytest -q` → full suite pass.
- `ruff check .` → clean.

**Done:**
- `FakeVault` exists and is the canonical test double for the Vault seam.
- `test_vault_sweeper.py` runs against `FakeVault`, no `MagicMock(spec=ObsidianClient)` remains in that file.

---

### Task 5 — Migrate remaining tests, rename attribute everywhere, delete the shim

**Files:**
- Rename: `sentinel-core/tests/test_obsidian_client.py` → `sentinel-core/tests/test_obsidian_vault.py`.
- Edit (app code):
  - `sentinel-core/app/main.py` — lines 26 (import), 180 (construction), 185 (state setter), 187 (health probe), 242 (processor wiring), 332 (status health check). All `obsidian_client` references and the `app.clients.obsidian` import.
  - `sentinel-core/app/routes/note.py` — `request.app.state.obsidian_client` → `request.app.state.vault`.
  - `sentinel-core/app/routes/message.py` — background-task `obsidian.write_session_summary` → `vault.write_session_summary`.
  - `sentinel-core/app/routes/status.py` — lines 13 and 40, both `request.app.state.obsidian_client` → `request.app.state.vault`.
  - `sentinel-core/app/services/message_processing.py` — `_append_hot_tier` parameter / attribute access.
  - `sentinel-core/scripts/trash_vault_root_junk.py` — line 23 import + construction call site.
- Edit (tests):
  - `sentinel-core/tests/test_message.py` — autouse fixture `MagicMock(obsidian)` → `FakeVault()`; rename `app.state.obsidian_client` → `app.state.vault` at all hits (lines 29, 209, 221, 235 and surrounding fixture setup). Pre-populate FakeVault with whatever the existing tests' assertions require by mirroring the data the old MagicMock returned (especially `get_user_context` returns).
  - `sentinel-core/tests/test_auth.py` — fixture/setup swaps `MagicMock` for `FakeVault()`; rename `app.state.obsidian_client` → `app.state.vault` at lines 52, 67, 70, 97. `get_user_context` call site at line 67 preserved verbatim (FakeVault implements it).
  - `sentinel-core/tests/test_cors.py` — line 21, rename `app.state.obsidian_client` → `app.state.vault`.
  - `sentinel-core/tests/test_integration_obsidian_llm.py` — all 8 hits: `app.state.obsidian_client = mock_obsidian` → `app.state.vault = FakeVault()` pre-populated to satisfy the existing assertions for `search_vault`/`get_recent_sessions`/`read_self_context` (note `search_vault` → `find` rename at any test-level call sites). Assertions and call paths preserved.
- Delete: `sentinel-core/app/clients/obsidian.py` (the shim from task 1). If `app/clients/` is now empty, delete the directory; if other clients still live there, leave the directory and its `__init__.py` in place.

**Action:**
- Rename `tests/test_obsidian_client.py` → `tests/test_obsidian_vault.py`. Inside: `ObsidianClient` → `ObsidianVault`; `search_vault(` → `find(`; `list_directory(` → `list_under(`. Assertions unchanged. (Test-Rewrite Ban allowed-list: rename + fixture-wiring refactor with preserved assertions.)
- Apply the edits enumerated above. All test-side migrations (`test_message.py`, `test_auth.py`, `test_cors.py`, `test_integration_obsidian_llm.py`, `test_vault_sweeper.py` already done in task 4) happen in this same atomic commit alongside the `app.state` rename and shim deletion. The atomic-green-commit rule requires that the moment `app.state.obsidian_client` disappears from the code path, every test that referenced it is updated in the same commit — otherwise the suite breaks at fixture setup time.
- Delete `app/clients/obsidian.py` (the shim from task 1).
- Final grep gate (run as part of verify), now extended to `sentinel-core/scripts/`:
  ```
  rg -n "ObsidianClient|app/clients/obsidian|app\.state\.obsidian_client|search_vault\(|list_directory\(" sentinel-core/app sentinel-core/tests sentinel-core/scripts
  ```
  Must return 0 matches. If any comment legitimately mentions the historical name, prefer to update the comment rather than rely on `rg -v '^#'`.

**Verify:**
- `pytest -q` → all pass.
- `ruff check .` → clean.
- The grep gate above (covering `app`, `tests`, AND `scripts`) returns 0 lines.
- ADR-0001 paths still pass: the three persona tests added in task 2 remain green.

**Done:**
- One name (`Vault`/`ObsidianVault`/`vault`) used throughout `app/`, `tests/`, AND `scripts/`.
- Shim deleted; no compatibility layer remains.

---

### Task 6 — Update CLAUDE.md, README, stale docstrings, and write ADR-0002

**Files:** `CLAUDE.md`, `README.md` (root or `sentinel-core/README.md` — wherever operator setup notes live), any `app/` module docstrings that mention `ObsidianClient`, `docs/adr/0002-vault-seam-location.md` (new).

**Action:**
- Sweep the repo for prose references to `ObsidianClient`:
  ```
  rg -n "ObsidianClient" --type md
  rg -n "ObsidianClient" sentinel-core/app
  ```
- Update each hit:
  - Operator setup notes / architecture descriptions → "Vault (`ObsidianVault` adapter)".
  - Module docstrings → "Vault" / "ObsidianVault" as appropriate.
- Do **not** touch `docs/adr/0001-sentinel-persona-source.md` — its language already says "vault" and now matches the code.
- Create `docs/adr/0002-vault-seam-location.md` recording the convention break:
  - **Decision.** The Vault Protocol and the `ObsidianVault` adapter live in `sentinel-core/app/vault.py`, not in `sentinel-core/app/clients/`.
  - **Rationale.** The Vault is a *capability seam* reflecting the domain language used throughout PROJECT.md and CONTEXT.md ("vault", "persona", "self-context"), not a generic external-system HTTP client. Co-locating Protocol + adapter in a single top-level module surfaces the seam at the module hierarchy and prevents future readers from treating it as one I/O adapter among many.
  - **Operator pre-authorization.** Round-2 architecture review Q4(a) — operator selected "Single file" explicitly with full awareness that this breaks the `app/clients/` convention.
  - **Consequence.** A future architecture pass that sees `app/clients/obsidian_*.py` analogues and asks "should `vault.py` move under `clients/`?" must read this ADR first; the answer is no.

**Verify:**
- `rg -n "ObsidianClient" .` → only matches inside `.git/`, `.venv/`, or this PLAN.md (planning artifact).
- `docs/adr/0002-vault-seam-location.md` exists and contains the four sections above.
- `pytest -q` → all pass (no code changes; sanity check only).

**Done:**
- Documentation language matches code language. The Vault seam is the canonical name everywhere.
- ADR-0002 records the convention break durably so it cannot be silently "fixed" by a future refactor.

---

## Verification (overall)

- `cd sentinel-core && PYTHONPATH=$(pwd)/../shared .venv/bin/pytest -q` → all pass (~250 tests; 243 existing + ~3 persona + ~4+ direct sweep tests).
- `cd sentinel-core && uvx ruff check .` → 0 errors.
- `rg -n "ObsidianClient|app/clients/obsidian|app\.state\.obsidian_client|search_vault\(|list_directory\(" sentinel-core/app sentinel-core/tests sentinel-core/scripts` → 0 matches.
- ADR-0001 contract preserved end-to-end:
  - vault-up + persona 200 → app starts, persona loaded
  - vault-up + persona 404 → `RuntimeError` at startup (hard fail)
  - vault-down → app starts with `_FALLBACK_PERSONA` and warning logged
  - per-request persona read failure → fallback + warning, never 503
- `app.state.vault` is the only name used (no `obsidian_client` attribute anywhere).
- `docs/adr/0002-vault-seam-location.md` exists.

## Guardrail call-outs

- **Spec-Conflict Guardrail.** ADR-0001 startup contract (vault-up+404 hard-fail; vault-down graceful-degrade; vault-up+200 success; per-request fallback) is preserved end-to-end. Task 2 adds explicit behavioral tests for all three startup branches.
- **Test-Rewrite Ban.** Tasks 4 and 5 perform fixture-wiring refactors (MagicMock → FakeVault, `ObsidianClient` → `ObsidianVault` references, file rename). All assertions and call paths preserved. Per the ban's "What is fine without consent" clause: "Renaming tests, moving them between files, or refactoring fixture wiring as long as the assertions and call paths are preserved." Each commit body documents this explicitly.
- **Behavioral-Test-Only Rule.** All new tests call vault methods directly and assert observable results — return values, raised exceptions, AND dict-state mutations on `FakeVault` (e.g. after `move_to_trash(src, when)`, `read_note(src)` returns `""` and `read_note(returned_dst)` returns the body). No source-grep tests, no request-shape-only assertions, no tautologies.
- **AI Deferral Ban.** All six tasks complete in one PLAN run. No partial migration; the shim is removed in task 5; documentation is swept and ADR-0002 written in task 6.
- **Convention break (pre-authorized + recorded).** `app/vault.py` holds an I/O adapter outside `app/clients/`. Operator picked Q4(a) explicitly during the grilling; ADR-0002 (task 6) records the decision durably so a future architecture pass cannot silently "fix" it.

## Constraints

- Commit directly to `main`. No feature branches, no PRs.
- One atomic commit per task (six commits total).
- Each commit must leave the tree green (`pytest -q` + `ruff check .` both pass).
- Planner does not execute — this PLAN.md is the implementation contract.
