# Stack Research

**Domain:** Agentic note-taking engine (arscontexta + BASB) added to an existing Python/FastAPI/Obsidian-REST/litellm system
**Researched:** 2026-07-05
**Confidence:** MEDIUM-HIGH (existing-code claims verified by direct read; arscontexta claims verified via raw GitHub file fetch, tool-classified LOW-confidence provider — cross-check against the live repo before implementation)

## Headline Recommendation

**Zero new runtime dependencies are required.** Every capability the v0.6.0 milestone needs — `_schema` block parsing, wikilink extraction, graph analysis (orphans/backlinks/density), MOC generation, and 6 Rs pipeline orchestration — is achievable by extending code patterns *already present* in `sentinel-core/app/` using dependencies *already pinned* in `sentinel-core/pyproject.toml` (`PyYAML>=6.0,<7.0`, `pydantic>=2.7.0`, stdlib `re`/`json`/`asyncio`). This matches arscontexta's own design philosophy: the upstream project itself ships as a Claude Code plugin built from **shell + `ripgrep` + prompting**, not a parsing/graph library — confirming that this problem space does not require heavyweight tooling even in its reference implementation.

## Recommended Stack

### Core Technologies (already present — no change)

| Technology | Version (pinned) | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| PyYAML | `>=6.0,<7.0` (latest release 6.0.3, verified current) | Parse/emit `---`-fenced YAML blocks | Already the sole YAML engine in `app/markdown_frontmatter.py`; extending it to a second (footer) fenced block is a same-file addition, not a new dependency |
| pydantic | `>=2.7.0` | Validate the parsed `_schema` dict shape (`type`, `hub`, `status` enums) | Already a hard FastAPI dependency; a `NoteSchema(BaseModel)` with `Literal[...]` fields gives `:check`/`:review` real validation errors for free — no new validation library needed |
| stdlib `re` | 3.12/3.13 stdlib | Wikilink extraction (`[[Note Title]]`, optional alias `[[Note Title\|alias]]`), claim-title / footer-block anchoring | Wikilink syntax is a fixed, simple grammar; a compiled regex constant (same pattern as the existing `_FRONTMATTER_RE` module constant) is sufficient and matches the codebase's established style |
| stdlib `json` | 3.12/3.13 stdlib | Persist a links/graph sidecar index in the Vault | Mirrors the exact precedent set by `app/services/embedding_sidecar_index.py` (`ops/sweeps/embedding-index.json`) — same encode/decode-via-fenced-code-block pattern for markdown-hosted JSON |
| stdlib `asyncio` + existing `TaskRunner` Protocol (`app/services/task_runner.py`) | 3.12/3.13 stdlib | Background execution of `:ralph`, `:pipeline`, `:reweave` | The codebase already has an `AsyncioTaskRunner.schedule()` seam used by the sweeper (`note_sweep_runner.py`); the 6 Rs commands fire-and-log through the same seam rather than blocking the Discord response |
| litellm (existing) | `>=1.83.0,<2.0` | AI reasoning for Reduce/Reflect/Reweave/Rethink stages, MOC/hub creation, `:connect` matching | Per phase-10 spec D-13, the 6 Rs pipeline is **prompt-driven**, not a deterministic code pipeline: `:ralph`/`:pipeline` send one constructed prompt to `call_core()` and let the model do the orchestration using vault context it already has — no new AI/orchestration library needed |

### Supporting additions (new *code*, zero new *dependencies*)

