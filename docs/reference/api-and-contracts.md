# Sentinel API and contracts reference

**Type:** Reference (Diataxis)
**Version audit:** Sentinel Core `v0.51.1`, Discord interface `v0.2.1`, Pathfinder module `v1.1.2`
**Scope:** HTTP APIs, message envelopes, module registration, container contracts, deployment files, and route inventory.

For rationale, see [Architecture](../explanation/architecture.md). For vault paths, see [Obsidian Vault Layout](obsidian-vault.md). For feature coverage, see [Feature Reference](features.md).

---

## Authentication

Every Sentinel Core endpoint except `GET /health` requires:

```http
X-Sentinel-Key: <contents of secrets/sentinel_api_key>
```

The Discord interface and module containers read the shared key from Docker secrets and forward it when calling Sentinel Core. Sentinel Core returns `401` when the header is missing or mismatched.

---

## Standard Message Envelope

Interfaces call `POST /message` with:

```json
{
  "content": "the user's message text",
  "user_id": "stable-user-id",
  "source": "discord",
  "channel_id": "channel-or-thread-id"
}
```

Fields:

| Field | Required | Notes |
|---|---:|---|
| `content` | yes | Raw user message |
| `user_id` | yes | Stable user identifier; Discord uses the snowflake string |
| `source` | no | Interface name such as `discord` |
| `channel_id` | no | Interface-specific channel or thread id |

Response:

```json
{
  "content": "assistant response",
  "model": "model-id"
}
```

---

## Sentinel Core Endpoints

