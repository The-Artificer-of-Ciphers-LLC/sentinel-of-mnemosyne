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
import { spawnPi, sendPrompt, getPiHealth } from './pi-adapter';

const app = Fastify({ logger: true });

interface PromptBody {
  message: string;
}

app.post<{ Body: PromptBody }>('/prompt', async (request, reply) => {
  const { message } = request.body;

  if (!message || typeof message !== 'string') {
    return reply.code(400).send({ error: 'message field required (string)' });
  }

  const health = getPiHealth();
  if (!health.alive) {
    return reply.code(503).send({ error: 'Pi subprocess not alive' });
  }

  try {
    const content = await sendPrompt(message);
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