| Addition | Where | Purpose | When to Use |
|----------|-------|---------|-------------|
| `split_footer_schema()` / `join_footer_schema()` | Extend `app/markdown_frontmatter.py` | Parse/emit the `_schema:` block at the **end** of a note | Symmetric to existing `split_frontmatter`/`join_frontmatter`: same `---`-fence convention, anchored at string end instead of start, same `yaml.safe_load`/`yaml.safe_dump` calls |
| `extract_wikilinks(body) -> list[str]` | New small module, e.g. `app/wikilinks.py` | Regex-extract `[[Target]]` / `[[Target\|alias]]` targets from a note body | Used by `:connect`, `:graph`, `:stats`, `:check`, and the sweeper's links-index pass |
| `NoteSchema` pydantic model | New, e.g. `app/services/note_schema.py` | Validate `type: permanent\|hub\|literature\|fleeting`, `status: draft\|ready`, presence of `hub` | Backs `:review` (single note) and `:check` (batch across `notes/`) |
| Links/graph sidecar index (`ops/sweeps/links-index.json`) | Extend `app/services/vault_sweeper.py` (or a sibling `note_sweep_runner` pass) | Precomputed adjacency: per-note outbound wikilinks + hub membership, written once per sweep | Avoids an O(n) full-`notes/`-read on every `:graph`/`:stats`/`:connect` call — same rationale as the embedding sidecar: "no per-note HTTP call at query time" |
| Hand-rolled graph metrics (orphans, backlinks, density) over the sidecar index | New, e.g. `app/services/graph_metrics.py` | `orphans = notes with 0 inbound AND no hub membership`; `backlinks[target] = [notes linking to target]` (reverse adjacency, one pass); `density = edges / notes` (or edges / possible-edges, pick one and document it) | Pure `dict`/`Counter`/`set` operations over the sidecar index; at personal-vault scale (hundreds to low thousands of notes) this is O(n) and sub-millisecond — no graph library needed |

## Installation

No `pyproject.toml` changes required. All additions are new Python modules inside `sentinel-core/app/`, not new packages.

```bash
# Nothing to install — verify the existing pins still resolve
cd sentinel-core && uv sync
```

## Alternatives Considered (and rejected)

