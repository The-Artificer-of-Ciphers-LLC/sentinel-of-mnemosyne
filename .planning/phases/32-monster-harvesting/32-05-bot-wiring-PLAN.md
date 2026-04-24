---
plan_id: 32-05
phase: 32
wave: 4
depends_on: [32-01, 32-04]
files_modified:
  - interfaces/discord/bot.py
autonomous: true
requirements: [HRV-01, HRV-02, HRV-03, HRV-04, HRV-05, HRV-06]
must_haves:
  truths:
    - "interfaces/discord/bot.py has a `build_harvest_embed` module-level helper: dict → discord.Embed, pure function, no I/O, handles single-monster + batch shapes"
    - "bot.py _pf_dispatch widens noun-check from {'npc'} to {'npc', 'harvest'} (D-04 top-level discovery)"
    - "bot.py _pf_dispatch adds a `harvest` branch: parses comma-separated monster names from `args` (not verb/rest), supports multi-word names (D-04, Pitfall 5)"
    - "Harvest dispatch posts to modules/pathfinder/harvest with {names: [...], user_id: ...}; returns {type: 'embed', content: '', embed: build_harvest_embed(result)}"
    - "Empty harvest args (`:pf harvest` with no names) returns a usage string; post_to_module NOT called"
    - "Multi-word monster names preserved: `:pf harvest Giant Rat` → names=['Giant Rat']"
    - "Comma-separated with surrounding whitespace trimmed: `:pf harvest Boar , Wolf , Orc` → names=['Boar','Wolf','Orc']"
    - "Top-level usage string in _pf_dispatch lists both 'npc' and 'harvest' nouns"
    - "Unknown-noun error message lists both supported categories"
    - "All 7 bot-layer tests from test_subcommands.py (test_pf_harvest_*) flip GREEN"
    - "Help text update: the existing npc verb-help block is unchanged (harvest is a sibling noun, not an npc verb)"
  tests:
    - "cd interfaces/discord && uv run --no-sync python -m pytest tests/test_subcommands.py -k harvest -q  # → 7 passed"
    - "cd interfaces/discord && uv run --no-sync python -m pytest tests/ -q  # → all green (no Phase 26-31 regressions)"
---

<plan_objective>
Wire the harvest layer into the Discord bot. Adds `build_harvest_embed` (pure dict → discord.Embed per D-03a), widens `_pf_dispatch` noun-check to accept `harvest`, adds the harvest dispatch branch (comma-separated batch with multi-word name support per D-04 + Pitfall 5), and updates the top-level usage + unknown-noun error strings. After this plan, all 7 bot-layer tests turn GREEN and the end-to-end HRV-01..06 contract is shippable.
</plan_objective>

<threat_model>
## STRIDE Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-32-05-T01 | Tampering | Crafted Discord message embedding `:pf harvest` pattern in multi-line attacks | accept | Single-DM personal use; message.content is passed through untouched; server-side Pydantic validator (Plan 32-04) catches control chars + batch cap. |
| T-32-05-T02 | Tampering | Embed content injection via LLM-generated component names containing Discord markup | mitigate | Field value truncated to 1024 chars (Discord API cap); discord.Embed escapes nothing itself but renders as-is. Accept LLM output display as-is because the server already marked verified:false and the embed footer signals "generated". |
| T-32-05-D01 | DoS | Extremely long monster name list causing embed overflow | mitigate (delegated) | Server enforces MAX_BATCH_NAMES=20 (Plan 32-04). Bot simply forwards; no bot-side cap needed. |
| T-32-05-I01 | Information Disclosure | Harvest embed revealing generated-vs-seed source attribution | N/A (desired) | D-04 footer INTENTIONALLY surfaces mixed-source counts for DM verification. Not a leak — a feature. |
| T-32-05-T03 | Tampering | Noun-widening accidentally accepting `monster` or other lookalike | mitigate | Explicit set check `noun in {"npc", "harvest"}`; regression test `test_pf_harvest_noun_recognised` locks in behaviour. |

**Block level:** none HIGH. ASVS L1 satisfied (stateless forwarding + server-side validation).
</threat_model>

<tasks>

