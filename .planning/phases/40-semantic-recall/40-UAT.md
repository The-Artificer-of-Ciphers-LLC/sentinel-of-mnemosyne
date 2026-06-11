---
status: partial
phase: 40-semantic-recall
source: [40-01-SUMMARY.md, 40-02-SUMMARY.md, 40-03-SUMMARY.md, 40-VERIFICATION.md]
started: 2026-06-11T00:00:00Z
updated: 2026-06-11T20:50:00Z
---

## Current Test

[testing complete — halted by blocker incident on Test 2]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running sentinel-core service, then start the app from scratch. Server boots without errors; the non-blocking startup index rebuild fires (background sweep writes ops/sweeps/embedding-index.json); a basic message / GET /context/{user_id} request returns live data without errors. Startup is NOT blocked waiting on the sweep.
result: pass
note: Recreated live core from the freshly-built Phase 40 image (running_image 7e38e5f8). Boot clean — no errors/tracebacks; container healthy in 12s; /health 200; pf2e module re-registered 200. "Startup embedding-index rebuild complete" logged AFTER "Application startup complete" → confirms non-blocking (D-06). Observed env warning (not a code defect): embedding model text-embedding-nomic-embed-text-v1.5 not loaded in LM Studio — graceful warning, app booted fine.

### 2. Live Semantic Paraphrase Recall (MEM-03)
expected: With a real Obsidian vault + LM Studio embeddings, run a sweep so per-note embeddings and the index are built. Then send a message whose wording is a paraphrase / near-synonym of an existing note (deliberately NOT sharing exact keywords with it). The semantically-matching note appears in the recalled warm context — visible in GET /context/{user_id} under "warm", or reflected in the assistant's answer — even though keyword-only BM25 search would have missed it.
result: issue
severity: blocker
reported: "INCIDENT (root cause CONFIRMED). The FIRST Phase-40 boot's non-blocking startup rebuild (D-06) ran a FULL vault sweep (walk→classify→embed→dedup→RELOCATE), not just an index build. It mis-classified the operator-critical persona and RELOCATED sentinel/persona.md → learning/persona/ (operator confirmed the file is now under learning/persona). On the next boot the app crash-looped: RuntimeError 'sentinel/persona.md missing from Vault' (composition.py:424 on Phase40 / :399 on v0.50.3). Obsidian + Local REST API were verified UP (27124/27123 both 200) — this was a misplaced file, not a vault outage. The startup index rebuild must NOT trigger the destructive classify/relocate sweep, the sweeper must never relocate sentinel/ (and other operator-critical) paths, and likely the relocation ran on degraded embeddings (model not yet loaded on the first boot) producing bad classifications. Blast radius beyond persona is unknown — other notes may also have been relocated."

### 3. Obsidian REST Accepts the .json Index Path (MEM-05 / D-07)
expected: After a sweep, the index exists in the vault at ops/sweeps/embedding-index.json. A PUT to the Obsidian Local REST API for that path returns 2xx, and a subsequent GET retrieves the same JSON body unchanged (a JSON object keyed by note path, each entry carrying embedding_b64 / embedding_model / content_hash). If the REST API rejects the .json extension, that is the documented fallback trigger (switch the index to a .md file) — report that outcome rather than treating it as a hard failure.
result: blocked
blocked_by: prior-phase
reason: "Could not run — Test 2's blocker incident took the system down and we rolled back to v0.50.3 (which has no Phase-40 index emission). Cannot verify a live .json index round-trip until the startup-sweep bug is fixed and Phase 40 is safely redeployed. Partial signal: the Obsidian Local REST API was observed to accept an arbitrary vault path during the persona restore (PUT/GET/DELETE of a .md path all returned 2xx); the FakeVault round-trip test in 40-02 is authoritative for the seam contract. A standalone PUT/GET of a .json path to ops/sweeps/ would confirm but was not run (out of the authorized API scope)."

## Summary

total: 3
passed: 1
issues: 1
pending: 0
skipped: 0
blocked: 1

## Gaps

- truth: "The non-blocking startup embedding-index rebuild (D-06) rebuilds the index without relocating vault files"
  status: failed
  reason: "Startup rebuild calls the full run_sweep (walk→classify→embed→dedup→relocate). It RELOCATED sentinel/persona.md → learning/persona/ (operator-confirmed), causing a crash-loop on the next boot (composition.py 'persona.md missing'). The sweeper does not protect the sentinel/ namespace and mis-classifies files when embeddings are degraded (first boot ran before the embedding model was loaded)."
  severity: blocker
  test: 2
  artifacts: [sentinel-core/app/composition.py, sentinel-core/app/services/vault_sweeper.py]
  missing: ["startup rebuild must build/refresh the index ONLY — never run the classify/relocate/trash sweep", "sweeper must treat sentinel/persona.md (and other operator-critical paths) as protected/never-relocate", "the sweep must abort or skip relocation when embeddings are unavailable/degraded rather than acting on bad classifications", "operator: audit the vault for OTHER files relocated by the bad sweep (blast radius)"]