| Capability | Recommended | Alternative considered | Why Not |
|-------------|-------------|-------------------------|---------|
| Frontmatter/schema parsing | Extend existing `app/markdown_frontmatter.py` (PyYAML, stdlib re) | `python-frontmatter` (PyPI, latest 1.3.0) | Would reintroduce exactly the triplicate-parsing problem `markdown_frontmatter.py`'s own docstring says was just consolidated away (it replaced 3 prior copies in `vault_sweeper.py`, `inbox.py`, `vault.py`). Also doesn't support a *footer* block at all — arscontexta's real format needs two fenced blocks, header and footer, which this library has no concept of. |
| Graph analysis (orphans/backlinks/density) | Hand-rolled `dict`/`set`/`Counter` over a JSON sidecar index | `networkx` (`/networkx/networkx`, stable) | Personal-vault graphs are small (hundreds–low thousands of nodes); the actual required operations (in-degree, reachability-from-hub, edge count) are a few lines of stdlib code. NetworkX adds a real dependency surface for algorithms (centrality, community detection, isomorphism) this milestone never asks for, and it still wouldn't solve wikilink extraction or REST-based note fetching — those still need to be hand-written regardless. |
| Graph analysis / vault introspection | Same as above, via the existing Vault REST seam | `obsidiantools` (PyPI) | Built around direct local-filesystem scanning of `.md` files with `pathlib`/`glob`, and pulls in `pandas` + `networkx` transitively. Architecturally incompatible with the Vault protocol's REST-only constraint (Obsidian Local REST API, no local mount — see `app/vault.py` / ADR-0002); would require bypassing the sole persistence seam. |
| 6 Rs pipeline / batch orchestration | Existing `AsyncioTaskRunner` (`app/services/task_runner.py`) fire-and-forget seam | `APScheduler` / `Celery` / `RQ` | No periodic or distributed-worker requirement exists: `:ralph`/`:pipeline`/`:reweave` are user/agent-initiated commands, exactly like the existing `/vault/sweep` endpoint trigger. Per D-13, there is explicitly "no bot-side iteration loop" — the single in-process `asyncio.create_task()` seam already used by the sweeper is sufficient and consistent. |
| Note body structure extraction | Targeted regex (frontmatter, footer schema, wikilinks, `#` heading) | `markdown-it-py` / `mistune` (full Markdown AST parsers) | Sentinel Core never renders note bodies to HTML or needs a full AST — it only needs to locate a handful of fixed syntactic patterns. This is the same reasoning the codebase already applied for frontmatter (`_FRONTMATTER_RE`, a single compiled regex, not a parser). |
| `_schema` shape validation | `pydantic.BaseModel` (already a dependency) | `jsonschema` / `voluptuous` | Pydantic is already a hard FastAPI dependency and directly produces the field-level validation errors `:review`/`:check` need to report — adding a second validation library for one small dict shape is pure duplication. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|--------------|
| `networkx` | Heavy dependency surface (algorithms for centrality/isomorphism/community detection this milestone never needs) for a graph that fits comfortably in a `dict` at personal-vault scale | Hand-rolled adjacency over the `ops/sweeps/links-index.json` sidecar (see above) |
| `python-frontmatter` / `frontmatter` (PyPI) | Duplicates `app/markdown_frontmatter.py`'s already-consolidated single-source-of-truth parser; has no concept of a *footer* schema block (arscontexta needs both header and footer fences) | Extend `app/markdown_frontmatter.py` with symmetric `split_footer_schema`/`join_footer_schema` |
| `obsidiantools` | Assumes direct local filesystem access to the vault (pathlib/glob scanning); the Vault is REST-only by design (Obsidian Local REST API, no local mount) — using it would mean bypassing the `Vault` Protocol seam entirely | Read note bodies via the existing `Vault` seam (`search_vault`, `read`/`get_user_context`-style calls) and parse with the hand-rolled regex/YAML helpers above |
| `APScheduler` / `Celery` / `RQ` | No periodic or multi-worker job requirement in this milestone's design (D-13: pipeline commands are single-prompt, agent-orchestrated, user/command-triggered, not scheduled) | Existing `AsyncioTaskRunner.schedule()` seam (`asyncio.create_task`) |
| `markdown-it-py` / `mistune` | Full Markdown→AST/HTML parsing is unnecessary; Sentinel Core never renders notes, it only extracts a few fixed patterns (frontmatter, footer schema, wikilinks) | Targeted compiled regex, same style as `_FRONTMATTER_RE` |
| Anthropic/Claude API as the pipeline's LLM | Hard constraint carried over from the phase-10 CONTEXT decisions: no `anthropic` SDK / `claude-*` calls in this feature's processing path — all 6 Rs AI processing goes through the existing local LM Studio / litellm provider path | `litellm` with the existing LM Studio provider config (`host.docker.internal:1234`) |

## Stack Patterns by Variant

**If the vault grows beyond a few thousand notes** (well beyond current personal-tool scale):
- Revisit the hand-rolled graph metrics decision; at that scale, `networkx` (or even a proper graph database) might earn its dependency cost for centrality-style queries. Not a concern for v0.6.0.

**If a future phase wants scheduled/periodic vault maintenance** (e.g. nightly auto-`:reweave`):
- That is explicitly out of this milestone's scope (D-13's design is command-triggered, not scheduled). If it becomes a requirement later, evaluate a minimal in-process scheduler (e.g. a simple `asyncio` loop with `asyncio.sleep`) before reaching for `APScheduler` — the operational scale (single operator, single vault) still doesn't justify a scheduling framework.

**If `_schema` needs richer typed fields beyond `type`/`hub`/`status`** (e.g. tags, confidence, source):
- Extend the `NoteSchema` pydantic model's fields — pydantic already supports optional fields, nested models, and custom validators, so this scales without adding a dependency.

## Version Compatibility

