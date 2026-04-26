# Phase 36: Foundry NPC Pull Import — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-26
**Phase:** 36-foundry-npc-pull-import
**Areas discussed:** Import flow, Duplicate handling

---

## Import flow

### Button style

| Option | Description | Selected |
|--------|-------------|----------|
| Text-input dialog | Header button → `DialogV2.input()` asking for NPC name → fetch by slug. No new backend endpoints. | |
| List picker | Header button → fetch all Sentinel NPCs → searchable `<select>` → select and import. Requires new `GET /npcs/` listing endpoint. | ✓ |
| Right-click context menu | `getActorDirectoryEntryContext` hook on existing actor — sync/refresh semantic only. | |

**User's choice:** List picker

---

### Listing data richness

| Option | Description | Selected |
|--------|-------------|----------|
| Name only | Returns `[{name, slug}]`. Fast, no frontmatter read per NPC. | |
| Name + level + ancestry | Returns `[{name, slug, level, ancestry}]`. Frontmatter read per NPC. Picker shows "Varek (Level 5, Human)". | ✓ |

**User's choice:** Name + level + ancestry

---

### Offline / error handling

| Option | Description | Selected |
|--------|-------------|----------|
| Show error notification | Dialog fails to open; `ui.notifications.error()` displays. | |
| Empty picker with retry button | Dialog opens with "No NPCs found. Is Sentinel running?" + Retry button. | ✓ |

**User's choice:** Empty picker with retry button

---

### Post-selection flow

| Option | Description | Selected |
|--------|-------------|----------|
| Import immediately | Select NPC → click Import → actor created. One dialog. | |
| Show confirmation step | Select NPC → preview panel → confirm to import. Extra click. | ✓ |

**User's choice:** Show confirmation step (two-step: select → preview → import)

---

### Preview content

| Option | Description | Selected |
|--------|-------------|----------|
| Listing data only | Shows name + level + ancestry from the listing response — no second API call. | ✓ |
| Full stat preview | Makes a second `GET /npcs/{slug}/foundry-actor` call to show AC, HP, saves. | |

**User's choice:** Listing data only (no extra fetch before confirmation)

---

## Duplicate handling

| Option | Description | Selected |
|--------|-------------|----------|
| Always create new | Always creates a new actor. DM manages duplicates manually. | |
| Auto-overwrite silently | Name-match → replace system data silently. Destroys manual Foundry edits. | |
| Confirm dialog | `Dialog.confirm()` — "Varek already exists. Overwrite?" — Yes overwrite, No create new. | ✓ |

**User's choice:** Confirm dialog

---

## Claude's Discretion

- **Route naming:** SC uses `npcs/` (plural) vs existing `npc/` (singular) router. Claude to implement as new `routes/npcs.py` with separate `prefix="/npcs"` router.
- **JS dialog framework:** ApplicationV2 vs DialogV2 for stateful two-step dialog. Researcher to confirm the right v14 API.
- **Overwrite field set:** Which fields to replace on `existing.update()` — Claude to limit to `system.*` + `name`, preserve Foundry-managed fields.
- **Module version bump:** 1.0.0 → 1.1.0.
- **REGISTRATION_PAYLOAD:** Two new routes to add; researcher confirms correct format.

## Deferred Ideas

- Right-click "Sync from Sentinel" via `getActorDirectoryEntryContext` hook
- List picker → typeahead `<datalist>` upgrade for large vaults
- Client-side filter/search above the `<select>`
- Bulk import (multi-select with per-item duplicate handling)
