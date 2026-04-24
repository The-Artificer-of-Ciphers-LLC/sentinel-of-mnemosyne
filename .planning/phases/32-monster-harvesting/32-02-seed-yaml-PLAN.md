---
plan_id: 32-02
phase: 32
wave: 1
depends_on: [32-01]
files_modified:
  - modules/pathfinder/pyproject.toml
  - modules/pathfinder/data/harvest-tables.yaml
  - modules/pathfinder/data/harvest-roster.txt
  - modules/pathfinder/scripts/scaffold_harvest_seed.py
autonomous: true
requirements: [HRV-01, HRV-02, HRV-03, HRV-04, HRV-05, HRV-06]
must_haves:
  truths:
    - "modules/pathfinder/pyproject.toml dependencies list contains 'rapidfuzz>=3.14.0' in alphabetical position (between pyyaml and reportlab)"
    - "modules/pathfinder/data/harvest-tables.yaml exists with top-level keys: version, source, levels, monsters"
    - "harvest-tables.yaml header comment cites ORC license attribution: 'Derived from Foundry VTT pf2e system' + 'ORC license' (per D-01 reshape)"
    - "modules/pathfinder/data/harvest-roster.txt exists as the canonical L1-3 monster name+level listing produced by scaffold_harvest_seed.py — deterministic input for Task 32-02-04 hand-curation"
    - "Every monster in harvest-roster.txt has a corresponding entry in harvest-tables.yaml (roster-line-count == monsters-entry-count; no silent substitution)"
    - "Every monster entry has: name (str), level (int, 1≤level≤3), traits (list[str]), components (list — may be empty for humanoid-only stubs)"
    - "Every component has: name (str), medicine_dc (int matching DC-by-level for the monster's level per Table 10-5), craftable (list)"
    - "Every craftable has: name (str), crafting_dc (int), value (str in format /^[0-9]+ (gp|sp|cp)( [0-9]+ (sp|cp))?$/)"
    - "Medicine DCs are correct per Table 10-5: level 1 → 15, level 2 → 16, level 3 → 18 (exact integers, no off-by-one)"
    - "modules/pathfinder/scripts/scaffold_harvest_seed.py exists as a one-shot scraper — httpx.Client sync, supports --output flag to write a deterministic roster file, not imported from app.main"
    - "Scaffolder's YAML render MUST NOT emit a half-shape that crashes lifespan validation; it either omits `components:` (so Pydantic default_factory applies) OR emits a fully-commented-out example entry"
    - "rapidfuzz is importable after `uv sync` — test_rapidfuzz_importable flips from RED to GREEN"
    - "yaml.safe_load(Path('modules/pathfinder/data/harvest-tables.yaml').read_text()) parses without exception"
  tests:
    - "python -c \"import tomllib; p = tomllib.loads(open('modules/pathfinder/pyproject.toml').read()); assert 'rapidfuzz>=3.14.0' in p['project']['dependencies']; print('OK')\""
    - "cd modules/pathfinder && uv run python -c 'import rapidfuzz; assert rapidfuzz.__version__ >= \"3.14.0\"; print(rapidfuzz.__version__)'"
    - "test -f modules/pathfinder/data/harvest-roster.txt  # canonical input produced by scaffolder"
    - "cd modules/pathfinder && uv run python -c \"import yaml; d = yaml.safe_load(open('data/harvest-tables.yaml').read()); assert d['version'] == '1.0'; assert d['source'] == 'foundryvtt-pf2e'; assert set([1,2,3]).issubset(set(d['levels'])); print(f'monsters: {len(d[\\\"monsters\\\"])}')\""
    - "cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py::test_rapidfuzz_importable -q  # flips GREEN after this plan"
    - "test -f modules/pathfinder/scripts/scaffold_harvest_seed.py  # scaffolder available for future DM self-service and roster regeneration"
---

<plan_objective>
Ship the data layer of Phase 32: add the rapidfuzz dependency, land the scaffold script (Foundry pf2e pathfinder-monster-core scraper), generate the deterministic L1-3 monster roster, and hand-curate `harvest-tables.yaml` from that roster. This plan ships ZERO app-code; helpers and route wiring live in Plans 32-03 / 32-04. The `test_rapidfuzz_importable` smoke test flips GREEN here.

Per the planner's no-deferral rule: the roster file is committed as the canonical input for hand-curation. Task 32-02-04 binds the YAML to the roster line-by-line — NO substitution without documentation.
</plan_objective>