<task id="32-05-01" type="execute" autonomous="true">
  <name>Task 32-05-01: Add build_harvest_embed + harvest dispatch branch + noun widen + usage/error updates (4 Edit calls, documented below)</name>
  <read_first>
    - interfaces/discord/bot.py (full file — lines 1-100 for imports + module helpers; lines 272-314 for build_stat_embed analog; lines 338-345 for top-level noun split + usage string; lines 344-345 for current noun-check rejection text; lines 516-528 for `stat` verb branch; lines 545-587 for `say` verb branch pattern)
    - .planning/phases/32-monster-harvesting/32-PATTERNS.md §9 (Analogs A/B/C; Gotchas 1-3 — especially Gotcha 3 "REPEAT OFFENDER" single-Edit rule for import+use)
    - .planning/phases/32-monster-harvesting/32-RESEARCH.md §Pattern 3 (full build_harvest_embed reference impl)
    - .planning/phases/32-monster-harvesting/32-CONTEXT.md D-03a, D-04, Resolved-batch-separator
    - .planning/phases/31-dialogue-engine/31-05-bot-wiring-PLAN.md (exemplar Task 31-05-02 — same file, same constraints)
  </read_first>
  <action>
EDIT `interfaces/discord/bot.py`. The four changes below are **non-contiguous** (spread across lines 272-345+) and therefore **cannot** land in a single Edit call with precise old_string/new_string matches. Use FOUR explicit Edit calls (one per change, in the order listed).

**Why NOT a single Write (Warning 3):** bot.py is ~650 lines with unrelated Phase 26-31 content. Rewriting the whole file via Write would be a diff-hostile operation and easy to get wrong. Four targeted Edits preserve the surrounding code.

**Ruff F401 risk (mitigated):** `build_harvest_embed` uses only `discord` (already imported at module top) — NO new imports are added. Therefore there is no intermediate unused-import state between the four Edits, and ruff cannot strip anything. Executor MUST confirm this by grepping for new import lines in the diff before commit. If an Edit inadvertently adds an unreferenced import, fix it in place — do NOT add `# noqa: F401`.

**The 4 Edits, in order:**

**Change 1 — Add `build_harvest_embed` helper.** Place it adjacent to `build_stat_embed` (around line 272 per PATTERNS.md §9 Analog C — verify exact line via `grep -n "^def build_stat_embed" interfaces/discord/bot.py`). Insert directly after the `build_stat_embed` function body ends:

```python
def build_harvest_embed(data: dict) -> "discord.Embed":
    """Build a Discord Embed from /harvest module response (HRV-01..06, D-03a, D-04).

    Single-monster: title=monster name+level, description=note/warning.
    Batch: title='Harvest report — N monsters', description=generated-count warning.
    Fields: one per aggregated component type (D-04) with Medicine DC + monsters tally + craftable bullets.
    Footer: source attribution (FoundryVTT pf2e | LLM generated | Mixed sources).
    """
    monsters = data.get("monsters", []) or []
    aggregated = data.get("aggregated", []) or []
    footer_text = data.get("footer", "")

    if len(monsters) == 1:
        m = monsters[0]
        title = f"{m.get('monster', '?')} (Level {m.get('level', '?')})"
        description_parts: list[str] = []
        if m.get("note"):
            description_parts.append(f"_{m['note']}_")
        if not m.get("verified", True):
            description_parts.append("⚠ Generated — verify against sourcebook")
        description = "\n".join(description_parts)
    else:
        title = f"Harvest report — {len(monsters)} monsters"
        generated_count = sum(1 for m in monsters if not m.get("verified", True))
        description = (
            f"⚠ {generated_count}/{len(monsters)} entries include generated data — verify."
            if generated_count
            else ""
        )

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.dark_green(),
    )

    for comp in aggregated:
        craftable_lines = [
            f"• {c.get('name', '?')} (Crafting DC {c.get('crafting_dc', '?')}, {c.get('value', '?')})"
            for c in comp.get("craftable", []) or []
        ]
        monsters_tally = ", ".join(comp.get("monsters", []) or [])
        field_value = (
            f"Medicine DC {comp.get('medicine_dc', '?')}\n"
            f"From: {monsters_tally}\n"
            + "\n".join(craftable_lines)
        )[:1024]  # Discord field value cap
        embed.add_field(name=comp.get("type", "?"), value=field_value, inline=False)

    embed.set_footer(text=footer_text)
    return embed
```

**Change 2 — Widen the noun rejection check.** Find the existing noun-rejection line near the top of `_pf_dispatch` (currently around line 344-345 per PATTERNS.md §9; verify via `grep -n 'Unknown pf category' interfaces/discord/bot.py`). The existing line reads:
```python
if noun != "npc":
    return f"Unknown pf category `{noun}`. Currently supported: `npc`."
```
Replace with:
```python
if noun not in {"npc", "harvest"}:
    return f"Unknown pf category `{noun}`. Currently supported: `npc`, `harvest`."
```

