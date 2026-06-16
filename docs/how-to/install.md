# How to install and run Sentinel

This guide installs the full Sentinel stack with Docker Compose: Sentinel Core, the Discord interface, and the Pathfinder 2e module. It uses the checked-in deployment files under `docs/deploy/` for a pre-built image install, and notes the source-tree equivalent where it differs.

---

## Prerequisites

Install or prepare:

- Docker Desktop on macOS, or Docker Engine with Docker Compose v2.20+ on Linux.
- LM Studio with a chat model loaded and the local OpenAI-compatible server running.
- An embedding model loaded in LM Studio if you use vault sweep, semantic recall, or Pathfinder rules lookup. The default is `text-embedding-nomic-embed-text-v1.5`.
- Obsidian with the Local REST API community plugin enabled.
- A Discord bot token if you want the Discord interface.

---

## Create a deploy directory

```bash
mkdir -p sentinel-deploy/secrets
cd sentinel-deploy

curl -fsSLO https://raw.githubusercontent.com/The-Artificer-of-Ciphers-LLC/sentinel-of-mnemosyne/main/docs/deploy/docker-compose.ghcr.yml
curl -fsSLo .env https://raw.githubusercontent.com/The-Artificer-of-Ciphers-LLC/sentinel-of-mnemosyne/main/docs/deploy/.env.sample
```

For a source checkout instead, run commands from the repository root and copy the root template:

```bash
cp .env.example .env
```

---

## Configure `.env`

Edit `.env` for your machine.

Required values:

| Variable | Example | Notes |
|---|---|---|
| `LMSTUDIO_BASE_URL` | `http://host.docker.internal:1234/v1` | LM Studio OpenAI-compatible `/v1` endpoint from inside Docker |
| `MODEL_NAME` | `gemma-4-e4b-it-mlx` | Sentinel Core chat model name, without provider prefix |
| `LITELLM_MODEL` | `openai/gemma-4-e4b-it-mlx` | Pathfinder model name, with LiteLLM provider prefix |
| `LITELLM_API_BASE` | `http://host.docker.internal:1234/v1` | Usually the same LM Studio endpoint |
| `OBSIDIAN_API_URL` | `http://host.docker.internal:27123` | Sentinel Core Obsidian Local REST API URL |
| `OBSIDIAN_BASE_URL` | `http://host.docker.internal:27123` | Pathfinder Obsidian Local REST API URL |
| `OBSIDIAN_VAULT_PATH` | `/Users/you/Documents/Mnemosyne` | Host path mounted at `/vault` for archive and Foundry imports |
| `DISCORD_ALLOWED_CHANNELS` | `1234567890,2345678901` | Leave empty to allow all channels; an allowlist is safer |
| `SENTINEL_ADMIN_USER_IDS` | `1234567890` | Discord user IDs allowed to run admin-only commands |

If the Obsidian Local REST API requires auth for Pathfinder's direct calls, set `OBSIDIAN_API_KEY` in `.env` as well. Sentinel Core reads the same key from `secrets/obsidian_api_key`.

---

## Create secret files

Secret files live under `secrets/`. Each file contains only the raw value.

```bash
echo -n "<obsidian_api_key>" > secrets/obsidian_api_key
echo -n "$(openssl rand -hex 32)" > secrets/sentinel_api_key
echo -n "<discord_bot_token>" > secrets/discord_bot_token
```

Create placeholders for optional secrets referenced by the compose file:

```bash
touch secrets/lmstudio_api_key
touch secrets/anthropic_api_key
touch secrets/alpaca_paper_api_key secrets/alpaca_paper_secret_key
touch secrets/alpaca_live_api_key secrets/alpaca_live_secret_key
```

When using Claude as the primary or fallback provider, put the Anthropic API key in `secrets/anthropic_api_key` and set `AI_PROVIDER=claude` or `AI_FALLBACK_PROVIDER=claude` in `.env`.

---

## Create the Sentinel persona

Create `sentinel/persona.md` in your Obsidian vault before first start.

If Obsidian is reachable and this file is missing, `sentinel-core` fails startup intentionally. A reachable vault without a persona file is treated as an incomplete operator setup.

Minimal seed:

```markdown
You are the Sentinel — the user's second brain.

Respond conversationally. Preserve useful context in the vault through the
system's normal filing pipeline. Do not expose implementation details unless
the user asks for them.
```

---

## Start the stack

For the pre-built image deployment:

```bash
docker compose -f docker-compose.ghcr.yml pull
docker compose -f docker-compose.ghcr.yml up -d
```

For a source checkout:

```bash
./sentinel.sh --discord --pf2e up -d
```

Core-only source start:

```bash
./sentinel.sh up -d
```

Stop all source-checkout services, including profiled services:

```bash
./sentinel.sh down
```

---

## Validate the installation

Check container state:

```bash
docker compose -f docker-compose.ghcr.yml ps
```

For a source checkout, omit `-f docker-compose.ghcr.yml`.

Check Sentinel Core:

```bash
SENTINEL_KEY=$(cat secrets/sentinel_api_key)

curl -s http://localhost:8000/health
curl -s -H "X-Sentinel-Key: $SENTINEL_KEY" http://localhost:8000/status
curl -s -H "X-Sentinel-Key: $SENTINEL_KEY" http://localhost:8000/modules
```

Send a smoke-test message:

```bash
curl -s -H "X-Sentinel-Key: $SENTINEL_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"smoke","content":"Reply with exactly: ok","source":"smoke"}' \
  http://localhost:8000/message
```

Expected results:

- `/health` returns HTTP 200.
- `/status` returns `status: ok` when Obsidian is reachable, or `degraded` when the core is up but Obsidian is unreachable.
- `/modules` includes a `pathfinder` registration when the Pathfinder module is running.
- `/message` returns a response envelope with `content`.

In Discord:

```text
/sen :help
/sen :pf rule list
/sen :pf player style list
```

---

## Update

Pre-built deployment:

```bash
docker compose -f docker-compose.ghcr.yml pull
docker compose -f docker-compose.ghcr.yml up -d
```

Source checkout:

```bash
git pull
./sentinel.sh --discord --pf2e up -d --build
```

---

## Troubleshooting quick checks

Use these first:

```bash
docker compose -f docker-compose.ghcr.yml logs -f sentinel-core
docker compose -f docker-compose.ghcr.yml logs -f sentinel-discord
docker compose -f docker-compose.ghcr.yml logs -f sentinel-pf2e
```

Common causes:

| Symptom | Check |
|---|---|
| `401 Unauthorized` | `X-Sentinel-Key` must match `secrets/sentinel_api_key` |
| Core startup fails with missing persona | Create `sentinel/persona.md` in the vault |
| `/status` is degraded | Obsidian Local REST API URL, key, and plugin state |
| Pathfinder does not appear in `/modules` | `pf2e-module` logs; rules embedding model must be loaded during startup |
| Discord bot is silent | Bot token, channel allowlist, bot intents, and `discord`/`discord-bot` logs |
| Foundry import cannot read archive files | `OBSIDIAN_VAULT_PATH` must point at the host vault path mounted into the Pathfinder container |

Further guides:

- [Troubleshoot Discord](troubleshoot-discord.md)
- [Troubleshoot Foundry](troubleshoot-foundry.md)
- [Foundry + Forge + Tailscale](foundry-forge-tailscale.md)

---

## Current shipped versions

- Sentinel Core `v0.51.1`
- Discord interface `v0.2.1`
- Pathfinder module `v1.1.2`
