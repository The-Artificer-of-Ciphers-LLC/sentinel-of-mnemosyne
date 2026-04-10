/**
 * pi-adapter.ts
 *
 * Single point of contact with @mariozechner/pi-coding-agent.
 * All pi-mono imports are isolated here. To upgrade pi-mono:
 *   1. Update package.json pin to new exact version
 *   2. Review pi-mono release notes for RPC protocol changes
 *   3. Update this file only — bridge.ts and callers are unaffected
 *
 * Pi RPC protocol: JSONL over stdin/stdout.
 * CRITICAL: DO NOT use readline for stdout parsing.
 *   readline splits on U+2028 (line separator) and U+2029 (paragraph separator),
 *   which are valid inside JSON strings. Manual \n-only splitting is required.
 */

import { spawn, ChildProcess } from 'child_process';

interface PiEvent {
  type: string;
  messages?: Array<{ role: string; content: string }>;
  [key: string]: unknown;
}

interface PiHealth {
  alive: boolean;
  restarts: number;
}

let piProcess: ChildProcess | null = null;
let restartCount = 0;
let isProcessing = false;
const pendingQueue: Array<() => void> = [];
let currentResolve: ((text: string) => void) | null = null;
let currentReject: ((err: Error) => void) | null = null;
let responseTimeout: ReturnType<typeof setTimeout> | null = null;

export function spawnPi(): void {
  piProcess = spawn('pi', ['--mode', 'rpc', '--no-session'], {
    stdio: ['pipe', 'pipe', 'inherit'],
  });

  // CRITICAL: Manual \n splitting — do NOT use readline
  let stdoutBuffer = '';
  piProcess.stdout!.on('data', (chunk: Buffer) => {
    stdoutBuffer += chunk.toString('utf8');
    const lines = stdoutBuffer.split('\n');
    stdoutBuffer = lines.pop()!; // keep incomplete last line in buffer
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const event: PiEvent = JSON.parse(trimmed);
        handleEvent(event);
      } catch {
        // Non-JSON output (startup logs, etc.) — ignore
      }
    }
  });

  piProcess.stdout!.on('close', () => {
    piProcess = null;
    isProcessing = false;
    // Reject any in-flight request
    if (currentReject) {
      currentReject(new Error('Pi subprocess exited unexpectedly'));
      currentResolve = null;
      currentReject = null;
    }
    if (responseTimeout) {
      clearTimeout(responseTimeout);
      responseTimeout = null;
    }
    restartCount++;
    console.warn(`[pi-adapter] Pi subprocess exited. Restart #${restartCount}. Respawning in 1s.`);
    setTimeout(spawnPi, 1000);
    // Drain queue after respawn settles
    setTimeout(drainQueue, 2000);
  });

  console.log('[pi-adapter] Pi subprocess started.');
  drainQueue();
}

function handleEvent(event: PiEvent): void {
  if (event.type === 'agent_end') {
    if (responseTimeout) {
      clearTimeout(responseTimeout);
      responseTimeout = null;
    }
    const messages = event.messages ?? [];
    const assistantMessages = messages.filter((m) => m.role === 'assistant');
    const lastContent = assistantMessages.length > 0
      ? assistantMessages[assistantMessages.length - 1].content
      : '';
    if (currentResolve) {
      currentResolve(lastContent);
      currentResolve = null;
      currentReject = null;
    }
    isProcessing = false;
    drainQueue();
  }
  // Other events (agent_start, turn_start, message_update, turn_end) are no-ops for Phase 1
}

function drainQueue(): void {
  if (isProcessing || pendingQueue.length === 0 || !piProcess) return;
  const next = pendingQueue.shift()!;
  next();
}

export function sendPrompt(message: string): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const execute = () => {
      if (!piProcess) {
        reject(new Error('Pi subprocess not alive'));
        return;
      }
      isProcessing = true;
      currentResolve = resolve;
      currentReject = reject;

      // 30-second hard timeout
      responseTimeout = setTimeout(() => {
        currentResolve = null;
        currentReject = null;
        isProcessing = false;
        reject(new Error('Pi response timeout after 30s'));
        drainQueue();
      }, 30_000);

      const cmd = JSON.stringify({ type: 'prompt', message }) + '\n';
      piProcess!.stdin!.write(cmd);
    };

    if (isProcessing || !piProcess) {
      pendingQueue.push(execute);
    } else {
      execute();
    }
  });
}

export function getPiHealth(): PiHealth {
  return {
    alive: piProcess !== null,
    restarts: restartCount,
  };
}
