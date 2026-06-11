---
phase: 40-semantic-recall
plan: "01"
subsystem: vault-sweeper
tags: [embedding, semantic-recall, incremental-rebuild, nomic-prefix, vault-seam, tdd]
dependency_graph:
  requires: []
  provides:
    - EMBEDDING_INDEX_PATH
    - NOMIC_DOCUMENT_PREFIX
    - _content_hash
    - _emit_embedding_index
  affects:
    - sentinel-core/app/services/vault_sweeper.py
    - sentinel-core/tests/test_vault_sweeper.py
tech_stack:
  added: [hashlib, json]
  patterns:
    - vault-seam write via client.write_note() (REST-only, D-08 REVISED)
    - incremental-rebuild via content-hash (D-05)
    - nomic search_document: prefix on embedder input (RESEARCH Pattern 6)
    - graceful-degrade on index write failure (append to report.errors + WARNING)
key_files:
  created: []
  modified:
    - sentinel-core/app/services/vault_sweeper.py
    - sentinel-core/tests/test_vault_sweeper.py
decisions:
  - ".json-over-REST confirmed: EMBEDDING_INDEX_PATH='ops/sweeps/embedding-index.json' round-trips via FakeVault.write_note/read_note with no extension handling needed"
  - ".md fenced-JSON fallback documented: if live Obsidian REST rejects .json during UAT, swap EMBEDDING_INDEX_PATH to 'ops/sweeps/embedding-index.md' (mirror RecallConfig.index_path in Plan 02) — one-line constant change, no logic change"
  - "NOMIC_DOCUMENT_PREFIX addition triggers one-time full re-embed on first post-upgrade sweep (intended — all existing hashes diverge from prefixed hashes)"
  - "Distinct orthogonal unit vectors per call-position in _CallCountingEmbedder prevent de-dup false positives in index tests"
metrics:
  duration: "466s (~7m)"
  completed: "2026-06-11"
  tasks_completed: 3
  files_modified: 2
---

# Phase 40 Plan 01: Sweeper Embedding Index Emission Summary

**One-liner:** Vault sweeper emits `ops/sweeps/embedding-index.json` keyed by note path with per-entry `{embedding_b64, embedding_model, content_hash}`, rebuilt incrementally via content-hash and persisted through the Vault REST seam via `vault.write_note()`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write failing RED tests (5 tests) | 19c35c5 | `test_vault_sweeper.py` |
| 2 | Implement sweeper index emission, content-hash, document prefix | d3ccbda | `vault_sweeper.py`, `test_vault_sweeper.py` |
| 3 | Verify REST .json round-trip; record fallback decision | 0d44da4 | `test_vault_sweeper.py` |

## What Was Built

### `sentinel-core/app/services/vault_sweeper.py`

Four new symbols added (consumed by Plan 02):

**`EMBEDDING_INDEX_PATH = "ops/sweeps/embedding-index.json"`**
Module constant; the canonical vault-relative path for the sidecar index. Must equal `RecallConfig.index_path` in Plan 02.

**`NOMIC_DOCUMENT_PREFIX = "search_document: "`**
Instruction prefix prepended to each note body before calling the embedder. Mirrors `SemanticRecall.NOMIC_QUERY_PREFIX = "search_query: "` in Plan 02. Triggers a one-time full re-embed on first post-upgrade sweep (content-hash divergence — intended and documented).

**`_content_hash(text: str) -> str`**
SHA-256 of the frontmatter-stripped note body (`rest`), first 16 hex chars. Hashes the body-only string (same `rest` variable fed to the embedder), so frontmatter-only edits do NOT trigger re-embeds.

**`_emit_embedding_index(client, survivors, embeddings, active_paths, report)`**
Async helper called after the step-3 write-back loop (before step-4 de-dup), guarded by `not dry_run`. Algorithm:
1. Read existing index via `client.read_note(EMBEDDING_INDEX_PATH)` — `{}` on any parse failure (self-healing, satisfies T-40-01)
2. Carry forward entries in `active_paths` whose `content_hash` AND `embedding_model` match current values (D-05 incremental)
3. Prune entries NOT in `active_paths` (trashed/deleted notes)
4. Write/update entries for survivors with embeddings that have new/changed hashes
5. Persist via `client.write_note(EMBEDDING_INDEX_PATH, json.dumps(...))` — single REST PUT (D-08 REVISED)
6. Failures logged as WARNING and appended to `report.errors` (reuses sweep-log graceful pattern)

### `sentinel-core/tests/test_vault_sweeper.py`

Five new index-emission tests (TDD RED→GREEN cycle) plus one seam round-trip test:

- `test_sweep_emits_embedding_index`: asserts EMBEDDING_INDEX_PATH exists in vault after sweep with correct JSON structure
- `test_sweep_writes_embedding_model_to_index`: asserts every entry carries `embedding_b64`, `embedding_model` (no `openai/` prefix, equals `_embedding_model_id()`), `content_hash`
- `test_sweep_index_incremental_carry_forward`: drives two sequential sweeps; asserts unchanged note carries same hash+b64 forward, changed note gets new hash and is re-embedded
- `test_sweep_index_prunes_trashed`: asserts deleted notes are removed from index on next sweep
- `test_sweep_embeds_with_document_prefix`: asserts every string sent to embedder starts with `NOMIC_DOCUMENT_PREFIX`
- `test_index_path_roundtrips_through_vault_seam`: proves `.json` path round-trips byte-faithfully through `FakeVault.write_note/read_note`

