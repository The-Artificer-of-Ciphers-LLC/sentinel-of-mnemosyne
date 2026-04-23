# Phase 31: Dialogue Engine — Discussion Log

**Session:** 2026-04-23
**Workflow:** `/gsd-discuss-phase 31` (default mode)
**Outcome:** 4/4 selected gray areas resolved; CONTEXT.md written.

---

## Gray Area Selection

**Question:** Which areas do you want to discuss for Phase 31: Dialogue Engine?

**Options presented:**
- ☐ Command syntax + scene form — verb under `:pf`, separator, scene form, reply shape
- ☐ Mood state machine — enum, shift trigger, shift granularity
- ☐ Conversation memory — stateless vs thread-context vs vault-persistent
- ☐ Scene orchestration — independent vs conversational, max NPCs

**User selected:** All four.

---

## Area 1: Command Syntax + Reply Shape

**Q1 — Command surface:** How should the `:pf` command look for single-NPC and multi-NPC dialogue?

**Options:**
- Two verbs: `say` + `scene`
- **One verb, N names** (selected) — `:pf npc say Varek | …` | `:pf npc say Varek,Baron | …`
- Promote to `:pf say` (breaks `:pf <noun> <verb>` pattern)

**Decision:** Single verb. Bot splits NPC list on comma. Consistent with existing `:pf npc <verb>` pattern from Phases 29 & 30.

**Q2 — Reply shape:** How should the NPC's reply be rendered in Discord?

**Options:**
- **Plain quoted text** (selected, recommended) — `> *action.* "reply"`
- Discord embed per NPC
- Embed only when mood changes

**Decision:** Plain quoted markdown. Easy to copy into session notes. For scenes, one message with multiple quote blocks stacked in order.

---

## Area 2: Mood State Machine

**Q1 — Mood enum:** What's the set of mood states an NPC can be in?

**Options:**
- **5-state spectrum** (selected, recommended) — `hostile → wary → neutral → friendly → allied`
- 3-state (hostile/neutral/friendly)
- Free-text + tag

**Decision:** Ordered 1D spectrum of exactly five values. Single-step shifts per interaction.

**Q2 — Shift trigger:** When does mood get re-evaluated and written back?

**Options:**
- Every dialogue turn via LLM
- **Only on salient events** (selected, recommended) — LLM returns `{reply, mood_delta: -1 | 0 | +1}`, write only when non-zero
- Manual `:pf npc mood <name> <state>`

**Decision:** Same LLM call returns `mood_delta`. Vault write skipped on zero-delta turns (most flavor chatter leaves mood alone). Clamp at endpoints.

---

## Area 3: Conversation Memory

**Q1 — Memory scope:** How much does the NPC remember across dialogue turns?

**Options:**
- Stateless per turn
- **Thread-scoped memory** (selected, recommended) — bot walks current Discord thread, filters prior `:pf npc say` turns, feeds as history
- Vault-persistent log
- Session-note log + thread mem (Phase 34 territory)

**Decision:** Thread-scoped. No vault writes for dialogue history — the Discord thread IS the session log. Mood persists in frontmatter; conversation does not persist beyond thread lifecycle. Token-budget cap is Claude's discretion.

---

## Area 4: Scene Orchestration

**Q1 — Scene interaction mode:** In a multi-NPC scene, how should NPCs interact?

**Options:**
- Parallel replies to party (recommended in prompt)
- Sequential with awareness
- **Round-robin with conversation** (selected) — NPCs reply in given order; each subsequent NPC sees prior NPCs' replies this turn; NPCs can address each other; future turns can continue without party input

**Decision:** Round-robin with awareness. Ambitious choice — user opted for the richest roleplay model. Serial LLM calls; no parallelism (each NPC's context depends on the previous NPC's reply this turn).

**Q2 — Scene limit:** What's the max NPC count for v1?

**Options:**
- 2 NPCs (matches ROADMAP literal)
- Up to 4 NPCs
- **No hard limit, warn >4** (selected)

**Decision:** No hard cap. Prepend a ⚠ warning line to the reply when ≥5 NPCs. Token usage and latency grow linearly — user responsibility above the soft cap.

**Q3 — Scene advance without party input:** How should the DM let NPCs continue talking without the party speaking?

**Options:**
- **Empty text after pipe** (selected, recommended) — `:pf npc say Varek,Baron |`
- Explicit verb `:pf npc continue …`
- Not supported in v1

**Decision:** Empty payload after pipe = scene advance. Bot detects empty/whitespace-only text and sends "the party is silent; continue the scene" framing to the LLM. Zero new syntax.

---

## Scope Redirects

None raised during discussion. User stayed in scope.

---

## Claude's Discretion

Captured in CONTEXT.md §Claude's Discretion. Key items:
- Exact tone-guidance prompt wording per mood state
- Exact scene-advance framing
- Token budget cap for thread-history inclusion
- Discord `Thread.history()` limit / filtering logic
- Whether to use a new `app/dialogue.py` module vs extending `app/llm.py`

---

## Ambition Note

The combination of D-06 (round-robin with conversation), D-20 (scene advance with empty payload), and D-18 (soft-cap at 4 with no hard limit) makes Phase 31 the most complex dialogue implementation feasible within the existing architecture. The planner should flag if research surfaces a simpler path that still satisfies the success criteria, so the user can reconsider before plans lock.
