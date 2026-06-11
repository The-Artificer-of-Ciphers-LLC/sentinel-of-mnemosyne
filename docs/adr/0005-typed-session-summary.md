# ADR-0005 — Typed SessionSummary and a RetentionPolicy: stop forgetting after three

**Status:** proposed (design converged in architecture review; no production code yet)
**Date:** 2026-06-11
**Related:** ADR-0003 (Recall module), ADR-0004 (Semantic recall), ADR-0002 (Vault seam location)

## Context

"Forgets after three" is a literal. `ObsidianVault.get_recent_sessions` lists only **today's and
yesterday's** `ops/sessions/` directories and returns the top **`limit=3`** as **raw markdown
strings**. The hot-tier `self_paths` is an inline literal list inside `_append_hot_tier`. Past the
3-deep / two-day window, earlier turns are dropped with no warm-tier fallback — because warm search
excludes `ops/` (the original debug finding, ADR-less). Sessions also cross the planned `Recall`
interface as raw strings the caller parses by hand; ADR-0003 deliberately left `RecalledContext.sessions`
as `list[str]` and deferred typing to here.

## Decision

Two changes, both owned by the `Recall` module (ADR-0003):

- Introduce a typed **`SessionSummary`** value (`date`, `user_id`, `time`, `user_msg`, `sentinel_msg`,
  `path`, `body`) replacing raw markdown strings as the return type of `get_recent_sessions` and the
  type of `RecalledContext.sessions`.
- Introduce a **`RetentionPolicy`** owned by `Recall`: the recent-session window (`limit` + day-window)
  becomes a policy object with defaults, not inline constants. Tunable and testable.

And close the cliff: **older session summaries become reachable through the recall index**
(ADR-0004 `SemanticRecall` / the ADR-0003 warm tier) instead of only the hot window. This requires
session content to be retrievable, which collides with the `ops/` exclusion that caused the original
bug. The resolution (decided in planning, not locked here): lean on the durable, searchable
conversation note already filed *outside* `ops/` (from the debug fix) as the retrievable carrier of a
turn, rather than relaxing the `ops/` exclusion globally. "Older than the hot window" is then
*recalled semantically*, not dropped.

### Interface sketch (illustrative — not yet implemented)

```python
@dataclass(frozen=True)
class SessionSummary:
    date: str; user_id: str; time: str
    user_msg: str; sentinel_msg: str
    path: str; body: str

@dataclass(frozen=True)
class RetentionPolicy:
    hot_limit: int = 3          # was the inline limit=3
    hot_window_days: int = 2    # was today+yesterday
    # older turns fall through to the recall index, not off a cliff

async def get_recent_sessions(self, user_id: str,
                              policy: RetentionPolicy) -> list[SessionSummary]: ...
# RecalledContext.sessions: list[SessionSummary]   (ADR-0003 had list[str])
```

## Considered Options

- **Just raise `limit` / widen the window.** Rejected: this is the debug "hot-tier expansion" option —
  it does not scale; a single long same-day conversation still overflows the window with no fallback.
- **Keep raw markdown strings.** Rejected: callers parse frontmatter from strings, there is no typed
  boundary, and sessions can't carry recency/score for merging with warm results.
- **Type `SessionSummary` back in Candidate 1.** Deferred there (ADR-0003) to keep C1 a focused
  extraction; it lands here with the retention work it belongs to.
- **Relax the `ops/` exclusion globally so session summaries are searchable.** Rejected as the primary
  path: it reintroduces the noise the exclusion was added to suppress (the Sentinel's own replies).
  Preferred instead: the indexed conversation note outside `ops/` (debug fix) + semantic recall.

## Relationship to other ADRs

Depends on **ADR-0003** (the `RetentionPolicy` and typed sessions live in `Recall`) and composes with
**ADR-0004** (older sessions are recalled via the semantic strategy). This **does** change
`get_recent_sessions`'s return type — a deliberate, bounded reopening of the **ADR-0002** Vault surface
for that one read method (touches `ObsidianVault`, `FakeVault`, and the adapter session tests).
`app/vault.py` does not move; ADR-0002's seam-location decision stands.

## Consequences

- The recent-session window becomes a tuned `RetentionPolicy`, not a constant — "three" is a knob.
- Typed `SessionSummary` ends frontmatter string-parsing at call sites and lets `Recall` merge sessions
  with warm results by recency.
- Older turns are recalled instead of dropped — the central "forgets after three" symptom is closed.
- Cost: the `get_recent_sessions` return-type change ripples to the Vault adapters and their tests.
- The `ops/sessions` retrievability question (links back to the original debug fix) must be resolved
  in planning — this ADR records the preferred direction, not the wiring.
- `Status: proposed` — design record only; no production code written.