<threat_model>
## STRIDE Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-32-02-T01 | Tampering | YAML deserialization injection (`!!python/object`) | mitigate (delegated) | Plan 32-03 loader uses `yaml.safe_load` only. This plan ships static YAML; no loader code. |
| T-32-02-I01 | Information Disclosure | License non-compliance (missing ORC attribution) | mitigate | Header comment in harvest-tables.yaml carries the full ORC attribution block per D-01. Verified by grep gate. |
| T-32-02-D01 | DoS | Malformed YAML crashes module at lifespan startup | mitigate (fail-fast) | YAML is parsed by Pydantic at startup (Plan 32-03). A malformed seed means Docker restart-loop, not silent misbehaviour. Acceptable by design per RESEARCH.md §YAML Loader. Additional mitigation: scaffold render emits a fully-commented-out example entry so a DM-edited scaffold cannot produce a Pydantic-invalid partial entry. |
| T-32-02-T02 | Tampering | Wrong DCs in seed (off-by-one on Table 10-5) | mitigate | Per-entry DC check: integer equals `{1:15, 2:16, 3:18}[level]` (except Hard/Rare adjustments, which the seed does NOT use in v1). Grep gate verifies the 3 expected DC values appear. |

**Block level:** none HIGH. T-32-02-T01 delegated to Plan 32-03. T-32-02-I01 mitigated by grep gate. T-32-02-D01 is a lifespan-startup concern (deterministic) + scaffolder render can't produce a half-shape. T-32-02-T02 mitigated by post-write validation. ASVS L1 satisfied.
</threat_model>

<tasks>

<task id="32-02-01" type="execute" autonomous="true">
  <name>Task 32-02-01: Add rapidfuzz to modules/pathfinder/pyproject.toml + uv sync</name>
  <read_first>
    - modules/pathfinder/pyproject.toml (full file — lines 5-13 for dependencies list)
    - .planning/phases/32-monster-harvesting/32-PATTERNS.md §6 (dependency edit + verifier)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md §Standard Stack (installation step)
  </read_first>
  <action>
EDIT `modules/pathfinder/pyproject.toml`:

Find the existing `dependencies = [...]` block (around lines 5-13). Insert `"rapidfuzz>=3.14.0",` keeping alphabetical ordering — between `"pyyaml>=6.0.0",` and `"reportlab>=4.4.0",`:

```toml
    "pyyaml>=6.0.0",
    "rapidfuzz>=3.14.0",
    "reportlab>=4.4.0",
```

Then run `uv lock && uv sync` to regenerate `uv.lock` and install the wheel into the module's venv. Do NOT use pip. Do NOT skip the lock update.

**Ruff single-Edit rule (PATTERNS.md §9, S10):** this edit is data-only (no Python imports added), so ruff's F401 doesn't apply. Safe as a standalone commit.

**Container rebuild note for downstream waves:** PATTERNS.md §6 says "rebuild the pf2e-module Docker container so the new wheel is installed." The container rebuild is implicit in the executor's normal dev loop (`docker compose build pf2e-module` or the equivalent `sentinel.sh` target). This task runs only the host-side `uv sync` — the Docker rebuild happens when Wave 2/3 starts its containerized integration tests. For the in-plan verification step, `uv run` inside `modules/pathfinder` uses the host venv which now has rapidfuzz.

**Worktree note:** in parallel worktrees, commit with `--no-verify` (S9). `uv lock` changes `uv.lock` — add it to the commit.
  </action>
  <acceptance_criteria>
    - `grep -F '"rapidfuzz>=3.14.0",' modules/pathfinder/pyproject.toml` matches exactly once
    - `grep -cE '^\s*"(pyyaml|rapidfuzz|reportlab)' modules/pathfinder/pyproject.toml` → 3 (alphabetical order preserved)
    - `cd modules/pathfinder && uv run python -c 'import rapidfuzz; assert rapidfuzz.__version__ >= "3.14.0"; print(rapidfuzz.__version__)'` exits 0 with a version >= 3.14.0
    - `cd modules/pathfinder && python -m pytest tests/test_harvest.py::test_rapidfuzz_importable -q` exits 0 (GREEN — the Wave-0 smoke test now passes)
    - `modules/pathfinder/uv.lock` is regenerated (file mtime updated in this commit)
    - No Python source file modified — this task is toml + lockfile only
  </acceptance_criteria>
  <automated>cd modules/pathfinder && uv run python -c 'import rapidfuzz; assert rapidfuzz.__version__ >= "3.14.0"; print(rapidfuzz.__version__)'</automated>
</task>

