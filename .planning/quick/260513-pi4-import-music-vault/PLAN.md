---
quick_id: 260513-pi4
slug: import-music-vault
date: 2026-05-13
description: Import external Obsidian music/songwriting vault from ~/trekkie/ into the Sentinel's primary vault under notes/music/
---

# Import Music Vault → notes/music/

## Source
`/Users/trekkie/trekkie/` — a Notion-export Obsidian vault, music/songwriting domain.

## Target
Sentinel primary vault, `notes/music/` subtree, accessed via the existing Obsidian REST API (`OBSIDIAN_API_URL=http://host.docker.internal:27123`, port 27123 → from the host reached at `http://127.0.0.1:27123`).

## Scope
38 real markdown files across:
- `Home/` (32 files, including `Stages of Life EP/`, `Seven Day Songwriting Challenge/`, `Song Writing Sprint - 1Q 2026/`)
- `EDM Prod Course Notes/` (1 file)
- `PML Live Course Notes/` (1 file)

Plus 1 empty daily-note placeholder (`2026-05-13.md`) — skipped.

## Exclusions
- AppleDouble metadata sidecars (`_*` at vault root, no `.md` extension — macOS resource forks from a Safari-downloaded Notion export, containing only `com.apple.quarantine` xattrs)
- `.obsidian/` directory (vault-local plugin config)
- Empty (0-byte) files

## Method
For each source file `~/trekkie/{rel_path}`:
- URL-encode `rel_path` segment-by-segment
- `PUT http://127.0.0.1:27123/vault/notes/music/{encoded_rel_path}` with `Authorization: Bearer ${OBSIDIAN_API_KEY}` and body = file contents
- Obsidian REST API auto-creates parent folders

## Tasks
1. Write `scripts/import_music_vault.py` — one-shot importer (URL-encoded paths, skip empties, dry-run flag)
2. Dry-run to confirm file list + targets
3. Live run; collect per-file HTTP status
4. Verify by listing `notes/music/` via REST API
5. Commit script + this PLAN/SUMMARY under `.planning/quick/`

## Reversibility
Each PUT creates a new file in the Sentinel vault — undo is `rm -rf <vault>/notes/music/` (or `DELETE /vault/notes/music/...` per file). Source vault at `~/trekkie/` is not modified.
