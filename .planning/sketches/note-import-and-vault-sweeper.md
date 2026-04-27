---
created: 2026-04-27
status: requirements-only — plan after 5kl lands
depends_on: 260427-5kl-litellm-helpers-consolidation
---

# Note Import + Vault Sweeper

Two related features for the 2nd brain. Plan as one quick task — they share infrastructure (classifier, taxonomy, low-confidence handling).

## Problem

1. **No discrete note import path.** Today, when the user sends "Finished the sing better course" the message lands in `ops/sessions/{date}/{user_id}-{time}.md` as a transcript. There's no path that classifies it as e.g. `learning/courses-completed/sing-better.md` with structured frontmatter.

2. **Existing vault has accumulated test garbage.** Notes like "hello are you there", "what can you do" from earlier testing exist alongside real notes. No sweep / cleanup mechanism.

## Feature 1 — Note import (forward-looking)

When a message comes in that looks like a fact-worth-saving (not a question, not chitchat), classify and file it as a discrete note.

### Classifier output

For each candidate note, the classifier returns:
- `topic` — one of a defined taxonomy (see below)
- `title` — short slug (e.g. `sing-better-course-completed`)
- `confidence` — float 0..1
- `frontmatter` — structured fields appropriate to the topic

### Taxonomy (initial; extensible)

| Topic | Vault path | When |
|---|---|---|
| `learning.course-completed` | `learning/courses/` | "Finished X course", "completed Y" |
| `learning.skill-update` | `learning/skills/` | progress notes on a skill |
| `accomplishment` | `accomplishments/` | one-off achievements |
| `journal` | `journal/{YYYY-MM-DD}/` | feelings, daily reflections |
| `reference.fact` | `references/` | discrete facts to remember |
| `observation` | `ops/observations/` | already exists via `:remember` |
| `chitchat` | (do not file) | "hello", "thanks", small talk |
| `garbage` | `_trash/` | clearly noise/test artifact |
| `unsure` | (prompt user) | confidence below threshold |

### Confidence threshold + interactive resolution

- High confidence (≥ 0.8) → file directly, log to `ops/notes-imported.md`
- Medium (0.5..0.8) → file but flag in a follow-up summary "Filed N notes; review at <link>"
- Low (< 0.5) → write to `inbox/_pending-classification.md` with the candidate and 3-4 topic options. User reviews via `:inbox` subcommand.

### New Discord subcommands

| Command | Behavior |
|---|---|
| `:note <content>` | Force-classify and file (skips the implicit transcript-only path) |
| `:note <topic> <content>` | Skip classifier, file under the given topic |
| `:inbox` | List pending low-confidence imports |
| `:inbox classify <n> <topic>` | Resolve a pending entry |
| `:inbox discard <n>` | Mark as garbage |

## Feature 2 — Vault sweeper

One-shot (or periodic) walk over the entire Obsidian vault that:
1. Reads every `.md` file
2. Re-classifies under the taxonomy above
3. Detects garbage: short messages, no signal, test artifacts, near-duplicates of recent garbage
4. **Does NOT delete** — moves to `_trash/{YYYY-MM-DD}/` so user can review
5. Surfaces low-confidence reclassifications to the inbox

### Garbage heuristics (cheap pre-filter, before LLM call)

- `< 20 chars` of body text → almost certainly noise
- Single line, no punctuation, matches conversational regex (`^(hi|hello|hey|test|are you there|what can you do|ping|yo)\b`) → garbage
- Empty/whitespace-only file → garbage
- Filename matches test-pattern (`test-*`, `tmp-*`, `untitled*`) AND content is short → garbage candidate

### Operator-facing

- `:vault-sweep` (admin only) — kicks off the walk
- Walks in chunks (e.g. 100 files at a time) so it doesn't lock up; reports progress
- Idempotent: a sweep marker (`sweep_pass: 2026-04-27T12:00`) is written to frontmatter so a second sweep doesn't re-process unchanged notes
- Garbage moves are logged to `ops/sweeps/{date}.md` with original path, new path, reason, classifier confidence

### Safety

- **No deletion ever** — only `_trash/` moves
- **Dry-run mode** by default: `:vault-sweep --dry-run` writes a report without moving anything
- **Requires confirmation** for first run after install; subsequent runs use the saved confirmation

## Constraints / open questions

- **Where the classifier lives.** Sentinel-core territory (it's a 2nd brain feature). Likely `sentinel-core/app/services/note_classifier.py`. Uses `acompletion_with_profile` from the 5kl refactor.
- **Taxonomy lock-in.** Above list is initial; needs review with the user before implementation. Particularly `learning.*` sub-taxonomy granularity.
- **Garbage near-duplicate detection.** Vector similarity? Hash? Worth deciding before plan: small vault → simple hash on normalised text is fine; large vault → embedding similarity. Current vault size unknown — measure first.
- **Inbox UI.** Discord-only or also a vault note that updates? Probably both: `inbox/_pending-classification.md` is the source of truth, `:inbox` reads it.
- **Reclassification of already-classified notes.** A sweep should NOT reclassify notes that already have valid topic frontmatter unless `--force-reclassify` is passed.

## Why this isn't part of 5kl

5kl is a structural refactor (move helpers, dedupe, change imports). Verification is "behavior unchanged."
This is a new feature with new code paths, new commands, new vault writes. Verification is "feature works as specified."
Bundling them makes the diff unreviewable and the verifier ambiguous about which thing broke.

This sketch becomes the basis for `/gsd-quick --discuss --research --validate` after 5kl lands. The `--discuss` will resolve the open questions above (taxonomy granularity, garbage strategy, inbox shape).
