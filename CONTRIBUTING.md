# Contributing to Sentinel of Mnemosyne

This guide is for anyone who wants to build a new module or interface for the Sentinel — including future-you coming back six months from now having forgotten how this all fits together.

The design principle: **you should be able to add a module without touching anything in the core.** A module is a Docker container (or a few), a Docker Compose override file, and optionally an HTTP API the Core can call. That's it.

---

## Development Setup

### Prerequisites

- Python 3.12
- Docker Compose v2 (`docker compose`, not `docker-compose`)

### Clone and setup

```bash
git clone https://github.com/The-Artificer-of-Ciphers-LLC/sentinel-of-mnemosyne.git
cd sentinel-of-mnemosyne
cp .env.example .env
# Fill in your values in .env
```

### Running tests

```bash
cd sentinel-core && pytest
```

### Running the stack locally

```bash
docker compose up
```

---

## Bug Reports & Non-Module Contributions

**Bug reports:** Use the GitHub issue template (Bug Report). Include your OS, Docker version, and the LM Studio model you have loaded. The more detail the better.

**Doc improvements:** Open a PR directly — no issue needed for small fixes like typos or clarifications.

**Core changes:** Open an issue first to discuss the change before building it. Core changes affect all modules and interfaces, so it helps to align on approach before writing code.

**Security vulnerabilities:** Do not open a public issue. See [SECURITY.md](SECURITY.md) for responsible disclosure instructions.

---

## How the Sentinel Works (Quick Recap)

When a user sends a message:

1. An **interface container** receives a message and posts a JSON envelope to the Core at `POST /message`
2. The **Sentinel Core** retrieves relevant context from Obsidian and builds a prompt
3. The Core calls **LiteLLM** directly to get an AI response (LM Studio, Claude, or other configured provider)
4. The Core writes a session note to Obsidian and returns the response to the interface
5. The interface delivers it back to the user

Modules extend this flow by exposing HTTP endpoints the Core can call during step 3 (for data retrieval or specialized operations). The Pi harness is NOT in the default message path — it is an optional coding tool started with `./sentinel.sh --pi`, scoped to the v0.7 Coder module.

---

## Building a Module

### Step 1 — Define what your module does

A module is a set of capabilities the AI can invoke during a conversation. Before writing code, write a plain-English list:

- What can users ask the module to do?
- What data does it read and write?
- What Obsidian folder structure does it use?
- Does it need any external APIs or services?

### Step 2 — Create the module folder

```
modules/
└── your-module-name/
    ├── docker-compose.override.yml   ← adds your container(s) to the system
    ├── Dockerfile                    ← your container definition
    ├── requirements.txt              ← or package.json, depending on language
    └── main.py                       ← your module's main logic
```

### Step 3 — Expose an HTTP API (if your module does work on request)

If the Core needs to call your module during a conversation (e.g., to log data or look something up), expose an HTTP endpoint your module container serves. The Core calls module endpoints via the `sentinel-net` Docker network using the container name as the hostname.

Example: a music module might expose `POST http://sentinel-music:8100/log-practice` which the Core calls when the AI determines a practice session should be logged.

If your module only writes to Obsidian on its own schedule (e.g., a finance importer running a cron job), you do not need to expose any HTTP endpoints.

### Step 4 — Write your Docker Compose override

```yaml
# modules/your-module-name/docker-compose.override.yml
services:
  your-module-name:
    build: ./modules/your-module-name
    container_name: sentinel-your-module
    restart: unless-stopped
    networks:
      - sentinel-net
    environment:
      - OBSIDIAN_API_URL=${OBSIDIAN_API_URL}
      - OBSIDIAN_API_KEY=${OBSIDIAN_API_KEY}
      - ANY_MODULE_SPECIFIC_VARS=${YOUR_VAR}
```

The `sentinel-net` network is defined in the base `docker-compose.yml` — all containers must join it to communicate.

### Step 5 — Register your module endpoint with the Core (optional)

If your module exposes HTTP endpoints the Core should call, document the endpoint URL and expected request/response shape in your module's README. The Core's ProviderRouter or a module-dispatch service routes calls to registered module endpoints.

Future versions (v0.5+) will have a formal module registration API. For now, the Core calls module endpoints explicitly based on configuration.

### Step 6 — Define your Obsidian folder structure

Document what folders and file formats your module uses. Convention:

```
/mnemosyne/
  /your-module-name/
    /[logical subfolder]/
      /[filename].md
```

Every file your module writes should have YAML frontmatter with at minimum:
- `date`
- `tags` (including your module name as a tag)

This makes vault-wide search and the Core's context retrieval work correctly.

### Step 7 — Test it

```bash
# Start the system with your module
./sentinel.sh --your-module up -d

# Add --discord or --messages to test via a real interface
./sentinel.sh --discord --your-module up -d

# Check logs
docker logs sentinel-your-module
docker logs sentinel-core
```

---

## Building an Interface

An interface is simpler than a module — it's just a translation layer with no AI logic.

### Interface contract

Your interface must:

1. Accept messages from its channel (Discord, Slack, etc.)
2. Translate each message into the **Standard Message Envelope** format
3. HTTP POST the envelope to `http://sentinel-core:8000/message` with the `X-Sentinel-Key` header
4. Receive the response envelope and deliver it back to the user

### Standard Message Envelope

**Outbound (your interface → Core):**
```json
{
  "id": "uuid-v4-string",
  "source": "your-interface-name",
  "user_id": "stable-user-identifier",
  "channel_id": "where-to-reply",
  "timestamp": "ISO8601",
  "content": "the message text",
  "attachments": [],
  "metadata": {}
}
```

**Inbound (Core → your interface):**
```json
{
  "id": "uuid-v4-string",
  "reply_to": "original-message-id",
  "source": "sentinel-core",
  "timestamp": "ISO8601",
  "content": "the response text",
  "actions": [],
  "metadata": {}
}
```

The `actions` array is optional. Ignore any action types you don't recognize.

### Interface folder structure

```
interfaces/
└── your-interface-name/
    ├── docker-compose.override.yml
    ├── Dockerfile
    ├── requirements.txt
    └── main.py (or bot.py, index.js, etc.)
```

---

## Obsidian Vault Conventions

All modules should follow these conventions so the Core's context retrieval and vault-wide search stay coherent.

**Frontmatter:** Every file written by the system must have YAML frontmatter. Minimum fields:
```yaml
---
date: 2026-04-06          # ISO date or datetime
tags: [your-module, ...]  # Always include your module name as a tag
---
```

**File naming:** Use lowercase with hyphens or dates. Avoid spaces.

**Folder depth:** Keep it shallow. Two levels under your module folder is usually enough. Deep nesting makes search harder.

**Don't write to `/core/`:** That folder belongs to the Sentinel Core. Your module gets its own top-level folder.

---

## Environment Variables

Add any new environment variables your module needs to `.env.example` with a comment explaining what they're for. Never commit actual secrets to the repo.

---

## Submitting a Module

> This section applies once the project is open to community contributions.

1. Fork the repo
2. Create a branch: `git checkout -b module/your-module-name`
3. Add your module under `modules/your-module-name/`
4. Update `.env.example` with any new variables
5. Add a brief entry to the modules table in `README.md`
6. Open a pull request with a description of what your module does

Module PRs should include at least one example conversation showing the module in action.

---

## Questions

Open an issue on GitHub. Tag it `module-help` or `interface-help` depending on what you're building.

---

## Branch Protection & Merge Process

- PRs require 1 approving review before merge
- The main branch is protected — direct pushes are reserved for maintainers during v0.x development
- Squash-merge preferred to keep history clean