**Change 3 — Update the top-level usage string.** Find the `len(parts) < 2` usage string (around line 340 per PATTERNS.md §9 Analog E; verify via `grep -n 'Usage: \`:pf' interfaces/discord/bot.py`). The existing line now reads (after Phase 31):
```python
return "Usage: `:pf npc <create|update|show|relate|import|say> ...`"
```
Replace with TWO usage lines (one per noun — preserves every existing verb):
```python
return (
    "Usage: `:pf npc <create|update|show|relate|import|say> ...` "
    "or `:pf harvest <Name>[,<Name>...]`"
)
```

(Backward compatible; unit test `test_pf_unknown_verb_help_includes_say` from Phase 31 still passes because the `say` verb is still listed; new unit test `test_pf_harvest_empty_returns_usage` asserts `"Usage"` and `"harvest"` appear in the return.)

**Change 4 — Add the harvest dispatch branch.** Per PATTERNS.md §9 "Alternative parsing" recommendation: re-parse from `args` rather than using the noun/verb split (cleaner for multi-word names). Insert this branch AFTER the noun-check widening (Change 2) and BEFORE the `if noun == "npc":` block. The exact placement: the existing `_pf_dispatch` body currently parses `parts = args.split(...)` and then has an `if noun == "npc":` block; add the harvest branch between the noun-rejection line and the `if noun == "npc":` block.

```python
if noun == "harvest":
    # Format: `:pf harvest <Name>[,<Name>...]` — comma-separated batch (D-04, Pitfall 5).
    # `:pf harvest` with zero args is caught by the generic `len(parts) < 2`
    # early-return at the top of `_pf_dispatch` (line 339) — it returns the
    # combined usage string BEFORE this branch runs. So the `if not names:`
    # fallback below is defensive (covers `:pf harvest ,` or `:pf harvest  `
    # where parts[1] exists but names parses empty), not redundant.
    # Re-parse from the original args to preserve multi-word names within commas.
    harvest_args = args[len("harvest"):].strip()
    names = [n.strip() for n in harvest_args.split(",") if n.strip()]
    if not names:
        return "Usage: `:pf harvest <Name>[,<Name>...]`"
    result = await _sentinel_client.post_to_module(
        "modules/pathfinder/harvest",
        {"names": names, "user_id": user_id},
        http_client,
    )
    return {
        "type": "embed",
        "content": "",
        "embed": build_harvest_embed(result),
    }
```

**Notes on integration with existing error handling:** The existing `except httpx.HTTPStatusError/ConnectError/TimeoutException` block at the bottom of `_pf_dispatch` (around lines 595-615 per PATTERNS.md §9 Gotcha 2) already covers all upstream errors. Do NOT add new except arms — the harvest branch raises the same exceptions the npc branches do.

**Notes on `http_client`:** The dispatch chain passes `http_client` through the call to `post_to_module`. Verify via `grep -n 'post_to_module' interfaces/discord/bot.py` that the existing pattern is `await _sentinel_client.post_to_module(path, payload, http_client)` — if the signature varies (some existing calls may use `http_client=...`), match the exact calling convention for the harvest branch.

