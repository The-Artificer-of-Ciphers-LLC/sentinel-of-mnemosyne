/**
 * Sentinel Connector — Foundry VTT module for Sentinel of Mnemosyne
 *
 * Hooks into PF2e-typed dice rolls and trigger-prefixed chat messages.
 * Delivers events via a webhook-first hybrid:
 *   - If sentinelBaseUrl is set: attempt Sentinel first (3s timeout), then fall back to webhook.
 *   - If sentinelBaseUrl is empty: post directly to Discord webhook (webhook-only mode).
 *   - If neither is configured: log once, no-op.
 *
 * Decisions implemented:
 *   D-01: preCreateChatMessage hook — forward PF2e rolls with dc
 *   D-02: chat forwarding only when trigger prefix matches
 *   D-03: X-Sentinel-Key stored as world setting (GM-only write, config:false — CR-03)
 *   D-04: compatibility minimum=12 verified=14 (in module.json)
 *   D-05: roll payload shape (event_type, roll_type, actor_name, target_name, outcome, ...)
 *   D-06: chat payload shape (event_type, actor_name, content, timestamp)
 *   D-07: sentinelBaseUrl stored as world setting (empty default = webhook-only mode)
 *   D-17: ESModule (no bundler) — Foundry v14 native support
 *   Plan 35-06: webhook-first fallback + PNACORSMiddleware gap closure
 *
 * IMPORTANT: preCreateChatMessage ALWAYS returns true — never suppresses Foundry messages.
 * postEvent() is called fire-and-forget (no await) so hook returns synchronously.
 */

const MODULE_ID = 'sentinel-connector';

// ---------------------------------------------------------------------------
// Outcome derivation (D-01 amendment — context.outcome may not be populated
// at preCreateChatMessage time per pf2e-modifiers-matter pattern).
// PF2e four-degree algorithm: delta = rollTotal - dcValue
// ---------------------------------------------------------------------------
function deriveOutcome(rollTotal, dcValue) {
  const delta = rollTotal - dcValue;
  if (delta >= 10) return 'criticalSuccess';
  if (delta >= 0)  return 'success';
  if (delta >= -9) return 'failure';
  return 'criticalFailure';
}

// ---------------------------------------------------------------------------
// Settings registration (D-02, D-03, D-07, Plan 35-06)
// ---------------------------------------------------------------------------
Hooks.once('init', () => {
  game.settings.register(MODULE_ID, 'sentinelBaseUrl', {
    name: 'Sentinel Base URL',
    hint: 'Sentinel server URL. LAN: http://192.168.1.x:8000  |  Forge play: https://mac-mini.tailXXXX.ts.net:8000  |  Leave empty for webhook-only mode.',
    scope: 'world',
    config: true,
    type: String,
    default: '',
  });

  game.settings.register(MODULE_ID, 'discordWebhookUrl', {
    name: 'Discord Webhook URL',
    hint: 'Discord incoming webhook URL for direct roll embeds. Used as fallback when Sentinel is unreachable, or as primary when Sentinel Base URL is empty. Get this from: Discord channel settings → Integrations → Webhooks → New Webhook → Copy Webhook URL.',
    scope: 'world',
    config: true,
    type: String,
    default: '',
  });

  game.settings.register(MODULE_ID, 'apiKey', {
    name: 'Sentinel API Key',
    hint: 'The X-Sentinel-Key shared secret from your .env file.',
    scope: 'world',
    config: false,  // CR-03: hide from settings UI panel — readable via browser devtools otherwise
    type: String,
    default: '',
  });

  game.settings.register(MODULE_ID, 'chatPrefix', {
    name: 'Chat Trigger Prefix (optional)',
    hint: 'Messages starting with this prefix are forwarded to Sentinel. Leave blank to disable chat forwarding.',
    scope: 'world',
    config: true,
    type: String,
    default: '',
  });
});

