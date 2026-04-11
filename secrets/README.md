# secrets/

One file per secret. Each file contains only the raw secret value (no quotes, no newline).
These files are gitignored. Copy from .env.example to know which files to create.

## Files needed

```
secrets/obsidian_api_key
secrets/sentinel_api_key
secrets/discord_bot_token
secrets/lmstudio_api_key          (optional — leave empty or omit if not used)
secrets/anthropic_api_key         (optional — leave empty or omit if not used)
secrets/alpaca_paper_api_key      (optional — trading module)
secrets/alpaca_paper_secret_key   (optional — trading module)
secrets/alpaca_live_api_key       (optional — trading module)
secrets/alpaca_live_secret_key    (optional — trading module)
```

## Create a secret file

```bash
echo -n "your-secret-value" > secrets/sentinel_api_key
```

The `-n` flag omits the trailing newline. App code strips whitespace anyway.

## Why file-based secrets?

Secrets injected via env_file are visible in `docker inspect`, process listings, and child
process environments. Docker secrets mount files at /run/secrets/ inside the container —
no env var, narrower exposure surface.

Non-secret config (URLs, log levels, modes) stays in `.env` and is safe to document in
`.env.example`.
