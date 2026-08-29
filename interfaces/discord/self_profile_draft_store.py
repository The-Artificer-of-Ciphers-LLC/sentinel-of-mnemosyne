"""Self-profile onboarding draft persistence for Discord dialogs.

Mirrors ``pathfinder_player_draft_store.py`` (same Obsidian REST frontmatter
round-trip shape) but scoped to the ``:onboard`` dialog's own draft directory
so the two dialogs never collide on disk.
"""

from __future__ import annotations

import os
import re

import yaml

_DRAFT_DIR = "ops/onboarding/_drafts"
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


class _NoTimestampLoader(yaml.SafeLoader):
    """SafeLoader that keeps ISO-8601 timestamps as plain strings."""


_NoTimestampLoader.yaml_implicit_resolvers = {
    ch: [
        (tag, regexp)
        for (tag, regexp) in resolvers
        if tag != "tag:yaml.org,2002:timestamp"
    ]
    for ch, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def draft_path(thread_id: int, user_id) -> str:
    """Canonical draft path under the Vault."""
    return f"{_DRAFT_DIR}/{thread_id}-{str(user_id)}.md"


def _vault_url(rel: str) -> str:
    base = os.environ.get(
        "OBSIDIAN_API_URL", "http://host.docker.internal:27123"
    ).rstrip("/")
    return f"{base}/vault/{rel}"


def _vault_headers() -> dict:
    """Bearer-key headers for the Obsidian REST API."""
    try:
        from bot import _read_secret

        key = _read_secret("obsidian_api_key", os.environ.get("OBSIDIAN_API_KEY", ""))
    except Exception:
        key = os.environ.get("OBSIDIAN_API_KEY", "")
    return {"Authorization": f"Bearer {key}"}


def _split_frontmatter(body: str) -> tuple[dict, str]:
    """Split a markdown body into frontmatter and remaining body."""
    match = _FRONTMATTER_RE.match(body or "")
    if not match:
        return ({}, body or "")
    try:
        fm = yaml.load(match.group(1), Loader=_NoTimestampLoader) or {}
        if not isinstance(fm, dict):
            fm = {}
    except yaml.YAMLError:
        fm = {}
    return (fm, body[match.end() :])


def _join_frontmatter(fm: dict, rest: str = "") -> str:
    """Render a frontmatter dict and optional body into markdown."""
    block = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).strip()
    return f"---\n{block}\n---\n\n{rest.lstrip()}"


async def draft_exists(thread_id: int, user_id, *, http_client) -> bool:
    """Return True when a draft exists for the thread/user pair."""
    try:
        resp = await http_client.get(
            _vault_url(draft_path(thread_id, user_id)),
            headers=_vault_headers(),
            timeout=10.0,
        )
    except Exception:
        return False
    return getattr(resp, "status_code", 0) == 200


async def save_draft(thread_id: int, user_id, draft: dict, *, http_client) -> None:
    """PUT the draft as a frontmatter-only markdown body."""
    body = _join_frontmatter(draft, "")
    headers = {**_vault_headers(), "Content-Type": "text/markdown"}
    resp = await http_client.put(
        _vault_url(draft_path(thread_id, user_id)),
        headers=headers,
        content=body,
        timeout=10.0,
    )
    raise_for_status = getattr(resp, "raise_for_status", None)
    if callable(raise_for_status) and resp.status_code >= 400:
        raise_for_status()


async def load_draft(thread_id: int, user_id, *, http_client) -> dict | None:
    """GET the draft and parse frontmatter. Returns None on 404."""
    resp = await http_client.get(
        _vault_url(draft_path(thread_id, user_id)),
        headers=_vault_headers(),
        timeout=10.0,
    )
    if resp.status_code == 404:
        return None
    if resp.status_code >= 400:
        raise_for_status = getattr(resp, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
    fm, _rest = _split_frontmatter(resp.text)
    return fm or None


async def delete_draft(thread_id: int, user_id, *, http_client) -> None:
    """DELETE the draft. 404 is tolerated for idempotent cleanup."""
    resp = await http_client.delete(
        _vault_url(draft_path(thread_id, user_id)),
        headers=_vault_headers(),
        timeout=10.0,
    )
    if resp.status_code not in (200, 204, 404):
        raise_for_status = getattr(resp, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
