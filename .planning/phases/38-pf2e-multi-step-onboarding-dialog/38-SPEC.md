# Phase 38: PF2E Multi-Step Onboarding Dialog — Specification

**Created:** 2026-05-08
**Ambiguity score:** 0.13 (gate: ≤ 0.20)
**Requirements:** 7 locked

## Goal

`:pf player start` with no args creates a Discord thread that walks the player through three questions (character name, preferred name, style preset), collects answers from plain-text replies in that thread, then calls `/player/onboard` with the assembled payload — replacing the temporary pipe-separated workaround as the primary onboarding path.

## Background

Phase 37 shipped `/player/onboard` as an atomic four-field POST (`user_id`, `character_name`, `preferred_name`, `style_preset`) and `PlayerStartCommand` posting `{user_id}` only. Live `:pf player start` therefore returned 422 from the route until commit `2026-05-07` mitigated by parsing pipe-separated args (`character_name | preferred_name | style_preset`) — see `interfaces/discord/pathfinder_player_adapter.py:30-71`. 37-CONTEXT.md line 129 originally specified that until `profile.md` shows `onboarded: true`, all `:pf player <verb>` other than `start`/`style` should redirect into onboarding completion. That redirect is missing today, and the pipe-separated UX is operator-grade rather than player-grade.

`bot.py:668` guards `on_message` to fire **only inside Discord threads** the bot owns. Plain-text replies in regular channels never reach the dispatcher, which constrains where a multi-step dialog can live. The Sentinel vault (Obsidian REST API) is the only persistence layer in this stack — there is no Redis, no SQLite, no in-process state store outside the request lifecycle.

## Requirements

1. **Thread-hosted dialog**: `:pf player start` with no args creates a Sentinel-owned thread for the dialog.
   - Current: `:pf player start` with no args returns a usage string in the channel where invoked
   - Target: With no args, `:pf player start` creates a public thread named `Onboarding — <discord display name>` off the invoking channel, posts the first question (`What is your character's name?`) in that thread, and registers the thread in `SENTINEL_THREAD_IDS` so `on_message` will route subsequent replies through `_route_message`
   - Acceptance: Live test — `:pf player start` in a channel with no draft creates a new thread; the thread's first message is the character-name prompt; the thread's `owner_id` is the bot

2. **Plain-text answer capture**: Player replies in the onboarding thread are interpreted as answers, not as new commands.
   - Current: Plain text in a Sentinel thread is routed to `_route_message` which calls the AI; there is no draft-state lookup
   - Target: When a plain-text message arrives in a thread that has a matching draft file, the message is consumed as the answer to the draft's `step` field; the draft advances to the next step or completes; the AI is NOT invoked for the message
   - Acceptance: With a draft at step `character_name`, replying `Kaela` in the thread updates the draft frontmatter `character_name: Kaela`, advances `step: preferred_name`, and posts the next question. The router does not call `_call_core` or the AI for that message.

3. **Vault-backed draft persistence**: Onboarding drafts survive bot restart indefinitely until completion or cancel.
   - Current: No transient state store exists
   - Target: Each draft is a markdown file at `mnemosyne/pf2e/players/_drafts/{thread_id}-{user_id}.md` with frontmatter `step`, `thread_id`, `user_id`, `character_name?`, `preferred_name?`, `started_at`. Created by `:pf player start`, mutated by each answer, deleted on `complete` or `:pf player cancel`. (Strict superset of Phase 37 ROADMAP criterion "transient state survives bot restart for at least 24h" — the vault file lives until cancelled.)
   - Acceptance: Stop the bot mid-dialog (after one answer); restart; reply with the next answer in the same thread; the draft frontmatter reflects both answers and the dialog completes correctly. The draft file appears in the vault on first answer and is deleted by completion.

