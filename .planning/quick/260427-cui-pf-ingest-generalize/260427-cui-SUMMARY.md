---
quick_id: 260427-cui
slug: pf-ingest-generalize
type: execute
wave: 1
status: code-complete-task3-blocked
depends_on: [260427-czb]
completed: 2026-04-27
commits:
  - 8eb3cac  # Task 1: rename cartosia_* → pf_archive_* / pf_npc_extract / routes.ingest
  - 26db9db  # Task 2 RED: failing tests for content-first router + ingest verb + alias parity
  - f324ac3  # Task 2 GREEN: content-first router; subfolder-parametric importer; :pf ingest verb; cartosia deprecation alias
tests:
  pathfinder: 252 passed, 4 pre-existing failures (deferred — see deferred-items.md)
  discord: 77 passed, 50 skipped
  new-tests-shipped: 4 synthetic router + 4 alias-parity importer + 4 ingest-verb/alias bot
authorized-test-swaps:
  - "cartosia-archive → archive/cartosia (imported_from frontmatter)"
  - "/cartosia → /ingest (route endpoint)"
  - "lore/codex/ → lore/ (codex test dest startswith)"
  - "ops/sweeps/cartosia-dry-run- → ops/sweeps/archive-cartosia-dry-run- (report path slug)"
---

# Quick Task 260427-cui: PF Ingest Generalize Summary

Refactored the cartosia-specific PF2e archive importer into a generic content-first ingester. Dropped six hardcoded archive-specific path-prefix literals (`Cartosia/`, `The NPCs/`, `Decided Rules/`, `Crafting System/`, `Codex of Elemental Gateways/`, `The Embercloaks/`) from routing branches in favour of content sniffs and generic folder-shape tokens.

## What shipped

**Router** (`modules/pathfinder/app/pf_archive_router.py`):
- New content-first detector: `_has_homebrew_markers(content)` fires on `**Rules:**`, `**Action:**`, `**Trigger:**`, `**Effect:**`, `**Activate**` bold prefixes.
- Generic folder-shape tokens replace archive-specific literals:
  - `npcs`, `characters`, `npc` → NPC envelope (was `The NPCs`)
  - `rules`, `crafting`, `homebrew` → homebrew (was `Decided Rules`, `Crafting System`)
  - `factions` → faction
- LegendKeeper envelope-page heuristic for locations: file basename slug == immediate parent dir slug → location (preserves `The Bleating Gate/The Bleating Gate.md` behaviour without naming the archive).
- Lore fallback at `mnemosyne/pf2e/lore/<topic>/<slug>.md` where `<topic>` is the slugified top-segment with leading `the-` stripped (so `The Embercloaks` → `embercloaks`, `Codex of Elemental Gateways` → `codex-of-elemental-gateways`). Replaces the prior cartosia-specific `lore/codex/`, `lore/embercloaks/` subdir branches.
- Structural invariant test passes: AST-walk over the router source confirms ZERO archive-specific path-literals (`Cartosia`, `The NPCs`, `Decided Rules`, `Crafting System`, `Codex of Elemental Gateways`, `The Embercloaks`) appear in routing-branch comparisons or container constants outside `_infer_owner_slug`.

**Importer** (`modules/pathfinder/app/pf_archive_import.py`):
- `run_import` gains `subfolder: str = "archive/cartosia"` kwarg, threaded through `_process_npc`, `_process_passthrough`, `_write_report`, `_render_report`.
- `imported_from` frontmatter reflects `subfolder` dynamically (was hardcoded `cartosia-archive`).
- Report path: `ops/sweeps/{slugify(subfolder)}-{kind}-{ts}.md` (was `ops/sweeps/cartosia-{kind}-{ts}.md`). Default subfolder slug = `archive-cartosia`.
- Report heading: `# PF2e Archive {Dry-Run|Import} Report ({subfolder})` (was `# Cartosia ... Report`).

**Route** (`modules/pathfinder/app/routes/ingest.py`):
- `IngestRequest` gains `subfolder: str = "archive/cartosia"` field; forwarded to `run_import`.

