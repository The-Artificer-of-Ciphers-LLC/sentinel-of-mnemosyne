---
quick_id: 260427-cui
slug: pf-ingest-generalize
type: execute
wave: 1
status: planned
depends_on: [260427-czb]
files_modified:
  - modules/pathfinder/app/cartosia_router.py            # → renamed to pf_archive_router.py
  - modules/pathfinder/app/cartosia_import.py            # → renamed to pf_archive_import.py
  - modules/pathfinder/app/cartosia_npc_extract.py       # → renamed to pf_npc_extract.py
  - modules/pathfinder/app/routes/cartosia.py            # → renamed to ingest.py
  - modules/pathfinder/app/main.py                       # lines 96, 228-230, 251-252, 314-316
  - modules/pathfinder/tests/test_cartosia_router.py     # → renamed test_pf_archive_router.py
  - modules/pathfinder/tests/test_cartosia_import_integration.py  # → renamed test_pf_archive_import_integration.py
  - modules/pathfinder/tests/test_cartosia_npc_extract.py  # → renamed test_pf_npc_extract.py
  - modules/pathfinder/tests/test_pf_archive_router_synthetic.py  # NEW
  - modules/pathfinder/tests/test_pf_archive_import_alias.py      # NEW
  - modules/pathfinder/tests/fixtures/test-fake-archive/Bestiary/Goblin Warrior.md  # NEW
  - modules/pathfinder/tests/fixtures/test-fake-archive/Locations/Mossy Cave.md     # NEW
  - modules/pathfinder/tests/fixtures/test-fake-archive/Rules/Hex Counter.md        # NEW
  - interfaces/discord/bot.py                            # _PF_NOUNS + dispatch branch
  - interfaces/discord/tests/test_subcommands.py         # rename ids; add alias-parity tests
autonomous: true

must_haves:
  truths:
    - "`:pf ingest <subfolder>` Discord verb classifies any PF2e archive folder using content-sniff-first rules — no hardcoded path prefixes like `Cartosia/` or `The NPCs/`."
    - "`:pf cartosia <archive_path>` continues to work via a deprecation alias that prints a one-line deprecation warning and forwards to the new ingest path with subfolder=`archive/cartosia`; output is byte-identical to the pre-refactor verb on the same input."
    - "All 44 pre-refactor cartosia tests + 59 pre-refactor Discord subcommand tests still pass after rename (no assertion weakening; only import-path / id-string updates allowed)."
    - "`route()` correctly classifies a synthetic non-cartosia folder: a Format-A PF2e stat block at `Bestiary/Goblin Warrior.md` → `npc_a`, a lore file at `Locations/Mossy Cave.md` → `lore`, a homebrew rule at `Rules/Hex Counter.md` → `homebrew`, all from content alone (zero `Cartosia/`, `The NPCs/`, `Decided Rules/`, `Crafting System/`, `Codex of Elemental Gateways/`, `The Embercloaks/` path matches in the new router)."
    - "Imported NPC/passthrough notes record `imported_from: archive/cartosia` (or whatever subfolder was passed) instead of the hardcoded literal `cartosia-archive`."
    - "Report files land at `ops/sweeps/{subfolder-slug}-import-<ts>.md` and `{subfolder-slug}-dry-run-<ts>.md` — slug derived from the subfolder argument."
    - "All eight cartosia edge cases preserved via content sniffs (NPC-as-folder, two-NPC file, dual-path duplicate, mis-placed Adventure Hooks under The NPCs, Talons-of-the-Claw faction sniff, orphan dialogue, `THings Said.md` typo, Format B `Secret\\n\\nInformation that only admins can see.` block stripping)."
    - "Phase 33 rules engine still does NOT see a phantom `homebrew` topic — homebrew destination unchanged at `mnemosyne/pf2e/homebrew/`."
  artifacts:
    - path: "modules/pathfinder/app/pf_archive_router.py"
      provides: "Shape-agnostic content-first archive router. Same RouteDecision dataclass + route() signature as the old cartosia_router."
      min_lines: 400
      contains: "def route("
    - path: "modules/pathfinder/app/pf_archive_import.py"
      provides: "Importer orchestrator with archive_root parameter; sets imported_from dynamically from subfolder."
      min_lines: 400
      contains: "async def run_import"
    - path: "modules/pathfinder/app/pf_npc_extract.py"
      provides: "Pure rename of cartosia_npc_extract.py — same extract_npc()/NpcExtractionError API."
      contains: "async def extract_npc"
    - path: "modules/pathfinder/app/routes/ingest.py"
      provides: "POST /ingest FastAPI route with subfolder field on the request model."
      contains: "@router.post(\"/ingest\")"
    - path: "modules/pathfinder/tests/test_pf_archive_router_synthetic.py"
      provides: "4-6 behavioral tests proving the router works on a non-cartosia synthetic folder via content-sniff alone."
      min_lines: 80
    - path: "modules/pathfinder/tests/test_pf_archive_import_alias.py"
      provides: "Alias-parity tests: `:pf cartosia` still works, prints deprecation warning, produces identical output to `:pf ingest archive/cartosia`."
      min_lines: 60
    - path: "modules/pathfinder/tests/fixtures/test-fake-archive/Bestiary/Goblin Warrior.md"
      provides: "Format A PF2e stat block fixture for synthetic-folder router test."
      contains: "**Creature 1**"
    - path: "modules/pathfinder/tests/fixtures/test-fake-archive/Locations/Mossy Cave.md"
      provides: "Lore/location fixture for synthetic-folder router test."
    - path: "modules/pathfinder/tests/fixtures/test-fake-archive/Rules/Hex Counter.md"
      provides: "Homebrew-rule fixture for synthetic-folder router test."
      contains: "Rules:"
  key_links:
    - from: "interfaces/discord/bot.py (_pf_dispatch)"
      to: "modules/pathfinder/app/routes/ingest.py (POST /ingest)"
      via: "POST modules/pathfinder/ingest with {archive_root, subfolder, dry_run, limit, force, confirm_large, user_id}"
      pattern: "modules/pathfinder/ingest"
    - from: "interfaces/discord/bot.py (cartosia alias branch)"
      to: "interfaces/discord/bot.py (ingest branch)"
      via: "alias forwards to ingest with subfolder='archive/cartosia' after printing deprecation warning"
      pattern: "Deprecated: use `:pf ingest"
    - from: "modules/pathfinder/app/pf_archive_router.py (route())"
      to: "RouteDecision"
      via: "content sniff (no path-prefix branches)"
      pattern: "_has_pf2e_stat_block|_has_format_b_sections|_has_personal_npc_markers|_is_dialogue_filename|_is_arc_filename|_is_harvest_filename"
    - from: "modules/pathfinder/app/pf_archive_import.py"
      to: "imported_from frontmatter field"
      via: "subfolder argument (default archive/cartosia for backward compat)"
      pattern: "imported_from"
