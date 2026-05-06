# Sentinel Connector — Complete Setup Guide

> **Version audit:** Reviewed for Sentinel v0.50 (2026-05-06).

> **Who this is for:** A Game Master who wants AI-powered roll narrations from their tabletop sessions appearing in Discord, automatically. No programming background required.

---

## What You're Setting Up

The **Sentinel Connector** is a Foundry VTT module that watches every attack roll, save, and skill check in your Pathfinder 2e game and sends it to an AI assistant (running locally on your Mac) that writes a one-sentence narration and posts it to your Discord server.

**What happens when a player rolls:**
1. The Foundry module sees the roll result
2. It sends the result to Sentinel (your local AI server)
3. Sentinel generates a dramatic narration using your local AI
4. The narration appears as a Discord embed in your DM channel — within a second or two

**Two modes:**
- **Webhook-only** (easiest): Sentinel is bypassed; embeds post directly to Discord with no narration. Works from anywhere, including Forge-hosted games. Great to start with.
- **Full mode with narration**: Sentinel is involved, LM Studio generates prose. Requires the Mac Mini to be reachable from wherever Foundry is running.

---

## What You Need Before Starting

| Item | Notes |
|------|-------|
| Mac Mini (or similar always-on Mac) | Runs LM Studio and the Docker stack |
| macOS 13 Ventura or newer | Required for Docker Desktop |
| Foundry VTT v12 or newer | v14 recommended |
| Pathfinder 2e system installed in Foundry | Required — this module is PF2e-only |
| A Discord server where you are admin | You'll create a bot and a webhook |
| Obsidian desktop app | Must be running on the Mac while Sentinel is active |

---

## Part 1 — Mac Mini: Install Prerequisites

### 1.1 Install Docker Desktop

1. Go to [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) and download the **Mac with Apple Silicon** or **Mac with Intel Chip** version (check  → About This Mac to confirm).
2. Open the downloaded `.dmg`, drag Docker to Applications, launch it.
3. Complete the onboarding (click through the prompts). Docker must show a **green "Running"** status in the menu bar before continuing.

**Verify:** Open Terminal (Spotlight → Terminal) and run:
```
docker compose version
```
You should see something like `Docker Compose version v2.x.x`. If you see `docker-compose: command not found`, try `docker compose` (with a space, no hyphen).

### 1.2 Install LM Studio

