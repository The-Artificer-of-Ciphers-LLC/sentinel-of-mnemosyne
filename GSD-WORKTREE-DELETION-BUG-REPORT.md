# Bug Report: Worktree Agents Systematically Delete Prior Work on Merge

**Repository under investigation:** sentinel-of-mnemosyne  
**Date of analysis:** 2026-04-10  
**Severity:** High — data-destructive, repeats across every phase, requires manual recovery after every multi-wave execution

---

## Summary

GSD executor worktrees delete previously-committed files when merging back to the feature branch. This has occurred **8 times across 6 phases** of a single project. Every instance required a manual restore commit. The pattern is consistent enough that it constitutes a systemic bug, not operator error.

---

## Incident Log (git evidence)

All of these are verified restore commits in the project's git history:

| Commit | Phase | What Was Deleted | Cause Noted in Commit Message |
|--------|-------|-----------------|-------------------------------|
| `a98342b` | Phase 1 | `PROJECT.md`, `REQUIREMENTS.md`, `config.json`, `CLAUDE.md`, all research docs, phase context files | "executor agents incorrectly deleted PROJECT.md…" |
| `ee7dcbb` | Phase 4, wave 1 | All Phase 3 planning files, interface files (`discord/`, `imessage/`), all Phase 4 PLANs | "Executor agent started from **main branch state** rather than feature branch HEAD" |
| `3778e6f` | Phase 4 (quick task) | `ARCHITECTURE-Core.md`, `README.md` reverted to pre-Phase-4 content | "gsd-executor worktree **reverted** ARCHITECTURE-Core.md and README.md to pre-Phase-4 content" |
| `60161b6` | Phase 5, task 05-03 | `ROADMAP.md`, `05-02-PLAN.md`, `05-03-PLAN.md` | "restore plan files and ROADMAP.md **deleted by executor worktree**" |
| `af85e26` | Phase 5, task 05-03 (merge) | `injection_filter.py`, `output_scanner.py`, `test_injection_filter.py`, `test_output_scanner.py`, `owasp-llm-checklist.md` | "restore files **deleted by 05-03 worktree merge**" |
| `08b6409` | Phase 6, wave 1 | Discord container `include` re-commented out of `docker-compose.yml` | "restore Discord bot container include … **removed by worktree**" |
| `c6f4753` | Phase 6, wave 2 | 14 Phase 5 files: `injection_filter.py`, `output_scanner.py`, `pentest-agent/*`, `owasp-llm-checklist.md`, `Dockerfile`, `main.py`, `message.py`, all associated tests | "Wave 2 executor incorrectly **ran git-clean** on the worktree" |
| `2b11b3f` | Phase 6, wave 2 | `docker-compose.yml` discord include re-commented again | "discord include **re-commented by Wave 2 agent**" |

**8 incidents. 0 phases without at least one deletion.**

---

## Root Cause Analysis

There are **two distinct failure modes** that produce the same symptom. Both have been observed in this project.

### Failure Mode A: Wrong Branch Base

The worktree is created from `main` (or a stale earlier commit) instead of the current feature branch HEAD.

**Evidence:** Commit `ee7dcbb` explicitly states: *"Executor agent started from main branch state rather than feature branch HEAD, causing it to delete Phase 3 planning files, interface files, and Phase 4 PLANs."*

**Mechanism:**
```
main (base)
  └── feature/phase-N  ← all wave 1 work committed here
        └── worktree created from main  ← WRONG: should be from feature HEAD
              └── wave 2 work committed to worktree branch
                    └── merge back to feature/phase-N
                          └── files added on feature branch AFTER main
                              appear as "deleted" relative to worktree branch
```

When the worktree branch is merged back, git uses the worktree's start point as the merge base. Files that the feature branch added after that point, which the worktree branch never touched, can be incorrectly treated as deleted.

### Failure Mode B: Destructive git Commands Inside Worktree

The executor agent runs `git clean` (or equivalent) inside the worktree directory, which removes files the worktree agent considers "untracked." When the worktree branch is subsequently merged, those absent files appear as deletions.

**Evidence:** Commit `c6f4753` states: *"Wave 2 executor incorrectly ran git-clean on the worktree, removing injection_filter.py, output_scanner.py, pentest-agent/* and associated tests."*

