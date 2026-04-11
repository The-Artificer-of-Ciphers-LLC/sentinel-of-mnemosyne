---
description: How the Sentinel system works — principles, patterns, conventions.
type: self
created: 2026-04-11
---

# Methodology

## Three-Space Model (arscontexta)

The vault is organized into three spaces:

- **self/** — Who you are. Identity, goals, relationships, methodology. The Sentinel reads these at every exchange to stay oriented.
- **notes/** — What you know. Permanent notes with atomic claims, YAML frontmatter, and wikilinks. Flat folder — no subdirectories.
- **ops/** — What you do. Time-bound operational data: sessions, reminders, queue, health logs, observations, tensions, methodology experiments.

## Note Quality Standard

A permanent note passes the quality bar when:
1. The title states a single claim that passes the "this note argues that [title]" test.
2. The body uses connective words (because, but, therefore) rather than summaries.
3. YAML frontmatter is complete (description, type, created, topics, relevant_notes, status).
4. Wikilinks connect it to at least one other note.

## Inbox-First Pipeline

New ideas enter as inbox items (ops/queue/). The Sentinel helps process them into permanent notes (notes/) via the :connect command. Processed items are archived (ops/archive/).

## PARA Synthesis (D-16)

PARA concepts are mapped to this structure without creating separate folders:
- Projects → ops/queue/ (active work items)
- Areas → self/goals.md (ongoing responsibilities)
- Resources → notes/ (permanent knowledge)
- Archives → ops/archive/ (completed/inactive)
