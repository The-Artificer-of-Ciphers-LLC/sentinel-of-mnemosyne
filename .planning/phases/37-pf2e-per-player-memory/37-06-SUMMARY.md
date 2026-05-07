---
phase: 37-pf2e-per-player-memory
plan: "06"
subsystem: pathfinder/per-player-memory
tags: [wave-1, green, player-memory, fcm, pvl, shared-seam]
type: auto
wave: 1
requires:
  - 37-01 (RED tests for the three shared seams)
  - 37-05 (alias-path lock-in: mnemosyne/pf2e/players/_aliases.json)
provides:
  - "app.player_identity_resolver — slug_from_discord_user_id, resolve_foundry_speaker, load_alias_map, load_foundry_alias_map"
  - "app.vault_markdown — _parse_frontmatter, build_frontmatter_markdown (shared util)"
  - "app.player_vault_store — read/write profile + npc_knowledge, append_to_inbox/questions/todo, _resolve_player_path isolation gate, list_player_files"
  - "app.memory_projection_store — write_player_map_section (four-section build), append_npc_history_row (two-mode), parse/build helpers"
  - "app.npc_matcher — match_npc_speaker(alias, *, obsidian_client, npc_roster)"
affects:
  - "Wave 2+ plans (37-07 orchestrator/onboarding, 37-08 capture, 37-09 recall, 37-10 canonization, 37-11 projection module) all consume these contracts"
tech-stack:
  added: []
  patterns:
    - "Function-scope symbol imports (Phase 33-01 pattern) — npc_matcher defers app.routes.npc.slugify import"
    - "Single I/O seam: _resolve_player_path is the only place player vault paths are constructed; raises ValueError on slug or relative path violations"
    - "GET-then-PUT for append helpers (project_obsidian_patch_constraint memory)"
    - "Line-anchored re.MULTILINE detection so mid-line literals don't trip existing-section branch"
key-files:
  created:
    - modules/pathfinder/app/player_identity_resolver.py
    - modules/pathfinder/app/vault_markdown.py
    - modules/pathfinder/app/npc_matcher.py
    - modules/pathfinder/app/player_vault_store.py
    - modules/pathfinder/app/memory_projection_store.py
  modified: []
decisions:
  - "Slug regex accepts both canonical hash form (p-{12 hex}) and operator-mapped alias slugs ([a-zA-Z0-9_-]{1,40}) so alias_map can produce readable slugs like p-custom while still passing isolation validation."
  - "resolve_foundry_speaker uses kwargs (actor=, alias_map=, npc_roster=, pc_character_names=) per the RED test contracts in 37-01 — these names override the plan's prose suggestion of speaker=/onboarded_players=."
  - "Single-file alias map (mnemosyne/pf2e/players/_aliases.json) with two sub-keys: discord_id_to_slug + foundry_actor_to_discord_id. Per-section loader functions return {} on missing/invalid file."
  - "vault_markdown extraction is additive — routes/npc.py keeps its private _parse_frontmatter copy; deferred follow-up to migrate it to avoid destabilizing existing NPC tests in this plan."
  - "npc_matcher defers `from app.routes.npc import slugify` to function scope so importing npc_matcher doesn't drag in the heavy LLM/Pi import chain at test collection time."
metrics:
  duration_minutes: 4
  tasks_completed: 3
  tests_added: 0
  tests_turned_green: 20
  files_created: 5
  files_modified: 0
completed: 2026-05-07
requirements: [PVL-06, PVL-07, FCM-01, FCM-02, FCM-03]
---

# Phase 37 Plan 06: Wave 1 GREEN — Shared Seam Implementations Summary

**One-liner:** Implements identity resolver, per-player vault store with slug-prefix isolation, four-section memory projection store with line-anchored two-mode NPC append, and NPC matcher — turning all 20 plan 37-01 RED tests GREEN and locking the contracts every downstream wave depends on.

## Objective Recap

Implement the five shared-seam modules (identity resolver, vault markdown util, vault store, projection store, NPC matcher) that lock the I/O and identity contracts for the per-player memory feature. Plan 37-01 had pre-written 20 failing tests against these contracts; this plan turns them all GREEN without modifying any test (Test-Rewrite Ban honored) and without wiring any FastAPI routes or Discord adapters (those land in 37-07 through 37-11).

## Tasks

### Task 1 — player_identity_resolver + vault_markdown + npc_matcher (commit `4d3d654`)

Created three modules:

- **player_identity_resolver.py** — `slug_from_discord_user_id(user_id, alias_map=None)` returns `f"p-{sha256(user_id).hexdigest()[:12]}"` (length 14, deterministic), or the alias_map override verbatim. `resolve_foundry_speaker(*, actor, alias_map, npc_roster, pc_character_names)` enforces FCM-01 precedence (alias > npc_roster > pc_character_names > unknown) and runs the matched Discord id back through `slug_from_discord_user_id`. `load_alias_map` / `load_foundry_alias_map` parse the locked JSON file at `mnemosyne/pf2e/players/_aliases.json` with `discord_id_to_slug` + `foundry_actor_to_discord_id` sub-keys; both return `{}` on missing or invalid JSON.
- **vault_markdown.py** — `_parse_frontmatter` (verbatim from `routes/npc.py:220-237`) + `build_frontmatter_markdown(frontmatter, body="")` using `yaml.safe_dump(default_flow_style=False, allow_unicode=True, sort_keys=False)`. Additive extraction — `routes/npc.py` retains its private copy until a deliberate follow-up.
- **npc_matcher.py** — `async match_npc_speaker(alias, *, obsidian_client, npc_roster=None) -> str | None` does case-insensitive roster lookup first, falls back to `slugify(alias) + obsidian_client.get_note("mnemosyne/pf2e/npcs/{slug}.md")`. Returns the slug if the probe finds the note, else None. `slugify` is imported at function scope to keep test collection cheap.

Verification: `pytest tests/test_player_identity_resolver.py` → 8 passed.

### Task 2 — player_vault_store with slug-prefix enforcement (commit `05b2fab`)

Created `player_vault_store.py` with `_resolve_player_path(slug, relative)` as the single I/O seam:

- Slug must be a non-empty string; cannot start with `.`, contain `/`, or contain `..`; must match `^(?:p-[a-f0-9]{12}|[a-zA-Z0-9_-]{1,40})$` (canonical hash form OR operator-mapped alias slug).
- Relative path cannot start with `/` or `.`, cannot contain `..`, `.`, or empty segments.
- Resolved path must start with `mnemosyne/pf2e/players/{slug}/`.
- Any violation raises `ValueError` with an explicit message.

Public helpers (all `async`, `obsidian` kwarg required):

- `read_profile`, `write_profile` — `players/{slug}/profile.md` round-trip; write uses `build_frontmatter_markdown`.
- `append_to_inbox`, `append_to_questions`, `append_to_todo` — GET-then-PUT (never `patch_heading`, per `project_obsidian_patch_constraint` memory). Default scaffolds when the file is absent.
- `read_npc_knowledge`, `write_npc_knowledge` — `players/{slug}/npcs/{npc}.md` (per-player namespace, distinct from the global Phase 29 NPC notes).
- `list_player_files` — recursive list under the slug prefix.

Verification: `pytest tests/test_player_vault_store.py` → 6 passed.

### Task 3 — memory_projection_store (commit `8c4718d`)

Created `memory_projection_store.py` with both projection writers:

- `_FOUR_SECTIONS = ("Voice Patterns", "Notable Moments", "Party Dynamics", "Chat Timeline")` — order matters; first write builds all four headings empty.
- `parse_player_map_sections(body)` — splits by `## ` headings, returns `{section: [lines]}`; tolerates missing sections; drops blank lines and any preamble above the first heading.
- `build_player_map_markdown(sections)` — always emits `# Player Map`, then all four headings in canonical order with their lines under each.
- `async write_player_map_section(slug, *, section, lines, obsidian)` — validates `section in _FOUR_SECTIONS`; GET; merge; PUT to `mnemosyne/pf2e/players/{slug}.md`.
- `async append_npc_history_row(npc_slug, *, row, obsidian)` — GET the NPC note at `mnemosyne/pf2e/npcs/{npc_slug}.md`. If `None`, return `"skipped (npc note missing)"`. If `re.compile(rf"^## {Foundry Chat History}\b", re.MULTILINE).search(body)` matches, call `obsidian.patch_heading(path, "Foundry Chat History", row, operation="append")` and return `"appended"`. Otherwise GET-then-PUT with the new section appended at end and return `"created"`. The line-anchored regex ensures mid-line literal mentions never trip the existing-section branch.

Verification: `pytest tests/test_memory_projection_store.py` → 6 passed.

## Verification

| Check | Expected | Actual |
|-------|----------|--------|
| Plan 01 RED tests turned GREEN | 20 (8+6+6) | 20 |
| All three test files pass cleanly | yes | yes (verified together) |
| Existing test status unchanged | yes | yes (no test files modified or skipped) |
| Files created | 5 | 5 |
| Files modified | 0 | 0 |
| `# TODO`, `pass`, `NotImplementedError` stubs | 0 | 0 |
| Behavioral-Test-Only Rule honored | n/a (no new tests) | n/a |
| Test-Rewrite Ban honored | yes | yes (no test edits) |
| Spec-Conflict Guardrail honored | yes | yes (additive only — no validated requirement deviations) |