<task id="32-02-02" type="execute" autonomous="true">
  <name>Task 32-02-02: Write the scaffold script modules/pathfinder/scripts/scaffold_harvest_seed.py</name>
  <read_first>
    - modules/pathfinder/app/pdf.py (whole file — style precedent for sync helper scripts per PATTERNS.md §7 "Scaffold script" no-analog)
    - .planning/phases/32-monster-harvesting/32-PATTERNS.md §7 (scaffold script no-analog — use httpx.Client sync, stdout output, not imported)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md §Foundry pf2e Data Schema (pathfinder-monster-core pack, `system.details.level.value`)
  </read_first>
  <action>
CREATE directory `modules/pathfinder/scripts/` (ensure `__init__.py` is NOT added — scripts are not importable).

CREATE `modules/pathfinder/scripts/scaffold_harvest_seed.py`:

```python
"""One-shot scaffolder — prints YAML skeleton + roster for level-1-3 monsters from Foundry pf2e.

Usage:
    # Default: write YAML scaffold to stdout (DM pipes to harvest-tables.yaml.scaffold)
    cd modules/pathfinder && uv run python scripts/scaffold_harvest_seed.py > data/harvest-tables.yaml.scaffold

    # --output <path>: write the plain roster (one monster per line: "<name>\\tlevel") to <path>
    cd modules/pathfinder && uv run python scripts/scaffold_harvest_seed.py --output data/harvest-roster.txt

Downloads the GitHub directory index for packs/pathfinder-monster-core, reads each JSON
file's `system.details.level.value` field, filters to levels 1-3, and:
  - stdout mode: prints a YAML scaffold the DM hand-edits to fill in `components`
  - --output mode: writes a simple "<Name>\\t<level>" roster file (Task 32-02-03 input)

This script is NOT imported by app.main and does NOT need to run inside the Docker
container. It is a DM convenience tool — the authoritative seed is the DM-curated
harvest-tables.yaml, not the script output.

Per S7 (HTTP client — httpx ONLY): uses httpx.Client (sync) for consistency with the
rest of the project. No requests, no aiohttp, no urllib.
"""

from __future__ import annotations

import argparse
import sys

import httpx

REPO_API = "https://api.github.com/repos/foundryvtt/pf2e/contents/packs/pathfinder-monster-core"
RAW_BASE = "https://raw.githubusercontent.com/foundryvtt/pf2e/master/packs/pathfinder-monster-core"


def fetch_level_1_to_3_monsters() -> list[dict]:
    """Return [{name, level, slug}] for all L1-L3 monsters in pathfinder-monster-core."""
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        listing = client.get(REPO_API).json()
        out: list[dict] = []
        for entry in listing:
            if entry.get("type") != "file":
                continue
            name = entry.get("name", "")
            if not name.endswith(".json"):
                continue
            slug = name[:-5]
            raw_url = f"{RAW_BASE}/{name}"
            try:
                doc = client.get(raw_url).json()
            except Exception as exc:  # noqa: BLE001 — best-effort scaffolder
                print(f"# skipped {slug}: {exc}", file=sys.stderr)
                continue
            level = (
                doc.get("system", {})
                .get("details", {})
                .get("level", {})
                .get("value")
            )
            if not isinstance(level, int) or level < 1 or level > 3:
                continue
            out.append({"name": doc.get("name", slug), "level": level, "slug": slug})
    out.sort(key=lambda m: (m["level"], m["name"]))
    return out


def render_roster(monsters: list[dict]) -> str:
    """Emit a deterministic roster for Task 32-02-03 hand-curation.

    One monster per line: '<Name>\\t<level>'. Sorted by (level, name).
    Task 32-02-03 binds the YAML entries line-by-line to this file.
    """
    return "\n".join(f"{m['name']}\t{m['level']}" for m in monsters) + "\n"


def render_yaml_scaffold(monsters: list[dict]) -> str:
    """Emit a YAML scaffold to stdout — DM hand-fills components per monster.

    Each entry omits the `components:` key entirely, AND emits a fully-commented-out
    example block showing the shape the DM should uncomment and fill in. This
    guarantees the file is Pydantic-valid at all DM-edit intermediate states:
      - A fresh scaffold (no components key) loads because `components` defaults to [].
      - A half-uncommented entry still has NO top-level components key until the DM
        uncomments ALL of the example lines together — no partial-component crash path.
    """
    lines = [
        "# modules/pathfinder/data/harvest-tables.yaml",
        "# Hand-curated harvest table for PF2e level 1-3 monsters.",
        "# Medicine DCs from Table 10-5 DCs by Level (GM Core pg. 52).",
        "# Craftable vendor values from Foundry VTT pf2e equipment pack (ORC license).",
        "# Derived from Foundry VTT pf2e system — ORC license, see github.com/foundryvtt/pf2e.",
        "",
        'version: "1.0"',
        'source: "foundryvtt-pf2e"',
        "levels: [1, 2, 3]",
        "monsters:",
    ]
    for m in monsters:
        lines.append(f'  - name: "{m["name"]}"')
        lines.append(f"    level: {m['level']}")
        lines.append("    traits: []        # DM: fill from Foundry JSON system.traits.value")
        # DO NOT emit `components: []` as a live key: if the DM later adds a nested
        # entry lacking required fields, Pydantic validation crashes the lifespan.
        # Instead, emit a fully-commented-out example block. The DM uncomments the
        # entire block together, preserving Pydantic validity at every intermediate
        # step. The module loads fine with no `components` key — default is [].
        lines.append("    # components:")
        lines.append('    #   - name: "Hide"')
        lines.append("    #     medicine_dc: 15    # L1→15, L2→16, L3→18 (Table 10-5)")
        lines.append("    #     craftable:")
        lines.append('    #       - name: "Waterskin"')
        lines.append("    #         crafting_dc: 10")
        lines.append('    #         value: "5 sp"')
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=None,
        help="If set, write a plain roster (name\\tlevel per line) to this path. Otherwise print YAML scaffold to stdout.",
    )
    args = parser.parse_args()

    monsters = fetch_level_1_to_3_monsters()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fp:
            fp.write(render_roster(monsters))
        print(f"# wrote {len(monsters)} monsters to {args.output}", file=sys.stderr)
    else:
        print(render_yaml_scaffold(monsters))
        print(f"# {len(monsters)} monsters scaffolded (levels 1-3)", file=sys.stderr)


if __name__ == "__main__":
    main()
```