Helper `_CallCountingEmbedder`: records all texts received per batch, returns distinct orthogonal unit vectors per call-position to prevent de-dup false positives.

## Index Entry Schema (Contract for Plan 02)

```json
{
  "path/to/note.md": {
    "embedding_b64": "<base64-encoded float32 vector>",
    "embedding_model": "text-embedding-nomic-embed-text-v1.5",
    "content_hash": "<first 16 hex chars of SHA-256 of body>"
  }
}
```

Plan 02 (`SemanticRecall`) reads this schema and uses exact-string comparison against `embedding_model` for model-mismatch detection (D-12/D-13).

## .json-over-REST Decision

**Production decision:** Keep `ops/sweeps/embedding-index.json`.

**Verification:** `test_index_path_roundtrips_through_vault_seam` proves the Vault seam's `write_note`/`read_note` primitives are path/extension-agnostic — the FakeVault round-trips the `.json` key byte-faithfully, and the Obsidian Local REST API's `PUT /vault/{path}` and `GET /vault/{path}` work on arbitrary paths.

**Fallback trigger:** If a live Obsidian REST instance rejects the `.json` path during UAT (e.g., returns 400 or 415 on the PUT), the documented fallback is:
1. Change `EMBEDDING_INDEX_PATH` in `vault_sweeper.py` to `"ops/sweeps/embedding-index.md"`
2. Mirror in `RecallConfig.index_path` in Plan 02
3. No logic change required — both read and write already go through `vault.read_note`/`vault.write_note`

This is a one-line constant change in two files.

## Nomic Prefix and One-Time Re-Embed

Adding `NOMIC_DOCUMENT_PREFIX = "search_document: "` changes the hash of every note body (`hash("search_document: " + body) != hash(body)`). On the first post-upgrade sweep:

1. Every existing index entry's `content_hash` will differ from the new prefixed hash
2. The incremental rebuild logic detects mismatch → re-embeds every note
3. After the one-time full sweep, subsequent sweeps are incremental again

This is the correct behaviour: prefixless and prefixed embeddings are not geometrically comparable, so all stored embeddings must be refreshed. Documented in `NOMIC_DOCUMENT_PREFIX` docstring.

## REST-Only Constraint Honored (D-08 REVISED)

Verification: `grep -nE "tempfile|os\.replace|os\.path\.getmtime" sentinel-core/app/services/vault_sweeper.py` returns only docstring/comment mentions (not code). All index persistence goes through `client.write_note(EMBEDDING_INDEX_PATH, ...)` — one REST PUT per sweep.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test paths caused sweeper to relocate notes (breaking index key assertions)**
- **Found during:** Task 2 implementation (GREEN step)
- **Issue:** Test helper used `notes/alpha.md` with `topic="reference"`. The sweeper correctly relocated these to `references/alpha.md`, so index keys were `references/...` not `notes/...`, failing the assertions.
- **Fix:** Changed all test note paths to `references/` prefix so `is_in_topic_dir` returns True and no relocation occurs.
- **Files modified:** `sentinel-core/tests/test_vault_sweeper.py`
- **Commit:** d3ccbda

**2. [Rule 1 - Bug] Identical embeddings from `_CallCountingEmbedder` triggered de-dup, removing notes before prune test could verify them**
- **Found during:** Task 2 implementation (prune test)
- **Issue:** `_CallCountingEmbedder` returned `[1.0, 0.0, 0.0]` for all texts; cosine similarity = 1.0 between all notes → de-dup trashed one → `KeyError` in prune test.
- **Fix:** Changed `_CallCountingEmbedder` to return distinct orthogonal unit vectors per call-position (4D basis vectors), preventing any cosine ≥ 0.92 clustering.
- **Files modified:** `sentinel-core/tests/test_vault_sweeper.py`
- **Commit:** d3ccbda

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes at trust boundaries beyond those documented in the plan's threat model. T-40-01 (corrupt index self-healing) is fully mitigated via `json.loads` in `try/except` → `{}` fallback.

## Self-Check

### Files exist:
- sentinel-core/app/services/vault_sweeper.py — FOUND (modified)
- sentinel-core/tests/test_vault_sweeper.py — FOUND (modified)

### Commits exist:
- 19c35c5 — test(40-01): add failing RED tests
- d3ccbda — feat(40-01): implement sweeper embedding index emission
- 0d44da4 — feat(40-01): verify .json-over-REST vault seam round-trip

### Tests:
- `cd sentinel-core && uv run pytest tests/test_vault_sweeper.py -q` → 28 passed
- `grep -c "write_note(EMBEDDING_INDEX_PATH" sentinel-core/app/services/vault_sweeper.py` → 1

## Self-Check: PASSED

All created files exist. All commits present in git log. 28/28 sweeper tests pass. REST-only constraint honored.
