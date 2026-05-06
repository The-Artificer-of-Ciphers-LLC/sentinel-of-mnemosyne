# Sentinel Installation Guide (v0.50)

## 1) Prerequisites
- Docker Desktop with Compose v2
- Obsidian running with Local REST API plugin enabled
- LM Studio running with a model loaded

## 2) Clone and configure
```bash
git clone https://github.com/The-Artificer-of-Ciphers-LLC/sentinel-of-mnemosyne.git
cd sentinel-of-mnemosyne
cp .env.example .env
```

Edit `.env` for your environment (`LMSTUDIO_BASE_URL`, model settings, CORS, etc.).

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

## 5) Start services
Core only:
```bash
./sentinel.sh up -d
```

Core + Discord + Pathfinder (v0.50):
```bash
./sentinel.sh --discord --pathfinder up -d
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

## 7) Rebuild after code changes
```bash
docker compose build sentinel-core
docker compose up -d --force-recreate sentinel-core
```