**Post-create smoke check** (verifies syntax + imports + scaffold renders a safe shape — does NOT run the network call, which would be slow and non-deterministic in CI):
```bash
cd modules/pathfinder && uv run python -c "import ast; ast.parse(open('scripts/scaffold_harvest_seed.py').read()); print('OK')"
cd modules/pathfinder && uv run python -c "import sys; sys.path.insert(0, '.'); from scripts.scaffold_harvest_seed import render_yaml_scaffold, render_roster; out = render_yaml_scaffold([{'name': 'Wolf', 'level': 1, 'slug': 'wolf'}]); assert 'name: \"Wolf\"' in out; assert 'level: 1' in out; assert 'ORC license' in out; assert 'components: []' not in out; assert '# components:' in out; roster = render_roster([{'name': 'Wolf', 'level': 1, 'slug': 'wolf'}]); assert roster == 'Wolf\\t1\\n'; print('OK')"
```

**Half-shape safety proof**: the scaffold render MUST NOT produce `components: []` as a live YAML key (Blocker 3 mitigation). Instead it emits a fully-commented-out template block. The DM uncomments the entire template at once, never producing a partial entry that crashes Pydantic at lifespan startup.
  </action>
  <acceptance_criteria>
    - `test -f modules/pathfinder/scripts/scaffold_harvest_seed.py` exits 0
    - `test -f modules/pathfinder/scripts/__init__.py` MUST NOT exist (scripts dir is not a package)
    - `grep -F 'import httpx' modules/pathfinder/scripts/scaffold_harvest_seed.py` matches (S7 compliance — httpx only)
    - `grep -cE 'import requests|import aiohttp|import urllib\.request' modules/pathfinder/scripts/scaffold_harvest_seed.py` → 0
    - `grep -F 'ORC license' modules/pathfinder/scripts/scaffold_harvest_seed.py` matches (attribution reminder in scaffold header)
    - `grep -F 'pathfinder-monster-core' modules/pathfinder/scripts/scaffold_harvest_seed.py` matches (correct pack name)
    - `grep -F '--output' modules/pathfinder/scripts/scaffold_harvest_seed.py` matches (roster mode supported)
    - `grep -F 'def render_roster' modules/pathfinder/scripts/scaffold_harvest_seed.py` matches
    - `grep -F '# components:' modules/pathfinder/scripts/scaffold_harvest_seed.py` matches (Blocker 3 — commented template, not live key)
    - `grep -F 'components: []' modules/pathfinder/scripts/scaffold_harvest_seed.py` returns 0 matches (Blocker 3 — MUST NOT emit the half-shape that crashes lifespan)
    - Syntax is valid: `python -c "import ast; ast.parse(open('modules/pathfinder/scripts/scaffold_harvest_seed.py').read())"` exits 0
    - Render smoke test: `cd modules/pathfinder && uv run python -c "import sys; sys.path.insert(0, '.'); from scripts.scaffold_harvest_seed import render_yaml_scaffold, render_roster; out = render_yaml_scaffold([{'name': 'Wolf', 'level': 1, 'slug': 'wolf'}]); assert 'name: \"Wolf\"' in out and 'level: 1' in out and 'ORC license' in out and '# components:' in out and 'components: []' not in out; assert render_roster([{'name': 'Wolf', 'level': 1, 'slug': 'wolf'}]) == 'Wolf\\t1\\n'; print('OK')"` exits 0 with output OK
    - grep -vE '^\s*#' modules/pathfinder/scripts/scaffold_harvest_seed.py | grep -E '(TODO|FIXME|NotImplementedError|raise NotImplementedError)' returns 0 matches (AI Deferral Ban)
  </acceptance_criteria>
  <automated>python -c "import ast; ast.parse(open('modules/pathfinder/scripts/scaffold_harvest_seed.py').read()); print('OK')"</automated>
