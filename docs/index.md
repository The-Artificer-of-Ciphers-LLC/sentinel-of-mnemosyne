# Sentinel of Mnemosyne — Documentation

This documentation follows the [Diataxis](https://diataxis.fr/) framework. Each document belongs to exactly one of four types: tutorials (learning by doing), how-to guides (working to a goal), reference (facts while working), or explanation (understanding why). Navigate by what you need right now.

---

## Tutorials (learning by doing)

Step-by-step lessons that build understanding through practice. Follow these when you are new to a topic and want to be guided through it end to end.

| Doc | Purpose |
|-----|---------|
| [Foundry VTT First Setup](tutorial/foundry-first-setup.md) | Install and configure the Pathfinder 2e Foundry module from scratch |

---

## How-to guides (working to a goal)

Practical recipes that assume you know the basics and need to accomplish a specific task. Dip in and out as needed.

| Doc | Purpose |
|-----|---------|
| [Install Sentinel](how-to/install.md) | Deploy the full stack with Docker Compose |
| [Onboard a Player](how-to/onboard-a-player.md) | Add a new player to the Pathfinder 2e module |
| [Foundry + Forge + Tailscale](how-to/foundry-forge-tailscale.md) | Expose a local Foundry instance through Forge and Tailscale |
| [Troubleshoot Discord](how-to/troubleshoot-discord.md) | Diagnose and fix common Discord bot issues |
| [Troubleshoot Foundry](how-to/troubleshoot-foundry.md) | Diagnose and fix common Foundry VTT integration issues |

---

## Reference (facts while working)

Accurate, up-to-date technical information. Use these when you need to look something up, not when you want to learn.

| Doc | Purpose |
|-----|---------|
| [Feature Reference](reference/features.md) | Current shipped and planned capability list |
| [Discord Commands](reference/discord-commands.md) | Every `/sen` command and subcommand with examples |
| [API and Contracts](reference/api-and-contracts.md) | Sentinel Core HTTP API, message envelope schema, module protocol |
| [Obsidian Vault Layout](reference/obsidian-vault.md) | Vault directory structure, frontmatter conventions, naming rules |
| [Foundry Secrets and Ports](reference/foundry-secrets-and-ports.md) | Secret file names, port assignments, and environment variables for Foundry |

---

## Explanation (understanding why)

Background reading that builds conceptual understanding. Not procedures — context and rationale.

| Doc | Purpose |
|-----|---------|
| [Architecture](explanation/architecture.md) | How the components fit together, design decisions, and request flow |

---

## Decision records

Architectural decision records (ADRs) capture the reasoning behind key design choices.

| ADR | Title |
|-----|-------|
| [ADR-0001](adr/0001-sentinel-persona-source.md) | Sentinel persona source |
| [ADR-0002](adr/0002-vault-seam-location.md) | Vault seam location |
| [ADR-0003](adr/0003-recall-module.md) | Recall module |
| [ADR-0004](adr/0004-semantic-recall.md) | Semantic recall |
| [ADR-0005](adr/0005-typed-session-summary.md) | Typed session summary |
