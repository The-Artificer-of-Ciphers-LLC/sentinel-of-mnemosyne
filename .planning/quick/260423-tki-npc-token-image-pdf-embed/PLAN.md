---
task: npc-token-image-pdf-embed
slug: tki
date: 2026-04-23
type: quick
scope: Token image upload via Discord + embed in stat-card PDF
---

# Quick Task — Token Image Upload and PDF Embedding

## Objective

Close the Midjourney loop: user runs `:pf npc token <name>` to get a prompt, generates an image in Midjourney, downloads it, and uploads it back via `:pf npc token-image <name>` with the image attached. The image is stored in the Obsidian vault under `pf2e/tokens/<slug>.png` and referenced from the NPC's `token_image:` frontmatter field. Subsequent `:pf npc pdf <name>` requests embed the image in the PDF header.

## Convention

- **Path**: `pf2e/tokens/<slug>.png` (relative to vault root — same root as `pf2e/npcs/`)
- **Frontmatter field**: `token_image: pf2e/tokens/<slug>.png` (relative path stored verbatim)
- **Content-Type**: `image/png` (Midjourney exports PNGs by default; other types out of scope for this task)
- **Fallback**: if `token_image` field absent or image fetch fails, PDF renders header-only as today

## Files

### Modified

1. **`modules/pathfinder/app/obsidian.py`** — add two binary methods:
   - `async def put_binary(path, data: bytes, content_type: str) -> None`
   - `async def get_binary(path: str) -> bytes | None`

2. **`modules/pathfinder/app/routes/npc.py`**:
   - New `NPCTokenImageRequest` model (`name: str`, `image_b64: str`)
   - New `@router.post("/token-image")` handler
   - Modify `pdf_export` to fetch token_image bytes and pass to `build_npc_pdf`

3. **`modules/pathfinder/app/pdf.py`**:
   - `build_npc_pdf(fields, stats, token_image_bytes: bytes | None = None)` signature change
   - If `token_image_bytes` is truthy, create `reportlab.platypus.Image` from `BytesIO(bytes)` sized ~1.5"×1.5" and insert before the Title paragraph

4. **`modules/pathfinder/app/main.py`**:
   - Add `{"path": "npc/token-image", "description": "Upload NPC token image to vault (OUT-02 extension)"}` to REGISTRATION_PAYLOAD (11 total routes)
   - Update docstring endpoint list

5. **`interfaces/discord/bot.py`**:
   - New `elif verb == "token-image":` branch in `_pf_dispatch`
   - Requires `attachments` non-empty; first attachment must have `content_type` starting with `image/`
   - Downloads via `http_client.get(attachment.url)`, base64-encodes, POSTs to `modules/pathfinder/npc/token-image`
   - Returns success message
   - Update unknown-verb error message to include `token-image`

### Tests

1. **`modules/pathfinder/tests/test_npc.py`** — append:
   - `test_npc_token_image_saves_binary_and_frontmatter` — mock obsidian.put_binary + get_note/put_note, verify image stored and frontmatter updated
   - `test_npc_token_image_rejects_unknown_npc` — 404 when NPC note missing
   - `test_npc_pdf_with_token_image_embeds` — when frontmatter has token_image AND get_binary returns bytes, PDF output includes image block (verify via byte presence in PDF)

## Non-Goals

- **Multi-image support** (portrait + token + scene) — single `token_image` field only
- **Content-type validation beyond starts-with-"image/"** — rely on ReportLab to fail safely on bad data
- **Resizing / thumbnailing** — store the image at whatever size Midjourney produces; PDF embed uses a fixed display size regardless
- **Midjourney API integration** — still manual (user generates, downloads, uploads); ADR from Phase 30 CONTEXT.md stands (bot-to-bot DM impossible)
- **Live UAT** — user runs the test manually in Discord after deploy

## Verification

```bash
cd /Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder
uv run pytest tests/ -q
# Expected: 42 passed (39 prior + 3 new)

# After build + deploy:
docker compose --profile pf2e up -d --build pf2e-module discord
docker exec sentinel-of-mnemosyne-sentinel-core-1 curl -sf -H "X-Sentinel-Key: $(cat /Users/trekkie/projects/sentinel-of-mnemosyne/secrets/sentinel_api_key)" http://localhost:8000/modules | python3 -c "import json, sys; print(len(json.load(sys.stdin)[0]['routes']))"
# Expected: 11 (was 10; +1 for npc/token-image)
```

Live Discord test (manual, after deploy):
- Reply in a thread with an image attached: `:pf npc token-image Jareth`
- Bot confirms the image is saved
- `:pf npc pdf Jareth` now attaches a PDF with the image in the header