---

<objective>
Refactor today's just-shipped cartosia importer into a generic Pathfinder
archive ingester. Drop hardcoded path-prefix sniffs (`Cartosia/`, `The NPCs/`,
`Decided Rules/`, `Crafting System/`, `Codex of Elemental Gateways/`,
`The Embercloaks/`) in favour of content-first rules. Add a `subfolder`
argument so the ingester works on any archive subtree. Preserve every shipped
behavior of `:pf cartosia` via a deprecation alias for one release.

Purpose: today's cartosia importer is the right shape but wrong scope —
naming and pre-flight routing assume a single specific archive layout. The
operator wants to ingest other PF2e archives (classes, bestiary fragments,
homebrew packs) without forking the importer or hardcoding more prefixes.

Output: rename four modules + four test files, refactor the router to
content-first detection, parameterise the importer with `archive_root` /
subfolder, add `:pf ingest <subfolder>` Discord verb with `:pf cartosia`
deprecation alias, add 4-6 synthetic-folder behavioural tests + 2 alias
parity tests. All 44 cartosia tests and 59 Discord subcommand tests stay
green throughout (rename test ids, do NOT weaken assertions).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/quick/260427-czb-cartosia-import/260427-czb-PLAN.md
@.planning/quick/260427-czb-cartosia-import/260427-czb-SUMMARY.md
@modules/pathfinder/app/cartosia_router.py
@modules/pathfinder/app/cartosia_import.py
@modules/pathfinder/app/cartosia_npc_extract.py
@modules/pathfinder/app/routes/cartosia.py
@modules/pathfinder/app/main.py
@interfaces/discord/bot.py
@CLAUDE.md

<interfaces>
<!-- Existing public contracts that the rename must preserve. Tests bind to these. -->

From cartosia_router.py (becomes pf_archive_router.py — same signatures):
```python
Bucket = Literal["npc_a","npc_b","npc_dialogue","location","homebrew",
                 "harvest","lore","session","arc","faction","skip"]

@dataclass(frozen=True)
class RouteDecision:
    bucket: Bucket
    slug: str
    dest: str
    reason: str
    owner_slug: str | None = None

def slugify(text: str) -> str: ...

def route(
    file_path: Path,
    content: str,
    *,
    archive_root: Path,
    known_npc_slugs: Iterable[str] = (),
) -> RouteDecision: ...
```

From cartosia_import.py (becomes pf_archive_import.py):
```python
class ImportCostGuardError(Exception): ...

@dataclass
class ImportReport:
    archive_root: str = ""
    dry_run: bool = True
    npc_count: int = 0
    location_count: int = 0
    # ... (full counter set unchanged)
    def asdict(self) -> dict: ...

async def run_import(
    *,
    archive_root: str,
    dry_run: bool,
    limit: int | None,
    force: bool,
    confirm_large: bool,
    obsidian_client: _ObsidianLike,
) -> ImportReport: ...
```

From routes/cartosia.py (becomes routes/ingest.py):
```python
class IngestRequest(BaseModel):
    archive_root: str
    subfolder: str = "archive/cartosia"   # NEW field, default = backward compat
    dry_run: bool = True
    limit: int | None = None
    force: bool = False
    confirm_large: bool = False
    user_id: str = ""

@router.post("/ingest")          # was @router.post("/cartosia")
async def ingest(req: IngestRequest) -> dict: ...
```
</interfaces>