</task>

<task id="32-02-03" type="execute" autonomous="true">
  <name>Task 32-02-03: Produce canonical L1-3 monster roster via scaffolder (data/harvest-roster.txt)</name>
  <read_first>
    - modules/pathfinder/scripts/scaffold_harvest_seed.py (output of Task 32-02-02 — --output mode)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md §Foundry pf2e Data Schema
  </read_first>
  <action>
RUN the scaffolder in roster mode to produce the canonical L1-3 monster list. This file is the deterministic input to Task 32-02-04 hand-curation — every entry in the roster MUST get a corresponding entry in the YAML, no silent substitution.

```bash
mkdir -p modules/pathfinder/data
cd modules/pathfinder && uv run python scripts/scaffold_harvest_seed.py --output data/harvest-roster.txt
```

**If the GitHub API rate-limits or the network call fails:** retry once. If it still fails, the executor MUST stop and surface the blocker to the human (per CLAUDE.md AI Deferral Ban — no silent fallback). The roster file is load-bearing for the next task.

**Post-run check** — confirm the file exists, is non-empty, and has the expected tab-separated shape:

```bash
cd modules/pathfinder && python -c "
from pathlib import Path
lines = Path('data/harvest-roster.txt').read_text().strip().splitlines()
assert len(lines) > 0, 'roster is empty'
for ln in lines:
    parts = ln.split('\t')
    assert len(parts) == 2, f'bad line: {ln!r}'
    name, level = parts
    assert name, f'empty name: {ln!r}'
    level_int = int(level)
    assert 1 <= level_int <= 3, f'level out of range: {ln!r}'
print(f'OK — {len(lines)} monsters in roster')
"
```

**Commit** the roster file alongside the scaffolder. It becomes the committed source of truth: if Paizo later adds L1-3 monsters to the pack, re-running the scaffolder produces a new roster, and a follow-up phase hand-curates the additions.
  </action>
  <acceptance_criteria>
    - `test -f modules/pathfinder/data/harvest-roster.txt` exits 0
    - `test -s modules/pathfinder/data/harvest-roster.txt` exits 0 (non-empty)
    - Every line matches the tab-separated shape `<name>\t<level>` with `level in {1, 2, 3}`. Verified by the Python check above exiting 0.
    - `wc -l modules/pathfinder/data/harvest-roster.txt` reports ≥ 20 lines (sanity check — the pathfinder-monster-core pack has ≥ 20 L1-3 entries)
    - The file is committed (tracked by git) alongside the scaffolder
  </acceptance_criteria>
  <automated>cd modules/pathfinder && python -c "
from pathlib import Path
lines = Path('data/harvest-roster.txt').read_text().strip().splitlines()
assert len(lines) >= 20
for ln in lines:
    name, level = ln.split('\t')
    assert name and 1 <= int(level) <= 3
print(f'OK {len(lines)}')
"</automated>
</task>

<task id="32-02-04" type="execute" autonomous="true">
  <name>Task 32-02-04: Hand-curate modules/pathfinder/data/harvest-tables.yaml — one entry per roster line</name>
  <read_first>
    - modules/pathfinder/data/harvest-roster.txt (output of Task 32-02-03 — deterministic input)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md §Code Examples Example 1 (YAML fragment)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md §DC-by-Level Table (verbatim: L0→14, L1→15, L2→16, L3→18, ...)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md §Foundry pf2e Data Schema (ORC license attribution template)
    - .planning/phases/32-monster-harvesting/32-PATTERNS.md §1 (YAML shape: version/source/levels/monsters; header comment block)
  </read_first>
  <action>
CREATE `modules/pathfinder/data/harvest-tables.yaml`.

**Binding rule (no silent deferral):** The YAML `monsters:` list MUST have exactly one entry for each line in `modules/pathfinder/data/harvest-roster.txt`. The monster NAMES and LEVELS in YAML MUST match the roster verbatim. No substitution. No "if not in pack, substitute" language. If the roster has 27 lines, the YAML has 27 entries.