// ---------------------------------------------------------------------------
// Hook registration (D-01, D-02)
// ---------------------------------------------------------------------------
Hooks.once('ready', () => {
  Hooks.on('preCreateChatMessage', (chatMessage, _data, _options) => {
    const pf2eFlags = chatMessage.flags?.pf2e;

    if (!pf2eFlags?.context) {
      // Not a PF2e roll — check chat prefix (D-02)
      const prefix = game.settings.get(MODULE_ID, 'chatPrefix');
      if (!prefix) return true; // no prefix configured — skip chat forwarding
      const content = chatMessage.content ?? '';
      if (!content.startsWith(prefix)) return true;

      const rawContent = content;
      const strippedContent = rawContent.startsWith(prefix)
        ? rawContent.slice(prefix.length).trim()
        : rawContent.trim();

      postEvent({
        event_type: 'chat',
        actor_name: chatMessage.speaker?.alias ?? 'DM',
        content: strippedContent,
        timestamp: new Date().toISOString(),
      });
      return true; // NEVER suppress the message
    }

    // PF2e roll — check if DC is tracked (D-01 filter)
    const context = pf2eFlags.context;
    const dcValue = context.dc?.value ?? null;
    // dc_hidden: DC structure exists but value is secret (captured BEFORE any early-return)
    const dc_hidden = (context.dc != null && dcValue == null);

    if (!context.dc) return true; // no DC at all — initiative, damage, flat check etc.

    const rollTotal = chatMessage.rolls?.[0]?.total ?? chatMessage.roll?.total;
    if (rollTotal == null) return true; // roll data unavailable — skip (Pitfall 2)

    // D-01 amendment: read pre-computed outcome or derive from roll math.
    // CR-01: when DC is hidden (dcValue=null), deriveOutcome would coerce null→0 and
    // produce wrong results. Use context.outcome when available; fall back to "unknown"
    // for hidden-DC rolls where pf2e hasn't pre-computed the outcome.
    const outcome = context.outcome
      ?? (dc_hidden ? 'unknown' : deriveOutcome(rollTotal, dcValue));

    const actorName = chatMessage.speaker?.alias ?? chatMessage.actor?.name ?? 'Unknown';

    // Resolve target name synchronously (A2 assumption — fromUuidSync may be unavailable)
    const targetTokenUuid = context.target?.token;
    const targetToken = (targetTokenUuid && typeof fromUuidSync === 'function')
      ? fromUuidSync(targetTokenUuid)
      : null;
    const targetName = targetToken?.name ?? null;

    postEvent({
      event_type: 'roll',
      roll_type: context.type ?? 'unknown',
      actor_name: actorName,
      target_name: targetName,
      outcome: outcome,
      roll_total: rollTotal,
      dc: dcValue,
      dc_hidden: dc_hidden,
      item_name: pf2eFlags.origin?.name ?? null,
      timestamp: new Date().toISOString(),
    });

    return true; // ALWAYS return true — never suppress the Foundry chat message
  });
});

// ---------------------------------------------------------------------------
// Hybrid POST: Sentinel primary (3s timeout) → Discord webhook fallback
//
// Sentinel path: LLM narration, full roll data, requires HTTPS for Forge play.
// Webhook path: direct Discord embed, no LLM, works from any browser/network.
// If sentinelBaseUrl is empty: skip Sentinel entirely, post webhook directly.
// If both are unconfigured: log once to console and return (no user-visible error).
// ---------------------------------------------------------------------------
const SENTINEL_TIMEOUT_MS = 3000;

const OUTCOME_EMOJI = {
  criticalSuccess: '🎯',
  success: '✅',
  failure: '❌',
  criticalFailure: '💀',
  unknown: '🎲',
};

const OUTCOME_COLOR = {
  criticalSuccess: 0x00FF00,
  success: 0x00AA00,
  failure: 0xFF4444,
  criticalFailure: 0x880000,
  unknown: 0x888888,
};

async function postEvent(payload) {
  const sentinelUrl = game.settings.get(MODULE_ID, 'sentinelBaseUrl');
  const sentinelKey = game.settings.get(MODULE_ID, 'apiKey');
  const webhookUrl = game.settings.get(MODULE_ID, 'discordWebhookUrl');

  // Primary path: Sentinel (LLM narration)
  if (sentinelUrl) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), SENTINEL_TIMEOUT_MS);
      await fetch(`${sentinelUrl}/modules/pathfinder/foundry/event`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Sentinel-Key': sentinelKey,
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      return; // success — no fallback needed
    } catch (err) {
      // AbortError = 3s timeout; TypeError = mixed content / network / CORS block
      console.warn('[sentinel-connector] Sentinel POST failed, falling back to webhook:', err.message);
    }
  }

  // Fallback path: direct Discord webhook (no LLM narration)
  if (!webhookUrl) {
    if (!sentinelUrl) {
      // Neither configured — log once, silent no-op
      console.info('[sentinel-connector] No Sentinel URL or Discord webhook configured — roll not forwarded.');
    }
    return;
  }

  // Build embed from local roll data
  const outcome = payload.outcome ?? 'unknown';
  const emoji = OUTCOME_EMOJI[outcome] ?? '🎲';
  const color = OUTCOME_COLOR[outcome] ?? 0x888888;

  let title = `${emoji} ${outcome}`;
  if (payload.actor_name) title += ` | ${payload.actor_name}`;
  if (payload.target_name) title += ` vs ${payload.target_name}`;

  let footerParts = [];
  if (payload.roll_total != null) footerParts.push(`Roll: ${payload.roll_total}`);
  if (payload.dc_hidden) {
    footerParts.push('DC: [hidden]');
  } else if (payload.dc != null) {
    footerParts.push(`DC/AC: ${payload.dc}`);
  }
  if (payload.item_name) footerParts.push(payload.item_name);
  if (payload.roll_type && payload.roll_type !== 'unknown') footerParts.push(payload.roll_type);

  const embed = {
    title,
    description: payload.event_type === 'chat' ? (payload.content ?? '') : '',
    footer: { text: footerParts.join(' | ') },
    color,
  };

  fetch(webhookUrl, {
    method: 'POST',
    mode: 'no-cors', // Discord webhooks: no CORS preflight, opaque response is fine
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ embeds: [embed] }),
  }).catch(() => {}); // fire-and-forget
}
