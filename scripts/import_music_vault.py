"""One-shot importer: ~/trekkie/ Obsidian vault → Sentinel vault notes/music/.

Usage:
    python scripts/import_music_vault.py --dry-run
    python scripts/import_music_vault.py
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.parse
from pathlib import Path

import httpx
from dotenv import dotenv_values

SOURCE = Path("/Users/trekkie/trekkie")
TARGET_PREFIX = "notes/music"
HOST_API = "http://127.0.0.1:27123"


def load_api_key() -> str:
    env = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
    key = env.get("OBSIDIAN_API_KEY") or os.environ.get("OBSIDIAN_API_KEY")
    if not key:
        sys.exit("OBSIDIAN_API_KEY not set in .env or environment")
    return key


def discover() -> list[Path]:
    files: list[Path] = []
    for p in SOURCE.rglob("*.md"):
        if any(part == ".obsidian" or part.startswith("._") for part in p.parts):
            continue
        if p.stat().st_size == 0:
            continue
        files.append(p)
    return sorted(files)


def encode_path(rel: Path) -> str:
    return "/".join(urllib.parse.quote(part, safe="") for part in rel.parts)


def put_file(client: httpx.Client, api_key: str, rel: Path, body: bytes) -> tuple[int, str]:
    url = f"{HOST_API}/vault/{TARGET_PREFIX}/{encode_path(rel)}"
    r = client.put(
        url,
        content=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "text/markdown",
        },
        timeout=15.0,
    )
    return r.status_code, r.text[:200]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    api_key = load_api_key()
    files = discover()
    print(f"Found {len(files)} markdown files under {SOURCE}")

    if args.dry_run:
        for f in files:
            rel = f.relative_to(SOURCE)
            print(f"  → {TARGET_PREFIX}/{rel}")
        return 0

    ok = 0
    fail = 0
    with httpx.Client(verify=False) as client:
        for f in files:
            rel = f.relative_to(SOURCE)
            body = f.read_bytes()
            status, text = put_file(client, api_key, rel, body)
            mark = "✓" if 200 <= status < 300 else "✗"
            print(f"  {mark} [{status}] {rel}")
            if 200 <= status < 300:
                ok += 1
            else:
                fail += 1
                print(f"      {text}")

    print(f"\nDone: {ok} ok, {fail} failed")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