**Header** — verbatim per D-01 reshape + ORC attribution:

```yaml
# modules/pathfinder/data/harvest-tables.yaml
# Hand-curated harvest table for PF2e level 1-3 monsters.
# Medicine DCs from Table 10-5 DCs by Level (GM Core pg. 52).
# Craftable vendor values from Foundry VTT pf2e equipment pack (ORC license).
# Derived from Foundry VTT pf2e system (github.com/foundryvtt/pf2e) —
# Paizo Monster Core / Equipment content used under ORC license with attribution.
#
# Roster source: data/harvest-roster.txt (produced by scripts/scaffold_harvest_seed.py).
# Every roster entry has a corresponding monsters: entry below (no substitution).
#
# Medicine DC convention:
#   - Default component uses the monster's level → DC from Table 10-5.
#   - Unusual components (venom glands, etc.) may add Hard (+2) — document inline.
#
# Crafting DC convention:
#   - Uses the CRAFTABLE item's level (not the monster's level) against Table 10-5.
#   - Level-0 common equipment → DC 14; level-1 uncommon items → DC 15 (+2 uncommon).
#
# Level-range scope (v1): 1-3. Level-4+ monsters fall through to LLM fallback with
# verified: false flag per D-02.
```

**Top-level structure** — exactly these keys:

```yaml
version: "1.0"
source: "foundryvtt-pf2e"
levels: [1, 2, 3]
monsters:
  # ... one entry per line in data/harvest-roster.txt ...
```

**Per-entry shape** — exact keys per PATTERNS.md §1 and RESEARCH.md Example 1:

```yaml
  - name: "Wolf"
    level: 1
    traits: [animal]
    components:
      - name: "Hide"
        medicine_dc: 15        # L1 → Table 10-5 → DC 15
        craftable:
          - name: "Leather armor"
            crafting_dc: 14    # item level 0 → DC 14
            value: "2 gp"
      - name: "Fangs"
        medicine_dc: 15
        craftable:
          - name: "Bone charm"
            crafting_dc: 14
            value: "5 sp"
```

**DC constants** (per RESEARCH.md verbatim — do NOT deviate):
- Level 1 monster: `medicine_dc: 15`
- Level 2 monster: `medicine_dc: 16`
- Level 3 monster: `medicine_dc: 18` (note: NOT 17 — Table 10-5 skips 17)

Craftable DCs use the craftable ITEM's level:
- Level-0 common items (leather armor, waterskin, dagger, torch): `crafting_dc: 14`
- Level-0 uncommon items or unusual materials: `crafting_dc: 16` (Hard adjustment +2)
- Level-1 items: `crafting_dc: 15`

**Value format** — strictly one of:
- `"N gp"` (e.g. `"2 gp"`)
- `"N sp"` (e.g. `"5 sp"`)
- `"N cp"` (e.g. `"3 cp"`)
- `"N gp N sp"` (mixed denomination; e.g. `"2 gp 5 sp"`)

**Humanoid coverage note** — a humanoid entry (e.g. Goblin Warrior) can have `components: []` with an inline comment:
```yaml
  - name: "Goblin Warrior"
    level: 1
    traits: [humanoid, goblin]
    components: []    # Humanoid remains — no standard harvestable components; DM may ratify later.
```
This is ACCEPTABLE per CONTEXT.md D-01 (the DM authors which monsters have components). An empty list is valid structurally; Plan 32-03's model validates `components: list[HarvestComponent]` which accepts empty. Humanoid entries still satisfy the binding rule (one entry per roster line).

**Process** (the work of this task):
1. Read `data/harvest-roster.txt`.
2. For EACH line, add a `monsters:` entry using the name and level from the roster verbatim.
3. Populate `components` per the DM's harvest-table authorship (draw from Paizo Monster Core / Foundry pf2e JSON for each monster). Humanoids may have `components: []`. Non-humanoids MUST have at least one component.
4. Verify every component respects the DC convention above.

