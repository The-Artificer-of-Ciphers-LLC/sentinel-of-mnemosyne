---
status: passed
phase: 46-6 Rs Pipeline Orchestrator
source: [46-VERIFICATION.md]
started: 2026-07-06T22:04:57Z
updated: 2026-07-07T00:25:25Z
---

## Current Test

[testing complete — 2/2 pass]

## Tests

### 1. Live :ralph/:pipeline run mutates the real Obsidian vault
expected: Seed `inbox/` with a raw capture, run `:ralph` in Discord against the real Obsidian vault with a live LM Studio/exo model. A `notes/{slug}.md` file appears with a claim-style H1 title, at least one wikilink, and a trailing ```_schema block (status: draft); the relevant MOC/hub note is created or updated (appended, not duplicated). Repeating with `:pipeline` drives the full Reduce->Verify->Reflect->Reweave->Rethink sequence end-to-end, respecting the self/ boundary.
result: pass
reason: "Initially failed to file any note (misdiagnosed as cold-start). Real root cause: Reduce→Verify→Reflect ordering + Reflect only linking hub→member meant no note ever got the member [[wikilink]] Verify requires → every note deleted+requeued. Fixed (commit 9b105f4): Reflect now writes a [[hub]] backlink into the member note and runs before Verify, with rollback-on-fail. Re-verified LIVE against the redeployed stack: seeded one clean claim → pipeline reported reduced=1, hubs_touched=1, verify_failed=0, errors=[]; a member note filed in notes/ with an H1 claim title, a [[Spaced Repetition]] wikilink, and a status:draft _schema block (check_note_compliance: zero failures); a hub note was created listing the member; Reweave appended a '## Reweave — <date>' section; self/ (5 entries) untouched throughout. Test artifacts cleaned up afterward."

### 2. Live pollable status reporting
expected: Start a pipeline run (`:pipeline` or `:ralph`), then poll `:pipeline status` / `:ralph status` repeatedly while the background task runs (also verify `GET /vault/pipeline/status` directly). Status transitions idle -> running -> complete (or blocked/error), with entries_processed and the per-phase counts advancing between polls, and a final real outcome is reported (not a silent "done").
result: pass
evidence: "`GET /vault/pipeline/status` returns the full PipelineReport schema; a live `POST /vault/pipeline/start` (mode=pipeline) returned an async `{pipeline_id, status:\"running\", mode}` ack; polling showed transitions idle→running→complete with `entries_processed` advancing (0→2) and per-phase counters populating (`reduced`, `verify_failed`, `verify_requeued`), `errors:[]`. Verified end-to-end."

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

## Findings

- RESOLVED BUG (was reported here as 'cold-start'): the pipeline filed zero notes in prod due to a Verify/Reflect ordering + wikilink-direction defect. Fixed in commit 9b105f4 with a real-compliance integration test added (the mocked verify_note tests had masked it). Verified live 2026-07-07.
- OPEN (low priority, separate): note_schema.has_claim_title vs moc_maintenance._slugify normalization may reject some punctuation-free H1 titles — but real Reduce-generated claim titles pass (verified live). Worth a quick separate check.
- OPEN (confirm): prod vault notes/ was empty (only self/ populated) — confirm the deployed container points at the intended vault.