4. **Completion calls existing route**: When all three answers are collected, the existing `/player/onboard` POST is invoked unchanged.
   - Current: `PlayerStartCommand` (pipe-syntax path) calls `request.sentinel_client.post_to_module("modules/pathfinder/player/onboard", payload, ...)` with the four-field payload
   - Target: After the third answer is captured, the dialog assembles the same four-field payload (`user_id`, `character_name`, `preferred_name`, `style_preset`) and POSTs to the same route. The route is not modified by this phase.
   - Acceptance: After completing the dialog with `character_name=Kaela`, `preferred_name=K`, `style_preset=Lorekeeper`, `mnemosyne/pf2e/players/k/profile.md` exists with `onboarded: true` and the three captured fields in frontmatter — identical to the pipe-syntax outcome.

5. **Mid-dialog command rejection**: Other `:pf player <verb>` commands issued by a player with a live draft are rejected with an actionable message.
   - Current: `:pf player note "foo"` mid-onboarding succeeds and writes to a non-existent profile, leaving the vault in an inconsistent state
   - Target: When a player has any open draft, attempting `:pf player {note,ask,npc,recall,todo,style,canonize}` returns a text response: `You have an onboarding dialog open in <thread_link>. Reply there to continue, or run :pf player cancel to abort.` No call to the underlying route is made.
   - Acceptance: Create a draft in thread A; from any channel, run `:pf player note "test"`; assert the response text matches the rejection template, links to thread A, and `notes.md` is unchanged.

6. **Cancel is explicit**: `:pf player cancel` removes the draft and lets the player start fresh.
   - Current: No `cancel` verb exists
   - Target: New `PlayerCancelCommand` registered in the dispatcher. With no draft for `(thread_id, user_id)`, returns `No onboarding dialog in progress.` With a draft, deletes the draft file via Obsidian DELETE, and replies `Onboarding cancelled. Run :pf player start to begin again.`
   - Acceptance: Create a draft; run `:pf player cancel` in the dialog thread; the draft file is gone from the vault; the next `:pf player start` from the same user in the same channel creates a brand-new thread + draft.

7. **Restart-start resumes**: Running `:pf player start` (no args) when a draft already exists in the same thread replays the next unanswered question.
   - Current: There is no draft model — every invocation acts as a fresh start
   - Target: `:pf player start` checks for `mnemosyne/pf2e/players/_drafts/{thread_id}-{user_id}.md`; if present, posts the prompt for the draft's current `step` instead of creating a new thread or starting over. Existing answers are preserved.
   - Acceptance: Answer the first question; run `:pf player start` again in the same thread; the bot re-posts the second question (preferred name), not the first; previously captured `character_name` is unchanged.

## Boundaries

**In scope:**
- New thread creation on no-arg `:pf player start`
- Draft file CRUD against `mnemosyne/pf2e/players/_drafts/`
- Plain-text answer capture inside a draft-bearing thread (modification to message routing in `bot.py` and/or `command_router.py`)
- New `PlayerCancelCommand`
- Mid-dialog rejection guard for the seven non-`start`/`cancel` verbs
- Resume-on-restart-start behaviour
- Wave-0 RED tests for every new behaviour (TDD)

**Out of scope:**
- Modifying the `/player/onboard` route schema or behaviour — Phase 37 already shipped it; reuse unchanged
- Configurable question text or i18n — questions are fixed strings shipped in code
- Editing an already-onboarded profile — that is a future verb, not part of onboarding
- Slash-command modal alternative (single Discord modal with three fields) — explicitly rejected in Round 2 because it isn't multi-step conversational
- Listening to plain text in non-thread channels — explicitly avoided to keep `on_message` blast radius unchanged
- 24h hard expiry of drafts — drafts persist until `:pf player cancel`; this is a strict superset of the Phase 37 ROADMAP "at least 24h" wording, not a regression
- Replacing the pipe-separated one-shot syntax — `:pf player start a | b | c` continues to work unchanged, regression-tested

## Constraints

