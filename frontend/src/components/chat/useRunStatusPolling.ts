import { useEffect, useMemo, useRef, type Dispatch, type SetStateAction } from 'react';
import { getAgentRunStatus } from '@/services/chatApi';
import { applyPolledRunStatus, upsertAgentRunStatusFromSocket } from './chatMessageList.mappers';
import type { MessageType } from './types';

export const RUN_STATUS_POLL_GRACE_MS = 8000;
export const RUN_STATUS_POLL_INTERVAL_MS = 5000;
export const RUN_STATUS_POLL_TIMEOUT_MS = 10 * 60 * 1000;

const RUN_STATUS_POLL_TIMEOUT_ERROR =
  'The agent run did not finish within 10 minutes. Please try sending the message again.';

function isPendingRun(message: MessageType): boolean {
  return message.runStatus === 'Queued' || message.runStatus === 'Started';
}

/**
 * Polling fallback for queued agent runs.
 *
 * The socket normally drives the pending bubble lifecycle via
 * `agent_run_status` events. If one of those events is missed the bubble
 * would stay Queued/Started forever, so while pending runs exist we poll
 * `get_agent_run_status` and replay the same mapper transitions the socket
 * handler would apply. Polling stops when no pending runs remain.
 */
export function useRunStatusPolling(
  messages: MessageType[],
  setMessages: Dispatch<SetStateAction<MessageType[]>>,
  conversationId: string | null
) {
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const firstSeenRef = useRef<Map<string, number>>(new Map());
  const inFlightRef = useRef(false);

  // Joined key only changes when the set of pending runs changes, so a
  // Queued -> Started socket transition does not restart the timers.
  const pendingKey = useMemo(
    () => messages.filter(isPendingRun).map((message) => message.key).join(','),
    [messages]
  );

  useEffect(() => {
    if (!conversationId || !pendingKey) {
      return;
    }

    const runIds = pendingKey.split(',');

    // Track when each run was first seen (for the per-run timeout) and prune
    // runs that are no longer pending.
    const now = Date.now();
    for (const runId of runIds) {
      if (!firstSeenRef.current.has(runId)) {
        firstSeenRef.current.set(runId, now);
      }
    }
    for (const runId of firstSeenRef.current.keys()) {
      if (!runIds.includes(runId)) {
        firstSeenRef.current.delete(runId);
      }
    }

    const pollOnce = async () => {
      if (inFlightRef.current) return;
      inFlightRef.current = true;
      try {
        await Promise.all(
          runIds.map(async (runId) => {
            const current = messagesRef.current.find((message) => message.key === runId);
            if (!current || !isPendingRun(current)) return;

            const firstSeen = firstSeenRef.current.get(runId) ?? now;
            if (Date.now() - firstSeen >= RUN_STATUS_POLL_TIMEOUT_MS) {
              setMessages((prev) =>
                upsertAgentRunStatusFromSocket(prev, {
                  type: 'agent_run_status',
                  agent_run_id: runId,
                  conversation_id: conversationId,
                  status: 'Failed',
                  error: RUN_STATUS_POLL_TIMEOUT_ERROR,
                })
              );
              return;
            }

            try {
              const result = await getAgentRunStatus(runId);
              if (!result?.status || result.status === current.runStatus) return;
              setMessages((prev) => applyPolledRunStatus(prev, result, conversationId));
            } catch (error) {
              // A failed poll must not kill the fallback; the next tick retries.
              console.error('Error polling agent run status:', error);
            }
          })
        );
      } finally {
        inFlightRef.current = false;
      }
    };

    // Give the socket a grace period to deliver its events before polling.
    let intervalId: ReturnType<typeof setInterval> | undefined;
    const graceTimeoutId = setTimeout(() => {
      void pollOnce();
      intervalId = setInterval(() => {
        void pollOnce();
      }, RUN_STATUS_POLL_INTERVAL_MS);
    }, RUN_STATUS_POLL_GRACE_MS);

    return () => {
      clearTimeout(graceTimeoutId);
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [pendingKey, conversationId, setMessages]);
}
