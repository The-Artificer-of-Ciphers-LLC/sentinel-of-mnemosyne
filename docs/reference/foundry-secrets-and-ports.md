# Foundry secrets and port reference

---

## Reference: what each secret file does

| File | What it stores | How to get it |
|------|---------------|---------------|
| `secrets/sentinel_api_key` | Internal password between Foundry module and Sentinel server | Generate: `openssl rand -hex 32` |
| `secrets/obsidian_api_key` | Obsidian REST API key | Obsidian → Settings → Local REST API |
| `secrets/discord_bot_token` | Discord bot login token | Discord Developer Portal → Bot → Token |

---

## Reference: port map

| Port | Service | Used by |
|------|---------|---------|
| `8000` | Sentinel Core (HTTP) | Foundry module on LAN |
| `8000` | Sentinel Core (HTTPS, with Tailscale cert) | Foundry module on Forge / internet |
| `8001` | Discord bot internal listener | Sentinel Core → Discord bot (internal Docker network only) |
| `27123` | Obsidian REST API (HTTP) | Sentinel Core → Obsidian (Mac-local only) |
| `1234` | LM Studio local server | Sentinel Core → LM Studio (Mac-local only) |
| `30000` | Foundry VTT | Default Foundry port |