Memtrace currently maps 44 HTTP endpoints across the repository, including Core and Pathfinder routes. Sentinel Core exposes the public gateway surface below.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/health` | no | Container health and non-blocking runtime probes |
| `POST` | `/message` | yes | Process a standard message envelope |
| `GET` | `/status` | yes | Report runtime status for Obsidian and active AI provider |
| `GET` | `/context/{user_id}` | yes | Debug recall context for a user |
| `POST` | `/note/classify` | yes | Classify content and file, inbox, or drop it |
| `GET` | `/inbox` | yes | List pending inbox entries with Discord-ready rendering |
| `POST` | `/inbox/classify` | yes | File an inbox entry under a topic |
| `POST` | `/inbox/discard` | yes | Remove an inbox entry without filing |
| `POST` | `/vault/sweep/start` | yes | Admin-gated vault sweep start; supports dry-run and force reclassify |
| `GET` | `/vault/sweep/status` | yes | Return current or last sweep status |
| `POST` | `/modules/register` | yes | Module startup registration |
| `GET` | `/modules` | yes | List registered modules |
| `GET` | `/modules/{name}/{path:path}` | yes | Proxy a GET request to a registered module |
| `POST` | `/modules/{name}/{path:path}` | yes | Proxy a POST request to a registered module |

### `POST /message` behaviour

The message route:

1. Validates the API key and envelope.
2. Assembles recall context from persona/self context, recent sessions, and warm semantic recall.
3. Applies prompt-injection filtering before provider calls.
4. Enforces context-window limits through the model registry and token guard.
5. Calls the configured LiteLLM provider path.
6. Scans the output before returning.
7. Schedules a session summary write.
8. Schedules best-effort note filing for substantive chat content.

### Note intake request formats

`POST /note/classify`:

```json
{
  "content": "note body",
  "topic": "learning"
}
```

`topic` is optional. Response action is one of `filed`, `inboxed`, or `dropped`.

`POST /inbox/classify`:

```json
{
  "entry_n": 1,
  "topic": "reference"
}
```

`POST /inbox/discard`:

```json
{
  "entry_n": 1
}
```

`POST /vault/sweep/start`:

```json
{
  "user_id": "discord-user-id",
  "force_reclassify": false,
  "dry_run": true,
  "source_folder": ""
}
```

Live sweep requests fail closed unless the runtime can confirm both the embedding model and classifier model are ready.

---

## Module Registration Contract

Every module container registers itself with Sentinel Core:

```http
POST /modules/register
X-Sentinel-Key: <shared key>
Content-Type: application/json
```

```json
{
  "name": "pathfinder",
  "base_url": "http://pf2e-module:8000",
  "routes": [
    {
      "path": "npc/create",
      "description": "Create NPC in Obsidian"
    }
  ]
}
```

Sentinel Core stores registrations in memory. Modules re-register on startup, and Pathfinder also sends a periodic registration heartbeat so a Sentinel Core restart self-heals.

Proxy path:

```text
/modules/{name}/{path:path} -> {base_url}/{path}
```

Proxy errors:

| Condition | Status |
|---|---:|
| Module name is not registered | `404` |
| Module transport error | `503` |
| Module request timeout on POST | `504` |

---

## Pathfinder Module Endpoints

Direct module routes are served inside the `pf2e-module` container. In normal operation, callers use Sentinel Core's proxy:

```text
POST /modules/pathfinder/npc/create
GET  /modules/pathfinder/npcs/
```

Pathfinder registers these routes:

| Method | Module path | Purpose |
|---|---|---|
| `GET` | `/healthz` | Module health check |
| `POST` | `/npc/create` | Create an NPC profile |
| `POST` | `/npc/update` | Update NPC fields |
| `POST` | `/npc/show` | Show NPC summary data |
| `POST` | `/npc/relate` | Add NPC relationship |
| `POST` | `/npc/import` | Bulk import NPCs from Foundry JSON |
| `POST` | `/npc/export-foundry` | Export NPC as Foundry actor JSON |
| `POST` | `/npc/token` | Generate a token image prompt |
| `POST` | `/npc/token-image` | Store an NPC token image |
| `POST` | `/npc/stat` | Return structured stat block data |
| `POST` | `/npc/pdf` | Generate a PDF stat card |
| `POST` | `/npc/say` | Generate in-character NPC dialogue |
| `POST` | `/harvest` | Monster harvest report |
| `POST` | `/rule/query` | PF2e rules query |
| `POST` | `/rule/show` | Show cached rulings under a topic |
| `POST` | `/rule/history` | Recent cached rulings |
| `POST` | `/rule/list` | List cached rule topics |
| `POST` | `/session` | Session verb router for `start`, `show`, and `end` |
| `POST` | `/foundry/event` | Receive Foundry VTT events |
| `POST` | `/foundry/messages/import` | Import Foundry chat logs |
| `GET` | `/npcs/` | List Sentinel NPCs |
| `GET` | `/npcs/{slug}/foundry-actor` | Return PF2e actor JSON for Foundry |
| `POST` | `/ingest` | Bulk import a PF2e archive folder |
| `POST` | `/player/onboard` | Create a per-player profile |
| `POST` | `/player/note` | Append a player note |
| `POST` | `/player/ask` | Store a player question |
| `POST` | `/player/npc` | Record player-specific NPC knowledge |
| `POST` | `/player/todo` | Append a player todo |
| `POST` | `/player/recall` | Deterministic player recall |
| `POST` | `/player/canonize` | Record a player-facing ruling outcome |
| `POST` | `/player/style` | List or set player style |
| `GET` | `/player/state` | Read player onboarding/style state |

The Discord command reference maps these routes to `:pf` commands.

---

## Container Contracts

### Sentinel Core

| Item | Value |
|---|---|
| Service | `sentinel-core` |
| Port | `8000` |
| Framework | FastAPI, Python 3.12 |
| Image | `ghcr.io/the-artificer-of-ciphers-llc/sentinel-core:latest` for deploy sample |
| Health | `GET /health` |

Required secret files:

- `secrets/sentinel_api_key`
- `secrets/obsidian_api_key`

Optional secret files:

- `secrets/lmstudio_api_key`
- `secrets/anthropic_api_key`
- Alpaca keys for planned trading module work

### Discord Interface

| Item | Value |
|---|---|
| Source service | `discord` |
| Deploy sample service | `discord-bot` |
| Image | `ghcr.io/the-artificer-of-ciphers-llc/sentinel-discord:latest` |
| Required secrets | `discord_bot_token`, `sentinel_api_key` |
| Main command | `/sen` |

### Pathfinder Module

| Item | Value |
|---|---|
| Service | `pf2e-module` |
| Registry name | `pathfinder` |
| Compose profile | `pf2e` |
| Internal port | `8000` |
| Image | `ghcr.io/the-artificer-of-ciphers-llc/sentinel-pathfinder:latest` |
| Health | `GET /healthz` |
| Vault mount | Host `OBSIDIAN_VAULT_PATH` mounted at `/vault` |

The vault mount is read-write for import flows that need filesystem locks, marker renames, or co-located dedupe state.

---

## Environment Variables

Non-secret configuration belongs in `.env`; secrets belong in `secrets/`.

| Variable | Used by | Purpose |
|---|---|---|
| `LMSTUDIO_BASE_URL` | Core | LM Studio `/v1` API base URL |
| `MODEL_NAME` | Core | Core chat model without provider prefix |
| `EMBEDDING_MODEL` | Core | Embedding model for recall/sweep |
| `AI_PROVIDER` | Core | `lmstudio`, `claude`, `ollama`, or `llamacpp` |
| `AI_FALLBACK_PROVIDER` | Core | `claude` or `none` |
| `CLAUDE_MODEL` | Core | Claude model id |
| `OBSIDIAN_API_URL` | Core | Obsidian Local REST API URL |
| `OBSIDIAN_BASE_URL` | Pathfinder | Obsidian Local REST API URL |
| `OBSIDIAN_API_KEY` | Pathfinder | Optional direct Obsidian REST bearer token |
| `OBSIDIAN_VAULT_PATH` | Pathfinder | Host path mounted as `/vault` |
| `LITELLM_MODEL` | Pathfinder | Module model with LiteLLM provider prefix |
| `LITELLM_API_BASE` | Pathfinder | OpenAI-compatible model server URL |
| `RULES_EMBEDDING_MODEL` | Pathfinder | Embedding model for PF2e rules retrieval |
| `SESSION_AUTO_RECAP` | Pathfinder | Auto-recap setting for session end |
| `SESSION_TZ` | Pathfinder | Timezone for session notes |
| `SESSION_RECAP_MODEL` | Pathfinder | Optional recap model override |
| `FOUNDRY_NARRATION_MODEL` | Pathfinder | Optional Foundry narration model override |
| `DISCORD_BOT_INTERNAL_URL` | Pathfinder | Internal Discord notification service URL |
| `DISCORD_ALLOWED_CHANNELS` | Discord | Comma-separated channel allowlist |
| `DISCORD_NOTIFY_CHANNEL_ID` | Discord | Foundry notification channel override |
| `SENTINEL_ADMIN_USER_IDS` | Core, Discord | Admin allowlist for destructive operations |
| `CORS_ALLOW_ORIGINS` | Core | Explicit browser origins |
| `CORS_ALLOW_ORIGIN_REGEX` | Core | Regex browser origins, typically Forge |
| `LOG_LEVEL` | All Python services | Logging verbosity |

---

## Compose Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Source-checkout stack using Compose `include` |
| `sentinel-core/compose.yml` | Core service |
| `interfaces/discord/compose.yml` | Discord interface service |
| `modules/pathfinder/compose.yml` | Pathfinder service with `pf2e` profile |
| `docs/deploy/docker-compose.ghcr.yml` | Pre-built image deployment sample |
| `docs/deploy/.env.sample` | Pre-built deployment environment template |

Source-checkout wrapper:

```bash
./sentinel.sh up -d
./sentinel.sh --discord --pf2e up -d
./sentinel.sh down
```

Pre-built image deployment:

```bash
docker compose -f docker-compose.ghcr.yml up -d
```