<existing-bot-dispatch-shape>
<!-- bot.py's `:pf cartosia` branch (lines ~875-947) — preserve exact flag parsing. -->
Re-tokenises the entire post-noun tail; first non-flag token = archive_path;
flags: --live (live=True), --dry-run (live=False), --force, --confirm-large,
--limit N (consumes next token, must be int), unknown `--` flag → error
string. Admin gate via `_is_admin(user_id)` BEFORE any parsing or POST.
Default dry_run=True. POSTs to `modules/pathfinder/cartosia` with
{archive_root, dry_run=not live, limit, force, confirm_large, user_id}.
Renders summary: "Cartosia {live import|dry-run} complete.\nReport: `<path>`\n..."

The new `:pf ingest` branch must use IDENTICAL flag-parsing logic and
identical admin gate. The first non-flag token becomes `subfolder`
(passed both as `archive_root` for backward-compat path resolution AND as
`subfolder` in the request body — see Task 2 for the dual-purpose handling).
The `:pf cartosia` alias prepends a one-line deprecation warning to the
output but otherwise produces an identical message body.
</existing-bot-dispatch-shape>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Rename modules + tests, fix imports (pure rename, no behavior change)</name>
  <files>
    modules/pathfinder/app/cartosia_router.py → modules/pathfinder/app/pf_archive_router.py
    modules/pathfinder/app/cartosia_import.py → modules/pathfinder/app/pf_archive_import.py
    modules/pathfinder/app/cartosia_npc_extract.py → modules/pathfinder/app/pf_npc_extract.py
    modules/pathfinder/app/routes/cartosia.py → modules/pathfinder/app/routes/ingest.py
    modules/pathfinder/tests/test_cartosia_router.py → modules/pathfinder/tests/test_pf_archive_router.py
    modules/pathfinder/tests/test_cartosia_import_integration.py → modules/pathfinder/tests/test_pf_archive_import_integration.py
    modules/pathfinder/tests/test_cartosia_npc_extract.py → modules/pathfinder/tests/test_pf_npc_extract.py
    modules/pathfinder/app/main.py
  </files>
  <action>
    Pure rename pass — observable behavior MUST be unchanged at the end of this task.

    1. `git mv` (preserves blame) the five module files and three test files to their new names listed above.

    2. Inside the renamed modules, fix internal imports:
       - `pf_archive_import.py`: `from app.cartosia_npc_extract import …` → `from app.pf_npc_extract import …`; `from app.cartosia_router import …` → `from app.pf_archive_router import …`
       - `routes/ingest.py`: `from app.cartosia_import import …` → `from app.pf_archive_import import …`. Rename the function name from `cartosia_import` (line 60) to `ingest` to match the route, and CHANGE the route decorator from `@router.post("/cartosia")` to `@router.post("/ingest")`. Rename `CartosiaImportRequest` → `IngestRequest`. **Do NOT add the `subfolder` field yet** — that's Task 2.

    3. Inside the renamed test files, update imports + mock targets:
       - `test_pf_archive_router.py`: `from app.cartosia_router import …` → `from app.pf_archive_router import …`
       - `test_pf_npc_extract.py`: `from app.cartosia_npc_extract import …` → `from app.pf_npc_extract import …`; mock paths `app.cartosia_npc_extract.acompletion_with_profile` → `app.pf_npc_extract.acompletion_with_profile`
       - `test_pf_archive_import_integration.py`: `from app.cartosia_import import …` → `from app.pf_archive_import import …`; mock paths `app.cartosia_npc_extract.acompletion_with_profile` → `app.pf_npc_extract.acompletion_with_profile`; `app.cartosia_import.download_token` → `app.pf_archive_import.download_token`

    4. Update `modules/pathfinder/app/main.py`:
       - line 96: `{"path": "cartosia", …}` → `{"path": "ingest", "description": "Bulk import PF2e archive subfolder (260427-cui)"}`
       - lines 228-230: `import app.routes.cartosia as _cartosia_module` → `import app.routes.ingest as _ingest_module`; `_cartosia_module.obsidian = obsidian_client` → `_ingest_module.obsidian = obsidian_client` (rename comment too)
       - lines 251-252: same rename in shutdown branch
       - lines 314-316: `from app.routes.cartosia import router as cartosia_router` → `from app.routes.ingest import router as ingest_router`; `app.include_router(cartosia_router)` → `app.include_router(ingest_router)` (update comment)

    5. Update `modules/pathfinder/tests/conftest.py` line 7 comment-mention of `app.cartosia_npc_extract` → `app.pf_npc_extract`.

    6. **Critical guardrail (Test-Rewrite Ban)**: do NOT modify any assertion, fixture content, or test logic. The only edits to test files are import paths and mock target strings. After this task, run all renamed test suites and confirm 44 pathfinder + 0 new bot test changes still pass. (Bot tests will fail in this task because bot.py still POSTs to `/cartosia`; that's fixed in Task 2.)

    7. Pillow + LegendKeeper image download stay as-is. compose.yml /vault mount unchanged. `mnemosyne/pf2e/homebrew/` destination unchanged.

    8. AT THIS TASK'S END: `:pf cartosia` is broken (route is gone, bot still calls it). That's intentional — Task 2 wires the new ingest route + alias.
  </action>
  <verify>
    <automated>cd modules/pathfinder && uv run pytest tests/test_pf_archive_router.py tests/test_pf_npc_extract.py tests/test_pf_archive_import_integration.py tests/test_legendkeeper_image.py -q  # MUST report 44 passed, identical id list to pre-rename minus the file-name prefix change</automated>
  </verify>
  <done>
    - 5 module files renamed via `git mv`; 3 test files renamed via `git mv`.
    - Old `cartosia_*` filenames no longer exist under modules/pathfinder/app or app/routes or tests/.
    - `grep -rn "cartosia_router\|cartosia_import\|cartosia_npc_extract\|routes.cartosia\|routes/cartosia" modules/pathfinder/ | grep -v __pycache__ | grep -v .pytest_cache | wc -l` returns 0.
    - `cd modules/pathfinder && uv run pytest tests/test_pf_archive_router.py tests/test_pf_npc_extract.py tests/test_pf_archive_import_integration.py tests/test_legendkeeper_image.py -q` reports 44 passed, 0 failed, 0 skipped.
    - Test assertions and fixture bytes are unchanged from pre-rename (`git diff --stat HEAD~1 -- modules/pathfinder/tests/test_pf_archive_router.py` should show only line-level additions matching the import path change).
    - Atomic commit: `refactor(pathfinder): rename cartosia_* modules to pf_archive_* / pf_npc_extract / routes.ingest (pure rename, no behavior change)`
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Refactor router to content-first; parameterise importer + route with subfolder; wire `:pf ingest` + `:pf cartosia` deprecation alias</name>
  <files>
    modules/pathfinder/app/pf_archive_router.py
    modules/pathfinder/app/pf_archive_import.py
    modules/pathfinder/app/routes/ingest.py
    interfaces/discord/bot.py
    modules/pathfinder/tests/test_pf_archive_router.py
    modules/pathfinder/tests/test_pf_archive_import_integration.py
    interfaces/discord/tests/test_subcommands.py
  </files>
  <behavior>
    Tests written FIRST (RED), then implementation (GREEN). Behaviors to lock:

    - **Router content-first (router test additions)**: a Format-A `**Creature 1** … **AC** 14` file under `Bestiary/Whatever.md` (NOT `Cartosia/`, NOT `The NPCs/`) routes to `npc_a` with reason mentioning "PF2e stat block", NOT a path-prefix reason. A homebrew-style file with "Rules:" + "Action:" markers under `Rules/Whatever.md` (NOT `Decided Rules/` or `Crafting System/`) routes to `homebrew` based on content markers, dest = `mnemosyne/pf2e/homebrew/<slug>.md`. A short lore file under `Locations/` routes to `lore`. The new content-first homebrew detector (`_has_homebrew_markers`) fires on `**Rules:**`, `**Action:**`, `**Trigger:**`, `**Effect:**`, or `**Activate**` bold prefixes.
    - **Backward compat (existing 21 router tests)**: every existing test still passes. Files under `Cartosia/`, `The NPCs/`, `Decided Rules/`, `Crafting System/`, `Codex of Elemental Gateways/`, `The Embercloaks/` route to the same buckets as before — but now via content sniffs (Format A / Format B / personal-NPC markers / homebrew markers / dialogue filename / arc filename / harvest filename / faction fallback for sparse files under any "characters" parent). Path-prefix branches in the router are removed; the only filesystem-aware behavior left is dialogue-owner resolution (which uses `known_npc_slugs`, not literal dir names except the cosmetic "the npcs" envelope skip in `_infer_owner_slug`).
    - **Importer subfolder field**: `run_import(archive_root="…", subfolder="archive/cartosia", …)` writes `imported_from: archive/cartosia` (not `cartosia-archive`) into every NPC and passthrough frontmatter. Subfolder defaults to `archive/cartosia` for backward compat. Report path = `ops/sweeps/{slug(subfolder)}-import-<ts>.md` (e.g. `archive-cartosia-import-2026-04-27T....md`).
    - **Route subfolder field**: `IngestRequest` gets `subfolder: str = "archive/cartosia"`; route forwards both `archive_root` and `subfolder` to `run_import`.
    - **`:pf ingest` verb**: `_PF_NOUNS` += `"ingest"`. Dispatch branch parses `<subfolder>` as the first non-flag token (e.g. `archive/cartosia`, `archive/classes`, or an absolute path), POSTs to `modules/pathfinder/ingest` with `subfolder=<token>` and `archive_root=<token>`. Same flags as cartosia: `--live`, `--dry-run`, `--limit N`, `--force`, `--confirm-large`. Same admin gate. Default dry_run=True.
    - **`:pf cartosia` alias**: still in `_PF_NOUNS`. Branch prints a deprecation line `Deprecated: use \`:pf ingest archive/cartosia\` instead — forwarding...\n` then INVOKES the same code path the ingest branch does, with subfolder hardcoded to `"archive/cartosia"` (the archive_root token from the user is still passed verbatim). For test parity, the deprecation prefix is the only difference from the ingest output.
    - **Alias parity (new test)**: a mocked POST capture shows `:pf ingest archive/cartosia --dry-run` and `:pf cartosia archive/cartosia --dry-run` send IDENTICAL request bodies (modulo `user_id`). Output strings differ ONLY by the leading `Deprecated: …\n` line.
    - **Bot test renames**: existing 6 cartosia bot tests in test_subcommands.py keep their assertions; only the deprecation-line presence is ADDED as a new assertion in the alias-still-works test. No existing assertion weakened.
    - **AI Deferral Ban / Spec-Conflict Guardrail**: every preserved cartosia behavior gets a content-sniff replacement. If any cartosia behavior cannot be reproduced via content sniff alone (e.g. some pathological dual-path edge case), STOP and surface to the operator before deleting the path branch — do not silently regress.
  </behavior>
  <action>
    **RED phase**

    1. Add 4-6 new behavioral tests to `modules/pathfinder/tests/test_pf_archive_router.py` (or split into `test_pf_archive_router_synthetic.py` if file gets >500 lines):
       - Create fixture files at `modules/pathfinder/tests/fixtures/test-fake-archive/Bestiary/Goblin Warrior.md` (Format A — PF2e stat block with `**Creature 1**`, `**AC** 14`, perception, ability scores), `Locations/Mossy Cave.md` (~400 chars of lore prose, no NPC/homebrew markers), `Rules/Hex Counter.md` (`**Rules:** …` + `**Action:** …` + `**Trigger:** …` block).
       - test_synthetic_format_a_under_bestiary_routes_to_npc_a: assert `route(...).bucket == "npc_a"` AND `"PF2e stat block" in reason`.
       - test_synthetic_lore_file_under_locations_routes_to_lore: assert bucket == "lore", dest under `mnemosyne/pf2e/lore/`.
       - test_synthetic_homebrew_under_rules_dir_routes_to_homebrew_via_content: assert bucket == "homebrew", dest == `mnemosyne/pf2e/homebrew/hex-counter.md`, reason mentions "homebrew markers" not "path prefix".
       - test_router_has_no_path_prefix_branches: introspect the router source — assert `"Cartosia"`, `"Decided Rules"`, `"Crafting System"`, `"Codex of Elemental Gateways"`, `"The Embercloaks"`, `"The NPCs"` (as routing literals, not as comments or fixtures) appear ONLY inside `_infer_owner_slug` (the dialogue envelope skip). This is a behavior-shaped guard against the path-prefix anti-pattern reappearing. Implementation: parse the router with `ast`, walk Compare/If nodes that look at `parts[0]`/`top`, assert no string literal in that set is compared. If `ast` walk feels brittle, alternative: use `inspect.getsource(pf_archive_router)`, strip docstring + comments via `tokenize`, then `assert "Decided Rules" not in stripped` etc. This is NOT a source-grep echo-chamber test — it asserts a structural invariant of the routing function that, if violated, would let the path-prefix anti-pattern silently come back.

    2. Add `tests/test_pf_archive_import_alias.py` with 2-3 alias-parity tests:
       - test_imported_from_uses_subfolder_argument: run an in-memory dry-run with subfolder="archive/classes"; assert at least one NPC's `proposed_writes` entry shows imported_from="archive/classes" (read it back from the MockObsidian's stored note bytes, parse YAML, assert `imported_from == "archive/classes"`).
       - test_report_path_slug_derives_from_subfolder: run with subfolder="archive/classes/wizard"; assert `report.report_path` matches `^ops/sweeps/archive-classes-wizard-dry-run-.*\.md$`.

    3. Add 2 new alias bot tests in `interfaces/discord/tests/test_subcommands.py`:
       - test_pf_cartosia_alias_prints_deprecation_warning_and_forwards: mock `_sentinel_client.post_to_module` to return a stub report; invoke `await bot._pf_dispatch("cartosia /tmp/fake --dry-run", "admin-user")`; assert result starts with `"Deprecated: use \`:pf ingest archive/cartosia\` instead — forwarding...\n"` AND POST was called with `("modules/pathfinder/ingest", payload, …)` AND `payload["subfolder"] == "archive/cartosia"`.
       - test_pf_ingest_archive_cartosia_produces_byte_identical_body: capture two POST payloads — one from `:pf ingest archive/cartosia --dry-run` and one from `:pf cartosia archive/cartosia --dry-run` (with the same user_id). Assert both payloads are equal as dicts (modulo nothing — they MUST be byte-identical).

    Run pytest. ALL new tests MUST fail RED (router still has path branches; importer rejects subfolder kwarg; bot has no ingest verb). Commit: `test(pathfinder,discord): RED tests for content-first router + ingest verb + cartosia alias parity`.

    **GREEN phase**

    4. Refactor `pf_archive_router.py`:
       - Delete the path-prefix branches: `_HOMEBREW_PARENT_DIRS`, `_CODEX_PARENT_DIR`, the `if top in _HOMEBREW_PARENT_DIRS` block, the `if top == _CODEX_PARENT_DIR` block, the `if top == "The Embercloaks"` block, the `if top == "Cartosia"` block, the `if any(p == "the npcs" for p in parent_lower)` factional fallback.
       - Replace with a content-first detector: add `_HOMEBREW_MARKERS_RES = (re.compile(r"\*\*Rules:\*\*"), re.compile(r"\*\*Action:\*\*"), re.compile(r"\*\*Trigger:\*\*"), re.compile(r"\*\*Effect:\*\*"), re.compile(r"\*\*Activate\*\*"))` and `_has_homebrew_markers(content) -> bool` that returns True if ≥1 marker fires.
       - New router post-Format-A/B fall-through (in this order):
         a. If `_has_homebrew_markers(content)` AND content body ≥ 200 chars → bucket=`homebrew`, dest=`mnemosyne/pf2e/homebrew/<slug>.md`, reason="homebrew markers (Rules/Action/Trigger/Effect/Activate) detected".
         b. If `_has_personal_npc_markers(content)` (Role/Function/Class/Player/Status/Personality/Habits/Goals/Flaws/Fears) → bucket=`npc_b`, dest=`mnemosyne/pf2e/npcs/<slug>.md`, reason="personal NPC markers detected".
         c. If `_is_factional_filename_or_short(content, stem)` → bucket=`faction`. (Defines factional as: short body, no personal markers, no homebrew markers, no NPC sniff. This is what catches `Talons of the Claw.md` today via the The-NPCs path branch; we replicate via content shape.) For Talons specifically the file is 99 chars → already caught by the `body_len < 200` skip; the faction branch only fires for files with body 200-1500 chars that have organisational descriptors but no personal markers. Add a heuristic: ≥2 hits among `**Members:**`, `**Leader:**`, `**Headquarters:**`, `**Goals:**` (org-shape) → faction.
         d. Fallback: lore at `mnemosyne/pf2e/lore/<slug>.md` (no top-segment topic subdir — the cartosia codex/embercloaks subdirs were path-driven; for generic ingestion we go flat into `lore/` and let the operator reorganise post-hoc, OR keep a topic subdir derived from the FIRST PATH SEGMENT relative to archive_root, since that's just folder-aware routing without being archive-specific. **Decision: keep first-path-segment topic subdir** — it's not cartosia-specific, applies uniformly, and matches the existing lore organisation. So fallback dest = `mnemosyne/pf2e/lore/<slugify(parts[0])>/<slug>.md`.).
       - Verify: all 21 existing router tests + the new 4 synthetic-fixture tests pass. The structural-invariant test (no Cartosia/Decided Rules/etc literals in routing branches) passes.

    5. Refactor `pf_archive_import.py`:
       - Add `subfolder: str = "archive/cartosia"` kwarg to `run_import`.
       - Replace the literal `"cartosia-archive"` (search shows it appears in `_process_npc` frontmatter dict and `_process_passthrough` fm dict) with `subfolder` everywhere it's used.
       - Update `_write_report`: `f"ops/sweeps/cartosia-{kind}-{ts}.md"` → `f"ops/sweeps/{slugify(subfolder)}-{kind}-{ts}.md"` (import slugify from pf_archive_router).
       - Update `_render_report` heading from "Cartosia Dry-Run/Import Report" → f"PF2e Archive {kind.title()} Report ({subfolder})".
       - Existing 11 integration tests still pass (they call `run_import` with default kwargs; the default subfolder gives `archive/cartosia` → `imported_from="archive/cartosia"` instead of `"cartosia-archive"`. CHECK: does any existing test assert on the literal `"cartosia-archive"`? If yes — that assertion is checking for the OLD shipped behavior; per Test-Rewrite Ban, STOP and surface this conflict to the operator. Likely answer: the existing tests assert on bucket counts and frontmatter shape but not the literal string; if so, proceed. Search: `grep -n "cartosia-archive" modules/pathfinder/tests/`. If matches found, they need to be updated to match the new dynamic value — this counts as "updating tests in lockstep with a feature change the operator explicitly approved" per CLAUDE.md Test-Rewrite Ban exception. The operator's prompt explicitly authorises `imported_from: <subfolder>`, so the test update is in-scope.)

    6. Refactor `routes/ingest.py`:
       - Add `subfolder: str = "archive/cartosia"` to `IngestRequest`.
       - Forward to `run_import(..., subfolder=req.subfolder, ...)`.

    7. Wire bot.py:
       - Replace `_PF_NOUNS = frozenset({"npc", "harvest", "rule", "session", "cartosia"})` with `_PF_NOUNS = frozenset({"npc", "harvest", "rule", "session", "ingest", "cartosia"})`.
       - Add a new `if noun == "ingest":` branch that mirrors the existing cartosia branch byte-for-byte, except:
         (a) admin gate same as cartosia
         (b) usage string says `:pf ingest <subfolder> [--live] [--dry-run] [--limit N] [--force] [--confirm-large]` (admin-only)
         (c) the first non-flag token is treated as `subfolder` (and ALSO passed as `archive_root` so the importer's filesystem walk works — the operator can pass either a subfolder relative path like `archive/cartosia` or an absolute path; the importer resolves it via `Path(archive_root).resolve()`).
         (d) POST target: `modules/pathfinder/ingest`
         (e) payload: `{"archive_root": archive_path, "subfolder": archive_path, "dry_run": not live, "limit": limit_val, "force": force_flag, "confirm_large": confirm_large, "user_id": user_id}`. (Note: archive_root and subfolder receive the same string here — the route accepts both.)
         (f) summary text: replace "Cartosia" with "PF2e archive ingest" in the response template.
       - Modify the `if noun == "cartosia":` branch:
         - Keep admin gate, flag parsing, archive_path extraction unchanged.
         - At dispatch time: hardcode `subfolder = "archive/cartosia"` in the payload (subfolder is FIXED for the alias regardless of what archive_path the user typed — that's the deprecation contract: cartosia means cartosia).
         - POST to `modules/pathfinder/ingest` (NOT `/cartosia` — route is gone).
         - Prepend the response with `"Deprecated: use `:pf ingest archive/cartosia` instead — forwarding...\n\n"` so the alias warning is the first line of the reply.
         - Update the bare `:pf cartosia` usage string at lines 819-825 to also include the deprecation hint.

    8. Update existing 6 cartosia bot tests: change the POST endpoint assertion `args[0][0] == "modules/pathfinder/cartosia"` → `args[0][0] == "modules/pathfinder/ingest"`. This is a feature-change-in-lockstep update per Test-Rewrite Ban exception (`Updating tests in lockstep with a feature change the user explicitly approved` — the operator's prompt explicitly authorises route renaming). Do not weaken any other assertion.

    Run all suites. ALL tests must be green. Commit: `refactor(pathfinder,discord): drop path-prefix routing in favor of content-first sniffs; add :pf ingest verb; :pf cartosia kept as deprecation alias`.
  </action>
  <verify>
    <automated>cd modules/pathfinder && uv run pytest tests/ -q && cd ../../interfaces/discord && uv run pytest tests/test_subcommands.py -q  # MUST report all green; pathfinder count = 44 + 4-6 router synthetic + 2-3 importer subfolder = 50-53; discord = 59 + 2 alias-parity = 61</automated>
  </verify>
  <done>
    - `grep -c "Cartosia\|Decided Rules\|Crafting System\|Codex of Elemental Gateways\|The Embercloaks\|the npcs" modules/pathfinder/app/pf_archive_router.py` finds matches ONLY inside (a) module/function docstrings (header prose), (b) the `_infer_owner_slug` envelope skip set, (c) inline historical-context comments. Filter command: `grep -nE 'Cartosia|Decided Rules|Crafting System|Codex of Elemental|The Embercloaks|the npcs' modules/pathfinder/app/pf_archive_router.py | grep -v '^\s*#' | grep -v '"""' | grep -v 'the npcs", "the npc"'` returns 0 lines. (Filters out docstrings, comments, and the envelope-skip set in `_infer_owner_slug`.)
    - `grep -n "cartosia-archive" modules/pathfinder/app/pf_archive_import.py` returns 0 matches. The literal lives only in test fixtures / historical SUMMARY references.
    - `grep -n "subfolder" modules/pathfinder/app/pf_archive_import.py modules/pathfinder/app/routes/ingest.py interfaces/discord/bot.py` shows the field defined and threaded end-to-end.
    - `grep -n "modules/pathfinder/ingest" interfaces/discord/bot.py` shows BOTH the ingest branch AND the cartosia alias branch POSTing to the new endpoint.
    - `grep -n "Deprecated: use" interfaces/discord/bot.py` shows the deprecation line in the cartosia alias branch.
    - All pathfinder tests pass: `cd modules/pathfinder && uv run pytest tests/ -q` reports ≥50 passed, 0 failed.
    - All discord subcommand tests pass: `cd interfaces/discord && uv run pytest tests/test_subcommands.py -q` reports ≥61 passed, 0 failed.
    - The structural-invariant test (test_router_has_no_path_prefix_branches) passes — the router has no string-literal compares against `Cartosia`, `Decided Rules`, `Crafting System`, `Codex of Elemental Gateways`, `The Embercloaks`, or `The NPCs` outside `_infer_owner_slug`.
    - Alias parity test passes — `:pf cartosia archive/cartosia --dry-run` and `:pf ingest archive/cartosia --dry-run` send byte-identical POST bodies (modulo the user_id which is the same in both).
    - Live smoke (manual, recorded under <success_criteria> below): operator runs `:pf cartosia /vault/archive/cartosia --dry-run` against the running pathfinder container and verifies the dry-run report matches the pre-refactor output bucket counts (19 NPCs, 12 locations, 10 homebrew, 2 harvest, 3 lore, 1 session, 1 arc, 0 factions, 4 dialogue, 3 skips, 0 errors). If counts differ, surface to operator BEFORE shipping (Spec-Conflict Guardrail — alias parity is shipped behavior).
    - Atomic commit: `refactor(pathfinder,discord): drop path-prefix routing for content-first sniffs; add :pf ingest verb; :pf cartosia preserved as deprecation alias`
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Operator alias-parity smoke against live cartosia archive</name>
  <what-built>
    Tasks 1-2 shipped: pf_archive_router (content-first), pf_archive_import (subfolder-parametric), routes/ingest, `:pf ingest` verb, `:pf cartosia` deprecation alias. All 50+ pathfinder tests + 61+ discord tests green. Now validate alias parity end-to-end against the real archive — the bytes-identical-output contract requires a live confirmation that the dry-run report count vector hasn't drifted.
  </what-built>
  <how-to-verify>
    1. Restart the pathfinder container so the new ingest route is mounted: `docker compose -f modules/pathfinder/compose.yml restart pf2e-module` (or whatever the project's restart pattern is — see `Module Dockerfiles hardcode deps vs pyproject.toml` memory; if anything was added to pyproject.toml that wasn't dual-shipped to Dockerfile, the container will restart-loop on ModuleNotFoundError — re-bake the image first).
    2. From the Discord client, in an admin-allowlisted channel: run `:pf cartosia /vault/archive/cartosia --dry-run`. Confirm:
       - First line of the response is the deprecation warning: `Deprecated: use \`:pf ingest archive/cartosia\` instead — forwarding...`
       - Bucket counts match the pre-refactor benchmark exactly: 19 NPCs, 12 locations, 10 homebrew, 2 harvest, 3 lore, 1 session, 1 arc, 0 factions, 4 dialogue, 3 skips, 0 errors. If ANY count differs, STOP — content-first sniffs have introduced a regression that the synthetic tests didn't catch. Surface the diff to the operator, do not proceed.
       - Report file landed at `mnemosyne/ops/sweeps/archive-cartosia-dry-run-<ts>.md` (NOT `cartosia-dry-run-<ts>.md` — the slug is now derived from the subfolder).
    3. Run the new verb head-to-head: `:pf ingest archive/cartosia --dry-run`. Confirm bucket counts match step 2 exactly. Confirm the response body has NO deprecation warning.
    4. Open the most recent dry-run report in Obsidian and spot-check 3-4 NPCs (Alice Twoorb, Provost Marshall Silas, Veela & Tarek, Apprentice Aldric). Confirm:
       - All four classify as `npc_a` or `npc_b` (NOT `faction`, NOT `lore`).
       - The `imported_from` line in their proposed-write metadata reads `archive/cartosia` (the new subfolder-derived value), NOT `cartosia-archive`.
    5. Confirm Phase 33 rules engine still has no phantom `homebrew` topic: `:pf rule list` returns only `misc`, `actions`, `off-guard` (or whatever the current cached topic set is — the absence of `homebrew` is the invariant, not the exact list).
  </how-to-verify>
  <resume-signal>Type "approved — alias parity holds, counts match, no phantom homebrew topic" or describe any drift / regression observed.</resume-signal>
</task>

</tasks>

<verification>
- Task 1: 44 pathfinder tests pass after pure rename; bot tests fail (expected — fixed in Task 2).
- Task 2: 50+ pathfinder tests + 61+ discord tests pass; structural-invariant test confirms no path-prefix literals in routing branches; alias-parity test confirms byte-identical POST bodies between `:pf ingest archive/cartosia` and `:pf cartosia <anything>`.
- Task 3: live smoke confirms dry-run bucket counts match pre-refactor (19/12/10/2/3/1/1/0/4/3/0); deprecation warning visible; report path slug derives from subfolder; no phantom homebrew topic.
</verification>

<success_criteria>
- `:pf ingest <subfolder>` works on any PF2e archive subtree using content-first detection.
- `:pf cartosia` continues to work for one release as a deprecation-warning alias; same flags, same admin gate, byte-identical request body, only-difference-in-output is the leading deprecation line.
- Router source has zero hardcoded archive-specific path-prefix literals in routing branches (Cartosia/, The NPCs/, Decided Rules/, Crafting System/, Codex of Elemental Gateways/, The Embercloaks/) — verified by structural-invariant test.
- All 8 cartosia edge cases preserved via content sniffs alone — verified by the existing 21 router tests staying green plus the new synthetic-folder test.
- `imported_from` frontmatter reflects the subfolder argument dynamically; no remaining occurrences of the literal `cartosia-archive`.
- Phase 33 rules engine `:pf rule list` still returns no phantom `homebrew` topic (homebrew destination unchanged at `mnemosyne/pf2e/homebrew/`).
- Pillow + LegendKeeper image download untouched (already shape-agnostic).
- Three atomic commits on main: `refactor(pathfinder): rename …`, `test(pathfinder,discord): RED tests for …`, `refactor(pathfinder,discord): drop path-prefix routing …`.
</success_criteria>

<output>
After completion, create `.planning/quick/260427-cui-pf-ingest-generalize/260427-cui-SUMMARY.md` documenting:
- Commits shipped, file rename map, bucket-count diff (should be zero — alias parity).
- Any cartosia edge case that needed a content-sniff redesign + the synthetic-fixture test that pins it.
- Deprecation removal date / next-release plan (operator decision; SUMMARY captures whatever was agreed).
</output>
