import { useCallback, useRef, type Dispatch, type MutableRefObject, type SetStateAction } from 'react';
import { toast } from 'sonner';
import { getAgentRunStatus } from '@/services/chatApi';
import type { MessageType } from '../types';
import { getStreamClientKey, getStreamRunId } from './activeRun';
import { findRunByClientKey } from './gatewayRecovery';
import { cancelAgentRun } from './runControl';
import { applyStopOutcome, cancelAndAwaitRun, markStopping, stopTimings } from './stopRun';

interface UseRunStopParams {
  isStreaming: boolean;
  /** Queued/Started run found in the loaded messages, if any. */
  pendingRunId: string | null;
  /** True when the composer holds a draft: Send wins over Stop for a queued run. */
  hasDraft: boolean;
  abortControllerRef: MutableRefObject<AbortController | null>;
  setMessages: Dispatch<SetStateAction<MessageType[]>>;
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Stopped before the stream reported its run: look it up by the key the request carried. */
async function findStoppedRun(clientKey: string): Promise<string | null> {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const runId = await findRunByClientKey(clientKey).catch(() => null);
    if (runId) return runId;
    await sleep(stopTimings.pollMs);
  }
  return null;
}

/**
 * Stop for streaming, queued and started runs: asks the server to cancel the
 * Agent Run, aborts the SSE fetch (if any), shows the message as stopping and
 * only shows it as cancelled once the run itself is terminal.
 */
export function useRunStop({ isStreaming, pendingRunId, hasDraft, abortControllerRef, setMessages }: UseRunStopParams) {
  const canStop = isStreaming || (!!pendingRunId && !hasDraft);
  const inFlightRef = useRef<Set<string>>(new Set());

  const handleStop = useCallback(() => {
    const knownRunId = isStreaming ? getStreamRunId() ?? pendingRunId : pendingRunId;
    const clientKey = isStreaming ? getStreamClientKey() : null;
    const token = knownRunId ?? clientKey ?? '';
    if (inFlightRef.current.has(token)) return;
    inFlightRef.current.add(token);

    const settle = async () => {
      const runId = knownRunId ?? (clientKey ? await findStoppedRun(clientKey) : null);
      if (!runId) {
        // No run was ever created: nothing is left running.
        setMessages((prev) => applyStopOutcome(prev, null, { status: 'Failed' }));
        return;
      }
      if (!knownRunId) {
        setMessages((prev) => prev.map((m) => (m.stopping && !m.agentRunId ? { ...m, agentRunId: runId } : m)));
      }
      const outcome = await cancelAndAwaitRun(runId, {
        cancel: cancelAgentRun,
        getStatus: getAgentRunStatus,
        sleep,
        now: Date.now,
        ...stopTimings,
      });
      setMessages((prev) => applyStopOutcome(prev, runId, outcome));
      if (!outcome) toast.error('The run has not stopped yet', { description: 'Check back in a moment.' });
    };

    setMessages((prev) => markStopping(prev, knownRunId, isStreaming));
    // Runs up to the first await now, so the cancel request is sent before the stream is torn down.
    const settled = settle();
    if (isStreaming) abortControllerRef.current?.abort();
    settled
      .catch((error: unknown) => {
        setMessages((prev) => applyStopOutcome(prev, knownRunId, null));
        toast.error('Could not stop the run', {
          description: error instanceof Error ? error.message : undefined,
        });
      })
      .finally(() => inFlightRef.current.delete(token));
  }, [isStreaming, pendingRunId, abortControllerRef, setMessages]);

  return { canStop, handleStop };
}
