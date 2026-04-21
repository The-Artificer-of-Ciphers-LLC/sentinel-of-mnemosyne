# secrets/

One file per secret. Each file contains only the raw secret value — no quotes, no trailing newline.
These files are gitignored. They are never committed to git.

## Why file-based secrets?

Secrets in `.env` or `env_file` are visible in `docker inspect`, process listings, and child
process environments. Docker secrets mount files at `/run/secrets/<name>` inside containers —
narrower exposure surface, no env var leak.

Non-secret config (URLs, log levels, modes) stays in `.env` and is safe to document.

## Secret files

### Required (core always needs these)

| File | Description | Where to get it |
|---|---|---|
| `secrets/obsidian_api_key` | Obsidian Local REST API key | Obsidian → Settings → Local REST API → API Key |
| `secrets/sentinel_api_key` | Shared secret — interfaces authenticate to sentinel-core with this | Generate: `openssl rand -hex 32` |

### Required for Discord interface

| File | Description | Where to get it |
|---|---|---|
| `secrets/discord_bot_token` | Discord bot token | [Discord Developer Portal](https://discord.com/developers/applications) → Your App → Bot → Token |

### Optional — AI providers

| File | Description | When needed |
|---|---|---|
| `secrets/anthropic_api_key` | Anthropic API key | When `AI_PROVIDER=claude` or `AI_FALLBACK_PROVIDER=claude` in `.env` |
| `secrets/lmstudio_api_key` | LM Studio API key | Only if LM Studio is configured to require auth (default: not required) |

### Optional — Trading module (v0.9)

| File | Description | Where to get it |
|---|---|---|
| `secrets/alpaca_paper_api_key` | Alpaca paper trading API key | [Alpaca Dashboard](https://app.alpaca.markets) → Paper → API Keys |
| `secrets/alpaca_paper_secret_key` | Alpaca paper trading secret key | Same as above |
| `secrets/alpaca_live_api_key` | Alpaca live trading API key | [Alpaca Dashboard](https://app.alpaca.markets) → Live → API Keys |
| `secrets/alpaca_live_secret_key` | Alpaca live trading secret key | Same as above |

## How to create a secret file

```bash
echo -n "your-secret-value" > secrets/obsidian_api_key
```

The `-n` flag omits the trailing newline. App code strips whitespace, but `-n` is good practice.

## Minimum setup (core + Discord)

```bash
# 1. Obsidian API key — copy from Obsidian settings
echo -n "paste-key-from-obsidian-settings" > secrets/obsidian_api_key

# 2. Sentinel API key — generate a random one
echo -n "$(openssl rand -hex 32)" > secrets/sentinel_api_key

# 3. Discord bot token — copy from Discord Developer Portal
echo -n "paste-bot-token-here" > secrets/discord_bot_token
```

## Create empty placeholder files (so compose doesn't error on missing files)

If you want to start without optional services, create empty files for secrets
referenced in docker-compose.yml:

```bash
touch secrets/lmstudio_api_key
touch secrets/anthropic_api_key
touch secrets/alpaca_paper_api_key secrets/alpaca_paper_secret_key
touch secrets/alpaca_live_api_key secrets/alpaca_live_secret_key
```