**Bot** (`interfaces/discord/bot.py`):
- `_PF_NOUNS` += `"ingest"` (cartosia retained as deprecation alias).
- Single fused branch handles both `noun in ("cartosia", "ingest")` paths:
  - Same flag-parser, same admin gate, same payload shape.
  - `cartosia` pins `subfolder = "archive/cartosia"` regardless of archive_path token.
  - `ingest` uses the user-supplied first non-flag token as both `archive_root` AND `subfolder`.
  - Both POST to `modules/pathfinder/ingest`.
  - cartosia branch prepends `Deprecated: use \`:pf ingest archive/cartosia\` instead — forwarding...\n\n` to the response.
- Summary template generic: `PF2e archive ingest {live import|dry-run} complete.`

## Authorized test-assertion lockstep updates

Per the operator's directive, four test-assertion changes were authorized as in-class with the cartosia-renaming refactor:

1. `imported_from: cartosia-archive` → `imported_from: archive/cartosia` (Phase 29 frontmatter) — affects `test_npc_frontmatter_includes_phase29_required_fields`.
2. `modules/pathfinder/cartosia` → `modules/pathfinder/ingest` (POST endpoint) — affects `test_pf_dispatch_cartosia_admin_dry_run_default` plus subfolder field added to payload-equality assertion.
3. `dest.startswith("mnemosyne/pf2e/lore/codex/")` → `dest.startswith("mnemosyne/pf2e/lore/")` (codex routing, archive-agnostic subdir) — affects `test_codex_lore_routes_to_lore_with_topic_subdir`.
4. `ops/sweeps/cartosia-dry-run-` → `ops/sweeps/archive-cartosia-dry-run-` (report path slug) — affects `test_dry_run_writes_only_report_and_returns_bucket_counts`.

No other test assertions were weakened. The Test-Rewrite Ban was honoured throughout — every change is in lockstep with a feature change the operator explicitly approved.

## Test counts

| Suite | Result |
|---|---|
| `modules/pathfinder/tests/` (whole module) | **252 passed**, 4 pre-existing failures (logged in `deferred-items.md`) |
| `modules/pathfinder/tests/test_pf_archive_router.py` | 21 passed (all original cartosia routing tests still green via content sniffs) |
| `modules/pathfinder/tests/test_pf_archive_router_synthetic.py` | **4 passed** (new — synthetic non-cartosia archive + structural-invariant) |
| `modules/pathfinder/tests/test_pf_archive_import_integration.py` | 11 passed |
| `modules/pathfinder/tests/test_pf_archive_import_alias.py` | **4 passed** (new — subfolder threading + report path slug + default backward-compat) |
| `modules/pathfinder/tests/test_pf_npc_extract.py` | 9 passed |
| `modules/pathfinder/tests/test_legendkeeper_image.py` | 3 passed |
| `interfaces/discord/tests/` (whole module) | **77 passed**, 50 skipped |
| `interfaces/discord/tests/test_subcommands.py` | 64 passed |
| Structural invariant `test_router_has_no_archive_specific_path_literals_in_routing_branches` | PASSED |
| Alias parity `test_pf_dispatch_cartosia_and_ingest_archive_cartosia_send_byte_identical_payload` | PASSED |

Pre-existing pathfinder failures (out of scope, logged in `deferred-items.md`):
- `test_foundry.py::test_roll_event_accepted` — NameError: `get_profile` (FVT module bug)
- `test_foundry.py::test_notify_dispatched` — NameError: `get_profile`
- `test_foundry.py::test_llm_fallback` — NameError: `get_profile`
- `test_registration.py::test_registration_payload_has_16_routes` — assertion pins 16 routes; payload now has 19. Verified pre-existing on main via `git stash; pytest; git stash pop`.

## Task 3 (live smoke) — operator-blocked

**Status:** code is verified correct via the full automated test suite (50+ pathfinder + 64 discord all green); live smoke against the running container could not be executed in this session because the pathfinder container fails to start without an **embedding model** loaded in LM Studio.