**Post-write verification** — run Python to confirm binding + shape:
```bash
cd modules/pathfinder && uv run python -c "
import yaml
import re
from pathlib import Path

# 1. Binding rule: roster line count == monsters entry count.
roster_lines = [ln for ln in Path('data/harvest-roster.txt').read_text().strip().splitlines() if ln.strip()]
roster_names = [ln.split('\t')[0] for ln in roster_lines]
roster_levels = {ln.split('\t')[0]: int(ln.split('\t')[1]) for ln in roster_lines}

doc = yaml.safe_load(Path('data/harvest-tables.yaml').read_text())
assert doc['version'] == '1.0'
assert doc['source'] == 'foundryvtt-pf2e'
assert set([1, 2, 3]).issubset(set(doc['levels']))
monsters = doc['monsters']
assert len(monsters) == len(roster_names), (
    f'binding violation: roster has {len(roster_names)} entries but YAML has {len(monsters)}'
)

yaml_names = {m['name'] for m in monsters}
missing = set(roster_names) - yaml_names
extra = yaml_names - set(roster_names)
assert not missing, f'missing from YAML: {sorted(missing)}'
assert not extra, f'extra in YAML (not in roster): {sorted(extra)}'

# 2. Per-entry DC + shape sanity
dc_table = {0: 14, 1: 15, 2: 16, 3: 18}
for m in monsters:
    assert 'name' in m and 'level' in m and 'traits' in m and 'components' in m, m
    assert 1 <= m['level'] <= 3, m
    assert m['level'] == roster_levels[m['name']], (
        f'level mismatch for {m[\"name\"]}: roster={roster_levels[m[\"name\"]]} yaml={m[\"level\"]}'
    )
    for comp in m['components']:
        assert 'name' in comp and 'medicine_dc' in comp and 'craftable' in comp, comp
        expected = dc_table[m['level']]
        assert comp['medicine_dc'] in (expected, expected + 2, expected + 5), (
            f'{m[\"name\"]}/{comp[\"name\"]}: medicine_dc={comp[\"medicine_dc\"]} does not match L{m[\"level\"]} DC {expected} (+2 hard / +5 rarity allowed)'
        )
        for craft in comp['craftable']:
            assert 'name' in craft and 'crafting_dc' in craft and 'value' in craft, craft
            assert isinstance(craft['crafting_dc'], int), craft
            assert re.match(r'^\d+ (gp|sp|cp)( \d+ (sp|cp))?\$', craft['value']), craft['value']

print(f'OK — {len(monsters)} monsters, roster binding verified')
"
```

**License attribution verification:**
```bash
grep -F 'ORC license' modules/pathfinder/data/harvest-tables.yaml
grep -F 'foundryvtt/pf2e' modules/pathfinder/data/harvest-tables.yaml
```
Both must match at least once.
  </action>
  <acceptance_criteria>
    - `test -f modules/pathfinder/data/harvest-tables.yaml` exits 0
    - `grep -F 'ORC license' modules/pathfinder/data/harvest-tables.yaml` matches (attribution present)
    - `grep -F 'github.com/foundryvtt/pf2e' modules/pathfinder/data/harvest-tables.yaml` matches (source cited)
    - `grep -F 'version: "1.0"' modules/pathfinder/data/harvest-tables.yaml` matches exactly once
    - `grep -F 'source: "foundryvtt-pf2e"' modules/pathfinder/data/harvest-tables.yaml` matches exactly once
    - Binding rule: YAML monsters count equals roster line count (verified by Python block above)
    - Every name in the roster appears in the YAML (verified by Python block — no silent substitution)
    - Every name in the YAML appears in the roster (verified by Python block — no ghost entries)
    - YAML parses and conforms to the shape check: the post-write verification Python block above exits 0 with output `OK — N monsters, roster binding verified`
    - No `medicine_dc: 17` exists anywhere in the file (Table 10-5 skips 17; off-by-one sanity): `grep -cE 'medicine_dc: 17\\b' modules/pathfinder/data/harvest-tables.yaml` → 0
    - No `medicine_dc: 14` at level 1 (Table 10-5 L1 is 15, not 14 — catches level-0 confusion): for every entry with `level: 1`, the medicine_dc MUST be in {15, 17, 20} (15 base, +2 Hard, +5 Rare). Verified by the Python block above.
    - All value strings match the regex `^\d+ (gp|sp|cp)( \d+ (sp|cp))?$` (verified by Python block)
  </acceptance_criteria>
  <automated>cd modules/pathfinder && uv run python -c "
import yaml, re
from pathlib import Path
roster_lines = [ln for ln in Path('data/harvest-roster.txt').read_text().strip().splitlines() if ln.strip()]
roster_names = [ln.split('\t')[0] for ln in roster_lines]
roster_levels = {ln.split('\t')[0]: int(ln.split('\t')[1]) for ln in roster_lines}
doc = yaml.safe_load(Path('data/harvest-tables.yaml').read_text())
assert doc['version'] == '1.0'
assert doc['source'] == 'foundryvtt-pf2e'
monsters = doc['monsters']
assert len(monsters) == len(roster_names)
yaml_names = {m['name'] for m in monsters}
assert set(roster_names) == yaml_names
dc_table = {0: 14, 1: 15, 2: 16, 3: 18}
for m in monsters:
    assert 1 <= m['level'] <= 3
    assert m['level'] == roster_levels[m['name']]
    for comp in m['components']:
        expected = dc_table[m['level']]
        assert comp['medicine_dc'] in (expected, expected + 2, expected + 5)
        for craft in comp['craftable']:
            assert isinstance(craft['crafting_dc'], int)
            assert re.match(r'^\d+ (gp|sp|cp)( \d+ (sp|cp))?\$', craft['value'])
