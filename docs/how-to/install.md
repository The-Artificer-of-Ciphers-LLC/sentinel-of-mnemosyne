# How to install and run Sentinel

This guide walks you through deploying the full containerised Sentinel stack from scratch using pre-built GHCR images and Docker Compose.

---

## Step 1 — Prerequisites

Ensure the following are in place before proceeding:

- **Docker Desktop** (Mac) or Docker + Docker Compose v2 on Linux
- **Obsidian** running with the [Local REST API community plugin](https://github.com/coddingtonbear/obsidian-local-rest-api) installed and enabled
- **LM Studio** running on your Mac Mini with a model loaded and the local server started

---

## Step 2 — Download sample deploy files and configure

Create a deploy folder and download the sample Compose file and environment template:

```bash
mkdir -p sentinel-deploy/secrets
cd sentinel-deploy

curl -fsSLO https://raw.githubusercontent.com/The-Artificer-of-Ciphers-LLC/sentinel-of-mnemosyne/main/docs/deploy/docker-compose.ghcr.yml
curl -fsSLo .env https://raw.githubusercontent.com/The-Artificer-of-Ciphers-LLC/sentinel-of-mnemosyne/main/docs/deploy/.env.sample
```

Edit `.env` for your environment (`LMSTUDIO_BASE_URL`, `OBSIDIAN_API_URL`, `OBSIDIAN_VAULT_PATH`, model settings, CORS, etc.).

---

## Step 3 — Create required secrets

Secrets live in the `secrets/` directory as individual files — one file per secret.

```bash
mkdir -p secrets

echo -n "<obsidian_api_key>" > secrets/obsidian_api_key
echo -n "$(openssl rand -hex 32)" > secrets/sentinel_api_key
```

Optional but common:

```bash
echo -n "<discord_bot_token>" > secrets/discord_bot_token
echo -n "<anthropic_api_key>" > secrets/anthropic_api_key
```

---

## Step 4 — Ensure the sentinel persona file exists

Create `sentinel/persona.md` in your Obsidian vault before starting.

> **Note:** If the vault is reachable but `sentinel/persona.md` is missing, startup will fail — create the file before starting.

---

## Step 5 — Pull and start services

```bash
docker compose -f docker-compose.ghcr.yml pull
docker compose -f docker-compose.ghcr.yml up -d
```

---

## Step 6 — Validate

Confirm the stack is healthy and the core message endpoint responds:

```bash
SENTINEL_KEY=$(cat secrets/sentinel_api_key)

curl -s http://localhost:8000/health
curl -s -H "X-Sentinel-Key: $SENTINEL_KEY" http://localhost:8000/status
curl -s -H "X-Sentinel-Key: $SENTINEL_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"smoke","content":"Reply with exactly: ok"}' \
  http://localhost:8000/message
```

---

## Updating

To update to a new image version, re-run steps 5 and 6.

---

## Further reading

For design rationale and architectural decisions, see [`../explanation/architecture.md`](../explanation/architecture.md).

---

## Versions

- Sentinel Core and Sentinel modules version independently.
- Current shipped baseline: Sentinel Core `v0.50`, Pathfinder module `v1.1`.
