---
status: partial
phase: 35-foundry-vtt-event-ingest
source: [35-VERIFICATION.md]
started: 2026-04-25T15:31:00Z
updated: 2026-04-25T17:15:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. End-to-end attack roll → Discord embed
expected: Discord embed posts to configured channel. Title has outcome emoji and label (e.g. 🎯 Critical Hit! — Seraphina → Goblin Warchief). Footer shows Roll total and DC/AC value. Narrative appears in embed description.
result: [pending]

### 2. Hidden-DC roll → DC: [hidden] in footer
expected: Footer reads 'DC: [hidden]' not 'DC/AC: 14'. Embed still posts. Foundry chat message is not suppressed.
result: [pending]

### 3. apiKey NOT visible in module settings panel (CR-03 fix)
expected: API key field does not appear in the Module Settings panel. Other settings (Base URL, Chat Prefix) appear normally.
result: [pending]

### 4. Webhook-only mode (no sentinelBaseUrl) delivers embed via Discord webhook
expected: With sentinelBaseUrl left empty and discordWebhookUrl set, making an attack roll posts an embed directly to Discord (no Sentinel involved). Embed has emoji title, outcome label, roll/DC footer.
result: [pending]

### 5. Sentinel timeout → webhook fallback (AbortController 3s)
expected: With sentinelBaseUrl pointing at an unreachable server (e.g. wrong IP), the roll still produces a Discord embed within ~4 seconds via the webhook fallback. No Foundry error dialog appears.
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