- The dialog MUST run inside a Sentinel-owned thread (`bot.py` `on_message` only fires there, line 668-669). Solutions that require listening outside threads are out of scope.
- Draft files MUST live under `mnemosyne/pf2e/players/_drafts/` so they remain inside the player vault hierarchy and are subject to the same per-player isolation guarantees as Phase 37 PVL-07.
- The `(thread_id, user_id)` composite key is canonical. The same user MAY have concurrent drafts in different threads — drafts are per-thread, not per-user.
- The mid-dialog rejection MUST NOT call the underlying route — no side-effect on `notes.md`, `questions.md`, `npc-knowledge.md`, etc.
- The onboarding thread becomes a regular Sentinel thread *after* completion — subsequent plain-text replies fall through to the normal AI path, not the draft path.
- Pre-existing pipe-syntax path (`:pf player start a | b | c`) MUST remain functional for at least Phase 38 — no removal, no deprecation warning yet.

## Acceptance Criteria

- [ ] `:pf player start` with no args creates a new thread and posts the character-name prompt as its first message
- [ ] A plain-text reply in a draft-bearing thread updates the draft and posts the next prompt; the AI is not invoked
- [ ] Bot restart between answers preserves the draft; resuming with the next answer completes correctly
- [ ] After all three answers, `mnemosyne/pf2e/players/{slug}/profile.md` exists with `onboarded: true` and matches the pipe-syntax outcome byte-for-byte (modulo `started_at`/`onboarded_at` timestamps)
- [ ] Mid-dialog `:pf player note|ask|npc|recall|todo|style|canonize` returns the rejection template and does NOT mutate the vault
- [ ] `:pf player cancel` with a draft deletes the draft file and replies with the cancel-acknowledgement message
- [ ] `:pf player cancel` with no draft replies `No onboarding dialog in progress.` and does nothing
- [ ] `:pf player start` re-issued in a thread with an in-flight draft re-posts the prompt for the current `step` and does NOT reset prior answers
- [ ] `:pf player start a | b | c` (pipe syntax) regression: produces the same `profile.md` it did before this phase, with no thread created
- [ ] Wave-0 RED tests exist for every requirement above and were written and committed BEFORE the implementation that makes them pass

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                              |
|--------------------|-------|------|--------|----------------------------------------------------|
| Goal Clarity       | 0.92  | 0.75 | ✓      | 7 locked, falsifiable requirements                 |
| Boundary Clarity   | 0.85  | 0.70 | ✓      | Explicit in/out lists; modal alternative rejected  |
| Constraint Clarity | 0.85  | 0.65 | ✓      | Storage location, key, gate-channel rule all locked|
| Acceptance Criteria| 0.85  | 0.70 | ✓      | 10 pass/fail items; Wave-0 RED required            |
| **Ambiguity**      | 0.13  | ≤0.20| ✓      |                                                    |

## Interview Log

| Round | Perspective     | Question summary                                  | Decision locked                                                            |
|-------|-----------------|---------------------------------------------------|----------------------------------------------------------------------------|
| 0     | Scout           | What exists today / what's the gap?              | Pipe-syntax mitigation in `pathfinder_player_adapter.py:30`; on_message only fires in threads (`bot.py:668`); no transient store |
| 1     | Researcher      | Where does transient state live?                 | Obsidian vault file per draft under `mnemosyne/pf2e/players/_drafts/`      |
| 1     | Researcher      | Mid-dialog non-start `:pf` verb behaviour?       | Reject with actionable message; do not call underlying route               |
| 1     | Researcher      | Concurrent dialogs same user different channel?  | Allowed — keyed strictly on `(thread_id, user_id)`                         |
| 2     | Boundary Keeper | Where does the dialog actually run?              | New thread created on `:pf player start`; reuses existing thread message path; no `on_message` widening |
| 2     | Boundary Keeper | How does a draft end?                            | `:pf player cancel` only — drafts persist indefinitely; supersets the ROADMAP 24h floor |
| 2     | Boundary Keeper | Restart-start with existing draft?               | Resume — replay the next unanswered question; preserve prior answers       |

---

*Phase: 38-pf2e-multi-step-onboarding-dialog*
*Spec created: 2026-05-08*
*Next step: /gsd-discuss-phase 38 — implementation decisions (router hook point, draft frontmatter writes, idempotent thread creation, test fixtures)*