**Smoke test**:
```bash
cd interfaces/discord && uv run --no-sync python -c "
import asyncio
from unittest.mock import AsyncMock, patch
import bot

# build_harvest_embed — pure-fn smoke (no actual Embed render; test stub sets discord.Embed = object-ish)
data = {
    'monsters': [{'monster': 'Boar', 'level': 2, 'source': 'seed', 'verified': True, 'components': [], 'note': None}],
    'aggregated': [{'type': 'Hide', 'medicine_dc': 16, 'craftable': [{'name': 'Leather armor', 'crafting_dc': 14, 'value': '2 gp'}], 'monsters': ['Boar']}],
    'footer': 'Source — FoundryVTT pf2e',
}
embed = bot.build_harvest_embed(data)
# In tests the discord stub may make Embed un-introspectable; at minimum the function runs without exception.
assert embed is not None

# Dispatch smoke — single monster
async def run():
    mock_result = {
        'monsters': [{'monster': 'Boar', 'level': 2, 'source': 'seed', 'verified': True, 'components': [], 'note': None}],
        'aggregated': [],
        'footer': 'Source — FoundryVTT pf2e',
    }
    with patch.object(bot._sentinel_client, 'post_to_module', new=AsyncMock(return_value=mock_result)) as mock_ptm:
        result = await bot._pf_dispatch('harvest Boar', 'user123')
    assert mock_ptm.call_args[0][0] == 'modules/pathfinder/harvest'
    payload = mock_ptm.call_args[0][1]
    assert payload['names'] == ['Boar']
    assert result['type'] == 'embed'

asyncio.run(run())

# Dispatch smoke — multi-word name
async def run2():
    with patch.object(bot._sentinel_client, 'post_to_module', new=AsyncMock(return_value={'monsters': [], 'aggregated': [], 'footer': ''})) as m:
        await bot._pf_dispatch('harvest Giant Rat', 'user123')
    assert m.call_args[0][1]['names'] == ['Giant Rat'], m.call_args[0][1]

asyncio.run(run2())

# Dispatch smoke — comma with whitespace
async def run3():
    with patch.object(bot._sentinel_client, 'post_to_module', new=AsyncMock(return_value={'monsters': [], 'aggregated': [], 'footer': ''})) as m:
        await bot._pf_dispatch('harvest Boar , Wolf , Orc', 'user123')
    assert m.call_args[0][1]['names'] == ['Boar', 'Wolf', 'Orc'], m.call_args[0][1]

asyncio.run(run3())

# Empty harvest returns usage
async def run4():
    with patch.object(bot._sentinel_client, 'post_to_module', new=AsyncMock(side_effect=AssertionError('should not be called'))) as m:
        out = await bot._pf_dispatch('harvest', 'user123')
    assert isinstance(out, str)
    assert 'Usage' in out and 'harvest' in out

asyncio.run(run4())

print('OK')
"
```

**Run the 7 harvest bot-layer tests:**
```bash
cd interfaces/discord && uv run --no-sync python -m pytest tests/test_subcommands.py -k 'harvest' -v
# Expected: 7 passed
```

**Verify no regressions in existing Phase 29/30/31 bot tests:**
```bash
cd interfaces/discord && uv run --no-sync python -m pytest tests/ -q
# Expected: all green
```
  </action>
  <acceptance_criteria>
    - grep -E '^def build_harvest_embed\(' interfaces/discord/bot.py matches
    - grep -F 'modules/pathfinder/harvest' interfaces/discord/bot.py matches
    - grep -F 'build_harvest_embed(result)' interfaces/discord/bot.py matches (branch uses the helper)
    - grep -F 'if noun not in {"npc", "harvest"}:' interfaces/discord/bot.py matches
    - grep -F 'Currently supported: `npc`, `harvest`.' interfaces/discord/bot.py matches
    - grep -F 'Usage: `:pf npc <create|update|show|relate|import|say> ...`' interfaces/discord/bot.py matches (preserved from Phase 31)
    - grep -F ':pf harvest <Name>[,<Name>...]' interfaces/discord/bot.py matches (new usage extension)
    - grep -F 'discord.Color.dark_green()' interfaces/discord/bot.py matches (harvest embed color)
    - grep -F '⚠ Generated — verify against sourcebook' interfaces/discord/bot.py matches (single-monster warning text)
    - grep -F '[:1024]' interfaces/discord/bot.py matches (Discord field cap enforcement)
    - Warning 3 F401 sanity: no new `import` lines added by this task's 4 Edits — the executor inspects the diff and confirms `build_harvest_embed` uses only pre-existing imports (`discord`, which is already at the top of bot.py). If the diff shows a new `import` line, remove it — do NOT suppress with `# noqa: F401`.
    - Warning 4 comment present: `grep -F 'zero args is caught by the generic' interfaces/discord/bot.py` matches (the early-return interaction note lives inside the harvest branch)
    - All 7 harvest bot tests pass: `cd interfaces/discord && uv run --no-sync python -m pytest tests/test_subcommands.py -k harvest -q` exit 0
    - No regression: `cd interfaces/discord && uv run --no-sync python -m pytest tests/ -q` exit code 0
    - Smoke test exits 0 with OK
    - grep -v '^#' interfaces/discord/bot.py | grep -E '(TODO|FIXME|NotImplementedError|raise NotImplementedError)' returns 0 NEW matches in lines added by this task
  </acceptance_criteria>
  <automated>cd interfaces/discord && uv run --no-sync python -m pytest tests/test_subcommands.py -k harvest -q && uv run --no-sync python -m pytest tests/ -q</automated>