print(f'OK {len(monsters)}')
"</automated>
</task>

</tasks>

<verification>
After all 4 tasks complete:

```bash
# 1. rapidfuzz installed and importable
cd modules/pathfinder && uv run python -c "import rapidfuzz; print(rapidfuzz.__version__)"

# 2. Wave-0 smoke test flips GREEN
cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py::test_rapidfuzz_importable -q
# Expected: 1 passed

# 3. Scaffold script compiles and renders deterministically (no half-shape)
cd modules/pathfinder && uv run python -c "import sys; sys.path.insert(0, '.'); from scripts.scaffold_harvest_seed import render_yaml_scaffold; out = render_yaml_scaffold([{'name': 'Wolf', 'level': 1, 'slug': 'wolf'}]); assert 'name: \"Wolf\"' in out; assert '# components:' in out; assert 'components: []' not in out; print('OK')"

# 4. Roster file exists and is non-empty
cd modules/pathfinder && wc -l data/harvest-roster.txt

# 5. YAML binding check (full check from Task 32-02-04 acceptance)
cd modules/pathfinder && uv run python -c "import yaml; from pathlib import Path; d = yaml.safe_load(Path('data/harvest-tables.yaml').read_text()); r = Path('data/harvest-roster.txt').read_text().strip().splitlines(); assert len(d['monsters']) == len(r); print(f'{len(d[\"monsters\"])} monsters bound to {len(r)} roster lines')"

# 6. The other RED tests in test_harvest.py still fail (waves 1 helpers + wave 2 route not yet landed)
cd modules/pathfinder && python -m pytest tests/test_harvest.py -q --ignore-glob='*integration*'
# Expected: 1 passed (rapidfuzz), 20 failed. Exit code != 0.

# 7. No Phase 29/30/31 regressions
cd modules/pathfinder && uv run python -m pytest tests/ -q -k 'not harvest'
# Expected: all green
```
</verification>

<success_criteria>
- `modules/pathfinder/pyproject.toml` lists `rapidfuzz>=3.14.0` alphabetically between `pyyaml` and `reportlab`
- `uv.lock` regenerated; `import rapidfuzz` works in the module venv
- `modules/pathfinder/scripts/scaffold_harvest_seed.py` exists — standalone httpx-based scraper (S7 compliant); supports `--output` flag; scaffold render emits commented-template, never `components: []` (Blocker 3)
- `modules/pathfinder/data/harvest-roster.txt` exists as the canonical L1-3 monster roster (Blocker 2 fix: deterministic input)
- `modules/pathfinder/data/harvest-tables.yaml` exists with one entry per roster line (Blocker 2 fix: no silent substitution)
- YAML passes structural validation (version, source, levels, monsters top-level keys; per-entry shape check)
- ORC license attribution header present in YAML (grep gate)
- Medicine DCs correct per Table 10-5 for each entry's level (no off-by-one)
- Craftable value strings match the gp/sp/cp regex (handles mixed denomination)
- No Phase 29/30/31 regressions
- `test_rapidfuzz_importable` flips GREEN
- AI Deferral Ban: zero TODO/FIXME/NotImplementedError/pass-as-body in the scaffold script or YAML
</success_criteria>

<output>
Create `.planning/phases/32-monster-harvesting/32-02-SUMMARY.md` documenting:
- Files created/modified: pyproject.toml (dep add), uv.lock (regen), scripts/scaffold_harvest_seed.py (new with --output), data/harvest-roster.txt (new — roster output), data/harvest-tables.yaml (new — bound to roster)
- rapidfuzz version installed (expect ≥ 3.14.0)
- Roster line count == YAML monster entry count (Blocker 2 binding proof)
- Per-level breakdown of monster entries (L1: X, L2: Y, L3: Z)
- Confirmation that scaffold render does NOT emit `components: []` (Blocker 3 half-shape fix)
- Confirmation that `test_rapidfuzz_importable` flipped GREEN
- Confirmation that no Phase 29/30/31 tests regressed
- Note: data layer complete; app.harvest helpers land in Plan 32-03; route + registration in 32-04.
- Worktree note per S9: commit with `--no-verify` in parallel worktrees.
</output>
</output>
