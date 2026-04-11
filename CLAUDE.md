<!-- GSD:project-start source:PROJECT.md -->
## Project

**Sentinel of Mnemosyne**

A self-hosted, containerized AI assistant platform built for personal use. The Sentinel wires together a local AI engine (LM Studio on a Mac Mini), an Obsidian vault as persistent memory, and pluggable interface/module containers — so the same engine can serve as a DM co-pilot, music practice journal, finance tracker, or autonomous stock trader depending on what you attach to it.

**Core Value:** A message goes in, an AI response that knows your history comes back — and what mattered gets written to Obsidian so the next conversation starts smarter.

### Constraints

- **Tech Stack**: Python/FastAPI for Sentinel Core — fits the AI/automation ecosystem, async handles concurrent interfaces cleanly
- **Tech Stack**: Node.js 22 LTS for Pi harness container — pi-mono requires >=20.6.0; Node 22 LTS is the correct choice (Node 24 is not yet LTS)
- **Tech Stack**: Docker Compose with `include` directive (Compose v2.20+) — preferred over `-f` flag stacking; resolves paths relative to each included file's directory
- **Dependencies**: Pi harness is a black box in v0.x — call it cleanly, do not modify it
- **Dependencies**: Obsidian must be running on the Mac for the REST API to be available — cannot be containerized
- **Dependencies**: LM Studio must have a model loaded before the Sentinel can respond — operational dependency, not a code dependency
- **Security**: Shared secret token (`X-Sentinel-Key`) for interface authentication — sufficient for personal local-network use, not enterprise-grade
- **Trading**: Live trading module requires explicit opt-in configuration — cannot be enabled accidentally; paper trading must precede live
- **Trading**: Cash-only, long-only, equities/ETFs only in v1 — no margin, no shorts, no derivatives
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Core Technologies
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 | Sentinel Core runtime | FastAPI requires 3.10+; 3.12 is the stable sweet spot (3.13 works but 3.12 has wider ecosystem testing) |
| FastAPI | ~0.135.x | HTTP API framework for Sentinel Core | Async-native, auto-generated OpenAPI docs, Pydantic v2 integration, dominant in the Python AI/automation space. No real competitor for this use case. |
| Node.js | 22 LTS | Pi harness container runtime | pi-mono requires >=20.6.0 (verified from package.json engines field). Node 22 is the current LTS. See ADR flag below regarding the Node 24 constraint. |
| Docker Compose | v2 (current) | Multi-service orchestration | Override file pattern is well-supported. Use `docker compose` (v2, no hyphen), not `docker-compose` (v1, deprecated). |
### Supporting Libraries -- Python (Sentinel Core)
| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `fastapi` | >=0.135.0 | Web framework | Current stable. Includes streaming JSONL support and strict content-type checking. |
| `uvicorn[standard]` | >=0.44.0 | ASGI server | The `[standard]` extra installs uvloop + httptools for production performance. |
| `pydantic` | >=2.7.0 | Data validation, message envelope models | Required by FastAPI. v2 is 5-50x faster than v1. Use `model_config = {"from_attributes": True}` not old `orm_mode`. |
| `pydantic-settings` | >=2.13.0 | Environment variable configuration | Loads .env files, validates config at startup, type-safe settings. Replaces hand-rolled `os.getenv()` patterns. |
| `httpx` | >=0.28.1 | Async HTTP client | For calling Obsidian REST API and LM Studio. Use `httpx.AsyncClient()` as a context manager for connection pooling. Do NOT use `requests` (blocking). |
| `discord.py` | >=2.7.0 | Discord bot interface | See Discord section below. |
| `alpaca-py` | >=0.43.0 | Alpaca trading API (paper + live) | Official SDK, replaces deprecated `alpaca-trade-api`. |
| `ofxtools` | >=0.9.5 | OFX file parsing | See OFX section below. |
### Supporting Libraries -- Node.js (Pi Harness)
| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `@mariozechner/pi-coding-agent` | Pin to 0.66.1 | AI execution layer | Latest stable as of 2025-04-08. Pin exactly; project is under active development. |
### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest` + `pytest-asyncio` | Testing | FastAPI + async requires pytest-asyncio for `async def test_*` functions |
| `httpx` | Test client | FastAPI's recommended test client (`from httpx import AsyncClient`) |
| `ruff` | Linting + formatting | Replaces black + flake8 + isort. Single tool, fast (Rust-based). |
| `mypy` | Type checking | Use with pydantic plugin (`pydantic.mypy`) for model validation |
| `docker compose watch` | Dev hot-reload | Rebuilds containers on file change. Use instead of volume-mounting source in production. |
## Installation
# Sentinel Core (Python)
# Discord interface
# Finance module
# Trading module
# Dev dependencies
# Pi harness (Node.js)
## Detailed Findings by Question
### 1. FastAPI Production Stack (HIGH confidence)
- **FastAPI** -- framework
- **Uvicorn** -- ASGI server (use `[standard]` extra for uvloop)
- **Pydantic v2** -- models, validation, settings
- **httpx** -- async HTTP client (replaces `requests`)
- **pydantic-settings** -- env var management (separate package since Pydantic v2)
### 2. Pi Harness Container -- RPC Mode (HIGH confidence)
- `{"type": "prompt", "content": "user message"}` -- send a prompt
- `{"type": "abort"}` -- stop current operation
- `{"type": "new_session"}` -- fresh conversation
- `{"type": "get_state"}` -- retrieve session state
- `{"type": "set_model", "provider": "...", "modelId": "..."}` -- switch model
- `agent_start` / `agent_end` -- conversation lifecycle
- `message_update` -- streaming text chunks
- `tool_execution_start/update/end` -- tool calls
- `turn_start` / `turn_end` -- reasoning turns
# Send a prompt
# Read events
### 3. Discord Bot Library (HIGH confidence)
- Slash commands (app_commands)
- Buttons, select menus, modals (ui components)
- Voice support
- Components v2 (latest Discord UI features)
- `py-cord` -- Fork created during the hiatus. Now redundant; less popular, smaller contributor pool.
- `disnake` -- Same story. Good library but unnecessary when discord.py is active again.
- `nextcord` -- Same story.
### 4. Apple Messages / iMessage Integration (MEDIUM confidence)
- `macpymessenger` (v0.2.0) -- modern, typed Python library wrapping AppleScript. Sends messages via the Messages app. Install: `pip install macpymessenger`
- Alternative: raw `osascript` calls from Python. macpymessenger is a thin wrapper over this.
- Poll `~/Library/Messages/chat.db` (SQLite) for new messages. This is how every iMessage integration works -- there is no push notification API.
- `imessage_reader` (PyPI) -- reads from chat.db, handles macOS Ventura's `attributedBody` hidden text issue.
- Alternative: `imessage-tools` -- similar, also handles Ventura+ attributedBody parsing.
- Full Disk Access must be granted to the Python interpreter (or Terminal.app) in System Settings
- chat.db schema changes between macOS versions -- Ventura changed where message body text lives
- No way to detect message delivery/read status programmatically
- Group chats have different handle formats
### 5. Obsidian Local REST API (HIGH confidence)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/vault/{path}` | Read a file |
| PUT | `/vault/{path}` | Create or replace a file |
| PATCH | `/vault/{path}` | Surgical edit (append, prepend, replace heading, update frontmatter) |
| DELETE | `/vault/{path}` | Delete a file |
| GET | `/vault/` | List vault contents |
| POST | `/search/simple/?query=...` | Full-text fuzzy search |
| POST | `/search/` | Dataview DQL or JsonLogic queries |
| GET | `/tags/` | List all tags with usage counts |
| GET | `/active/` | Get currently open file |
| POST | `/commands/` | Run an Obsidian command |
| GET | `/open/{path}` | Open a file in the Obsidian UI |
### 6. OFX Parsing -- ofxtools (MEDIUM confidence)
- OFX is a stable specification (hasn't changed significantly in years)
- ofxtools handles both OFXv1 (SGML) and OFXv2 (XML)
- Zero external dependencies (stdlib only)
- Converts OFX to native Python objects with proper types
### 7. Alpaca Trading SDK (HIGH confidence)
- OOP design with request/response models (Pydantic-based)
- Unified SDK covering Trading API, Market Data API, and Broker API
- Async support via httpx under the hood
### 8. Python-to-Node.js IPC Pattern (HIGH confidence)
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| FastAPI | Flask | Never for this project. Flask is sync-first; FastAPI's async is essential for concurrent interface handling. |
| httpx | requests | Never in async code. `requests` blocks the event loop. |
| httpx | aiohttp | httpx has a cleaner API, better Pydantic integration, and is FastAPI's recommended test client. |
| discord.py | py-cord / disnake | Only if discord.py development stops again (unlikely given v2.7.1 momentum). |
| ofxtools | ofxparse | ofxparse is less maintained and handles fewer OFX edge cases. |
| alpaca-py | alpaca-trade-api | Never. The old SDK is deprecated. |
| Pydantic Settings | python-dotenv | python-dotenv only loads .env files. pydantic-settings validates, type-checks, and documents all configuration. |
| Fastify (bridge) | Express | Express works fine but Fastify is faster and has better TypeScript support for new code. |
| Node 22 LTS | Node 24 | Use Node 24 if you need cutting-edge V8 features. Otherwise, Node 22 LTS is the production-safe choice. |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `requests` library | Blocks the async event loop. Will cause timeouts under concurrent load. | `httpx` with `AsyncClient` |
| `alpaca-trade-api` | Officially deprecated by Alpaca | `alpaca-py` |
| `py-cord` / `disnake` / `nextcord` | Forks created during discord.py's hiatus. Now redundant -- discord.py is active again with v2.7.x | `discord.py` |
| Pydantic v1 syntax | FastAPI dropped v1 support. `class Config: orm_mode = True` will break. | Pydantic v2: `model_config = {"from_attributes": True}` |
| `python-dotenv` alone | No validation, no type safety, silent failures on missing vars | `pydantic-settings` (loads .env AND validates) |
| `docker-compose` (v1, hyphen) | Deprecated. Docker Compose v1 is no longer maintained. | `docker compose` (v2, space, built into Docker CLI) |
| SQLite/PostgreSQL for core data | Obsidian vault IS the database. Adding a traditional DB creates data split and defeats the "human-readable markdown" principle. | Obsidian REST API for all reads/writes |
| Node.js `readline` for RPC parsing | readline splits on U+2028 and U+2029 (Unicode line separators), which are valid inside JSON strings. This breaks JSONL protocol compliance. | Manual line splitting on `\n` only |
## ADR Flags and Concerns
### Flag 1: Node.js Version Constraint (MEDIUM severity)
### Flag 2: Pi RPC Port 8765 (LOW severity)
### Flag 3: Obsidian HTTPS Self-Signed Cert (LOW severity)
### Flag 4: iMessage Interface is Mac-Native Only (MEDIUM severity)
## Version Compatibility Matrix
| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| FastAPI >=0.135.0 | Python >=3.10 | 3.12 recommended |
| FastAPI >=0.135.0 | Pydantic >=2.7.0 | Pydantic v1 NOT supported |
| Pydantic >=2.7.0 | pydantic-settings >=2.0.0 | Separate package since Pydantic v2 |
| uvicorn >=0.44.0 | Python >=3.10 | Use `[standard]` extra for uvloop |
| discord.py >=2.7.0 | Python >=3.8 | aiohttp is a dependency |
| alpaca-py >=0.43.0 | Python >=3.8 | Uses httpx internally |
| pi-coding-agent 0.66.1 | Node.js >=20.6.0 | Pin exact version |
## Sources
- [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/) -- version and Python requirements (HIGH confidence)
- [FastAPI best practices repo](https://github.com/zhanymkanov/fastapi-best-practices) -- production patterns (MEDIUM confidence)
- [pi-mono GitHub repo](https://github.com/badlogic/pi-mono) -- RPC docs, package.json, releases (HIGH confidence)
- [pi-mono RPC protocol docs](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/rpc.md) -- JSONL protocol (HIGH confidence)
- [pi-mono npm page](https://www.npmjs.com/package/@mariozechner/pi-coding-agent) -- version info (HIGH confidence)
- [discord.py PyPI](https://pypi.org/project/discord.py/) -- v2.7.1, March 2026 (HIGH confidence)
- [discord.py GitHub](https://github.com/Rapptz/discord.py) -- active development confirmed (HIGH confidence)
- [Obsidian Local REST API GitHub](https://github.com/coddingtonbear/obsidian-local-rest-api) -- endpoints, auth, v3.6.1 (HIGH confidence)
- [Obsidian Local REST API interactive docs](https://coddingtonbear.github.io/obsidian-local-rest-api/) -- Swagger/OpenAPI spec (HIGH confidence)
- [ofxtools PyPI](https://pypi.org/project/ofxtools/) -- v0.9.5 (MEDIUM confidence -- maintenance status unclear)
- [ofxtools docs](https://ofxtools.readthedocs.io/en/latest/) -- usage patterns (HIGH confidence)
- [alpaca-py GitHub](https://github.com/alpacahq/alpaca-py) -- v0.43.2, Nov 2025 (HIGH confidence)
- [Alpaca SDKs docs](https://docs.alpaca.markets/docs/sdks-and-tools) -- official recommendation to use alpaca-py (HIGH confidence)
- [macpymessenger GitHub](https://github.com/ethan-wickstrom/macpymessenger) -- iMessage sending (MEDIUM confidence)
- [imessage_reader PyPI](https://pypi.org/project/imessage-reader/) -- iMessage reading from chat.db (MEDIUM confidence)
- [httpx PyPI](https://pypi.org/project/httpx/) -- v0.28.1 (HIGH confidence)
- [pydantic-settings GitHub](https://github.com/pydantic/pydantic-settings) -- v2.13.1 (HIGH confidence)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

## Protected Files — NEVER Delete or Overwrite

The following files are immutable planning artifacts. **You are not authorised to delete, rename, move, or overwrite them.** They have been deleted silently three times by AI agents and each incident required manual recovery.

| File | Protection |
|------|-----------|
| `.planning/ROADMAP.md` | macOS `uchg` flag + PreToolUse hook + this rule |

**To update ROADMAP.md legitimately (human only):**
```bash
chflags nouchg .planning/ROADMAP.md
# make edits
chflags uchg .planning/ROADMAP.md
```

AI agents: if you believe ROADMAP.md needs updating, output the proposed change as text and stop. Do not attempt to modify the file directly.

## Git Workflow

**PROJECT OVERRIDE — This overrides the global no-main-commits rule for this project only.**

Commit directly to `main`. Do not create feature branches or pull requests for this project.

- `git add <files> && git commit -m "..."` — commit directly to main
- `git push origin main` — push directly to main
- **No PRs.** No feature branches. No `gh pr create`.

This is a personal single-developer project. The PR workflow adds friction without benefit here.

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

| Skill | Description | Path |
|-------|-------------|------|
| code-review-excellence | Master effective code review practices to provide constructive feedback, catch bugs early, and foster knowledge sharing while maintaining team morale. Use when reviewing pull requests, establishing review standards, or mentoring developers. | `.agents/skills/code-review-excellence/SKILL.md` |
| docx | "Use this skill whenever the user wants to create, read, edit, or manipulate Word documents (.docx files). Triggers include: any mention of 'Word doc', 'word document', '.docx', or requests to produce professional documents with formatting like tables of contents, headings, page numbers, or letterheads. Also use when extracting or reorganizing content from .docx files, inserting or replacing images in documents, performing find-and-replace in Word files, working with tracked changes or comments, or converting content into a polished Word document. If the user asks for a 'report', 'memo', 'letter', 'template', or similar deliverable as a Word or .docx file, use this skill. Do NOT use for PDFs, spreadsheets, Google Docs, or general coding tasks unrelated to document generation." | `.agents/skills/docx/SKILL.md` |
| error-handling-patterns | Master error handling patterns across languages including exceptions, Result types, error propagation, and graceful degradation to build resilient applications. Use when implementing error handling, designing APIs, or improving application reliability. | `.agents/skills/error-handling-patterns/SKILL.md` |
| git-advanced-workflows | Master advanced Git workflows including rebasing, cherry-picking, bisect, worktrees, and reflog to maintain clean history and recover from any situation. Use when managing complex Git histories, collaborating on feature branches, or troubleshooting repository issues. | `.agents/skills/git-advanced-workflows/SKILL.md` |
| pdf | Use this skill whenever the user wants to do anything with PDF files. This includes reading or extracting text/tables from PDFs, combining or merging multiple PDFs into one, splitting PDFs apart, rotating pages, adding watermarks, creating new PDFs, filling PDF forms, encrypting/decrypting PDFs, extracting images, and OCR on scanned PDFs to make them searchable. If the user mentions a .pdf file or asks to produce one, use this skill. | `.agents/skills/pdf/SKILL.md` |
| pptx | "Use this skill any time a .pptx file is involved in any way — as input, output, or both. This includes: creating slide decks, pitch decks, or presentations; reading, parsing, or extracting text from any .pptx file (even if the extracted content will be used elsewhere, like in an email or summary); editing, modifying, or updating existing presentations; combining or splitting slide files; working with templates, layouts, speaker notes, or comments. Trigger whenever the user mentions \"deck,\" \"slides,\" \"presentation,\" or references a .pptx filename, regardless of what they plan to do with the content afterward. If a .pptx file needs to be opened, created, or touched, use this skill." | `.agents/skills/pptx/SKILL.md` |
| skill-creator | Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, edit, or optimize an existing skill, run evals to test a skill, benchmark skill performance with variance analysis, or optimize a skill's description for better triggering accuracy. | `.agents/skills/skill-creator/SKILL.md` |
| xlsx | "Use this skill any time a spreadsheet file is the primary input or output. This means any task where the user wants to: open, read, edit, or fix an existing .xlsx, .xlsm, .csv, or .tsv file (e.g., adding columns, computing formulas, formatting, charting, cleaning messy data); create a new spreadsheet from scratch or from other data sources; or convert between tabular file formats. Trigger especially when the user references a spreadsheet file by name or path — even casually (like \"the xlsx in my downloads\") — and wants something done to it or produced from it. Also trigger for cleaning or restructuring messy tabular data files (malformed rows, misplaced headers, junk data) into proper spreadsheets. The deliverable must be a spreadsheet file. Do NOT trigger when the primary deliverable is a Word document, HTML report, standalone Python script, database pipeline, or Google Sheets API integration, even if tabular data is involved." | `.agents/skills/xlsx/SKILL.md` |
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->

## AI Deferral Ban

AI agents operating in this project cannot defer, skip, or classify-away any work item. This includes:
- Leaving `# TODO` or `# FIXME` comments instead of implementing
- Marking test findings as MEDIUM/LOW to avoid fixing them
- Using stub implementations (`pass`, `raise NotImplementedError`)
- Adding `# type: ignore` or `# noqa` suppressions without fixing the root cause
- Deciding a code review finding is "out of scope" or "for future work"

Only the human operator can defer work. If an AI agent encounters something it cannot fix, it must STOP and present the specific blocker to the human — it may not silently skip and continue.
