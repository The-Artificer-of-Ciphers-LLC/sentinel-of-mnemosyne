# How to troubleshoot the Foundry module

---

## No Discord embed appears after a roll

1. **Is the Discord bot online?** Check your Discord server — the bot should show as Online.
2. **Check the module settings** — in Foundry Settings → Module Settings → Sentinel Connector, verify the API Key matches `cat ~/sentinel/secrets/sentinel_api_key`.
3. **Check Sentinel logs:**
   ```bash
   docker compose logs pf2e-module --tail=30
   ```
   Look for lines starting with `ERROR` or `422 Unprocessable Entity`.
4. **Is LM Studio running?** Open LM Studio, go to Local Server, and confirm the server is started. If not, start it and wait 10 seconds before rolling again.

---

## "Mixed content" error in browser console (Forge users)

You're trying to make an HTTP call from an HTTPS page. Two solutions:
- Use **webhook-only mode** (leave Sentinel Base URL empty) — no mixed content issue
- Set up **Tailscale** ([How to configure Tailscale HTTPS for Forge-hosted games](foundry-forge-tailscale.md)) so Sentinel has an HTTPS address

---

## The module won't install ("manifest URL not found")

The Sentinel stack isn't running, or your IP address has changed. Verify:
```bash
docker compose ps
ipconfig getifaddr en0
```
If your IP changed, update the manifest URL with the new one.

---

## Obsidian integration not working (session notes, NPC memory)

- Confirm Obsidian is open and the vault is visible on screen (Obsidian pauses the REST API when the app is in the background on some macOS versions)
- Go to **Obsidian → Settings → Local REST API** and verify it shows "Running on port 27123"
- Check the API key: `cat ~/sentinel/secrets/obsidian_api_key` should match what's shown in Obsidian settings

---

## Tailscale certificate errors

Run `tailscale cert mac-mini.YOUR-TAILNET.ts.net` again — certificates expire every 90 days. Then copy the new files to `~/sentinel/certs/` and restart the stack.

---

## "Connection refused" when testing the module

Make sure Docker is running (`docker compose ps` shows healthy), and that your firewall allows connections on port 8000:
```bash
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /usr/bin/docker
```
