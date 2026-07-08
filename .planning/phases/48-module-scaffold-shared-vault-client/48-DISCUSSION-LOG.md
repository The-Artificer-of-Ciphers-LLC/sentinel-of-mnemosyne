# Phase 48: Module Scaffold + Shared Vault Client - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-08
**Phase:** 48-module-scaffold-shared-vault-client
**Areas discussed:** Shared client shape (XMOD-01), pf2e cutover strictness (criterion #4), First music/ write + schema proof (MUS-02/05), Sweeper skip vs zero-Core-changes (MUS-01/Pitfall 1)

Mode: advisor (research-backed comparison tables; 4 parallel `gsd-advisor-researcher` agents, calibration tier `standard`). Non-technical-owner reframing: OFF (technical owner).

---

## ① Shared ObsidianClient shape (XMOD-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Lean base + pf2e subclass | Core 4 methods shared; pf2e subclass adds binary/heading | |
| Lift-and-shift whole client | Copy pf2e's 7-method client verbatim into shared | |
| Core + optional mixins | Shared core + composable binary/heading mixins | ✓ (refined) |

**User's choice:** "Other" → *"review 3, knowing that we're adding this module and review the PRD for the plans for future modules, to me a core that has common makes more sense now vs when you have four things going and then decide to combine."* → validated against `docs/PRD-Sentinel-of-Mnemosyne.md` §6.1–6.6 (6 modules total; core methods shared by all) and locked as **composable `ObsidianClientCore` + `ObsidianHeadingMixin` + `ObsidianBinaryMixin` in `sentinel_shared`, built now**.
**Notes:** Follow-up sub-decision — binary methods placed as a **shared mixin too** (user-confirmed), so pf2e is pure composition and no future media module has to copy pf2e. pf2e = `ObsidianClient(Core, BinaryMixin, HeadingMixin)`; music = `Core` only.

---

## ② pf2e cutover strictness (criterion #4)

| Option | Description | Selected |
|--------|-------------|----------|
| Strict, no shim | Delete duplicated logic, rewrite the 2 import sites, gate on pf2e pytest re-run | ✓ |
| Allow re-export shim | Keep app/obsidian.py as a one-line re-export | |

**User's choice:** Strict, no shim.
**Notes:** Blast radius verified tiny — only 2 real coupling sites (`main.py`, `test_aliases_path_probe.py`); ~10 duck-typed consumers + 7 local `FakeObsidian` doubles unaffected. Full pf2e suite re-run is an acceptance criterion.

---

## ③ First music/ write + schema proof (MUS-02/05)

| Option | Description | Selected |
|--------|-------------|----------|
| Hub + 3 subfolder hubs, cross-linked | music/index.md ⇄ lessons/practice-log/ideas hubs | ✓ |
| Single music/index.md hub | One hub only — fails the verified orphan rule | |
| Throwaway smoke note | Write→read→assert→delete; no lasting namespace | |

**User's choice:** Hub + 3 subfolder hubs, cross-linked.
**Notes:** Verified orphan rule (`graph_analysis.build_graph_report`): `orphan ⇔ not outlinks and not backlinks`, and wikilinks resolve only against existing files → a lone hub self-flags as orphan. Also verified Core's `:graph`/`:check` is `NOTES_ROOT`-scoped, so `music/` is invisible to Core's checker → compliance proven structurally in-module; no Core change.

---

## ④ Sweeper skip-prefix + warm-tier vs zero-Core-changes (MUS-01/Pitfall 1)

| Option | Description | Selected |
|--------|-------------|----------|
| Env-only, both vars, generated | SWEEP_SKIP_PREFIXES + PROTECTED_NAMESPACES in deploy env, generated from Core defaults | ✓ |
| Env skip-prefix only | Only SWEEP_SKIP_PREFIXES; no protected-namespace net | |
| One-line Core default edit | Add music/ to Core's default tuple — violates MUS-01 | |

**User's choice:** Env-only, both vars, generated from Core defaults.
**Notes:** Verified both env vars use pydantic **REPLACE** semantics → must reproduce Core's full default tuple + `music/`; generate, don't hand-copy. Warm-tier `RecallConfig.exclude_prefixes` has no env path → exclusion deferred (would need a Core change).

## Claude's Discretion
- Client file layout inside `sentinel_shared` (single module vs subpackage); music `app/obsidian.py` subclass-vs-alias; hub-note prose beyond schema shape; the env-override generation mechanism.

## Deferred Ideas
- Warm-tier recall exclusion for `music/` → future `:music history` phase (needs Core change).
- Binary vault storage → mixin built but unused; only a hypothetical Media/Discovery module (PRD §6.4, v2+).
- `patch_heading` adoption by music ("Listening Log") → later music phase.
- Real routes (practice/idea/history/routine, Discord wiring, ListenBrainz/Discogs) → Phases 49+.
