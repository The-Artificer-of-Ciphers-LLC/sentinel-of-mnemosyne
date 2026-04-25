/**
 * Sentinel Connector — Foundry VTT module for Sentinel of Mnemosyne
 *
 * Hooks into PF2e-typed dice rolls and trigger-prefixed chat messages,
 * POSTs structured events to POST {SENTINEL_BASE_URL}/modules/pathfinder/foundry/event.
 *
 * Decisions implemented:
 *   D-01: preCreateChatMessage hook — forward PF2e rolls with dc
 *   D-02: chat forwarding only when trigger prefix matches
 *   D-03: X-Sentinel-Key stored as world setting (GM-only write)
 *   D-04: compatibility minimum=12 verified=14 (in module.json)
 *   D-05: roll payload shape (event_type, roll_type, actor_name, target_name, outcome, ...)
 *   D-06: chat payload shape (event_type, actor_name, content, timestamp)
 *   D-07: SENTINEL_BASE_URL stored as world setting
 *   D-17: ESModule (no bundler) — Foundry v14 native support
 *
 * IMPORTANT: preCreateChatMessage ALWAYS returns true — never suppresses Foundry messages.
 * fetch() calls use .catch(() => {}) — fire-and-forget, never block the hook.
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
// Settings registration (D-02, D-03, D-07)
// ---------------------------------------------------------------------------
Hooks.once('init', () => {
  game.settings.register(MODULE_ID, 'baseUrl', {
    name: 'Sentinel Base URL',
    hint: 'Base URL of your Sentinel server, e.g. http://192.168.1.10:8000',
    scope: 'world',
    config: true,
    type: String,
    default: 'http://localhost:8000',
  });

  game.settings.register(MODULE_ID, 'apiKey', {
    name: 'Sentinel API Key',
    hint: 'The X-Sentinel-Key shared secret from your .env file.',
    scope: 'world',
    config: true,
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
      _postChatEvent(chatMessage, prefix);
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

    // D-01 amendment: read pre-computed outcome or derive from roll math
    const outcome = context.outcome ?? deriveOutcome(rollTotal, dcValue);

    const actorName = chatMessage.speaker?.alias ?? chatMessage.actor?.name ?? 'Unknown';

    // Resolve target name synchronously (A2 assumption — fromUuidSync may be unavailable)
    const targetTokenUuid = context.target?.token;
    const targetToken = (targetTokenUuid && typeof fromUuidSync === 'function')
      ? fromUuidSync(targetTokenUuid)
      : null;
    const targetName = targetToken?.name ?? null;

    _postRollEvent({
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
// POST helpers (D-05, D-06, D-07)
// ---------------------------------------------------------------------------
function _postRollEvent(payload) {
  const baseUrl = game.settings.get(MODULE_ID, 'baseUrl');
  const apiKey = game.settings.get(MODULE_ID, 'apiKey');
  if (!apiKey) return; // not configured — skip silently

  fetch(`${baseUrl}/modules/pathfinder/foundry/event`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Sentinel-Key': apiKey,
    },
    body: JSON.stringify(payload),
  }).catch(err => console.warn('[sentinel-connector] Roll POST failed:', err));
}

function _postChatEvent(chatMessage, prefix) {
  const baseUrl = game.settings.get(MODULE_ID, 'baseUrl');
  const apiKey = game.settings.get(MODULE_ID, 'apiKey');
  if (!apiKey) return;

  const rawContent = chatMessage.content ?? '';
  const content = rawContent.startsWith(prefix)
    ? rawContent.slice(prefix.length).trim()
    : rawContent.trim();

  fetch(`${baseUrl}/modules/pathfinder/foundry/event`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Sentinel-Key': apiKey,
    },
    body: JSON.stringify({
      event_type: 'chat',
      actor_name: chatMessage.speaker?.alias ?? 'DM',
      content: content,
      timestamp: new Date().toISOString(),
    }),
  }).catch(err => console.warn('[sentinel-connector] Chat POST failed:', err));
}