Verification commands:
```bash
cd modules/pathfinder
pytest tests/test_player_identity_resolver.py   # 8 passed
pytest tests/test_player_vault_store.py         # 6 passed
pytest tests/test_memory_projection_store.py    # 6 passed
pytest tests/test_player_identity_resolver.py \
       tests/test_player_vault_store.py \
       tests/test_memory_projection_store.py    # 20 passed
```

## Deviations from Plan

**1. [Rule 1 - Bug] Kwarg names in `resolve_foundry_speaker` differ from plan prose**

- **Found during:** Task 1 (test execution).
- **Issue:** Plan 37-06's `<action>` block listed `resolve_foundry_speaker(speaker, *, alias_map, foundry_alias_map, npc_roster, onboarded_players)`, but the RED tests in plan 37-01 (already committed and locked) call it with kwargs `actor=`, `alias_map=`, `npc_roster=`, `pc_character_names=`. The plan-01 contract is the source of truth for plan 37-06 (it's the explicit RED → GREEN target).
- **Fix:** Implemented the function with the kwarg names the RED tests use (`actor`, `pc_character_names`). The semantics are identical — only the names differ.
- **Files modified:** `modules/pathfinder/app/player_identity_resolver.py`.
- **Commit:** `4d3d654`.

**2. [Rule 1 - Bug] `write_player_map_section` and `append_npc_history_row` use kwargs for `section`/`lines`/`row`**

- **Found during:** Task 3.
- **Issue:** Plan prose described `write_player_map_section(slug, section, lines, *, obsidian)` and `append_npc_history_row(npc_slug, row, *, obsidian)`, but the RED tests pass `section=`, `lines=`, `row=` as keyword arguments after `slug`/`npc_slug`. Implemented with `*,` after `slug`/`npc_slug` to make these kwargs-only — matches the test call shape and is more readable at call sites (downstream waves will call these from many places).
- **Fix:** Signatures use `slug, *, section, lines, obsidian` and `npc_slug, *, row, obsidian`.
- **Files modified:** `modules/pathfinder/app/memory_projection_store.py`.
- **Commit:** `8c4718d`.

**3. [Rule 3 - Blocking] `npc_matcher` slugify import deferred to function scope**

- **Found during:** Task 1 (regression-check on routes/npc.py imports).
- **Issue:** A top-level `from app.routes.npc import slugify` would force any caller that imports `npc_matcher` to also drag in `app.llm` → `sentinel_shared`, which can't import in some environments (and would slow test collection).
- **Fix:** Moved the import inside `match_npc_speaker` (function scope, Phase 33-01 pattern). `noqa: PLC0415` annotates the deliberate deferral.
- **Files modified:** `modules/pathfinder/app/npc_matcher.py`.
- **Commit:** `4d3d654`.

## Out-of-scope Findings (Not Fixed)

`pytest tests/` collects 299 tests on this host but 199 fail and 3 collect-error — all due to host-only environment issues (`PIL`, `sentinel_shared`, `app.main`). These predate this plan and are unrelated to the five new modules. Confirmed by `git stash && pytest tests/test_npc.py::test_npc_create_success` failing identically without my changes applied. Recorded here per scope-boundary rule; not fixed in this plan. Container-side execution (where these deps are present) is the canonical run target.

The deferred refactor of `routes/npc.py` to consume `vault_markdown._parse_frontmatter` instead of its private copy is documented in plan 37-06's `<action>` block as intentionally out of scope and will land in a follow-up plan.

## TDD Gate Compliance

This plan is the **GREEN** half of the TDD cycle for Wave 0/1 of the per-player memory feature. The RED gate is plan 37-01 (commits `8a1060e`, `44d0974`, `2726301`). The GREEN gate commits are:

- `4d3d654` — feat(37-06): add player identity resolver, vault_markdown util, npc_matcher
- `05b2fab` — feat(37-06): add player_vault_store with slug-prefix isolation gate
- `8c4718d` — feat(37-06): add memory_projection_store with two-mode NPC append

Each GREEN commit follows the corresponding RED commit in linear history. No REFACTOR commit needed — the implementations were written cleanly against the locked contracts and there is no duplication to consolidate within plan 37-06's scope.

## Self-Check: PASSED

Files exist:
- FOUND: modules/pathfinder/app/player_identity_resolver.py
- FOUND: modules/pathfinder/app/vault_markdown.py
- FOUND: modules/pathfinder/app/npc_matcher.py
- FOUND: modules/pathfinder/app/player_vault_store.py
- FOUND: modules/pathfinder/app/memory_projection_store.py

Commits exist:
- FOUND: 4d3d654 (feat 37-06: identity resolver + vault_markdown + npc_matcher)
- FOUND: 05b2fab (feat 37-06: player_vault_store)
- FOUND: 8c4718d (feat 37-06: memory_projection_store)
