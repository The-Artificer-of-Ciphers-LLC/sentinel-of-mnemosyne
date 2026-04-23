---
task: npc-token-image-pdf-embed
slug: tki
date: 2026-04-23
type: quick
status: complete
---

# Quick Task Summary — Token Image Upload + PDF Embed

## Objective

Close the Midjourney token loop: user generates a token via `:pf npc token <name>`, creates the image in Midjourney, downloads the PNG, and uploads it back with `:pf npc token-image <name>` (image attached). Image is stored in the Obsidian vault and automatically embedded in subsequent `:pf npc pdf <name>` stat cards.

## Outcome

Complete. All 5 files in scope modified; 3 new tests added; 42/42 passing (39 prior + 3 new).

## Files Changed

| File | Change |
|------|--------|
| `modules/pathfinder/app/obsidian.py` | `put_binary` + `get_binary` methods (committed in WIP pass) |
| `modules/pathfinder/app/routes/npc.py` | `NPCTokenImageRequest` model, `/token-image` handler, `/pdf` fetches token image |
| `modules/pathfinder/app/pdf.py` | `build_npc_pdf` accepts optional `token_image_bytes`; inserts 1.5"×1.5" `Image` before Title |
| `modules/pathfinder/app/main.py` | REGISTRATION_PAYLOAD +1 route (11 total); docstring updated |
| `interfaces/discord/bot.py` | `elif verb == "token-image"` branch in `_pf_dispatch`; unknown-verb list updated |
| `modules/pathfinder/tests/test_npc.py` | 3 new tests (saves binary+frontmatter, 404 on unknown NPC, PDF embeds when present) |

## Convention

- **Token image path:** `mnemosyne/pf2e/tokens/<slug>.png` (same parent as `mnemosyne/pf2e/npcs/`)
- **Frontmatter field:** `token_image: mnemosyne/pf2e/tokens/<slug>.png` (absolute vault path)
- **Content-Type:** `image/png` hardcoded (Midjourney exports PNG; other types out of scope)
- **Size cap:** 10 MB server-side (matches `/npc/import`)

## Path Clarification

PLAN.md originally wrote `pf2e/tokens/` but the actual NPC prefix is `mnemosyne/pf2e/npcs/`. Honored the intent ("same root as npcs folder") rather than the literal path — tokens live at `mnemosyne/pf2e/tokens/` to keep vault organization consistent.

## Frontmatter Update Strategy

Used `patch_frontmatter_field` (Obsidian REST v3 PATCH with `Operation: replace`, `Target: token_image`) rather than GET-then-PUT rebuild. Same pattern as `/npc/relate`. Semantically correct for single-field changes and avoids re-serializing the entire note body.

## PDF Embed

`build_npc_pdf` signature extended with optional `token_image_bytes: bytes | None = None`. When present, inserts a `reportlab.platypus.Image(BytesIO(bytes), width=1.5*inch, height=1.5*inch)` at the head of the story list. Best-effort: `get_binary` returns `None` on 404/error, so a missing image falls back cleanly to header-only PDF.

## Discord UX

In-thread flow:
1. `:pf npc token Jareth` → bot returns Midjourney `/imagine` prompt
2. User runs Midjourney, downloads PNG
3. User replies in thread with `:pf npc token-image Jareth` + PNG attachment
4. Bot validates `content_type` starts with `image/`, fetches attachment, base64-encodes, POSTs
5. Bot confirms: "Token image saved … Run `:pf npc pdf Jareth` to see it embedded"
6. `:pf npc pdf Jareth` attaches a PDF with image in header

## Tests Added

- `test_npc_token_image_saves_binary_and_frontmatter` — verifies `put_binary` called with correct path + PNG signature + `image/png`, and `patch_frontmatter_field` records the vault path
- `test_npc_token_image_rejects_unknown_npc` — 404 before any vault writes when NPC note missing
- `test_npc_pdf_with_token_image_embeds` — `get_binary` called for path from frontmatter; resulting PDF contains `/FlateDecode` marker proving raster embedding

## Verification

```bash
cd modules/pathfinder
uv run pytest tests/ -q
# 42 passed in 1.74s ✓

uv run python -c "from app.main import REGISTRATION_PAYLOAD; print(len(REGISTRATION_PAYLOAD['routes']))"
# 11 ✓
```

## Deploy

```bash
docker compose --profile pf2e up -d --build pf2e-module discord
```

Then in Discord (live UAT, user-driven):
- `:pf npc token Jareth` → copy MJ prompt, generate, download PNG
- Reply in same thread with `:pf npc token-image Jareth` + PNG attached → bot confirms save
- `:pf npc pdf Jareth` → PDF now has token in header
