---
phase: 40-semantic-recall
plan: "06"
subsystem: vault / ops-tooling / deployment
tags: [blast-radius, audit, human-verify, protected-namespace, persona-restore, redeploy, uat]

dependency_graph:
  requires:
    - phase: 40-04
      provides: rebuild_embedding_index + fail-closed safe-to-mutate probe (verified live)
    - phase: 40-05
      provides: is_protected_path guard in relocate/move_to_trash (verified live under a real sweep)
    - phase: 40-07
      provides: single-source index path + extension-aware encode/decode + stale-skip (verified live)
provides:
  - operator-run two-mode read-only blast-radius audit (provenance + inventory) — CLEAN on live vault
  - authoritative known-good inventory manifest for the audit
  - empirical confirmation that the redeployed image's 40-05 guard blocks the original incident move
affects: [deployment, vault-sweeper, recall, sweep-remediation]

tech-stack:
  added: []
  patterns:
    - read-only forensic audit gated behind LIVE_TEST=1 (no-op without it; exit 2 ≠ clean)
    - protected-file restore via REST PUT (write/copy), never relocate (40-05 destination guard blocks moves into protected namespaces)

key-files:
  created:
    - .planning/phases/40-semantic-recall/40-06-known-good-inventory.json
  modified: []   # scripts/uat_phase40_blast_radius.py was committed in 20c1c51 (Task 1)

key-decisions:
  - "Persona restore = strip ALL sweep-injected frontmatter (provenance + 4KB embedding_b64), keep body verbatim — loader injects persona file verbatim as system prompt with no frontmatter stripping, so the garbage was live in the running prompt"
  - "Running image must be REBUILT (docker compose up -d --build), not restarted — source is baked into the image, and the running container predated the entire 40-04/05/07 gap-closure wave by ~5 hours"
  - "Live sweep is the authoritative index builder + the real guard test; dry-run first to preview intent, then live with guard backstop"

requirements-completed: [MEM-05, blast-radius-audit, persona-restore-verify, protected-namespace-guard-live]

duration: ~1 session (operator-driven checkpoint)
completed: "2026-06-12"
---

# Phase 40 Plan 06: Operator Blast-Radius Audit + Human-Verify Checkpoint Summary

**Two-mode read-only blast-radius audit script (Task 1, committed earlier) plus the live human-verify checkpoint (Task 2), executed against the production stack on 2026-06-12.**

## Performance

- **Task 1 (auto):** audit script `scripts/uat_phase40_blast_radius.py` — committed `20c1c51` (890 lines)
- **Task 2 (checkpoint:human-verify):** executed live this session against the real Obsidian vault + LM Studio + redeployed core
- **Completed:** 2026-06-12

## Accomplishments

1. **Blast-radius audit run CLEAN (authoritative).** Initial run surfaced **1 CRITICAL**: `sentinel/persona.md` was at its correct path but still carried the incident's relocation provenance frontmatter (`original_path`, `topic_moved_at: 2026-06-11T20:31:03Z`) plus the sweep's classification fields and a ~4 KB `embedding_b64` blob. Remediated, re-run CLEAN (exit 0) with an authoritative `--inventory` manifest (no drift-prone fallback).

2. **Persona restored to clean state.** Because the persona loader injects the file **verbatim** as the system prompt (no frontmatter stripping — `composition.py`/`vault.read_persona` return raw text), the ~4 KB of sweep frontmatter was live in the running system prompt. Restored via REST `PUT /vault/sentinel/persona.md` to body-only (5191 → 816 bytes). Confirmed clean after boot, after the live sweep, and after a live message.