1. Go to [lmstudio.ai](https://lmstudio.ai) and download for Mac.
2. Open LM Studio. On first launch it will ask you to download a model.
3. Download **Llama 3.2 8B Instruct** (search for "llama 3.2 8b" in the model browser). The 8B model runs well on a Mac Mini with 16 GB RAM. The download is ~5 GB.
4. Once downloaded, load the model: click it in the left sidebar, then click **Load**.
5. Enable the local server: in the left sidebar click the **Local Server** icon (looks like `<->`), then click **Start Server**. Leave the port at `1234`.

> LM Studio must be running with a model loaded every time you use Sentinel. It does not start automatically — you'll need to open it and start the server before game night.

### 1.3 Install Obsidian

1. Download from [obsidian.md](https://obsidian.md) and install.
2. Create a new vault called **Mnemosyne** (or any name you like) somewhere convenient — e.g. `~/Documents/Mnemosyne`.
3. In Obsidian, open **Settings → Community plugins**, turn off Safe Mode, click **Browse**, search for **Local REST API**, install it, and enable it.
4. Go to **Settings → Local REST API** and copy the **API Key** — you'll need it in Part 3.
5. Under the same settings, note the ports. You want **HTTP port 27123** enabled (toggle it on if it's off).

> Obsidian must be running and the vault must be open every time you use Sentinel. It cannot run in the background by itself — keep it in your Dock.

---

## Part 2 — Discord: Create a Bot and a Webhook

### 2.1 Create a Discord Bot

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications) and click **New Application**. Name it "Sentinel" (or anything you like).
2. In the left sidebar, click **Bot**.
3. Click **Reset Token**, confirm, then copy the token — save it somewhere safe. **You only see this once.**
4. Scroll down on the Bot page and enable these **Privileged Gateway Intents**:
   - Message Content Intent
5. In the left sidebar, click **OAuth2 → URL Generator**.
6. Under Scopes, check **bot**. Under Bot Permissions, check **Send Messages** and **Read Message History**.
7. Copy the generated URL, paste it in your browser, and invite the bot to your Discord server.

### 2.2 Find Your Channel IDs

1. In Discord, open **Settings → Advanced** and enable **Developer Mode**.
2. Right-click the channel where you want roll narrations to appear and click **Copy Channel ID**. Save this number.

### 2.3 Create a Discord Webhook (for webhook-only mode)

A webhook lets Sentinel post embeds without the full bot — useful for Forge-hosted games or as a fallback.

1. In Discord, right-click the same channel → **Edit Channel → Integrations → Webhooks**.
2. Click **New Webhook**, give it a name like "Sentinel Rolls", then click **Copy Webhook URL**. Save this URL.

> The webhook URL is a secret — anyone who has it can post to your channel. Don't share it publicly.

---

## Part 3 — Mac Mini: Configure and Start Sentinel

### 3.1 Download the Sentinel project

Open Terminal and run:

```bash
git clone https://github.com/YOUR_REPO_HERE/sentinel-of-mnemosyne.git ~/sentinel
cd ~/sentinel
```

*(Replace the URL with your actual repository URL.)*

### 3.2 Create your configuration files

**Copy the template:**
```bash
cp .env.example .env
```

Open `.env` in TextEdit (or any text editor) and set these values:

| Setting | What to put |
|---------|-------------|
| `DISCORD_ALLOWED_CHANNELS=` | The channel ID you copied in Step 2.2. Example: `DISCORD_ALLOWED_CHANNELS=1234567890123456789` |
| Everything else | Leave the defaults unless you changed LM Studio's port |

**Create the secrets files** — these hold sensitive values and are never stored in the main config:

```bash
# Your Obsidian REST API key (from Step 1.3)
echo -n "paste-your-obsidian-key-here" > secrets/obsidian_api_key

# A random key Sentinel uses internally — just generate one
echo -n "$(openssl rand -hex 32)" > secrets/sentinel_api_key

# Your Discord bot token (from Step 2.1)
echo -n "paste-your-bot-token-here" > secrets/discord_bot_token
```

### 3.3 Start the stack

```bash
docker compose --profile pf2e up -d
```

This downloads and starts all the containers. The first run takes a few minutes. Once it settles, verify everything is running:

```bash
docker compose ps
```

All services should show **Up** or **healthy**. If anything shows **Exit**, check the logs:

```bash
docker compose logs pf2e-module --tail=50
```

### 3.4 Find your Mac's local IP address

Open Terminal and run:

```bash
ipconfig getifaddr en0
```

If that returns nothing, try `en1` instead. Write down the address — it will look like `192.168.1.XX`. This is your **Sentinel Base URL**: `http://192.168.1.XX:8000`.

---

## Part 4 — Foundry VTT: Install the Module

### 4.1 Install Sentinel Connector

1. In Foundry, click **Setup → Add-on Modules → Install Module**.
2. At the bottom, paste this URL in the **Manifest URL** field:
   ```
   http://192.168.1.XX:8000/foundry/static/module.json
   ```
   Replace `192.168.1.XX` with your Mac's actual IP from Step 3.4.
3. Click **Install**. Foundry will download and install the module.

### 4.2 Enable and configure the module

1. Open your World, go to **Settings → Manage Modules**, find **Sentinel Connector**, and enable it.
2. Go to **Settings → Configure Settings → Module Settings → Sentinel Connector**.
3. Fill in the fields:

| Field | Value |
|-------|-------|
| **Sentinel Base URL** | `http://192.168.1.XX:8000` (your Mac's IP) — or leave empty for webhook-only mode |
| **API Key** | The contents of your `secrets/sentinel_api_key` file. Read it with: `cat ~/sentinel/secrets/sentinel_api_key` |
| **Chat Prefix** | A trigger phrase (e.g. `!sentinel`) for chat-message forwarding. Can leave blank if you only want rolls. |
| **Discord Webhook URL** | The webhook URL from Step 2.3 |

4. Click **Save** (or close — Foundry saves automatically).

### 4.3 Test it

Make an attack roll in Foundry against a target with a DC. Within a few seconds you should see an embed appear in your Discord channel. The embed shows:
- An emoji and outcome label in the title (🎯 Critical Hit!, ✅ Success, etc.)
- A one-sentence AI narration (if Sentinel Base URL is set and LM Studio is running)
- Roll total and DC/AC in the footer

If no embed appears, see the Troubleshooting section at the end of this guide.

---

## Part 5 — Tailscale: Play on Forge from Anywhere

> **Skip this section** if you run Foundry locally on the same network as your Mac Mini. Tailscale is only needed for **Forge-hosted games** or playing over the internet.

The problem Tailscale solves: when Foundry runs on Forge's servers, your players' browsers try to reach your Mac Mini directly. Browsers block unencrypted requests from HTTPS pages to HTTP addresses (called "mixed content"). Tailscale gives your Mac Mini a stable HTTPS address that browsers trust.

### 5.1 Sign up for Tailscale

1. Go to [tailscale.com](https://tailscale.com) and click **Get started**.
2. Sign in with your Google, Microsoft, or GitHub account — no password needed.
3. Tailscale is **free** for personal use (up to 100 devices).

### 5.2 Install Tailscale on your Mac Mini

1. Go to [tailscale.com/download](https://tailscale.com/download) and download the Mac version.
2. Install and open Tailscale. Sign in with the same account you used on the website.
3. Your Mac will appear in the [Tailscale admin console](https://login.tailscale.com/admin/machines) with a machine name like `mac-mini` and a Tailscale IP like `100.XX.XX.XX`.

### 5.3 Enable HTTPS for your Mac

Tailscale can issue a real, browser-trusted HTTPS certificate for your machine. In Terminal:

```bash
tailscale cert mac-mini.YOUR-TAILNET.ts.net
```

Replace `mac-mini` with your actual machine name and `YOUR-TAILNET` with your tailnet name — both visible in the [Tailscale admin console](https://login.tailscale.com/admin/machines). The machine name is shown under the device, and your tailnet name appears in the top-left of the admin console.

This creates two files in your current directory:
- `mac-mini.YOUR-TAILNET.ts.net.crt` — the certificate
- `mac-mini.YOUR-TAILNET.ts.net.key` — the private key

Move them to the sentinel project:
```bash
mkdir -p ~/sentinel/certs
mv mac-mini.YOUR-TAILNET.ts.net.crt ~/sentinel/certs/
mv mac-mini.YOUR-TAILNET.ts.net.key ~/sentinel/certs/
```

> The certificate expires every 90 days. Tailscale renews it automatically as long as the machine is connected — just re-run the `tailscale cert` command when needed and restart Sentinel.

### 5.4 Install Tailscale on your players' devices (optional but recommended)

For the full experience, your players can also install Tailscale and join your tailnet. This isn't strictly required for the webhook-only mode — the Discord webhook works from any network. It's only needed if your players want the full LLM narration experience from Forge.

Each player:
1. Installs Tailscale from [tailscale.com/download](https://tailscale.com/download)
2. Signs in with their own account
3. You invite them to your tailnet: in the [Tailscale admin console](https://login.tailscale.com/admin/machines), click **Share** on your Mac Mini and send them an invite link

### 5.5 Configure Sentinel to use HTTPS

Open `~/sentinel/.env` and add (or update) the following:

```
# Tailscale HTTPS cert paths (for Forge/internet play)
SSL_CERTFILE=/run/secrets/ssl_cert
SSL_KEYFILE=/run/secrets/ssl_key
```

Then add the cert files as Docker secrets. Add these lines to the `secrets:` section at the bottom of your `compose.yml`:

```yaml
secrets:
  ssl_cert:
    file: ./certs/mac-mini.YOUR-TAILNET.ts.net.crt
  ssl_key:
    file: ./certs/mac-mini.YOUR-TAILNET.ts.net.key
```

Restart the stack:
```bash
cd ~/sentinel
docker compose --profile pf2e down
docker compose --profile pf2e up -d
```

### 5.6 Update the Foundry module settings for Tailscale

In Foundry **Settings → Module Settings → Sentinel Connector**, change the **Sentinel Base URL** to:

```
https://mac-mini.YOUR-TAILNET.ts.net:8000
```

That's it. Now rolls from Forge will reach your Mac Mini over an encrypted Tailscale tunnel, and the full LLM narration flow works.

---

## Part 6 — Forge-Hosted Games: Webhook-Only Mode (No Tailscale Required)

If you don't want to set up Tailscale, webhook-only mode still gives you roll embeds in Discord — just without the AI narration.

1. In Foundry module settings, leave **Sentinel Base URL** blank.
2. Set **Discord Webhook URL** to the webhook URL from Step 2.3.
3. That's all. Rolls will post a basic embed (outcome, actor, roll total, DC) directly to Discord via the webhook. No Mac Mini connectivity required.

---

## Everyday Use

**Before each session:**
1. Open LM Studio on the Mac Mini → Local Server → Start Server (if not already running)
2. Open Obsidian on the Mac Mini, make sure the Mnemosyne vault is open
3. Run `docker compose --profile pf2e up -d` in Terminal (if the stack isn't already running)
4. Open Foundry and start your world

**To check if everything is running:**
```bash
cd ~/sentinel
docker compose ps
```

**To stop the stack:**
```bash
docker compose --profile pf2e down
```

**To see live logs (useful for debugging):**
```bash
docker compose logs -f pf2e-module discord-bot
```
Press Ctrl+C to stop watching.

---

## Troubleshooting

### No Discord embed appears after a roll

1. **Is the Discord bot online?** Check your Discord server — the bot should show as Online.
2. **Check the module settings** — in Foundry Settings → Module Settings → Sentinel Connector, verify the API Key matches `cat ~/sentinel/secrets/sentinel_api_key`.
3. **Check Sentinel logs:**
   ```bash
   docker compose logs pf2e-module --tail=30
   ```
   Look for lines starting with `ERROR` or `422 Unprocessable Entity`.
4. **Is LM Studio running?** Open LM Studio, go to Local Server, and confirm the server is started. If not, start it and wait 10 seconds before rolling again.

### "Mixed content" error in browser console (Forge users)

You're trying to make an HTTP call from an HTTPS page. Two solutions:
- Use **webhook-only mode** (leave Sentinel Base URL empty) — no mixed content issue
- Set up **Tailscale** (Part 5) so Sentinel has an HTTPS address

### The module won't install ("manifest URL not found")

The Sentinel stack isn't running, or your IP address has changed. Verify:
```bash
docker compose ps
ipconfig getifaddr en0
```
If your IP changed, update the manifest URL with the new one.

### Obsidian integration not working (session notes, NPC memory)

- Confirm Obsidian is open and the vault is visible on screen (Obsidian pauses the REST API when the app is in the background on some macOS versions)
- Go to **Obsidian → Settings → Local REST API** and verify it shows "Running on port 27123"
- Check the API key: `cat ~/sentinel/secrets/obsidian_api_key` should match what's shown in Obsidian settings

### Tailscale certificate errors

Run `tailscale cert mac-mini.YOUR-TAILNET.ts.net` again — certificates expire every 90 days. Then copy the new files to `~/sentinel/certs/` and restart the stack.

### "Connection refused" when testing the module

Make sure Docker is running (`docker compose ps` shows healthy), and that your firewall allows connections on port 8000:
```bash
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /usr/bin/docker
```

---

## Reference: What Each Secret File Does

| File | What it stores | How to get it |
|------|---------------|---------------|
| `secrets/sentinel_api_key` | Internal password between Foundry module and Sentinel server | Generate: `openssl rand -hex 32` |
| `secrets/obsidian_api_key` | Obsidian REST API key | Obsidian → Settings → Local REST API |
| `secrets/discord_bot_token` | Discord bot login token | Discord Developer Portal → Bot → Token |

---

## Reference: Port Map

| Port | Service | Used by |
|------|---------|---------|
| `8000` | Sentinel Core (HTTP) | Foundry module on LAN |
| `8000` | Sentinel Core (HTTPS, with Tailscale cert) | Foundry module on Forge / internet |
| `8001` | Discord bot internal listener | Sentinel Core → Discord bot (internal Docker network only) |
| `27123` | Obsidian REST API (HTTP) | Sentinel Core → Obsidian (Mac-local only) |
| `1234` | LM Studio local server | Sentinel Core → LM Studio (Mac-local only) |
| `30000` | Foundry VTT | Default Foundry port |
