---
status: pending
phase: 33-rules-engine
task: 33-05-06 (checkpoint:human-verify — in-Discord visual)
parent_uat: .planning/phases/33-rules-engine/33-UAT-RESULT.md
prerequisites: live UAT 17/17 PASS (33-UAT-RESULT.md status=resolved)
---

# Phase 33 — Discord Visual UAT Walkthrough

This is the operator-only verification gate that the live UAT script cannot reach.
Tests the rendering layer (Discord embed colors, fonts, banners), the D-11
placeholder-edit UX (which only manifests in real DM round-trips, not in HTTP
test clients), and the on-disk D-13/D-14 frontmatter as the human reads it.

**Stack precondition:** all 4 containers running fresh Phase 33 code (verified
during this session — pf2e-module image rebuilt at commit 50ef0f7 + restarted).

**Vault precondition:** `mnemosyne/pf2e/rulings/` exists in Obsidian. If you
already ran the live UAT today, this folder may have leftover cache files —
they were cleaned up by the UAT teardown step, but verify in Obsidian that
the directory is empty before starting fresh checks.

**How to use this checklist:** Open this file in your editor on one screen,
Discord on another. For each step, type the command in your `:pf` channel (or
DM with the bot), inspect the response, and tick the box. If a check fails,
note the failure inline and stop — most failures cascade.

---

## Section A — Source-path rendering (UAT-1 visual equivalent)

Tests the green-embed source-citation path. Pre-warm the chat model first by
sending one quick message so cold-start doesn't pollute the timing observation.

### A1. Pre-warm chat model
- [ ] Send any throwaway message in the channel (e.g. `:pf help` or just `hi`)
- **Expected:** something — anything — comes back. Ignore the content.
- **Why:** the first LLM call after container restart triggers model load
  in LM Studio (~30s). Pre-warming separates that from the timing of A2.

### A2. Source-cited ruling — green embed
- [ ] Type: `:pf rule What does the off-guard condition do?`
- **Expected:**
  - Within ~1 second, a placeholder message appears: `:hourglass: Looking up rules...` (or similar)
  - Within ~5-15 seconds, that **same message** is edited to show an embed
  - **Embed color: green**
  - **Embed title:** the question text
  - **Embed body:** a short answer + reasoning ("why")
  - **Footer / source field:** `Pathfinder Player Core` with a section name (and a page number if the chunk had one)
  - **No banner text** like `[GENERATED — verify]`
  - **Citations field** populated with at least one citation entry — possibly with an Archives of Nethys URL if `aon-url-map.json` had a match
- **Fail signals:**
  - Placeholder shows but never edits → check `pf2e-module` logs for LLM timeout
  - Embed is yellow with `[GENERATED — verify]` → corpus retrieval missed (cosine < 0.65)
  - Embed has no source field → bot's `build_ruling_embed` not rendering D-08 properly

### A3. Verify Obsidian frontmatter (D-13 + D-14)
- [ ] Open Obsidian, navigate to `mnemosyne/pf2e/rulings/off-guard/`
- [ ] You should see one new file with an 8-char-hex name (e.g. `a3f7c2e1.md`)
- [ ] Open it and inspect the YAML frontmatter
- **Expected fields:**
  - `question:` matches what you typed
  - `answer:` matches the embed body
  - `marker: source`
  - `topic: off-guard`
  - `composed_at: 2026-04-25T...` (ISO timestamp, today)
  - `last_reused_at: 2026-04-25T...` (same as composed_at on first write)
  - `embedding_model: text-embedding-nomic-embed-text-v1.5`
  - `embedding_hash:` 40-char hex string
  - `query_embedding:` long base64 string (the float32 query vector)
  - `citations:` list with at least one `book: Pathfinder Player Core` entry
- **Fail signals:**
  - File is missing → check `pf2e-module` logs for an Obsidian PUT error
  - `last_reused_at` ≠ `composed_at` on a fresh write → bug in route's frontmatter builder

---

## Section B — Generated-path rendering (UAT-3 visual equivalent)

Tests the yellow-embed `[GENERATED — verify]` path. Use a query the corpus
won't have a clean match for.

### B1. Generated ruling — yellow embed + banner
- [ ] Type: `:pf rule Can a Kineticist's impulse crit on a save DC check?`
- **Expected:**
  - Placeholder → edit pattern same as A2
  - **Embed color: yellow** (Discord renders this as gold/amber)
  - **Banner text** present somewhere prominent: `[GENERATED — verify]` or similar
  - **Source field:** absent or marked as "no source — generated"
  - **Citations:** empty array or omitted entirely (D-12: never fabricate URLs)
- **Fail signals:**
  - Embed is green and cites a source → false-positive corpus hit; check threshold
  - No banner → bot's marker-color branching is wrong

### B2. Verify Obsidian write
- [ ] Open `mnemosyne/pf2e/rulings/<topic>/` (whatever topic the LLM classified — likely `misc` or `spellcasting`)
- [ ] New file present
- [ ] Frontmatter has `marker: generated` and **empty `citations: []`**

