import { useEffect } from 'react';
import type { Socket } from 'socket.io-client';
import { useSocket } from '@/contexts/SocketContext';

const DOCTYPE = 'Agent Flow Run';

/** Open views per run on each socket: the room is left only when the last one closes. */
const viewers = new WeakMap<Socket, Map<string, number>>();

/**
 * Joins the document room of an open Flow Run, so its live events reach everyone who may read the run, not
 * only the person who started it. The server checks read permission; without it nothing is delivered.
 */
export function useFlowRunRoom(runId: string | null): void {
  const socket = useSocket();

  useEffect(() => {
    if (!socket || !runId) return;
    const counts = viewers.get(socket) ?? new Map<string, number>();
    viewers.set(socket, counts);
    counts.set(runId, (counts.get(runId) ?? 0) + 1);

    // A reconnected socket has left every room, so join again on each connect.
    const subscribe = () => socket.emit('doc_subscribe', DOCTYPE, runId);
    if (socket.connected) subscribe();
    socket.on('connect', subscribe);

    return () => {
      socket.off('connect', subscribe);
      const left = (counts.get(runId) ?? 1) - 1;
      if (left > 0) {
        counts.set(runId, left);
        return;
      }
      counts.delete(runId);
      socket.emit('doc_unsubscribe', DOCTYPE, runId);
    };
  }, [socket, runId]);
}