| Package | Compatible With | Notes |
|-----------|-----------------|-------|
| `PyYAML>=6.0,<7.0` | Python 3.12/3.13 | 6.0.3 is current (adds Python 3.14 + free-threading support); existing pin already covers it, no bump needed |
| `pydantic>=2.7.0` | Python 3.12/3.13, FastAPI `>=0.135.0` | Already exercised across the codebase for request/response models; `Literal[...]` + `BaseModel` is enough for `_schema` validation, no `pydantic-yaml` needed |
| Existing `AsyncioTaskRunner` Protocol | Any Python 3.12+ | No version dependency; it's in-repo code, not a package |

## Integration Points With Existing Stack

- **Vault seam (`app/vault.py`)**: all new reads (note bodies for wikilink/schema extraction) and writes (the links-index sidecar, moved/reweaved notes) MUST go through this Protocol — do not add any direct-filesystem or direct-REST-client code path (ADR-0002).
- **Sweeper (`app/services/vault_sweeper.py`, `note_sweep_runner.py`)**: extend the existing sweep pass to also compute and persist the links-index sidecar in the same pass that already computes embeddings — one vault-read pass serving two indexes, not two.
- **`markdown_frontmatter.py`**: the natural home for the new footer-schema split/join pair; keep it as the single SPOT for both frontmatter and `_schema` parsing, consistent with its existing docstring intent ("single source of truth").
- **`TaskRunner` Protocol**: `:ralph`/`:pipeline`/`:reweave` command handlers schedule work through this seam so the Discord response returns immediately and the pipeline logs via the existing `BackgroundTasks`/best-effort-write pattern already used for session summaries.
- **Discord bot (`interfaces/discord/bot.py`)**: the 27-command routing (`_SUBCOMMAND_PROMPTS` + new `_PLUGIN_PROMPTS`, `:plugin:` prefix check per D-12) is pure extension of the existing dict-based router — no new dependency, and it lives outside `sentinel-core` entirely.

## Sources

- `/yaml/pyyaml` (Context7, confidence MEDIUM) — confirmed PyYAML API stability; version cross-checked via web search (pypi.org, github.com/yaml/pyyaml/releases) — 6.0.3 current, already within the existing `>=6.0,<7.0` pin
- `/networkx/networkx` (Context7, confidence MEDIUM) — confirmed NetworkX is a general-purpose graph library, used to ground the "rejected as overkill" analysis
- Direct file reads (confidence HIGH — primary source, own repo): `sentinel-core/pyproject.toml`, `sentinel-core/app/markdown_frontmatter.py`, `sentinel-core/app/services/embedding_sidecar_index.py`, `sentinel-core/app/services/task_runner.py`, `sentinel-core/app/services/note_sweep_runner.py` — used to confirm existing dependency pins and established code patterns to extend rather than duplicate
- `https://github.com/agenticnotetaking/arscontexta` and `reference/kernel.yaml`, `reference/three-spaces.md`, `reference/templates/base-note.md`, `reference/templates/moc.md` (WebFetch, tool-classified confidence LOW — cross-check against the live repo before implementation) — confirmed: (1) arscontexta itself is a shell/ripgrep/prompt-driven Claude Code plugin with no parsing or graph library, (2) the real note format uses a `---`-fenced **footer** block (not a special schema fence) for topics/hub membership, symmetric to the header frontmatter fence — this directly informed the `split_footer_schema`/`join_footer_schema` recommendation
- `python-frontmatter`, `obsidiantools` (WebSearch, confidence LOW, used only to identify and then reject alternatives — versions and dependency footprints per pypi.org listings)
- `.planning/PROJECT.md`, `docs/2nd-brain-original-design/10-CONTEXT-master-spec.md` (project's own recovered design spec, confidence HIGH as primary source of requirements)

---
*Stack research for: arscontexta+BASB note-taking core on existing Sentinel Core (FastAPI/Obsidian-REST/litellm/numpy) stack*
*Researched: 2026-07-05*
