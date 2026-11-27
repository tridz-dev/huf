import type { MessageType } from '../types';

/**
 * Agent Run id of the SSE turn currently in flight. The stream endpoint emits
 * it in its first frame (`run_started`), before any provider output, so Stop
 * can cancel the run on the server even while it is still thinking.
 */
let streamRunId: string | null = null;

export function setStreamRunId(runId: string | null): void {
  streamRunId = runId;
}

export function getStreamRunId(): string | null {
  return streamRunId;
}

/** Idempotency key sent with the SSE turn in flight; finds its run before `run_started` arrives. */
let streamClientKey: string | null = null;

export function newStreamClientKey(): string {
  streamClientKey = `chat-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  return streamClientKey;
}

export function getStreamClientKey(): string | null {
  return streamClientKey;
}

/** Id of the newest Queued/Started run among the loaded messages (its message key is the run id). */
export function findPendingRunId(messages: MessageType[]): string | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.from === 'assistant' && (message.runStatus === 'Queued' || message.runStatus === 'Started')) {
      return message.agentRunId || message.key;
    }
  }
  return null;
}
