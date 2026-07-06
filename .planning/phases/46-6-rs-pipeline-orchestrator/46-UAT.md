---
status: testing
phase: 46-6 Rs Pipeline Orchestrator
source: [46-VERIFICATION.md]
started: 2026-07-06T22:04:57Z
updated: 2026-07-06T22:04:57Z
---

## Current Test

number: 1
name: Live :ralph/:pipeline run mutates the real Obsidian vault
expected: |
  Seed `inbox/` with a raw capture, then run `:ralph` (and separately `:pipeline`) in Discord
  against the real Obsidian vault with a live LM Studio/exo model. A `notes/{slug}.md` file
  appears with a claim-style H1 title, at least one wikilink, and a trailing ```_schema block
  (status: draft); the relevant MOC/hub note is created or updated (appended, not duplicated).
  For `:pipeline`, the full Reduce -> Verify -> Reflect -> Reweave sequence runs and an
  end-of-run Rethink triage occurs; the self/ boundary is respected throughout (no links into
  or writes against self/ content).
awaiting: user response

## Tests

### 1. Live :ralph/:pipeline run mutates the real Obsidian vault
expected: Seed `inbox/` with a raw capture, run `:ralph` in Discord against the real Obsidian vault with a live LM Studio/exo model. A `notes/{slug}.md` file appears with a claim-style H1 title, at least one wikilink, and a trailing ```_schema block (status: draft); the relevant MOC/hub note is created or updated (appended, not duplicated). Repeating with `:pipeline` drives the full Reduce->Verify->Reflect->Reweave->Rethink sequence end-to-end, respecting the self/ boundary.
result: [pending]

### 2. Live pollable status reporting
expected: Start a pipeline run (`:pipeline` or `:ralph`), then poll `:pipeline status` / `:ralph status` repeatedly while the background task runs (also verify `GET /vault/pipeline/status` directly). Status transitions idle -> running -> complete (or blocked/error), with entries_processed and the per-phase counts advancing between polls, and a final real outcome is reported (not a silent "done").
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
