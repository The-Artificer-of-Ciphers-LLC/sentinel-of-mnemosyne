# Sentinel Installation Guide (Sentinel Core v0.50 / Pathfinder module v1.1)

## Versioning note
- Sentinel Core and Sentinel modules version independently.
- Current shipped baseline: Sentinel Core `v0.50`, Pathfinder module `v1.1`.

## 1) Prerequisites
- Docker Desktop with Compose v2
- Obsidian running with Local REST API plugin enabled
- LM Studio running with a model loaded

## 2) Download sample deploy files and configure
```bash
mkdir -p sentinel-deploy/secrets
cd sentinel-deploy

curl -fsSLO https://raw.githubusercontent.com/The-Artificer-of-Ciphers-LLC/sentinel-of-mnemosyne/main/docs/deploy/docker-compose.ghcr.yml
curl -fsSLo .env https://raw.githubusercontent.com/The-Artificer-of-Ciphers-LLC/sentinel-of-mnemosyne/main/docs/deploy/.env.sample
```

Edit `.env` for your environment (`LMSTUDIO_BASE_URL`, `OBSIDIAN_API_URL`, `OBSIDIAN_VAULT_PATH`, model settings, CORS, etc.).

## 3) Create required secrets
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

## 4) Ensure sentinel persona exists
Create `sentinel/persona.md` in your vault.

Startup policy:
- Vault reachable + missing persona => startup fails (intentional)
- Vault unreachable => startup degrades with warning

## 5) Pull and start services
```bash
docker compose -f docker-compose.ghcr.yml pull
docker compose -f docker-compose.ghcr.yml up -d
```

## 6) Validate
```bash
SENTINEL_KEY=$(cat secrets/sentinel_api_key)

curl -s http://localhost:8000/health
curl -s -H "X-Sentinel-Key: $SENTINEL_KEY" http://localhost:8000/status
curl -s -H "X-Sentinel-Key: $SENTINEL_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"smoke","content":"Reply with exactly: ok"}' \
  http://localhost:8000/message
```

## 7) Updating images
```bash
docker compose -f docker-compose.ghcr.yml pull
docker compose -f docker-compose.ghcr.yml up -d
```