**Mechanism:**
- Worktree is created correctly from feature branch HEAD
- `injection_filter.py` etc. are committed and present in the worktree filesystem
- Agent runs `git clean -fd` (or `-fdx`) to "start fresh"
- Tracked-but-unwanted files are removed from the filesystem
- Agent stages and commits only its own deliverables
- Merge includes the deletion of all `git clean`-removed files

### Failure Mode C: Agent Reverts Files It Didn't Intend to Touch

A subtler variant. The agent reads a file, modifies it for its own task, but its view of the file is from the worktree base (not current feature branch HEAD), so it overwrites with stale content.

**Evidence:** Commit `3778e6f`: *"gsd-executor worktree reverted ARCHITECTURE-Core.md and README.md to pre-Phase-4 content."* Commit `2b11b3f`: discord include re-commented on the second occurrence despite wave 1 having already fixed it.

---

## Reproduction Pattern

Any multi-wave phase execution where:
1. Wave N commits files to the feature branch
2. GSD creates a worktree for Wave N+1

...will reproduce one or more of these failure modes. Based on this project's history, the probability is effectively 100% — it has happened every single phase.

---

## Impact

- **Direct:** Committed, working code (services, tests, security configurations, documentation) is silently deleted and must be manually restored.
- **Indirect:** The restore commits themselves are large and messy, making `git log` and `git blame` harder to use. Work that should have been a clean history of additive commits instead shows deletion/restore cycles.
- **Time cost:** Each incident requires the user to identify what was deleted, find the correct restore point, and hand-write a restore commit. In this project that happened 8 times in one day of work.
- **Risk:** If a deletion goes unnoticed (which is plausible given the volume of output), production behavior changes silently. In this project, security filters (`injection_filter.py`, `output_scanner.py`) were deleted — if that had gone unnoticed, the security layer would have been absent at deploy time.

---

## What Is Not the Problem

- The individual executor agents produce correct code for their assigned tasks. The deliverables from each wave are generally correct.
- The merge strategy itself is not wrong — git merge is doing the right thing given the inputs. The inputs (worktree base, staged deletions) are wrong.
- This is not a conflict-resolution issue. There are no merge conflicts. The deletions land clean.

---

## Proposed Fixes

### Fix 1 (Failure Mode A): Always create worktrees from feature branch HEAD

When `gsd-executor` creates a worktree for a wave/task, the worktree must be created from the **current HEAD of the feature branch**, not from `main` and not from the branch's first commit. Concretely:

```bash
# Wrong
git worktree add /tmp/worktree-xyz main

# Right
git worktree add /tmp/worktree-xyz HEAD
# or
git worktree add /tmp/worktree-xyz $(git rev-parse HEAD)
```

The executor must resolve `HEAD` at the moment of worktree creation, on the correct feature branch.

### Fix 2 (Failure Mode B): Prohibit destructive git commands inside worktrees

The executor agent must not run `git clean`, `git rm`, `git reset --hard`, or `git checkout -- .` inside a worktree. These commands have no legitimate use in a scoped executor agent and are the proximate cause of deletion in multiple incidents.

This can be enforced at the tool level (block these commands via a hook when `GSD_WORKTREE=1` is set in the environment) or via explicit instructions in the executor's system prompt.

### Fix 3 (Failure Mode C): Verify file content against feature branch before modifying shared files

When a worktree agent modifies a file that existed before the worktree was created (e.g., `docker-compose.yml`, `ARCHITECTURE-Core.md`), it should diff against the feature branch HEAD — not its worktree base — to avoid regressing changes made by prior waves. Or more simply: the orchestrator should cherry-pick or rebase rather than merge when integrating worktree output.

### Fix 4 (All modes): Post-merge verification step

After every worktree merge, GSD should run an automated check: `git diff feature-branch-pre-merge..HEAD --name-only | grep "^D"` and surface any unexpected deletions to the user before the merge commit is finalized. This is a safety net, not a root fix.

---

## Suggested Issue Title

`gsd-executor worktree merge systematically deletes prior-wave committed files`

## Labels

`bug`, `worktree`, `data-loss`, `executor`, `high-severity`
