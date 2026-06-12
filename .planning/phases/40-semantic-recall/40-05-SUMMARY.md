---
phase: 40-semantic-recall
plan: "05"
subsystem: vault
tags: [protected-namespace, security, vault-guard, obsidian-vault, ProtectedPathError]

# Dependency graph
requires:
  - phase: 40-semantic-recall
    provides: vault.py relocate/move_to_trash primitives that this plan guards
provides:
  - PROTECTED_NAMESPACES tuple (explicit literal, env-overridable) in app/vault.py
  - is_protected_path() segment-boundary predicate in app/vault.py
  - _active_protected_namespaces() lazy settings-reader in app/vault.py
  - Settings.protected_namespaces explicit literal tuple in app/config.py
  - ProtectedPathError(SecurityError) typed refusal in app/errors.py
  - Source guard (is_protected_path(src)) in ObsidianVault.relocate
  - Destination guard (is_protected_path(dst)) in ObsidianVault.relocate (concern 6)
  - Source guard (is_protected_path(path)) in ObsidianVault.move_to_trash
  - Behavioral tests for all guards in tests/test_obsidian_vault.py
affects: [40-04, 40-06, vault-sweeper, recall, sweep-remediation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Protected-namespace guard on Vault primitives (seam-level, not caller-level)"
    - "_active_protected_namespaces() lazy settings-reader with try/except fallback (mirrors _active_skip_prefixes)"
    - "Explicit literal tuple in config.py (never implicit default) for operator-critical sets"
    - "Write/copy restore path: write_note is unguarded; relocate-into-protected is refused"

key-files:
  created: []
  modified:
    - sentinel-core/app/errors.py
    - sentinel-core/app/config.py
    - sentinel-core/app/vault.py
    - sentinel-core/tests/test_obsidian_vault.py

key-decisions:
  - "Protected set ships as (sentinel/, self/, security/) — explicit literal tuple, env-overridable via PROTECTED_NAMESPACES"
  - "Destination protection added: relocate INTO a protected namespace is also refused (concern 6)"
  - "write_note is intentionally NOT guarded — it is the operator write/copy restore path (round-3 item 4)"
  - "Guard lives on ObsidianVault primitives (Vault seam), not in sweep decision logic — every future caller inherits protection"
  - "40-04 owns vault_sweeper.py and the catch-and-continue ProtectedPathError handling in sweep branches"

patterns-established:
  - "Vault-seam guard: first-statement raise before any read/write/delete I/O"
  - "Explicit literal tuple for operator-critical namespace sets (never bare default argument)"
  - "Write/copy restore path documented in error class docstring and SUMMARY"

requirements-completed: [MEM-05]

# Metrics
duration: 4min
completed: 2026-06-12
---

# Phase 40 Plan 05: Protected-Namespace Vault Guard Summary

**Vault-seam-level ProtectedPathError guard on relocate (src+dst) and move_to_trash using an explicitly-enumerated PROTECTED_NAMESPACES tuple, blocking the sentinel/persona.md relocation incident at the primitive level**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-06-12T01:27:07Z
- **Completed:** 2026-06-12T01:31:01Z
- **Tasks:** 2 (TDD)
- **Files modified:** 4

## Accomplishments

- Added `ProtectedPathError(SecurityError)` to `app/errors.py` with docstring recording the write/copy restore path corollary
- Added `PROTECTED_NAMESPACES` explicit literal tuple, `_active_protected_namespaces()` lazy reader, and `is_protected_path()` segment-boundary predicate to `app/vault.py`
- Added `Settings.protected_namespaces` explicit literal tuple to `app/config.py` with scope-decision inline comment
- Wired source guard (`is_protected_path(src)`) and destination guard (`is_protected_path(dst)`) as the FIRST statements of `ObsidianVault.relocate`, and source guard as the FIRST statement of `ObsidianVault.move_to_trash`
- All 60 `test_obsidian_vault.py` tests pass; all 39 `test_vault_sweeper.py` tests pass; 359 full-suite pass

## Protected-Set Scope Decision (round-2 item F — explicit record)

**Shipped protected namespaces:** `("sentinel/", "self/", "security/")`

Rationale for each namespace:

- **`sentinel/`** — Non-negotiable. `sentinel/persona.md` is probed at startup in `ObsidianVault.read_persona()` and its absence crash-loops boot at `composition.py:424` (`'sentinel/persona.md missing from Vault'`). Loss of this file is the original incident.
- **`self/`** — Identity-critical. `get_user_context()` reads `self/identity.md` as the operator identity context. `RecallConfig.self_paths` lists `self/` files. While its absence degrades gracefully (returns `None`, no boot halt), the identity context is a first-class operator concern and warrants the same protection as `sentinel/`.
- **`security/`** — Operator-curated security namespace, already present in `sweep_skip_prefixes`. It is an explicit operator namespace whose loss would be silent and harmful. Protected so a sweep can never accidentally move its contents.

The fallback rule (plan objective): narrowing the set to `sentinel/`-only would be acceptable if `self/` and `security/` were proven not identity-critical, but the evidence above justifies shipping all three. Any future narrowing requires a recorded rationale in a follow-up SUMMARY — it may never be implicit.

## Operator Restore Path (round-3 item 4 — explicit record)

Because the destination guard in `ObsidianVault.relocate` refuses any call where `is_protected_path(dst)` is True, **a relocate-based restore of a protected file is blocked by design**.

**To restore `sentinel/persona.md` after a bad sweep:**
1. Locate the relocated file (e.g. at `learning/persona/persona.md` where the sweep moved it)
2. Read its body: `await vault.read_note("learning/persona/persona.md")`
3. Restore: `await vault.write_note("sentinel/persona.md", body)` — OR use Obsidian REST `PUT /vault/sentinel/persona.md`
4. `write_note` is intentionally NOT guarded; a write-based restore succeeds

**Do NOT** call `vault.relocate("learning/persona/persona.md", "sentinel/persona.md")` — this would hit the destination guard and raise `ProtectedPathError`.

This guidance is also recorded in the `ProtectedPathError` class docstring in `app/errors.py`.

## Cross-Plan Relationship (concern 8)

This plan adds the PRIMITIVE-LEVEL guard (raises `ProtectedPathError`). **Plan 40-04 owns `vault_sweeper.py`** and is responsible for catching `ProtectedPathError` in all destructive sweep branches, recording the refusal, and continuing. The full sweep-continues-after-refusal integration test (a real sweep over `sentinel/persona.md` that continues across all three destructive branches) lives in 40-04, which owns `test_vault_sweeper.py`. This plan's tests prove only that the primitive raises and the file is untouched — which is sufficient because `FakeVault` delegates `relocate`/`move_to_trash` to `ObsidianVault` method bodies.

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for PROTECTED_NAMESPACES, is_protected_path, ProtectedPathError** - `217f387` (test)
2. **Task 1 GREEN: Implement PROTECTED_NAMESPACES, is_protected_path, ProtectedPathError** - `fab378a` (feat)
3. **Task 2 RED: Failing tests for vault guard enforcement** - `d149c60` (test)
4. **Task 2 GREEN: Wire guards into relocate (src+dst) and move_to_trash** - `72a0706` (feat)

## Files Created/Modified

- `sentinel-core/app/errors.py` — Added `ProtectedPathError(SecurityError)` with restore-path docstring
- `sentinel-core/app/config.py` — Added `Settings.protected_namespaces` explicit literal tuple with scope-decision comment
- `sentinel-core/app/vault.py` — Added `PROTECTED_NAMESPACES`, `_active_protected_namespaces()`, `is_protected_path()`, guards in `relocate` and `move_to_trash`
- `sentinel-core/tests/test_obsidian_vault.py` — Added 26 behavioral/spy tests for all guard scenarios

## Decisions Made

- **Protected set = (sentinel/, self/, security/)**: All three are identity-/boot-critical. Evidence recorded in "Protected-Set Scope Decision" section above.
- **Destination protection shipped**: Relocating INTO a protected namespace is also refused (concern 6) to prevent namespace poisoning.
- **write_note intentionally unguarded**: This is the operator's write/copy restore path. Only `relocate` and `move_to_trash` are guarded because only those move files.
- **Guard lives on ObsidianVault, not in sweeper**: Defense-in-depth; any future caller inherits the protection without additional work.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Minor: f-string syntax error in one test assertion (unmatched brackets in f-string) caught by pytest collection. Fixed before RED commit.

## Known Stubs

None — all implemented behavior is fully wired.

## Threat Flags

No new security-relevant surface introduced beyond the plan's threat model. The guards close T-40-17, T-40-18, T-40-26, and T-40-35 as described in the plan's threat register.

## Next Phase Readiness

- 40-04 can now rely on `ProtectedPathError` being raised by the vault primitives; its sweep branches need to catch and continue on `ProtectedPathError`
- 40-06's remediation checkpoint can use `write_note` (not `relocate`) to restore any files that prior sweeps moved out of protected namespaces
- The guard is active for all callers — no additional wiring needed

## Self-Check: PASSED

---
*Phase: 40-semantic-recall*
*Completed: 2026-06-12*
