# Set up Sentinel Connector for the first time

> **Version audit:** Reviewed for Sentinel Core v0.50 and Pathfinder module v1.1 (2026-05-08).

By the end of this tutorial you will have a working **Sentinel Connector** that watches every attack roll, save, and skill check in your Pathfinder 2e game and posts a Discord embed to your DM channel within a second or two of each roll. You will finish in webhook-only mode — roll embeds appear without AI narration — which is the correct starting point and works from anywhere, including Forge-hosted games.

---

## What you need before starting

| Item | Notes |
|------|-------|
| Mac Mini (or similar always-on Mac) | Runs LM Studio and the Docker stack |
| macOS 13 Ventura or newer | Required for Docker Desktop |
| Foundry VTT v12 or newer | v14 recommended |
| Pathfinder 2e system installed in Foundry | Required — this module is PF2e-only |
| A Discord server where you are admin | You'll create a bot and a webhook |
| Obsidian desktop app | Must be running on the Mac while Sentinel is active |

---

## Part 1 — Mac Mini: install prerequisites

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

## Part 2 — Discord: create a bot and a webhook

### 2.1 Create a Discord bot

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications) and click **New Application**. Name it "Sentinel" (or anything you like).
2. In the left sidebar, click **Bot**.
3. Click **Reset Token**, confirm, then copy the token — save it somewhere safe. **You only see this once.**
4. Scroll down on the Bot page and enable these **Privileged Gateway Intents**:
   - Message Content Intent
5. In the left sidebar, click **OAuth2 → URL Generator**.
6. Under Scopes, check **bot**. Under Bot Permissions, check **Send Messages** and **Read Message History**.
7. Copy the generated URL, paste it in your browser, and invite the bot to your Discord server.

### 2.2 Find your channel IDs

1. In Discord, open **Settings → Advanced** and enable **Developer Mode**.
2. Right-click the channel where you want roll narrations to appear and click **Copy Channel ID**. Save this number.

### 2.3 Create a Discord webhook (for webhook-only mode)

A webhook lets Sentinel post embeds without the full bot — useful for Forge-hosted games or as a fallback.

1. In Discord, right-click the same channel → **Edit Channel → Integrations → Webhooks**.
2. Click **New Webhook**, give it a name like "Sentinel Rolls", then click **Copy Webhook URL**. Save this URL.

> The webhook URL is a secret — anyone who has it can post to your channel. Don't share it publicly.

---

## Part 3 — Mac Mini: configure and start Sentinel

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

## Part 4 — Foundry VTT: install the module

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

> **Webhook-only mode:** If you left **Sentinel Base URL** blank, embeds still appear — outcome, actor, roll total, and DC post directly to Discord via the webhook. There is no AI narration, and no Mac Mini connectivity is required. This is the correct webhook-only state.

If no embed appears at all, see [How to troubleshoot the Foundry module](../how-to/troubleshoot-foundry.md).

---

## After setup: running the stack each session

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

## Next steps

- [How to configure Tailscale HTTPS for Forge-hosted games](../how-to/foundry-forge-tailscale.md) — enable full AI narration when Foundry runs on Forge or over the internet
- [How to troubleshoot the Foundry module](../how-to/troubleshoot-foundry.md) — fix common problems
- [Foundry secrets and port reference](../reference/foundry-secrets-and-ports.md) — what each secret file and port does
