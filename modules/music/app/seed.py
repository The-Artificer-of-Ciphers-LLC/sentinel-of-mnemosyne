"""First music/ vault write — cross-linked hub-mesh seed (MUS-05, D-08/D-09/D-10).

Writes the ONLY seed content this phase produces: a 4-note hub mesh
(``music/index.md`` + one index per subfolder) that is provably zero-orphan
under the vendored ``sentinel_shared.graph_check`` orphan rule and gives
Phase 49+ practice/idea/lesson notes durable, resolvable link targets from
their very first write instead of being born orphans.

CORRECTED HUB-MESH DESIGN (see 48-04-PLAN.md objective): Core's
``resolve_wikilink`` (sentinel-core/app/services/graph_analysis.py:56-72)
matches wikilink targets strictly by UNIQUE filename stem. Naming every note
``index.md`` (colliding stems) and linking by full path would NOT resolve
under that rule. Every note below therefore has a UNIQUE stem
(``index``, ``lessons-index``, ``practice-log-index``, ``ideas-index``) and
every wikilink target is a BARE stem — the module-side test
(``tests/test_music_vault_seed.py``) is the gate that proves the mesh is
genuinely zero-orphan, not merely well-intentioned.

Every note body carries (D-09): leading YAML frontmatter, an H1 claim
title, >=1 resolvable wikilink, and a trailing ```_schema fenced block with
``title``/``wikilinks`` plus the reserved ``listenbrainz_context`` /
``discogs_context`` fields set null (Phase 48 does not wire either
integration).

Writes go exclusively through the module's own ``ObsidianClient``
(``ObsidianClientCore.put_note`` — never Core's Vault Protocol, MUS-02).
"""
from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class _VaultWriter(Protocol):
    async def put_note(self, path: str, content: str) -> None: ...


HUB_NOTES: dict[str, str] = {
    "music/index.md": """---
type: hub
---

# Music Module Hub

Central index for the Music Lesson Tracker module. Practice logs, lesson
notes, and song/technique ideas all link back to this hub, and this hub
links out to each subtree's own index.

- [[lessons-index]] -- lesson notes
- [[practice-log-index]] -- practice log entries
- [[ideas-index]] -- song and technique ideas

```_schema
title: Music Module Hub
wikilinks:
  - lessons-index
  - practice-log-index
  - ideas-index
listenbrainz_context: null
discogs_context: null
```
""",
    "music/lessons/lessons-index.md": """---
type: hub
---

# Music Lessons Index

Lesson notes for the Music module land under this index, cross-linked back
to the module hub.

- [[index]] -- back to the Music module hub

```_schema
title: Music Lessons Index
wikilinks:
  - index
listenbrainz_context: null
discogs_context: null
```
""",
    "music/practice-log/practice-log-index.md": """---
type: hub
---

# Music Practice Log Index

Practice-log entries for the Music module land under this index, cross-linked
back to the module hub.

- [[index]] -- back to the Music module hub

```_schema
title: Music Practice Log Index
wikilinks:
  - index
listenbrainz_context: null
discogs_context: null
```
""",
    "music/ideas/ideas-index.md": """---
type: hub
---

# Music Ideas Index

Song and technique ideas for the Music module land under this index,
cross-linked back to the module hub.

- [[index]] -- back to the Music module hub

```_schema
title: Music Ideas Index
wikilinks:
  - index
listenbrainz_context: null
discogs_context: null
```
""",
}


async def seed_music_hub(client: _VaultWriter) -> None:
    """Idempotently PUT each ``HUB_NOTES`` entry via the module's ``ObsidianClient``.

    ``put_note`` fully replaces a note (idempotent re-seed on every restart).
    Callers (``app.main``'s ``lifespan``) MUST wrap this call so a vault
    outage is logged and swallowed rather than crashing startup — this
    function itself lets ``put_note``'s ``httpx.HTTPStatusError`` propagate
    on failure so the caller's guard is the single place that decides
    graceful-degrade behavior.
    """
    for path, body in HUB_NOTES.items():
        await client.put_note(path, body)
        logger.info("Seeded music hub note: %s", path)
