---
status: resolved
phase: 33-rules-engine
source: [./scripts/uat_phase33.sh]
started: 2026-04-25T00:18:00Z
completed: 2026-04-25T00:35:00Z
result: 17/17 passed (after Phase 33.1 D-05 calibration)
result_history:
  - 2026-04-25T00:19Z 16/17 — UAT-8 failed at user-locked 0.80
  - 2026-04-25T00:35Z 17/17 — UAT-8 passes after Phase 33.1 calibrated 0.70
addresses_resolved_in:
  - .planning/phases/33-rules-engine/33.1-SUMMARY.md
---

# Phase 33 — Live UAT Result

## Summary

| Metric | Value |
|---|---|
| Total assertions | 17 |
| Passed | 16 |
| Failed | 1 (UAT-8 — calibration, not correctness) |
| Stack rebuild | ✓ |
| 14-route registration | ✓ |
| LM Studio embeddings | ✓ |
| pf2e-module lifespan corpus load | ✓ 148 chunks, 22 topics, shape (148, 768) |

## Result Table

| ID | Test | Status | Detail |
|----|------|--------|--------|
| pre | LM Studio embeddings reachable (L-10) | ✓ | dim=768 |
| UAT-16 | Stack smoke (sc/pf healthy, 14 routes, rule present) | ✓ | sc=True pf=True routes=14 |
| UAT-1 | Flanking source hit | ✓ | status=200, dt=1.40s (after warmup) |
| UAT-2 | Off-guard condition source hit | ✓ | marker=source, books=['Pathfinder Player Core'] |
| UAT-3 | Edge-case generated | ✓ | marker=generated, citations=0 |
| UAT-4 | PF1 decline THAC0 (no cache write) | ✓ | marker=declined, no_cache=True |
| UAT-5 | PF1 decline spell schools | ✓ | marker=declined |
| UAT-6 | Soft-trigger flat-footed-after-trip passes | ✓ | marker=source (NOT declined) |
| UAT-7 | Identical-query cache hit < 3s | ✓ | reused=True, dt=0.59s |
| **UAT-8** | **Reuse match ≥ 0.80 returns cached note** | **✗** | **reused=False — empirical 0.7765 < locked 0.80** |
| UAT-9 | Reuse match < 0.80 composes fresh | ✓ | marker=source, reused=False |
| UAT-10 | Topic-slug folder layout ≥1 ruling /rulings/flanking/ | ✓ | count=2 |
| UAT-11 | :pf rule \<text\> via bot returns embed | ✓ | type=suppressed |
| UAT-12 | :pf rule show \<topic\> returns str | ✓ | rendered topic listing |
| UAT-13 | :pf rule history returns str | ✓ | rendered history |
| UAT-14 | D-15 Monster-Core query → generated (NOT declined) | ✓ | marker=generated |
| UAT-15 | Slow-query placeholder.send + placeholder.edit | ✓ | sent=1, edits=1, edit_has_embed=True |

## UAT-8 — Calibration Failure (D-05 reuse threshold)

**Test pair (cosine measured against text-embedding-nomic-embed-text-v1.5):**

| Query A | Query B | Cosine |
|---------|---------|--------|
| `How does flanking work?` | `If I'm flanking an enemy, what happens to their AC?` | **0.7765** |

**D-05 reuse threshold:** 0.80 (user-locked in 33-CONTEXT.md)

**Implication:** With this embedding model, common paraphrases of the same intent land in the 0.75-0.79 band. Strict 0.80 means reuse-match only fires on near-identical queries. UAT-7 (identical-query exact-hash cache hit) still works because that path is sha1-based, not cosine.

**Decision needed (operator-only — D-05 is user-locked):**

1. **Accept** — D-05 = 0.80 is intentionally strict, reuse only on near-identical queries. Update UAT-8 to use a closer paraphrase (or split into UAT-8a "near paraphrase ≥0.80 reuses" and UAT-8b "loose paraphrase <0.80 composes fresh").
2. **Re-tune** — re-classify D-05 reuse threshold as Claude's-Discretion-pending-calibration (similar to how retrieval threshold was). Run a calibration sweep against a paraphrase fixture to pick an empirical F1-max. Likely lands at ~0.72-0.76.
3. **Different embedding model** — try a re-ranker layer or swap to `bge-large-en-v1.5` for tighter paraphrase clustering. Material rebuild — corpus must be re-embedded and all D-13 frontmatter regenerated.

## Pre-UAT Bugs Caught and Fixed Mid-Run

The live UAT also caught two issues that pytest missed:

| Bug | Commit | Description |
|---|---|---|
| litellm provider prefix missing | `9f1f65b` | `embed_texts()` was called with bare model name; litellm errored "LLM Provider NOT provided" at lifespan startup. Fix: prepend `openai/` at call site (matches `resolve_model.py` pattern). Settings keeps bare name for D-13 frontmatter round-trip. |
| `docker exec` container name | `eb364a8` | `uat_phase33.sh` used bare service name `pf2e-module` for `docker exec`; compose creates `<project>-<service>-1`. Fix: switched to `docker compose exec -T pf2e-module`. |

## Pending Human-Verify (Task 33-05-06)

The 17-assertion live UAT exercises the HTTP/router/bot dispatch layers but does NOT verify in-Discord visual rendering. Task 33-05-06 still requires:

- Real DM session: `:pf rule <free text>` shows D-11 placeholder ("Looking up rules...") then edits to final embed
- Embed colors: green=[SOURCE], yellow=[GENERATED — verify], red=[DECLINED]
- Banner text on generated rulings ("[GENERATED — verify]")
- Obsidian inspection: D-13 frontmatter (model/hash/embedding base64) + D-14 last_reused_at update on cache hit

## Container State Post-UAT

All 4 service containers are running fresh Phase 33 images:
- sentinel-core (proxy + 14-route registry)
- pf2e-module (lifespan loaded 148 chunks, embedding index built)
- discord (bot.py with `_PF_NOUNS` widened to include `rule`, `build_ruling_embed` rendering D-08 shape)
- ofelia, pentest-agent (unchanged)

LM Studio loaded models: `meta-llama-3.1-8b-instruct-abliterated-mlx` (chat), `qwen3.6-35b-a3b` (chat), `qwen2.5-coder-14b-instruct-mlx` (coder), `mistralai/devstral-small-2507` (chat), `text-embedding-nomic-embed-text-v1.5` (embedding — newly loaded for this UAT).
