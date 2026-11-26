import type { AgentRunStatusResponse } from '@/services/chatApi';
import type { MessageType } from '../types';
import { CANCELLED_BY_USER, type CancelRunResult } from './runControl';

/** Server wording for a run that ended because the browser closed the stream (what Stop does). */
const CLIENT_DISCONNECTED = 'Client disconnected';

export interface StopOutcome {
  status: 'Success' | 'Failed';
  response?: string | null;
  error?: string | null;
}

export interface StopDeps {
  cancel: (runId: string) => Promise<CancelRunResult>;
  getStatus: (runId: string) => Promise<AgentRunStatusResponse>;
  sleep: (ms: number) => Promise<void>;
  now: () => number;
  pollMs: number;
  totalTimeoutMs: number;
}

export const stopTimings = { pollMs: 2000, totalTimeoutMs: 10 * 60 * 1000 };

function toOutcome(status: 'Success' | 'Failed', run?: AgentRunStatusResponse): StopOutcome {
  if (status === 'Success') return { status, response: run?.response };
  const error = run?.error;
  return { status, error: !error || error === CLIENT_DISCONNECTED ? CANCELLED_BY_USER : error };
}

/**
 * Ask the server to cancel a run, then poll until the run is terminal. Resolves
 * null when it is still open at the deadline: it must not be shown as cancelled.
 */
export async function cancelAndAwaitRun(runId: string, deps: StopDeps): Promise<StopOutcome | null> {
  const result = await deps.cancel(runId);
  const terminal = result.status === 'Success' || result.status === 'Failed' ? result.status : null;
  if (!terminal && !result.cancel_requested) throw new Error('The server did not accept the stop request.');
  const deadline = deps.now() + deps.totalTimeoutMs;
  for (;;) {
    let run: AgentRunStatusResponse | undefined;
    try {
      run = await deps.getStatus(runId);
    } catch {
      // A failed poll is retried until the deadline.
    }
    if (run?.status === 'Success' || run?.status === 'Failed') return toOutcome(run.status, run);
    // The cancel call already reported a terminal run: trust it if the status read fails.
    if (terminal && !run) return toOutcome(terminal);
    if (deps.now() >= deadline) return null;
    await deps.sleep(deps.pollMs);
  }
}

/** Show the stopped run's bubble as "stopping" (not cancelled) until the server confirms. */
export function markStopping(messages: MessageType[], runId: string | null, streaming: boolean): MessageType[] {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (m.from !== 'assistant' || m.error) continue;
    const isRun = !!runId && (m.key === runId || m.agentRunId === runId);
    if (isRun || (streaming && !m.runStatus)) {
      const next = [...messages];
      next[i] = { ...m, stopping: true, agentRunId: runId ?? m.agentRunId, reasoningStreaming: false };
      return next;
    }
  }
  return messages;
}

/** Apply the terminal result to the stopping bubble; `null` only drops the stopping state. */
export function applyStopOutcome(
  messages: MessageType[],
  runId: string | null,
  outcome: StopOutcome | null
): MessageType[] {
  return messages.map((m) => {
    const isRun = runId ? m.key === runId || m.agentRunId === runId : !!m.stopping && !m.agentRunId;
    if (m.from !== 'assistant' || !isRun) return m;
    if (!outcome) return { ...m, stopping: false };
    if (outcome.status === 'Failed') {
      return { ...m, stopping: false, runStatus: 'Failed', error: outcome.error ?? CANCELLED_BY_USER };
    }
    // The run finished before the stop took effect: show its real reply.
    return {
      ...m,
      stopping: false,
      runStatus: 'Success',
      error: undefined,
      versions: m.versions.map((v, i) => (i === 0 ? { ...v, content: outcome.response || v.content } : v)),
    };
  });
}
