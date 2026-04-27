# Quick Task 260427-vl1: Note Import + Vault Sweeper — Research

**Researched:** 2026-04-27
**Domain:** sentinel-core 2nd-brain feature (note classification + Obsidian vault sweep)
**Confidence:** HIGH (all decisions verified against existing code; one MEDIUM gap on inbox concurrency)

## Summary

This task lands cleanly on existing infrastructure. The classifier service belongs at `sentinel-core/app/services/note_classifier.py` and uses the same `litellm.acompletion` + `model_profiles` plumbing already wired in for sentinel-core (no `acompletion_with_profile` wrapper exists in sentinel-core — only in pathfinder; either port it to `shared/sentinel_shared/` or call `litellm.acompletion` directly with the resolved profile's stop sequences). The Obsidian REST API supports neither recursive listing nor a move endpoint, so the sweeper must walk per-directory and implement move as PUT-new + DELETE-old. Embedding-similarity de-dup reuses the exact pattern from `modules/pathfinder/app/llm.py::embed_texts` and `app/rules.py::cosine_similarity` — copy, do not invent. Admin gate for `:vault-sweep` does not exist today: there is a `DISCORD_ALLOWED_CHANNELS` env-var pattern, but no user-id allowlist; least-invasive path is a new `SENTINEL_ADMIN_USER_IDS` env var checked against `str(message.author.id)`. The current vault is nearly empty (9 .md files, only `pf2e/` populated) so first-sweep performance is a non-issue, but the algorithm must still scale to ~1000 notes for the eventual real vault.

**Primary recommendation:** Copy the pathfinder write-through-cache + frontmatter-base64-embedding pattern as-is, port `acompletion_with_profile` into `sentinel_shared`, wrap every Obsidian write in GET-then-PUT (never PATCH against fields that may not exist — see `project_obsidian_patch_constraint` memory), and gate `:vault-sweep` via env-var user-id allowlist.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `:note` / `:inbox` / `:vault-sweep` parsing & user-id admin gate | Discord interface (`interfaces/discord/bot.py`) | — | `handle_sentask_subcommand` already owns colon-prefix dispatch + user-id extraction |
| Note classifier (LLM + structured output) | sentinel-core service (`app/services/note_classifier.py`) | — | 2nd-brain feature; reuses existing `model_selector` + `model_profiles` |
| Pre-filter regex / heuristics | sentinel-core service | — | Must run before LLM call for budget reasons; pure transform, unit-testable |
| Embedding similarity for sweep de-dup | sentinel-core service (new helper) | — | Copy pattern from `modules/pathfinder/app/rules.py::cosine_similarity` + `llm.py::embed_texts` |
| Obsidian read/write/walk | sentinel-core client (`app/clients/obsidian.py` — extend) | — | Existing `ObsidianClient` is the single Obsidian access point |
| HTTP routes (`POST /note/classify`, `POST /vault/sweep/start`, `GET /vault/sweep/status`, `GET/PUT /inbox`) | sentinel-core router (`app/routes/note.py` new) | — | Discord bot calls sentinel-core over HTTP; never reaches Obsidian directly except for thread-id persistence |
| Inbox file source-of-truth | Obsidian vault (`inbox/_pending-classification.md`) | sentinel-core route | File is authoritative; bot mutates via GET-then-PUT |

## Standard Stack (verified — already in repo)

| Library | Version | Purpose | Verified |
|---------|---------|---------|----------|
| `litellm` | >=1.83.0 | LLM call (`acompletion`, `aembedding`) | `[VERIFIED: sentinel-core/pyproject.toml]` |
| `httpx` | >=0.28.1 | Obsidian REST + LM Studio client | `[VERIFIED: sentinel-core/app/clients/obsidian.py]` |
| `pydantic` | >=2.7.0 | `ClassificationResult` model | `[VERIFIED: sentinel-core uses Pydantic v2]` |
| `numpy` | (already in pathfinder image) | Cosine similarity | `[VERIFIED: modules/pathfinder/app/rules.py L32]` — sentinel-core does NOT currently depend on numpy; check Dockerfile dual-ship requirement (see Pitfall 4) |
| `PyYAML` | (already in repo) | Frontmatter parse/dump | `[VERIFIED: pathfinder uses yaml.safe_load + yaml.dump]` |
| `sentinel_shared.model_profiles` | local | Stop sequences per model family | `[VERIFIED: shared/sentinel_shared/model_profiles.py]` |

**Need to ship:**
- Port `modules/pathfinder/app/llm_call.py::acompletion_with_profile` into `shared/sentinel_shared/llm_call.py` so sentinel-core can use it without a cross-module import (or duplicate-with-comment if the shared package boundary is contested).
- Add `numpy` and `PyYAML` (if missing) to `sentinel-core/pyproject.toml` AND `sentinel-core/Dockerfile` per `project_dockerfile_deps` memory — adding to pyproject alone causes restart-loop on `ModuleNotFoundError`.

## Detailed Findings

### 1. Classifier service shape

**Location:** `sentinel-core/app/services/note_classifier.py`

**Function signature:**

```python
from pydantic import BaseModel
from typing import Literal

TopicSlug = Literal["learning", "accomplishment", "journal", "reference",
                    "observation", "noise", "unsure"]

class ClassificationResult(BaseModel):
    topic: TopicSlug
    confidence: float  # 0.0..1.0, rounded to 1 decimal
    title_slug: str    # kebab-case, max 60 chars; classifier-suggested
    reasoning: str     # 1-2 sentences, for inbox display

async def classify_note(
    candidate_text: str,
    user_topic: str | None = None,  # explicit override → bypass classifier
) -> ClassificationResult: ...
```

**LLM call:** `litellm.acompletion(model=resolved.model, response_format={"type": "json_object"}, ...)` with system prompt enumerating the 7 closed-vocab slugs (mirror the `coerce_topic` discipline from `modules/pathfinder/app/rules.py::RULE_TOPIC_SLUGS`). Wrap in salvage path identical to `classify_rule_topic` — JSON parse failure or unknown slug coerces to `unsure` with confidence 0.0.

**Model:** `resolve_model("structured")` via the sentinel-core `app/services/model_selector.py::select_model` — the `"structured"` rubric prefers function-calling-capable models, exactly what JSON mode wants. `[VERIFIED: sentinel-core/app/services/model_selector.py L183]`.

**No native sentinel-core `resolve()` helper exists yet.** Sentinel-core has `select_model` + `discover_active_model` but no `ResolvedModel` bundle. Two options for the planner: (a) port pathfinder's `ResolvedModel` + `resolve()` into `sentinel_shared` (preferred — DRY), or (b) compose locally inside `note_classifier.py`. Flag as **planner decision**.

**Pre-filter ordering inside classifier:**
1. `_apply_cheap_filter(text, filename=None)` → returns `("noise", 1.0)` or `None`
2. If user supplied explicit `user_topic` ∈ closed vocab → return `(user_topic, 1.0)` immediately, no LLM call
3. Otherwise → LLM call → coerce → return

### 2. Cheap pre-filter

**Verified vault state:** the live vault at `/Users/trekkie/projects/2ndbrain/mnemosyne/` currently contains only `pf2e/*` subfolders and zero stray notes at root — no test garbage was committed there. **The garbage we need to filter is theoretical (a future state where Discord transcripts get auto-imported), not present today.** This is significant: the sweeper's first run on this vault will move zero notes. The user's mental model of "test garbage in the vault" is forward-looking; current vault is clean. `[VERIFIED: filesystem listing 2026-04-27]`

**Concrete patterns from CONTEXT.md, frozen:**

```python
import re

_OPENERS = re.compile(
    r"^\s*(hi|hello|hey|test|are you there|what can you do|ping|yo|sup|"
    r"thanks|thank you|ok|okay)\b",
    re.IGNORECASE,
)
_TEST_FILENAME = re.compile(r"^(test-|tmp-|untitled)", re.IGNORECASE)

def _apply_cheap_filter(text: str, filename: str | None = None) -> tuple[str, float] | None:
    body = (text or "").strip()
    if not body:
        return ("noise", 1.0)
    if len(body) < 20:
        # additional safety: if it starts with an opener, definitely noise
        if _OPENERS.match(body):
            return ("noise", 1.0)
        # short but doesn't match opener → leave to LLM (could be legit one-line journal)
        return None
    if filename and _TEST_FILENAME.match(filename) and len(body) < 200:
        return ("noise", 1.0)
    if _OPENERS.match(body) and "\n" not in body and len(body) < 80:
        return ("noise", 1.0)
    return None
```

**Additional patterns worth considering (from existing vault structures elsewhere in the codebase):**
- Discord-thread-id files: pure-numeric content (`ops/discord-threads.md` is a list of bare integers, one per line). The sweeper must skip `ops/discord-threads.md` and any file whose entire body is integers — these are bot state, not knowledge.
- Frontmatter-only files (no body): treat as already-classified if frontmatter contains `topic`; otherwise treat as `noise`.

**Open question for planner:** does the pre-filter run on `_trash/` recovery? CONTEXT.md says no (sweeper skips `_trash/` entirely). Good — confirmed.

### 3. Embedding similarity for near-duplicate detection

**Embedding endpoint:** Reuse `litellm.aembedding` exactly as `modules/pathfinder/app/llm.py::embed_texts` does. `[VERIFIED: modules/pathfinder/app/llm.py L402-481]`.

```python
async def embed_texts(texts: list[str], model: str, api_base: str | None = None) -> list[list[float]]:
    litellm_model = model if "/" in model else f"openai/{model}"
    resp = await litellm.aembedding(model=litellm_model, input=texts, api_base=api_base, timeout=60.0)
    data = resp["data"] if isinstance(resp, dict) else resp.data
    return [[float(x) for x in (item["embedding"] if isinstance(item, dict) else item.embedding)] for item in data]
```

Model: `text-embedding-nomic-embed-text-v1.5` via LM Studio (already proven at scale in pf2e rules retrieval — 148 chunks). Vector dim: 768.

**De-dup algorithm (N=100..1000 — full pairwise is fine):**

```python
import numpy as np
# vectors: shape (N, 768), already L2-normalized? No — pathfinder cosine handles raw vectors.
def find_dup_clusters(matrix: np.ndarray, threshold: float = 0.92) -> list[list[int]]:
    """Return groups of indices where every pair has cosine >= threshold.
    Uses pathfinder's cosine_similarity (handles zero-norm rows safely)."""
    from app.services.note_embedding import cosine_similarity  # ported from rules.py
    n = matrix.shape[0]
    # full pairwise: n*(n-1)/2 = 499,500 comparisons at N=1000 — < 1s on numpy
    sim = matrix @ matrix.T  # raw dot, then normalize per-row
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    safe = np.where(norms == 0.0, 1.0, norms)
    sim = sim / (safe * safe.T)
    np.fill_diagonal(sim, 0.0)  # never match self
    # union-find / connected components on (sim >= threshold)
    visited = set()
    clusters = []
    for i in range(n):
        if i in visited: continue
        cluster = [i]
        stack = [i]
        while stack:
            j = stack.pop()
            for k in np.where(sim[j] >= threshold)[0]:
                if k not in visited:
                    visited.add(int(k))
                    cluster.append(int(k))
                    stack.append(int(k))
        if len(cluster) > 1:
            clusters.append(cluster)
        visited.add(i)
    return clusters
```

**Per-cluster keeper rule (from CONTEXT.md):** keep the older note with longer content; move the rest to `_trash/`. Concrete: `keeper = max(cluster, key=lambda idx: (-mtime[idx], len(body[idx])))` — older wins on first key (negative mtime), longer wins on tie.

**Caching:** copy pathfinder's frontmatter base64 pattern. `[VERIFIED: modules/pathfinder/app/rules.py L564-592 _encode/_decode_query_embedding]`

```yaml
---
topic: reference
embedding_model: text-embedding-nomic-embed-text-v1.5
embedding_b64: <base64 of float32 little-endian bytes>
sweep_pass: 2026-04-27T12:34:56Z
---
```

On re-sweep, decode `embedding_b64` from frontmatter; only re-embed if missing or `embedding_model` changed. **Do NOT use a sidecar `_meta/embeddings.json`** — frontmatter pattern is already proven, atomic per-note (no merge conflicts), and survives note-rename.

### 4. Obsidian REST API gaps for the sweeper

**Verified via official docs (https://github.com/coddingtonbear/obsidian-local-rest-api):**

| Need | Endpoint | Status |
|------|----------|--------|
| List directory | `GET /vault/{path}/` | Non-recursive — top level only `[CITED: github.com/coddingtonbear/obsidian-local-rest-api]` |
| Recursive walk | — | **Not supported.** Must walk per-directory. |
| Move/rename | — | **No native endpoint.** Implement as `PUT /vault/{new_path}` + `DELETE /vault/{old_path}` (in that order — copy first, then delete; if delete fails after copy, log and continue — duplicate is recoverable, lost data is not). |
| Read | `GET /vault/{path}` | OK |
| Write | `PUT /vault/{path}` | OK (creates or replaces — see Pitfall 1) |
| Delete | `DELETE /vault/{path}` | OK |
| PATCH targets | heading / block / frontmatter | Only safe on **existing** fields (per `project_obsidian_patch_constraint` memory — replace-on-missing fails 400). For new frontmatter fields use GET-then-PUT. |

**Recursive walk algorithm:**

```python
async def walk_vault(client: ObsidianClient, root: str = "") -> AsyncIterator[str]:
    """Yield every .md file path under root. Skips _trash/ subtree (D-decision)."""
    queue = [root]
    while queue:
        dir_path = queue.pop(0)
        if dir_path.startswith("_trash"):  # CONTEXT.md: never recurse into _trash/
            continue
        listing = await client.list_directory(dir_path)  # NEW method
        for entry in listing:
            # entries ending with "/" are subdirs; others are files
            full = f"{dir_path}/{entry}".strip("/")
            if entry.endswith("/"):
                queue.append(full)
            elif entry.endswith(".md"):
                yield full
```

**`ObsidianClient.list_directory()` — new method to add:**

```python
async def list_directory(self, path: str = "") -> list[str]:
    """GET /vault/{path}/ — returns mixed list of filenames + subdir names (subdirs end with '/').
    Returns [] on 404 or any error (graceful degrade)."""
    async def _inner():
        url = f"{self._base_url}/vault/{path}/" if path else f"{self._base_url}/vault/"
        resp = await self._client.get(url, headers=self._headers, timeout=10.0)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        files = data if isinstance(data, list) else data.get("files", [])
        return [f if isinstance(f, str) else f.get("path", "") for f in files]
    return await self._safe_request(_inner(), [], "list_directory")
```

**Idempotent skip during sweep:** read each note's frontmatter; if `sweep_pass` matches today's date AND `topic` is set AND `embedding_b64` is present, skip without re-embedding. This collapses unchanged-note cost to a single GET per note. `--force-reclassify` flag bypasses the skip.

**Move-to-trash semantics:**

```python
async def move_to_trash(client, src_path: str, reason: str) -> None:
    """PUT to _trash/{date}/{filename}, then DELETE src. Both via Obsidian REST."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = src_path.rsplit("/", 1)[-1]
    dst = f"_trash/{today}/{filename}"
    body = await client.read_note(src_path)
    # Annotate with trash metadata before write — append a frontmatter field
    body_with_meta = _annotate_trash(body, original_path=src_path, reason=reason, sweep_at=_iso_now())
    await client.write_note(dst, body_with_meta)
    await client.delete_note(src_path)
```

**Filename collisions in `_trash/{date}/`:** if `_trash/2026-04-27/foo.md` already exists, suffix with hash (`foo-{8hex}.md`) — never overwrite an existing trash entry.

### 5. Interactive resolution via the inbox file

**File path:** `inbox/_pending-classification.md` — the leading underscore prevents Obsidian's daily-note plugins from touching it and orders it first in the file tree.

**Format (human-editable + bot-parseable):**

```markdown
---
type: pending-classification-inbox
updated: 2026-04-27T12:34:56Z
---

# Pending Classification

Edit the `topic:` field on any entry to file it; the bot picks up changes on the next `:inbox`.
Or use `:inbox classify <n> <topic>` / `:inbox discard <n>` from Discord.

## Entry 1
- timestamp: 2026-04-27T11:00:00Z
- topic: unsure
- suggested: reference, observation
- confidence: 0.4
- reasoning: Looks like a discrete fact but uncertain whether it's about you or the world.

> Finished the sing-better course. Took 6 weeks.

## Entry 2
- timestamp: 2026-04-27T11:05:00Z
- topic: unsure
- suggested: journal
- confidence: 0.3
- reasoning: Reflective tone, no concrete claim.

> Feeling stuck on the bridge passage.
```

**Parser:** split body on `^## Entry \d+$` boundaries (regex `re.split(r"^## Entry \d+\s*$", body, flags=re.MULTILINE)`). Within each section: parse `- key: value` lines (YAML-ish but flat), grab the `> quoted` block as `candidate_text`. Pydantic model `PendingEntry { entry_n: int, timestamp: str, topic: str, suggested: list[str], confidence: float, reasoning: str, candidate_text: str }`.

**Concurrency / conflict resolution (MEDIUM confidence):**

The user can edit the inbox in Obsidian while the bot is mid-write. Three viable strategies:

| Strategy | Pros | Cons |
|----------|------|------|
| **Last-writer-wins** (read → modify → PUT) | Simplest. Matches existing pattern in `_persist_thread_id` (PATCH append). | User edits during a multi-second LLM round-trip can be silently overwritten. |
| **Read-modify-write with content-hash precheck** | Detects concurrent edits; bot aborts and retries on hash mismatch. | Adds an extra GET. ~10 LOC. |
| **PATCH append-only for additions, GET-PUT only for resolution** | Bot adds entries via `Obsidian-API-Content-Insertion-Position: end` (no body race); resolution still GET-PUT but small window. | Mixes two write paths; harder to keep formatting consistent. |

**Recommendation:** Start with last-writer-wins for adds (PATCH append with `Obsidian-API-Content-Insertion-Position: end` — already used in `_persist_thread_id` at `bot.py:1303`), and read-modify-write with content-hash precheck for `:inbox classify N <topic>` and `:inbox discard N`. The classify/discard window is the only real race risk because it modifies existing content; appends are safe via the PATCH-end pattern.

`[ASSUMED]` PATCH with `Obsidian-API-Content-Insertion-Position: end` works on a markdown file without a heading anchor when the target is the whole document. This is consistent with the existing `_persist_thread_id` usage but the official docs don't make the no-target case fully explicit. Verify in plan via a smoke test.

**`:inbox classify N <topic>` flow:**
1. GET inbox file → parse → find Entry N
2. Build target note path: `{topic_dir}/{title_slug}-{date}.md` from Entry N's candidate_text (call classifier with explicit `user_topic=topic` to get a clean title_slug)
3. PUT target note (graceful on collision: append `-{8hex}` suffix)
4. Remove Entry N from inbox body, renumber subsequent entries
5. PUT inbox file (with content-hash precheck — re-GET, hash, abort if changed)

### 6. `:vault-sweep` admin gate

**Today's reality:** there is **no user-id allowlist** in `bot.py`. The only access control is `DISCORD_ALLOWED_CHANNELS` (channel-level) at `bot.py:81-90`. `[VERIFIED: grep DISCORD_USER\|allowed_users\|admin returns 0 matches in bot.py]`

**Least-invasive gate:**

```python
# at module top, near DISCORD_ALLOWED_CHANNELS_RAW
SENTINEL_ADMIN_USER_IDS_RAW = os.environ.get("SENTINEL_ADMIN_USER_IDS", "")
ADMIN_USER_IDS: frozenset[str] = frozenset(
    uid.strip() for uid in SENTINEL_ADMIN_USER_IDS_RAW.split(",") if uid.strip()
)

def _is_admin(user_id: str) -> bool:
    """If allowlist is empty (unset env), refuse all (fail-closed for admin gate)."""
    return bool(ADMIN_USER_IDS) and user_id in ADMIN_USER_IDS
```

In `handle_sentask_subcommand`:

```python
if subcmd == "vault-sweep":
    if not _is_admin(user_id):
        return "Admin only. Set SENTINEL_ADMIN_USER_IDS in your env to use this command."
    return await _vault_sweep_dispatch(args, user_id)
```

**Fail-closed default** (empty env → no admins) is the correct posture for a destructive-feeling op, even though sweep moves to `_trash/` rather than deleting. If the user wants the sweeper open to all, they explicitly set `SENTINEL_ADMIN_USER_IDS=*` and we add a `*` shortcut. Document the env var in `.env.example` and `secrets/README.md`.

`user_id` is `str(message.author.id)` per `bot.py:1452`, which is a stable Discord snowflake — perfect for a fixed allowlist.

### 7. Pitfalls / gotchas

#### Pitfall 1: PUT replaces silently — sweep idempotency depends on it

Obsidian `PUT /vault/{path}` creates-or-replaces. If two sweep passes overlap (e.g. user runs `:vault-sweep` twice quickly), the second pass's writes silently overwrite the first's annotations. **Mitigation:** lock via a sentinel file `ops/sweeps/_in-progress.md` written at sweep start, deleted at end. Refuse to start a second sweep if the lockfile exists with mtime < 1h ago. Stale lock (>1h) → log warning, take over. `[VERIFIED: pattern matches phase 32 G-1 cache-aside discipline]`

#### Pitfall 2: PATCH replace-on-missing field returns 400

From `project_obsidian_patch_constraint` memory: PATCH frontmatter operation `replace` on a field that doesn't exist returns HTTP 400. The sweeper writes new fields (`topic`, `confidence`, `embedding_b64`, `sweep_pass`) that aren't in legacy notes. **Use GET-then-PUT, never PATCH**, for any sweep-classified note write. Pathfinder learned this — see `modules/pathfinder/app/routes/rule.py` D-14 comment ("D-14: update last_reused_at, GET-then-PUT (NEVER the surgical PATCH — L-3)").

#### Pitfall 3: Embedding endpoint down → partial sweep

If LM Studio is offline mid-sweep, `embed_texts` raises. **Mitigation (matches CONTEXT.md "no deferral" rule):** skip the embedding step on failure (log WARNING per note), still write `topic`/`confidence`/`sweep_pass` frontmatter. The note remains classified but un-deduped; next sweep retries the embedding via the "missing `embedding_b64` → re-embed" path described in §3. Do not block the whole sweep — the user wants the categorical classification work to complete even if de-dup degrades.

#### Pitfall 4: numpy + PyYAML in sentinel-core image

`project_dockerfile_deps` memory: adding a Python dep requires dual-ship in `pyproject.toml` AND `Dockerfile` or container restart-loops on `ModuleNotFoundError`. sentinel-core does not currently import numpy. The classifier service needs it for cosine similarity. **Plan must include**: bump `sentinel-core/pyproject.toml` AND `sentinel-core/Dockerfile` together, plus a regression smoke test (`test_numpy_importable`) following the Phase 32 G-1 / Phase 33-01 pattern.

#### Pitfall 5: Sweeper churn on bot-generated notes

The sweeper would naively reclassify every `ops/sessions/*/*.md` (transcripts) and `ops/observations/*.md` (observations) on first run, potentially moving them to topics they don't belong to. **Mitigation:**
- Skip any path under `ops/sessions/` (transcripts are not knowledge — already covered by `:remember`/`:note observation` paths).
- Skip any path under `pf2e/` (out of scope per CONTEXT.md: "No Foundry / pf2e module concern").
- Skip any path under `_trash/`.
- Skip any note whose existing `source` frontmatter is `note-import` or `vault-sweep` AND `sweep_pass` is the current run's timestamp (already-this-pass skip).

Concrete `_should_skip(path: str, frontmatter: dict, current_pass: str) -> bool` helper goes in `note_classifier.py`.

#### Pitfall 6: numbered-list renumbering after `:inbox classify N`

Entry numbering is positional (1..N). When entry 3 is filed/discarded, entries 4..N must shift down. If the user's next command is `:inbox classify 5 reference` referring to the OLD numbering, the bot files the wrong entry. **Mitigation:** the bot's response to `:inbox classify N` includes the new state of the inbox (or a "now showing the renumbered list" footer), and the user is expected to re-read `:inbox` before issuing another classify. Alternatively: address entries by stable timestamp instead of index — `:inbox classify 11:00 reference`. **Recommendation:** keep positional indexing for v1 (matches CONTEXT.md C2 listing format), document the renumbering in the response text.

#### Pitfall 7: Already-this-pass loop on cluster moves

When the sweeper finds a duplicate cluster and moves N-1 of them to `_trash/`, those moves must NOT count toward the next-iteration walk. The walk should be **frozen at start** (collect the full file list, then process), not re-listed per file. Otherwise the queue could include `_trash/` entries we just wrote. The `walk_vault` algorithm in §4 already handles this by skipping `_trash/` at queue-pop time.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Cosine similarity | Naive Python loop | numpy + the `cosine_similarity` function in `modules/pathfinder/app/rules.py` (copy it; it handles zero-norm rows safely) |
| Frontmatter parse/dump | Hand-rolled YAML | `yaml.safe_load` + `yaml.dump(sort_keys=False, allow_unicode=True, default_flow_style=False)` — same pattern as `build_ruling_markdown` |
| LLM stop sequences | Hand-coded per model | `sentinel_shared.model_profiles.get_profile(model_id, api_base)` + the (to-be-ported) `acompletion_with_profile` wrapper |
| Slug generation | Hand-rolled regex | Reuse `app.routes.npc.slugify` (already cross-imported by pathfinder rules) — or copy into a sentinel-core helper to keep modules decoupled |
| Embedding base64 codec | Custom | Copy `_encode_query_embedding` / `_decode_query_embedding` from `modules/pathfinder/app/rules.py` |
| Discord subcommand dispatch | New router | Extend `interfaces/discord/bot.py::handle_sentask_subcommand` — same pattern as `:remember`, `:capture`, `:plugin:*` |

## Code Examples

### Classify-and-file flow (sentinel-core route handler shape)

```python
# sentinel-core/app/routes/note.py
@router.post("/note/classify")
async def classify_and_file(req: ClassifyRequest, request: Request) -> ClassifyResponse:
    obsidian = request.app.state.obsidian_client
    classifier = request.app.state.note_classifier  # singleton from lifespan

    result = await classifier.classify(req.content, user_topic=req.topic)

    if result.topic == "noise":
        return ClassifyResponse(action="dropped", reason="cheap-filter:noise")

    if result.confidence < 0.5 or result.topic == "unsure":
        await _append_to_inbox(obsidian, req.content, result)
        return ClassifyResponse(action="inboxed", topic=result.topic, confidence=result.confidence)

    # High/medium confidence → file directly
    target_path = _topic_path(result.topic, result.title_slug)
    body = _build_note_markdown(req.content, result, source="note-import")
    await obsidian.write_note(target_path, body)  # NEW method (not write_session_summary)
    return ClassifyResponse(action="filed", path=target_path,
                            topic=result.topic, confidence=result.confidence)
```

### Frontmatter for filed notes

```yaml
---
topic: reference
title_slug: pf2e-monster-core-release
confidence: 0.9
created: 2026-04-27T12:34:56Z
source: note-import   # or 'vault-sweep' or 'legacy'
embedding_model: text-embedding-nomic-embed-text-v1.5  # only present for sweep-classified
embedding_b64: <base64>                                  # only present for sweep-classified
sweep_pass: 2026-04-27T12:34:56Z                         # only present for sweep-classified
---

# {first 60 chars of content as title}

{verbatim content}
```

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | PATCH with `Obsidian-API-Content-Insertion-Position: end` works on a target-less file (whole-document append). | §5 inbox concurrency | If wrong: bot can't append entries via PATCH — fall back to GET-then-PUT for adds too. Adds one round-trip, not blocking. |
| A2 | LM Studio's nomic-embed-text-v1.5 endpoint stays available; embedding the full vault (≤1000 notes × 1 vector each) completes in < 60s. | §3 de-dup | If wrong: sweep degrades (no de-dup), but classification proceeds (Pitfall 3 mitigation). |
| A3 | sentinel-core's `select_model("structured")` returns a JSON-mode-capable model when LM Studio has any function-calling model loaded. | §1 classifier | If wrong: classifier returns malformed JSON → coerce to `unsure` (graceful degrade is already designed in). |
| A4 | A flat 7-category taxonomy is what the user really wants (locked in CONTEXT.md Q1 → B). | §1 classifier | Already user-confirmed in CONTEXT.md; no risk. |
| A5 | The fail-closed admin-gate default (empty env → no admins) is acceptable. The user is the operator and will set the env var. | §6 admin gate | If wrong: user can't run `:vault-sweep` at first deploy; they read the error message and set the env var. Self-correcting. |

## Open Questions

1. **Port `acompletion_with_profile` to `sentinel_shared` vs duplicate?**
   - Pathfinder's wrapper is generic and battle-tested.
   - Sentinel-core has no equivalent today.
   - Recommendation: port to `shared/sentinel_shared/llm_call.py`. Update pathfinder's import path in the same task or a follow-up. Planner decision.

2. **Port `ResolvedModel` + `resolve()` to sentinel-core?**
   - Pathfinder has `resolve_model.py::resolve()` returning `(model, profile, api_base)` bundle.
   - Sentinel-core has the constituent pieces (`select_model`, `model_profiles.get_profile`, `settings.litellm_api_base`) but no bundle.
   - Recommendation: yes, copy the 30-LOC bundle into `sentinel-core/app/services/note_classifier.py` (or a sibling module) — promoting it to `sentinel_shared` is the cleaner DRY play but expands scope.

3. **Inbox renumbering UX:** keep positional (1..N) and re-display after each operation, or switch to timestamp-based addressing? Recommendation: positional for v1; revisit if user friction emerges.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| LM Studio `/v1/embeddings` | Sweeper de-dup | ✓ (proven in pf2e) | nomic-embed-text-v1.5 | Skip de-dup, classify-only (Pitfall 3) |
| LM Studio chat (structured/JSON mode) | Classifier | ✓ | per `model_selector("structured")` | Coerce-to-`unsure` on parse failure |
| Obsidian REST API | All vault I/O | ✓ | non-encrypted port 27123 | None — feature blocks if Obsidian is down |
| numpy in sentinel-core image | Cosine similarity | ✗ — must be added | — | Dual-ship in pyproject + Dockerfile |

## Sources

### Primary (HIGH confidence)
- `modules/pathfinder/app/rules.py` (cosine, embedding b64, frontmatter pattern)
- `modules/pathfinder/app/llm.py::embed_texts`, `classify_rule_topic`
- `modules/pathfinder/app/llm_call.py::acompletion_with_profile`
- `modules/pathfinder/app/resolve_model.py::resolve`
- `sentinel-core/app/services/model_selector.py`, `model_registry.py`
- `sentinel-core/app/clients/obsidian.py` (existing client surface)
- `interfaces/discord/bot.py:1187-1294` (subcommand dispatch), `:1300-1313` (PATCH-append pattern)
- `shared/sentinel_shared/model_profiles.py`
- Local filesystem inspection of `/Users/trekkie/projects/2ndbrain/mnemosyne/`

### Secondary (MEDIUM confidence)
- https://github.com/coddingtonbear/obsidian-local-rest-api — confirmed endpoint inventory; no native move/recursive-list
- https://coddingtonbear.github.io/obsidian-local-rest-api/ — Swagger reference

### Memory
- `project_obsidian_patch_constraint` (PATCH replace-on-missing returns 400 — use GET-then-PUT)
- `project_dockerfile_deps` (dual-ship pyproject + Dockerfile or restart-loop)

## Metadata

- Standard stack: HIGH — every dependency already in the repo with verified version
- Architecture: HIGH — service boundaries match existing patterns 1:1
- Pitfalls: HIGH — each pitfall has either a code precedent or a memory entry
- Inbox concurrency: MEDIUM — A1 (PATCH whole-document append) needs smoke-test confirmation in plan

**Research date:** 2026-04-27
**Valid until:** 2026-05-04 (LM Studio model loadout and Obsidian plugin version are stable; no library upgrades in flight)
