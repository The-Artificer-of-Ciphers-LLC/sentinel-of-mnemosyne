# Phase 26: Nyquist Validation Cleanup — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-21
**Phase:** 26-nyquist-validation-cleanup
**Areas discussed:** Test stubs (item 5), Repair scope for 07/10, VALIDATION.md depth for 04/06

---

## Test Stubs (Item 5)

| Option | Description | Selected |
|--------|-------------|----------|
| Verify + update paths | Confirm existing files pass, update Phase 10 VALIDATION.md paths only | |
| Verify + expand with samples | Confirm files pass, expand with sample Discord commands | ✓ |
| Start fresh at correct path | Create new files ignoring Phase 25's work | |

**User's choice:** Verify + expand with samples

---

| Option | Description | Selected |
|--------|-------------|----------|
| Key subcommands + mock cleanup | Mock Obsidian, teardown deletes mocked paths | |
| Routing only, no cleanup needed | Pure unit routing test, no I/O | |
| Integration tests with real cleanup | Live Obsidian calls + automated teardown | ✓ |

**User's choice:** Integration tests with real cleanup — live Obsidian REST API, real commands, real test writes

---

| Option | Description | Selected |
|--------|-------------|----------|
| pytest fixture with teardown | autouse fixture, DELETE /vault/{path} per test | ✓ |
| Isolated test vault path | Delete entire test-run/ dir at end of suite | |
| Manual cleanup | Developer runs cleanup script | |

**User's choice:** pytest fixture with teardown (autouse, DELETE /vault/{path})

---

## Repair Scope for 07/10

| Option | Description | Selected |
|--------|-------------|----------|
| Full repair: add missing sections | Phase 07: add Per-Task Verification Map. Phase 10: fix stale paths. Both get nyquist_compliant: true. | ✓ |
| Minimal: metadata only | Flip frontmatter only, no new content | |

**User's choice:** Full repair — add missing sections to both

---

| Option | Description | Selected |
|--------|-------------|----------|
| Current test coverage | Map tests that exist today | |
| Reconstruct original plan | Archaeology from PLAN.md + SUMMARY.md | ✓ |

**User's choice:** Reconstruct original plan — historical accuracy, not just current coverage

---

## VALIDATION.md Depth for 04/06

| Option | Description | Selected |
|--------|-------------|----------|
| Current test suite | Map tests that exist today | |
| Reconstruct from plans/summaries | Read PLAN.md + SUMMARY.md for each phase | ✓ |

**User's choice:** Reconstruct from plans/summaries — consistent approach with 07/10

---

## Scope Triage (Additional Ideas)

The user raised three additional ideas during area selection:

1. **Automated Discord command tests with sample commands + cleanup the database** — Captured in Test Stubs decisions above (integration tests, pytest teardown).

2. **Validate proper LLM is installed and available in tools** — Out of scope for Phase 26. User confirmed it must be in v0.40 release → proposed as **Phase 28: LLM Health & Startup Validation**.

3. **Validate right LLM for best chat performance on given hardware platform** → Same Phase 28.

## Claude's Discretion

- Nyquist matrix table structure: follow 25-VALIDATION.md as authoritative template
- Test write prefix: `ops/test-run-{uuid}/` for single-teardown cleanup
- pytest marker: `@pytest.mark.integration` to support Obsidian-absent CI runs

## Deferred Ideas

- **LLM availability check at startup** → Phase 28
- **LLM performance/hardware baseline** → Phase 28