---

## Section C — Decline-path rendering (UAT-4/5 visual equivalent)

Tests the red-embed PF1-decline path. Critical that NO cache file is written
on declined queries (D-06 hard rule).

### C1. PF1 decline — red embed
- [ ] **Note the current contents of `mnemosyne/pf2e/rulings/`** before typing
  (count the topic folders — you'll verify nothing was added after)
- [ ] Type: `:pf rule What is THAC0?`
- **Expected:**
  - Response within ~1 second (no LLM call — PF1 denylist short-circuits at the route)
  - **Embed color: red**
  - **Embed body** starts with: `This Sentinel only supports PF2e Remaster (2023+).`
  - **Mentions** the trigger term (`THAC0`) and points to AoN 1e
  - **No source citations**
- **Fail signals:**
  - Response takes >5s → PF1 denylist isn't matching, route is calling LLM
  - Embed isn't red → marker-color branching wrong
  - Apology language ("Sorry, I can't...") → D-07 wording broke

### C2. NO cache write (D-06 hard rule)
- [ ] Refresh Obsidian's file tree
- [ ] Confirm `mnemosyne/pf2e/rulings/` topic folder count is **identical** to before C1
- [ ] No new file with `marker: declined` exists anywhere
- **Fail signals:**
  - Any new file appeared → route is writing cache for declined queries (regression — see UAT-4 in 33-UAT-RESULT.md)

### C3. Soft-trigger discrimination (UAT-6 visual)
- [ ] Type: `:pf rule My character is flat-footed after being tripped — what's the penalty?`
- **Expected:**
  - **NOT declined** even though "flat-footed" appears (Player Core renamed it to "off-guard"; the soft trigger is a query about combat state, not a PF1 reference)
  - Embed is green or yellow (source or generated), not red
- **Fail signals:**
  - Red decline embed → PF1 regex over-fires; check `app/rules.py` denylist

---

## Section D — Cache-hit + reuse-match (UAT-7/8 visual)

Tests both fast paths: identical-query exact-hash hit (sub-second), and
paraphrase reuse-match cosine hit (D-05 calibrated 0.70).

### D1. Identical-query exact-hash cache hit
- [ ] Re-type **exactly** the A2 query: `:pf rule What does the off-guard condition do?`
- **Expected:**
  - Response within ~1 second (no LLM call — exact sha1 hash match)
  - **Embed identical to A2** (same question, answer, why, citations)
  - **`reused: true` field** somewhere visible — the bot may render this as
    an italic line or a small footer field (per D-05 wording: `_reusing prior
    ruling on <topic> — confirm applicability_`)
- **Fail signals:**
  - Response takes >5s → exact-hash cache lookup isn't firing; check route logs

### D2. Paraphrase reuse-match (the UAT-8 case — newly fixed in Phase 33.1)
- [ ] Type a paraphrase: `:pf rule What's the AC penalty for being off-guard?`
- **Expected:**
  - Response within ~1-2 seconds (still no LLM call — cosine hit on the cached A2 ruling)
  - **Embed body** ≈ same answer as A2 (same source citation)
  - **Italic reuse line** present: something like `_reusing prior ruling on
    off-guard — confirm applicability_`
- **Fail signals:**
  - Embed shows fresh ruling (no italic note) and took 5-15s → cosine fell
    below 0.70; check the actual cosine via the logs (`pf2e-module` writes
    `INFO ... reuse-match` log lines with similarity scores)
  - Note: in Phase 33.1 calibration, this kind of paraphrase pair averaged
    0.79; if you're seeing <0.70 in real usage, that's a calibration data
    point worth flagging

### D3. Verify D-14 last_reused_at update
- [ ] Open the SAME Obsidian file from A3 (the `off-guard/<sha>.md` file)
- [ ] Refresh the file (Obsidian may need explicit reload — `Cmd+R` or
  click out and back in)
- [ ] Compare `composed_at` and `last_reused_at`
- **Expected:**
  - `composed_at` UNCHANGED from A3
  - `last_reused_at` is **later than `composed_at`** by however many minutes
    elapsed between A2 and D2 — this is the D-14 GET-then-PUT update on cache hit
- **Fail signals:**
  - `last_reused_at` unchanged → route's D-14 update path is broken (regression
    against the L-3 PATCH-replace fix)
  - File is corrupted / has no frontmatter → catastrophic, check route logs

---

## Section E — Sub-verbs (UAT-12/13 visual)

Tests the three enumeration endpoints (no LLM, pure Obsidian directory walks).

### E1. `:pf rule show <topic>`
- [ ] Type: `:pf rule show off-guard`
- **Expected:**
  - Response within ~1 second
  - **Plain message text** (not a fancy embed) listing the rulings under
    `off-guard/` topic — should include the file from A2/D2
  - Format roughly: `**Rulings under \`off-guard\`** (N):\n• \`a3f7c2e1\` — What does the off-guard condition do? [source]`