Diagnosis:
- `docker compose build pf2e-module` succeeds.
- `docker compose up -d pf2e-module` recreates the container, but startup raises `litellm.exceptions.BadRequestError: OpenAIException - Error code: 400 - {'error': "No models loaded. Please load a model in the developer page or use the 'lms load' command."}` from the embeddings boot path.
- LM Studio currently has `cydonia-v1.2-magnum-v4-22b-mlx` and `qwen3.6-35b-a3b` loaded — both are chat models, not embedding models. The pathfinder rules engine (Phase 33) issues an embeddings call on container startup; without an embedding model it crashes the FastAPI app and uvicorn exits.
- This is unrelated to the cui refactor. The same precondition would have blocked any live cartosia run today.
- Operator action needed: load an embedding model in LM Studio (e.g. `text-embedding-nomic-embed-text-v1.5`), then `docker compose -f docker-compose.yml up -d pf2e-module` and run the two smokes:
  - `:pf cartosia /vault/archive/cartosia --dry-run` — confirm deprecation prefix line + bucket counts (expected benchmark: 19 NPCs / 12 locations / 10 homebrew / 2 harvest / 3 lore / 1 session / 1 arc / 0 factions / 4 dialogue / 3 skipped).
  - `:pf ingest archive/cartosia --dry-run` — confirm bucket counts match exactly + no deprecation prefix.

The directive's bucket-count comparison vs benchmark cannot be produced without the live container. The synthetic tests + the existing 21 cartosia-fixture router tests give strong static evidence that bucket assignments are unchanged for the real archive, but the operator should still run the live smoke before declaring the deprecation alias parity contract met.

## Decisions

- **Locations folder is NOT a generic container token.** A flat `Locations/Mossy Cave.md` (no envelope-page sibling) routes to **lore**, not location. The synthetic test `test_synthetic_lore_file_under_locations_routes_to_lore` pins this. Rationale: a folder named `Locations/` with sparse-prose children is genuinely lore in the archive shapes we've seen; the LegendKeeper envelope-page pattern (`X/X.md`) is the unambiguous structural signal for an actual location entry. Operators reorganise post-hoc if they want flatter location filing.
- **Lore fallback uses top-segment topic subdir, not flat lore/.** Preserves the existing per-topic organisation (`lore/codex-of-elemental-gateways/`, `lore/embercloaks/`) without hardcoding archive-specific names. The leading `the-` strip on the topic slug is the only special-case heuristic and is documented in the module docstring.
- **Subfolder default = `archive/cartosia`** (with slash) for backward compat. The pre-refactor literal was `cartosia-archive` (with dash, used as a frontmatter value, not a path). The new default value is the path-shaped form because that's what the operator types as the `:pf ingest` argument; this is also what's stored in `imported_from`. This is a behaviour change to a shipped frontmatter value — authorized in lockstep with the refactor.

## Deprecation removal date

To be agreed with the operator after the live smoke confirms parity. Suggested: keep `:pf cartosia` alias through one full sweep cycle (a week), then remove the noun from `_PF_NOUNS` in the next quick task. Operator decision; not scheduled here.

## Self-Check: PASSED

- Files created/modified all exist:
  - `modules/pathfinder/app/pf_archive_router.py` — modified, FOUND
  - `modules/pathfinder/app/pf_archive_import.py` — modified, FOUND
  - `modules/pathfinder/app/routes/ingest.py` — modified, FOUND
  - `interfaces/discord/bot.py` — modified, FOUND
  - `modules/pathfinder/tests/test_pf_archive_router.py` — modified, FOUND
  - `modules/pathfinder/tests/test_pf_archive_import_integration.py` — modified, FOUND
  - `interfaces/discord/tests/test_subcommands.py` — modified, FOUND
  - `.planning/quick/260427-cui-pf-ingest-generalize/deferred-items.md` — created, FOUND
- Commits exist:
  - `8eb3cac` (Task 1 rename) — FOUND
  - `26db9db` (RED tests) — FOUND
  - `f324ac3` (GREEN refactor) — FOUND