3. **Discovered and corrected a stale deployment (the session's headline finding).** The running `sentinel-core` image was built `2026-06-11T20:40:47Z` — ~5 hours **before** the entire gap-closure wave (40-04 `01:04–01:25Z`, 40-05 `01:27–01:32Z`, 40-07 `01:37–01:43Z`). Source is baked into the image, so the "5-hour-healthy" container had been running **pre-fix code with the 40-05 protected-namespace guard INACTIVE the whole time.** A `docker compose restart` (done first) only reused the stale image. Rebuilt + redeployed via `docker compose up -d --build sentinel-core` → new image `2026-06-12T02:29:09Z` with 40-04/05/07 baked in.

4. **Cold-start regression PASSED on the correct image.** Clean boot, `Persona loaded from vault (812 chars)`, `Application startup complete`, no `RuntimeError`. The 40-04 startup rewire is now live: `Startup embedding-index rebuild complete` logs (absent on the old image), the **stale phantom `learning/persona.md` index entry was dropped**, and persona survived boot uncorrupted (read-only rebuild).

5. **40-05 guard verified LIVE under a real sweep (UAT Test 2).** Dry-run confirmed the classifier **still** wants to move `sentinel/persona.md → learning/persona.md` (topic=learning, conf 0.90) — the exact incident move. The live sweep attempted it; the guard blocked it. Post-sweep: persona still at `sentinel/persona.md` (816 bytes, clean), `learning/persona.md` → **404**, all 5 `self/` files present. Backed by **77 sweeper/vault guard tests** passing (incl. `test_run_sweep_protected_path_error_continues_and_processes_others`).

6. **UAT Test 3 (index round-trip) PASSED.** Byte-identical PUT→GET of a known JSON body (incl. unicode) at the active `.json` index path via the Obsidian REST API; the live sweep's own `embedding-index.json` write also round-trips and parses cleanly. **53 recall tests** pass, incl. `test_recall_json_extension_round_trip` / `_md_extension_round_trip`.

7. **Paraphrase recall verified LIVE through the real recall code (UAT Test 2).** Ran `Recall._warm_search` and `SemanticRecall.search` inside the deployed container against the live index with the paraphrase query *"who acts as my external memory and recalls my history so chats are not starting from scratch"* — which shares **no keywords** with the persona text. Result: `sentinel/persona.md` surfaced via `SemanticRecall.search` at **cosine 0.6869** (floor 0.50) and entered the warm tier via `Recall._warm_search` (rrf_score 0.016393, real body). A BM25/keyword search shares zero terms, so the hit is purely semantic — MEM-03/MEM-04 confirmed live, read-only, zero vault mutation. Also backed by 53 recall tests (incl. `test_semantic_paraphrase_returns_correct_note`, `test_end_to_end_paraphrase_recall`, `test_semantic_stale_entry_skipped_non_stale_returned`) and a live `POST /message` smoke test that returned a clean, in-character persona reply (`google/gemma-4-e4b`).

## Resume-Signal Data (per 40-06-PLAN checkpoint)

- **Audit exit code:** 0 (CLEAN) after persona remediation; ran with **`--inventory` (authoritative)**, not the drift-prone fallback.
- **Findings/restored:** 1 CRITICAL — `sentinel/persona.md` stale relocation provenance + 4 KB embedding frontmatter. Restored via REST PUT to body-only. 2 INFO (`Welcome.md → _trash`, expected).
- **Index round-trip path in effect:** `ops/sweeps/embedding-index.json` (`.json`, matches 40-07's `EMBEDDING_INDEX_PATH`). Round-trip preserved.
- **Paraphrase recall:** verified LIVE — a zero-keyword-overlap paraphrase query surfaced `sentinel/persona.md` at cosine 0.6869 via `SemanticRecall.search` and into the warm tier via `Recall._warm_search`, proving semantic (not keyword) recall on the deployed image. (Observation: persona.md is currently the only embeddable note — `mnemosyne/` is excluded `pf2e/` data, `self/` excluded from warm recall — and it is BOTH in the embedding index AND warm-recall-eligible, so it can be injected both as the system prompt and as warm context. Flagged as a recall-config namespace question, not a 40-06 blocker.)
- **Persona survival:** confirmed after boot AND after a real sweep (40-05 guard held).

## Decisions Made

- **Restore strips ALL sweep frontmatter, not just provenance keys** — the embedding/classification fields don't belong on a protected system-prompt file and were polluting the live prompt.
- **Rebuild over restart** — required to ship the gap-closure fixes; restart alone reuses the baked-in stale image.

## Deviations from Plan

- The checkpoint assumed Step 1 ("redeploy the Phase-40 image with the fixes") had been done. It had **not** — the live image predated all fixes. The redeploy was performed as part of this checkpoint. This is the most important operational finding: prior verification against the running container would have been verifying pre-fix code.

## Issues Encountered

- Initial `docker compose restart` reused the stale image (no rebuild) — corrected with `--build`.
- Sweeper does not verbosely log the guard firing; blockage confirmed empirically (persona unmoved, `learning/persona.md` 404) + by the passing `protected_path_error_continues` test.

## Known Stubs

None.

## Threat Flags

- The live system ran **without the 40-05 protected-namespace guard for ~5 hours** post-incident (stale image). Now closed by the redeploy. Recommend a deploy-freshness check (image build time vs HEAD) before trusting future "healthy" status, and confirming the `sentinel-ofelia` cron does not trigger sweeps against an unguarded image.

## Next Phase Readiness

- Phase 40 fully complete and **verified live** (not just unit-tested). Phase 41 (Typed SessionSummary + Retention) can build on a confirmed-safe sweep + working semantic recall index path.

## Self-Check: PASSED

---
*Phase: 40-semantic-recall*
*Completed: 2026-06-12*