- **Fail signals:**
  - Response is an embed → bot's sub-verb branching wrong
  - Empty list when files exist → Obsidian list_directory not finding the topic folder

### E2. `:pf rule history [N]`
- [ ] Type: `:pf rule history` (no number — defaults to 10)
- **Expected:**
  - Plain message text listing recent rulings across all topics, sorted by `last_reused_at` desc
  - Should include entries from A2, B1, D1 in that approximate order (most recent first)
  - Format roughly: `**Recent rulings (N=10):**\n• 2026-04-25T... — \`off-guard/What does the off-guard condition do?\` [source]`
- [ ] Type: `:pf rule history 3`
- **Expected:** same format, capped at 3 entries
- **Fail signals:**
  - More than 50 entries returned for `history 100` → bot/backend isn't
    clamping to 50 (IN-03 fix didn't take effect — check commit 6a44f56)

### E3. `:pf rule list`
- [ ] Type: `:pf rule list`
- **Expected:**
  - Plain message text listing TOPIC FOLDERS (not individual rulings) under `mnemosyne/pf2e/rulings/`
  - Should include `off-guard`, `misc` or `spellcasting` (whatever B1 classified to), and probably `flanking` from earlier
  - Each topic shows a count of rulings within
- **Fail signals:**
  - Returns individual rulings instead of topic folders → bot's list-vs-show wires crossed

---

## Section F — D-15 scope-lock visual (UAT-14 visual equivalent)

Tests that Monster Core queries flow through `[GENERATED — verify]`, NOT
through `[DECLINED]`. D-15 is the most-litigated decision in CONTEXT.md and
worth eyeballing.

### F1. Monster-Core query → yellow generated, NOT red declined
- [ ] Type: `:pf rule How do I run an Aboleth Mucus save?`
- **Expected:**
  - **Embed color: yellow** (generated)
  - **Banner:** `[GENERATED — verify]`
  - **NOT** a red decline embed (Monster Core is an "advanced book" per D-15
    Player-Core-MVP scope, but advanced-book queries flow through fallback
    composition — they're not PF1, just out of corpus scope)
- **Fail signals:**
  - Red decline embed → PF1 denylist over-fires on Monster Core terms (regression)
  - Empty / no response → route's fallback path broke

---

## Section G — Cleanup (don't skip)

Leaving 8+ test cache files in your real Obsidian vault is annoying. Clean up.

### G1. Delete test cache files
- [ ] In Obsidian, navigate to `mnemosyne/pf2e/rulings/`
- [ ] Delete the topic folders you generated during this checklist:
  - `off-guard/`
  - whatever B1 generated (likely `misc/` or `spellcasting/`)
  - `dying/`, `flanking/`, etc., if any other UAT runs left files
- [ ] Verify `mnemosyne/pf2e/rulings/` is empty (or contains only your real
  prior rulings if you've used `:pf rule` before)

### G2. Mark this checklist resolved
- [ ] Edit the frontmatter of this file: change `status: pending` → `status: resolved`
- [ ] Add a `completed:` ISO timestamp
- [ ] If anything failed: leave `status: failed` and create a debug session
  via `/gsd-debug` for the specific failure

---

## Section H — When you're done

- [ ] If A through F all PASS:
  - Phase 33 is **fully complete**: 142/142 pytest + 17/17 live UAT + Discord visual confirmed
  - Update `.planning/STATE.md` to mark Phase 33 fully verified
  - Commit + push: `docs(phase-33): mark Discord visual UAT complete`
  - Phase 33 closes; v0.5 milestone advances to 6/9 (after 33 closes)
- [ ] If anything failed:
  - Note the specific section + step in this file inline
  - Run `/gsd-debug "Phase 33 Discord visual: <section.step> failed: <symptom>"` to start a debug session
  - The container stack is left running with Phase 33 + 33.1 code, so debug can hit the live route directly

---

## Reference: where each check maps to a Phase 33 design decision

| Section | Decisions tested | Lints tested |
|---------|------------------|--------------|
| A | D-08 (response shape), D-09 (citation format), D-12 (URL honesty), D-13 (frontmatter embedding metadata), D-14 (last_reused_at) | L-3 (no PATCH), L-7 (proxy path) |
| B | D-08, D-12 (no citations on generated) | — |
| C | D-06 (PF1 denylist), D-07 (decline message) | — |
| D | D-05 (reuse threshold = 0.70 calibrated), D-14 (last_reused_at update) | L-3 (GET-then-PUT) |
| E | D-10 (4 sub-verbs) | — |
| F | D-15 (scope-lock — Monster Core generates, not declines) | L-1 (advanced-book fallback) |
| G | (cleanup) | — |

This checklist is the operator's read-receipt for the entire D-XX/L-XX
locked-decision matrix in `33-CONTEXT.md`. Every box ticked = one
decision verified end-to-end against real LLM + real Obsidian + real Discord.
