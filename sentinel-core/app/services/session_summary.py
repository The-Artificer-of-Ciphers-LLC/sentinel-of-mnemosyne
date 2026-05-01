"""Session summary path/content builder."""

from __future__ import annotations

from datetime import datetime, timezone


def build_session_summary(user_id: str, user_msg: str, ai_msg: str, model: str) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M-%S")
    path = f"ops/sessions/{date_str}/{user_id}-{time_str}.md"
    content = f"""---
timestamp: {now.isoformat()}
user_id: {user_id}
model: {model}
---

## User

{user_msg}

## Sentinel

{ai_msg}
"""
    return path, content
