---
status: complete
quick_id: 260708-mz4
task: "Research OKF and assess whether it should be incorporated into Sentinel"
date: 2026-07-08
outcome: assessment-only (no code change — recommendation is do-not-incorporate-now)
recommendation: do-not-incorporate-now
---

# Quick Task 260708-mz4: OKF Incorporation Assessment — Summary

## What this task was
A **research + decision** task (`/gsd-quick --research`), not a build task: read Google Cloud's Open Knowledge Format (OKF) announcement and decide whether OKF needs to be incorporated into Sentinel. The deliverable is the assessment itself — see `260708-mz4-RESEARCH.md`. No production code was written because the assessment concluded no change is warranted.

## Decision
**Do NOT incorporate OKF now.**

## Why (one paragraph)
OKF turned out to be a v0.1 *draft* that formalizes "a directory of markdown files with YAML frontmatter" — explicitly modeled on Obsidian vaults and Karpathy's LLM-wiki pattern, i.e. almost exactly what Sentinel already implements (markdown notes + `_schema` frontmatter + `[[wikilinks]]` + hub notes + a zero-orphan graph invariant). Sentinel is ~90% OKF-conformant by accident of good design. But OKF's value is *cross-vendor/agent portability*, and Sentinel is a single-user personal memory with no external OKF consumer; the only mechanical change OKF would force — converting `[[wikilinks]]` to plain markdown links — would degrade Obsidian's graph/backlink UX and Sentinel's zero-orphan substrate for zero current benefit. Adopting a Google-led draft spec into a mature system is premature.

## Positive takeaway
OKF is **design validation**: a major vendor independently converged on Sentinel's "markdown vault as agent-consumable memory" architecture.

## Follow-up (backlog, NOT scheduled)
If OKF matures past v0.1 draft AND a concrete consumer emerges, the right shape is an **optional `sentinel_shared` export adapter** (`vault → OKF bundle`) that leaves the native wikilink vault untouched — not a native-format migration. Details + trigger conditions in `260708-mz4-RESEARCH.md` §5.

## Artifacts
- `260708-mz4-RESEARCH.md` — full OKF briefing (cited primary sources) + OKF↔Sentinel mapping + recommendation.

## Self-Check: PASSED
Assessment complete, decision recorded with rationale and follow-up conditions. No code change (correct for an assess-only task).
