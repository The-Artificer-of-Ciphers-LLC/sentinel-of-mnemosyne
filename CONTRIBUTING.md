# Contributing to Sentinel of Mnemosyne

This guide is for anyone who wants to build a new module or interface for the Sentinel — including future-you coming back six months from now having forgotten how this all fits together.

The design principle: **you should be able to add a module without touching anything in the core.** A module is a Docker container (or a few), a Docker Compose override file, and a set of pi skill files. That's it.

---

## Development Setup

### Prerequisites

- Python 3.12
- Node.js 22 LTS
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

1. An **interface container** receives it and posts a JSON envelope to the Core at `POST /message`
2. The **Sentinel Core** retrieves relevant context from Obsidian, builds a prompt, and sends it to the Pi harness
3. The **Pi harness** (the `coding-agent` AI runner) executes the prompt against LM Studio and returns a response
4. The Core writes a session note to Obsidian and returns the response to the interface
5. The interface delivers it back to the user

Modules hook in at step 2/3: they register as pi **skills** that the AI can invoke, and they optionally expose HTTP endpoints the Core can call directly.

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
    ├── main.py                       ← your module's main logic
    └── skills/
        └── your-skill-name.md        ← one or more pi skill files
```

### Step 3 — Write your pi skill file(s)

Skills are what the AI calls when it needs your module to do something. A skill is a markdown file with YAML frontmatter:

```markdown
---
name: music-log-practice
description: Log a music practice session. Use when the user mentions practicing an instrument, working on a piece, or doing a lesson. Arguments: duration in minutes, pieces worked on, notes about the session.
---

# Log Practice Session

When invoked, write a practice session entry to the Obsidian vault.

The entry should go to `/music/practice-log/YYYY-MM-DD.md` with this frontmatter:

```yaml
---
date: [today's date]
duration_minutes: [from arguments]
pieces: [from arguments]
tags: [practice, music]
---
```

After writing the file, confirm to the user that the session was logged and ask if they want to add any additional notes.
```

Key rules for skill files:
- `name` must be lowercase with hyphens only, 1–64 characters
- `description` is what the AI reads to decide whether to call this skill — be specific about when to use it and what arguments it expects
- The body is the instruction the AI follows when the skill is invoked — write it clearly, as if explaining to a capable assistant

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
    volumes:
      - ./modules/your-module-name/skills:/app/skills:ro
```

The `sentinel-net` network is defined in the base `docker-compose.yml` — all containers must join it to communicate.

### Step 5 — Register your skills with the Pi harness

Skills in `modules/your-module-name/skills/` need to be visible to the Pi harness container. The recommended approach is a shared Docker volume mounted into both your module container and the Pi harness. See the base `docker-compose.yml` for the `pi-skills` volume definition.

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
docker logs pi-harness
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
