// pi-harness/src/bridge.test.ts
import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest';

// vi.mock is hoisted above all imports by vitest's transform layer.
// The factory MUST include ALL four exports that bridge.ts imports from pi-adapter.
// Omitting any export causes undefined destructuring and a runtime error in bridge.ts.
vi.mock('./pi-adapter', () => ({
  spawnPi: vi.fn(),
  sendPrompt: vi.fn(),
  getPiHealth: vi.fn(() => ({ alive: true, restarts: 0 })),
  sendReset: vi.fn(),
}));

// Imports come AFTER vi.mock() so the hoisted mock is in place before bridge.ts loads.
import { buildApp } from './bridge';
import { sendReset } from './pi-adapter';

describe('POST /reset', () => {
  let app: ReturnType<typeof buildApp>;

  beforeAll(async () => {
    app = buildApp();
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
  });

  it('returns 200 with { status: ok }', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/reset',
    });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({ status: 'ok' });
  });

  it('calls sendReset() exactly once per request', async () => {
    vi.clearAllMocks();
    await app.inject({ method: 'POST', url: '/reset' });
    expect(sendReset).toHaveBeenCalledOnce();
  });
});
