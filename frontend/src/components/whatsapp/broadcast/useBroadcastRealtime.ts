import { useEffect, useState } from 'react';
import { useSocket } from '@/contexts/SocketContext';

export const BROADCAST_EVENT = 'wa_broadcast_progress';
const DOCTYPE = 'WhatsApp Broadcast';

export interface BroadcastProgress {
  broadcast: string;
  status: string;
  total: number;
  queued: number;
  sending: number;
  sent: number;
  delivered: number;
  read: number;
  failed: number;
  deferred: number;
  unknown: number;
  skipped: number;
  pause_reason?: string | null;
}

/**
 * Live progress for one broadcast over the shared socket. `live` is true while the socket is connected and
 * subscribed to the broadcast's document room; callers keep polling as the fallback (slowly while live).
 */
export function useBroadcastRealtime(name: string, onProgress: (p: BroadcastProgress) => void): { live: boolean } {
  const socket = useSocket();
  const [live, setLive] = useState(false);

  useEffect(() => {
    if (!socket) { setLive(false); return; }
    const subscribe = () => { socket.emit('doc_subscribe', DOCTYPE, name); setLive(true); };
    const down = () => setLive(false);
    const handler = (data: BroadcastProgress) => { if (data?.broadcast === name) onProgress(data); };
    if (socket.connected) subscribe();
    socket.on('connect', subscribe);
    socket.on('disconnect', down);
    socket.on('connect_error', down);
    socket.on(BROADCAST_EVENT, handler);
    return () => {
      socket.emit('doc_unsubscribe', DOCTYPE, name);
      socket.off('connect', subscribe);
      socket.off('disconnect', down);
      socket.off('connect_error', down);
      socket.off(BROADCAST_EVENT, handler);
    };
  }, [socket, name, onProgress]);

  return { live };
}
