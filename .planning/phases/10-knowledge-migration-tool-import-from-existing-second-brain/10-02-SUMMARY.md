---
phase: 10-knowledge-migration-tool-import-from-existing-second-brain
plan: "02"
subsystem: obsidian-vault
tags: [vault-migration, path-update, 2nd-brain, mnemosyne]
dependency_graph:
  requires: []
  provides: [mnemosyne-vault-scaffold, 2nd-brain-paths-in-code]
  affects: [sentinel-core/app/clients/obsidian.py, sentinel-core/app/routes/message.py, mnemosyne/]
tech_stack:
  added: []
  patterns: [single-user-vault-identity, ops-sessions-path, arscontexta-three-space-model]
key_files:
  created:
    - mnemosyne/self/identity.md
    - mnemosyne/self/methodology.md
    - mnemosyne/self/goals.md
    - mnemosyne/self/relationships.md
    - mnemosyne/self/memory/.gitkeep
    - mnemosyne/notes/index.md
    - mnemosyne/templates/permanent-note.md
    - mnemosyne/ops/reminders.md
    - mnemosyne/ops/discord-threads.md
    - mnemosyne/ops/sessions/.gitkeep
    - mnemosyne/ops/health/.gitkeep
    - mnemosyne/ops/observations/.gitkeep
    - mnemosyne/ops/tensions/.gitkeep
    - mnemosyne/ops/methodology/.gitkeep
    - mnemosyne/ops/queue/.gitkeep
    - mnemosyne/ops/archive/.gitkeep
  modified:
    - sentinel-core/app/clients/obsidian.py
    - sentinel-core/app/routes/message.py
    - sentinel-core/tests/test_obsidian_client.py
decisions:
  - "mnemosyne/ is gitignored as personal vault data; scaffold files force-added (-f) per plan to establish initial structure in repo"
  - "get_user_context() user_id param retained for interface compatibility; path hardcoded to self/identity.md (D-01 single-user)"
metrics:
  duration: ~5 min
  completed: 2026-04-11T12:12:58Z
  tasks_completed: 2
  files_created: 16
  files_modified: 3
---

# Phase 10 Plan 02: Vault Path Migration and 2nd Brain Scaffold Summary

Replaced all legacy `core/` vault path references in Python code with 2nd brain paths, and created the complete mnemosyne/ directory structure with stub files — unlocking Wave 2 (context injection upgrade + Discord commands).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Migrate core/ paths to 2nd brain paths | 11b4322 | obsidian.py, message.py, test_obsidian_client.py |
| 2 | Create 2nd brain vault directory structure | 18ac012 | 16 vault files created |

## What Was Built

**Task 1 — Path migration (obsidian.py, message.py):**
- `get_user_context()`: reads `self/identity.md` instead of `core/users/{user_id}.md`. user_id param kept for interface compatibility. D-01: single-user system.
- `get_recent_sessions()`: reads `ops/sessions/{date}/` instead of `core/sessions/{date}/`. Both the directory listing URL and the candidates tuple path updated.
- `_write_session_summary()`: writes to `ops/sessions/{date_str}/{user_id}-{time_str}.md`. Path comment updated to match.
- `test_obsidian_client.py`: mock fixtures updated to match new paths (`/vault/self/identity.md`, `/vault/ops/sessions/`).

**Task 2 — Vault scaffold:**
- `self/` space: 4 stub .md files (identity, methodology, goals, relationships) with YAML frontmatter (type: self). Plus memory/ subdirectory per D-01 vault spec.
- `notes/` space: index.md hub note (type: hub, status: draft).
- `templates/`: permanent-note.md with all 6 YAML fields (description empty, type: permanent, created: {{date}}, topics, relevant_notes, status: draft).
- `ops/` space: reminders.md and discord-threads.md (D-04 startup read target). 7 .gitkeep files for empty subdirectories (sessions, health, observations, tensions, methodology, queue, archive).
- D-16 PARA synthesis honored: no ops/projects/ or ops/areas/ subfolders.

## Verification

```
PASS: grep "core/users|core/sessions" obsidian.py message.py → 0 matches
PASS: grep "self/identity.md" obsidian.py → 2 matches (docstring + code)
PASS: grep "ops/sessions" obsidian.py → 3 matches
PASS: grep "ops/sessions" message.py → 2 matches (docstring + code)
PASS: find mnemosyne/self -name "*.md" → 4 files
PASS: type: permanent in templates/permanent-note.md
PASS: type: hub in notes/index.md
PASS: Discord Thread IDs in ops/discord-threads.md
PASS: find mnemosyne/ops -name ".gitkeep" → 7 files
PASS: 10/10 test_obsidian_client.py tests pass
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_obsidian_client.py mocks to match new vault paths**
- **Found during:** Task 1 verification
- **Issue:** Test fixtures mocked `core/users/` and `core/sessions/` paths; after path migration these tests returned None/empty causing 9/10 failures
- **Fix:** Updated `obsidian_user_context_mock` to match `/vault/self/identity.md`, `obsidian_directory_listing_mock` to match `/vault/ops/sessions/`, and `test_write_session_summary_calls_put` to use `ops/sessions/` path
- **Files modified:** `sentinel-core/tests/test_obsidian_client.py`
- **Commit:** 11b4322

**2. [Rule 3 - Blocking] Force-added mnemosyne/ vault files despite .gitignore**
- **Found during:** Task 2 commit
- **Issue:** `.gitignore` excludes `mnemosyne/` as personal vault data. Plan explicitly lists these files as `files_modified` and requires them tracked in the repo as initial scaffold.
- **Fix:** Used `git add -f` to force-add the scaffold structure. Documented in commit message. Live vault data (session files, personal notes added later) will remain excluded by the gitignore rule as intended.
- **Files modified:** mnemosyne/ (all 16 scaffold files)
- **Commit:** 18ac012

## Known Stubs

The vault stub files are intentional stubs by design — they are scaffold placeholders for the user to populate:

| File | Stub Nature | Resolution |
|------|-------------|------------|
| mnemosyne/self/identity.md | Empty identity — user fills in | User populates directly in Obsidian |
| mnemosyne/self/goals.md | Empty goals — user fills in | User populates directly in Obsidian |
| mnemosyne/self/relationships.md | Empty relationships — user fills in | User populates directly in Obsidian |
| mnemosyne/templates/permanent-note.md | Template with {{date}} placeholder | Obsidian templater plugin resolves on use |

These stubs do not prevent the plan's goal from being achieved — the code paths are wired and the vault structure exists. The Sentinel will gracefully skip context injection when identity.md is empty (returns the stub content as context, which is harmless).

## Threat Surface

No new threat surface beyond what the plan's threat model covers. T-10-02-01 (relationships.md personal data) is already guarded by `injection_filter.wrap_context()` in message.py. T-10-02-02 (path now hardcoded, removes user_id injection surface) reduces attack surface.

## Self-Check: PASSED

Files verified:
- sentinel-core/app/clients/obsidian.py — contains `self/identity.md` and `ops/sessions`
- sentinel-core/app/routes/message.py — contains `ops/sessions`
- mnemosyne/self/identity.md — exists
- mnemosyne/templates/permanent-note.md — exists, contains `type: permanent`
- mnemosyne/ops/discord-threads.md — exists, contains `Discord Thread IDs`
- mnemosyne/ops/sessions/.gitkeep — exists
- mnemosyne/self/memory/.gitkeep — exists

Commits verified:
- 11b4322 — feat(10-02): migrate core/ vault paths to 2nd brain paths
- 18ac012 — feat(10-02): create 2nd brain vault directory structure
