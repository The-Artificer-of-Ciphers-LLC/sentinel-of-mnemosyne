# ADR-0003 — Recall is a module above the Vault seam, not behavior inside the message processor

**Status:** proposed (design converged; no production code yet)
**Date:** 2026-06-11
**Related:** ADR-0002 (Vault seam location), ADR-0001 (Sentinel persona source)

## Context

The Sentinel "forgets after three": once a conversation passes the Hot tier it retrieves nothing.
The cause is architectural, not a bug. **Retrieval has no module.** Hot-tier and Warm-tier
assembly are private methods on `MessageProcessor` (`_append_hot_tier`, `_append_warm_tier`,
`_allocate_budgets`), with every relevance threshold, exclusion list, session window, and budget
ratio as an inline literal in `message_processing.py`. The only way to test "how the Sentinel
remembers" is through the full `POST /message` path, and `GET /context/{user_id}` re-implements
hot-tier assembly a second time. A related finding (out of scope here, see ADR-0002 future
backings and the C2 follow-up): the sweeper writes an embedding into every note's frontmatter that
no retrieval path ever reads back — semantic recall is half-built.

## Decision

Extract a deep **Recall** module that owns retrieval policy and sits **above** the Vault seam.

- `Recall` owns *what to remember*: Self namespace reads, recent Session summaries, Warm-tier
  vault search, the relevance threshold, the namespace exclusions, the recent-session window, and
  the per-tier selection budgets (the `0.15` / `0.10` split).
- `Recall.assemble(request, budget)` returns a **`RecalledContext`** value — ranked, budget-trimmed
  memory items. It does **not** return chat messages.
- `MessageProcessor` keeps *how to present and defend*: the **Sentinel persona** read,
  `injection_filter.wrap_context()`, the "Understood." pairs, and the final whole-prompt
  `TokenBudget.check()`.
- `GET /context/{user_id}` delegates to `Recall` and serializes `RecalledContext`. The duplicated
  inline assembly is deleted.
- `Recall` depends on the `Vault` Protocol only. It does **not** move or modify `app/vault.py`
  (ADR-0002 stands — see Relationship below).

### Interface sketch (illustrative — not yet implemented)

```python
@dataclass(frozen=True)
class SearchResult:
    path: str
    score: float          # Obsidian's negative BM25 value, named and typed here
    body: str             # full note text (snippet fallback if read fails)

@dataclass(frozen=True)
class RecalledContext:
    self_context: list[str]        # raw markdown, as today
    sessions: list[str]            # raw markdown, as today (ADR-future: SessionSummary)
    warm: list[SearchResult]       # typed at Recall's edge

class Recall:
    def __init__(self, vault: Vault, *, config: RecallConfig = DEFAULT) -> None: ...
    async def assemble(self, request: MessageRequest, budget: int) -> RecalledContext: ...
    # private: _hot_self() · _hot_sessions() · _warm_search() · _allocate()
    # _warm_search(): vault.find() -> filter(threshold, exclude-prefixes) -> list[SearchResult]
```

## Considered Options

- **Recall returns ready-to-inject messages** (owns `injection_filter` + the pairs + per-tier
  truncation). Rejected: the memory module would then know about prompt-injection *defense*
  formatting — the wrong layer. Chosen instead: Recall returns content; the processor presents it.
- **Fold the Sentinel persona into Recall** (matches CONTEXT.md's old Hot-tier definition).
  Rejected: persona is operator-curated *identity* (system role), not recalled memory. CONTEXT.md
  was sharpened to say so.
- **Build the `RetrievalStrategy` seam now.** Rejected: Warm search has one adapter (Obsidian BM25)
  today; one adapter is a hypothetical seam, not a real one. Warm search stays a private
  `Recall._warm_search()`, *shaped* for extraction. The real seam arrives with a second adapter
  (`SemanticRecall`) in the follow-up.
- **Type `find()` in the Vault Protocol.** Rejected for this step: it touches `ObsidianVault`,
  `FakeVault`, and the adapter tests (the ADR-0002 surface). Instead the raw Obsidian dicts are
  translated to `SearchResult` at Recall's edge; leakage stops there. Pushing typing into the
  Protocol becomes a clean later step.
- **Migrate the existing through-`/message` tier tests down to Recall.** Rejected: the project's
  Test-Rewrite Ban (operator decides retirement). The existing tests are kept; `test_recall.py` is
  added against `FakeVault`. Retirement remains a separate operator call.
- **Type `SessionSummary` now.** Deferred: `RecalledContext.sessions` stays raw `list[str]` for
  this step; a later candidate introduces typed `SessionSummary` + a `RetentionPolicy`.

## Relationship to ADR-0002

ADR-0002 places the `Vault` Protocol at `app/vault.py` as a single top-level capability seam and
forbids silently undoing it. This ADR does **not** touch that decision: `Recall` is a new module
that *consumes* the Vault seam from above. `vault.py` does not move. A separate, still-open question
— whether the wide 15-method Vault Protocol should later shed its memory/sweep methods (which would
reopen ADR-0002) — is explicitly **not** decided here.

## Consequences

- The interface becomes the test surface: "given these vault notes + this message, `assemble`
  returns these ranked items" — no `MessageProcessor`, no AI provider, no `injection_filter`.
- All retrieval constants concentrate in one module (locality); every memory tweak lands in one
  place (leverage across the message path and `/context`).
- `RecalledContext` is half-typed by design this step (warm typed, self/sessions raw) — an accepted
  scope boundary, closed later when `SessionSummary` lands.
- `Status: proposed` — this records the design only. No production code has been written.
