/**
 * bridge.ts
 *
 * Fastify HTTP bridge. Receives POST /prompt from Sentinel Core
 * and forwards to Pi subprocess via pi-adapter.ts.
 *
 * This file does NOT import from @mariozechner/pi-coding-agent directly.
 * All pi-mono contact is in pi-adapter.ts (adapter pattern, CORE-02).
 */

import Fastify from 'fastify';
import { spawnPi, sendPrompt, getPiHealth, resetSession } from './pi-adapter';

const app = Fastify({ logger: true });

interface MessageItem {
  role: string;
  content: string;
}

interface PromptBody {
  message?: string;
  messages?: MessageItem[];
}

/**
 * Serialize a messages array into a flat string for Pi RPC.
 * Pi v0.66 sendPrompt() only accepts message: string — no messages array.
 * Format: [ROLE]: content pairs separated by double newline.
 * Roles are uppercased: user→USER, assistant→ASSISTANT.
 */
function serializeMessages(messages: MessageItem[]): string {
  return messages
    .map((m) => `[${m.role.toUpperCase()}]: ${m.content}`)
    .join('\n\n');
}

app.post<{ Body: PromptBody }>('/prompt', async (request, reply) => {
  const body = request.body;

  let messageStr: string;
  if (body.messages && Array.isArray(body.messages) && body.messages.length > 0) {
    messageStr = serializeMessages(body.messages);
  } else if (body.message && typeof body.message === 'string') {
    messageStr = body.message;
  } else {
    return reply.code(400).send({ error: 'message (string) or messages (array) field required' });
  }

  const health = getPiHealth();
  if (!health.alive) {
    return reply.code(503).send({ error: 'Pi subprocess not alive' });
  }

  try {
    const content = await sendPrompt(messageStr);
    return reply.send({ content });
  } catch (err: unknown) {
    const errMessage = err instanceof Error ? err.message : 'Unknown error';
    if (errMessage.includes('not alive') || errMessage.includes('exited')) {
      return reply.code(503).send({ error: errMessage });
    }
    if (errMessage.includes('timeout')) {
      return reply.code(504).send({ error: errMessage });
    }
    return reply.code(500).send({ error: errMessage });
  }
});

app.post('/session/reset', async (_request, reply) => {
  const health = getPiHealth();
  if (!health.alive) {
    return reply.code(503).send({ error: 'Pi subprocess not alive' });
  }
  try {
    await resetSession();
    return reply.send({ ok: true });
  } catch (err: unknown) {
    const errMessage = err instanceof Error ? err.message : 'Unknown error';
    return reply.code(500).send({ error: errMessage });
  }
});

app.get('/health', async (_request, reply) => {
  const health = getPiHealth();
  return reply.send({
    status: health.alive ? 'ok' : 'degraded',
    piAlive: health.alive,
    restarts: health.restarts,
  });
});

const PORT = parseInt(process.env.PORT ?? '3000', 10);

async function start() {
  // Spawn Pi subprocess before accepting requests
  spawnPi();

  await app.listen({ port: PORT, host: '0.0.0.0' });
  console.log(`[bridge] Fastify listening on port ${PORT}`);
}

start().catch((err) => {
  console.error('[bridge] Fatal startup error:', err);
  process.exit(1);
});
