import { useCallback, type Dispatch, type MutableRefObject, type SetStateAction } from 'react';
import { toast } from 'sonner';
import type { MessageType } from '../types';
import { getStreamRunId } from './activeRun';
import { CANCELLED_BY_USER, cancelAgentRun } from './runControl';

interface UseRunStopParams {
  isStreaming: boolean;
  /** Queued/Started run found in the loaded messages, if any. */
  pendingRunId: string | null;
  /** True when the composer holds a draft: Send wins over Stop for a queued run. */
  hasDraft: boolean;
  abortControllerRef: MutableRefObject<AbortController | null>;
  setMessages: Dispatch<SetStateAction<MessageType[]>>;
}

export function markCancelled(messages: MessageType[], runId: string | null, streaming: boolean): MessageType[] {
  let target = -1;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (m.from !== 'assistant' || m.error) continue;
    const isRun = !!runId && (m.key === runId || m.agentRunId === runId);
    const isStreamBubble = streaming && !m.runStatus;
    if (isRun || isStreamBubble) {
      target = i;
      break;
    }
  }
  if (target < 0) return messages;
  const next = [...messages];
  next[target] = { ...next[target], runStatus: 'Failed', error: CANCELLED_BY_USER, reasoningStreaming: false };
  return next;
}

/**
 * Stop for streaming, queued and started runs: cancels the Agent Run on the
 * server, aborts the SSE fetch (if any) and shows the message as cancelled.
 * The server persists the run as Failed / "Cancelled by user", so a reload
 * shows the same state.
 */
export function useRunStop({ isStreaming, pendingRunId, hasDraft, abortControllerRef, setMessages }: UseRunStopParams) {
  const canStop = isStreaming || (!!pendingRunId && !hasDraft);

  const handleStop = useCallback(() => {
    const runId = isStreaming ? getStreamRunId() ?? pendingRunId : pendingRunId;
    const cancel = runId ? cancelAgentRun(runId) : Promise.resolve(null);
    if (isStreaming) {
      // Streaming: tear down the fetch right away; the cancel request is best effort.
      cancel.catch(() => undefined);
      setMessages((prev) => markCancelled(prev, runId, true));
      abortControllerRef.current?.abort();
      return;
    }
    cancel
      .then((result) => {
        if (result?.cancel_requested) setMessages((prev) => markCancelled(prev, runId, false));
      })
      .catch((error: unknown) => {
        toast.error('Could not stop the run', {
          description: error instanceof Error ? error.message : undefined,
        });
      });
  }, [isStreaming, pendingRunId, abortControllerRef, setMessages]);

  return { canStop, handleStop };
}