</task>

</tasks>

<verification>
End-of-Phase-32 gate (after this plan completes the bot wiring):

```bash
# 1. Bot tests all green (7 new + existing)
cd interfaces/discord && uv run --no-sync python -m pytest tests/ -q
# Expected: all green

# 2. Module tests still green
cd modules/pathfinder && uv run python -m pytest tests/ -q
# Expected: all green (20 harvest unit + 3 integration + Phase 29/30/31 unbroken)

# 3. Full Phase 32 contract verification
cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py -v
# Expected: 20 passed
cd modules/pathfinder && uv run python -m pytest tests/test_harvest_integration.py -v
# Expected: 3 passed
cd interfaces/discord && uv run --no-sync python -m pytest tests/test_subcommands.py -k harvest -v
# Expected: 7 passed

# 4. Help text + usage string include `harvest`
grep -F 'harvest <Name>[,<Name>...]' interfaces/discord/bot.py && echo "PASS — harvest usage" || echo "FAIL"
grep -F 'Currently supported: `npc`, `harvest`' interfaces/discord/bot.py && echo "PASS — noun list" || echo "FAIL"

# 5. Cache write path uses GET-then-PUT (D-03b + memory invariant) — module-side regression guard
grep -F 'patch_frontmatter_field' modules/pathfinder/app/routes/harvest.py && echo "FAIL — PATCH in harvest handler" || echo "PASS"

# 6. REGISTRATION_PAYLOAD has 13 routes
cd modules/pathfinder && uv run python -c "from app.main import REGISTRATION_PAYLOAD; print('routes:', len(REGISTRATION_PAYLOAD['routes']))"
# Expected: routes: 13

# 7. Manual smoke test checklist (from 32-VALIDATION.md Manual-Only):
#    Run sentinel.sh up, then in Discord:
#      :pf harvest Boar
#      :pf harvest Boar,Wolf,Orc
#      :pf harvest Barghest    # out of seed → LLM fallback with verified:false
#      :pf harvest 'Wolf Lord' # fuzzy below cutoff → LLM fallback
#      :pf harvest 'Alpha Wolf' # fuzzy above cutoff → seed Wolf + note
#    Open mnemosyne/pf2e/harvest/barghest.md and verify frontmatter has verified: false.
```

After all 7 gates pass, update 32-VALIDATION.md frontmatter `wave_0_complete: true` AND mark Phase 32 ready for `/gsd-verify-work`.
</verification>

<success_criteria>
- All 7 bot-layer tests pass.
- All 20 module-layer unit tests + 3 integration tests still pass.
- Existing Discord tests (Phase 26-31) not regressed.
- `harvest` verb is dispatchable from `:pf harvest` in Discord.
- Top-level usage string + unknown-noun error both include `harvest`.
- Noun-widening is a strict set check (regression guard via `test_pf_harvest_noun_recognised`).
- Comma-separated batch with whitespace trim works; multi-word names preserved.
- Embed rendering matches D-03a; footer source attribution present; D-04 aggregated-by-component display.
- HRV-01..06 satisfied end-to-end (HTTP + Discord).
- AI Deferral Ban: zero TODO/FIXME/NotImplementedError introduced in bot.py changes.
</success_criteria>

<output>
Create `.planning/phases/32-monster-harvesting/32-05-SUMMARY.md` documenting:
- Files modified: interfaces/discord/bot.py — added build_harvest_embed helper, widened noun-check to {npc, harvest}, added harvest dispatch branch, updated top-level usage string
- Test results: 7 harvest bot tests + 20 module unit + 3 integration all green
- Documented deferred items (carried forward from CONTEXT Deferred Ideas): Medicine-check roll simulation (Phase 33), inventory tracking (future), crafting timelines (future), rules-engine integration for harvesting (Phase 33), session-log append of harvest events (Phase 34)
- Documented limitation (RESEARCH Pitfall 7): seed-level-locking when fuzzy-matched variant is higher level than seed — DM must adjust DC mentally for now; v2 could accept `:pf harvest Wolf/5` level override
- Manual smoke test checklist (5 items per 32-VALIDATION.md Manual-Only) — for human to run after deployment
- Note: Phase 32 ready for `/gsd-verify-work`. Run `/gsd-verify-work 32` next.
- Worktree note per S9: commit with `--no-verify` in parallel worktrees.
</output>
