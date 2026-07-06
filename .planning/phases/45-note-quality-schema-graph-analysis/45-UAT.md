---
status: testing
phase: 45-note-quality-schema-graph-analysis
source: [45-VERIFICATION.md]
started: 2026-07-06T17:59:04Z
updated: 2026-07-06T17:59:04Z
---

## Current Test

number: 1
name: _schema block rendering and wikilink resolution in live Obsidian
expected: |
  The `_schema` block renders as a gray fenced code block (not raw markdown text);
  wikilinks in the note and in the hub's member list resolve/navigate correctly.
awaiting: user response

## Tests

### 1. _schema block rendering and wikilink resolution in live Obsidian
steps: After deploy, open a `notes/` note carrying a trailing `_schema` block and a
  materialized hub note in the live Obsidian desktop app's Reading View.
expected: The `_schema` block renders as a gray fenced code block (not raw markdown text);
  wikilinks in the note and in the hub's member list resolve/navigate correctly.
why_manual: Requires a real Obsidian instance + REST plugin; not reproducible in the automated suite.
requirements: NOTE-01, NOTE-02
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
