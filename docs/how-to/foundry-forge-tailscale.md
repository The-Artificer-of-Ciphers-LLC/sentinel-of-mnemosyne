# How to configure Tailscale HTTPS for Forge-hosted games

**Prerequisites:** the base stack from the [first-setup tutorial](../tutorial/foundry-first-setup.md) must already be running.

The problem Tailscale solves: when Foundry runs on Forge's servers, your players' browsers try to reach your Mac Mini directly. Browsers block unencrypted requests from HTTPS pages to HTTP addresses (called "mixed content"). Tailscale gives your Mac Mini a stable HTTPS address that browsers trust.

---

## 5.1 Sign up for Tailscale

1. Go to [tailscale.com](https://tailscale.com) and click **Get started**.
2. Sign in with your Google, Microsoft, or GitHub account — no password needed.
3. Tailscale is **free** for personal use (up to 100 devices).

---

## 5.2 Install Tailscale on your Mac Mini

1. Go to [tailscale.com/download](https://tailscale.com/download) and download the Mac version.
2. Install and open Tailscale. Sign in with the same account you used on the website.
3. Your Mac will appear in the [Tailscale admin console](https://login.tailscale.com/admin/machines) with a machine name like `mac-mini` and a Tailscale IP like `100.XX.XX.XX`.

---

## 5.3 Enable HTTPS for your Mac

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

---

## 5.4 Install Tailscale on your players' devices (optional but recommended)

For the full experience, your players can also install Tailscale and join your tailnet. This isn't strictly required for the webhook-only mode — the Discord webhook works from any network. It's only needed if your players want the full LLM narration experience from Forge.

Each player:
1. Installs Tailscale from [tailscale.com/download](https://tailscale.com/download)
2. Signs in with their own account
3. You invite them to your tailnet: in the [Tailscale admin console](https://login.tailscale.com/admin/machines), click **Share** on your Mac Mini and send them an invite link

---

## 5.5 Configure Sentinel to use HTTPS

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

---

## 5.6 Update the Foundry module settings for Tailscale

In Foundry **Settings → Module Settings → Sentinel Connector**, change the **Sentinel Base URL** to:

```
https://mac-mini.YOUR-TAILNET.ts.net:8000
```

That's it. Now rolls from Forge will reach your Mac Mini over an encrypted Tailscale tunnel, and the full LLM narration flow works.
