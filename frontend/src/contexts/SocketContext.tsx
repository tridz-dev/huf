import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import type { Socket } from 'socket.io-client';
import { createFrappeSocket } from '../utils/socket';

type FrappeWindow = Window & {
  frappe?: { boot?: { sitename?: string; socketio_port?: string } };
};

const SocketContext = createContext<Socket | null>(null);

/** Live-updates connection state, shown as one quiet indicator in the header instead of an error toast. */
export type SocketStatus = 'connecting' | 'connected' | 'offline';

const SocketStatusContext = createContext<SocketStatus>('connecting');

export function useSocket(): Socket | null {
  return useContext(SocketContext);
}

export function useSocketStatus(): SocketStatus {
  return useContext(SocketStatusContext);
}

export function SocketProvider({ children }: { children: ReactNode }) {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [status, setStatus] = useState<SocketStatus>('connecting');

  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let cleanupConnection: (() => void) | undefined;

    const tryConnect = (attemptsLeft: number) => {
      if (cancelled) return;

      const siteName = (window as FrappeWindow).frappe?.boot?.sitename;
      // Port resolution: boot (when the backend provides it) → the page's own
      // port (dev/standalone socket.io) → Frappe's default socket.io port.
      const port =
        (window as FrappeWindow).frappe?.boot?.socketio_port ||
        window.location?.port ||
        '9000';

      if (!siteName) {
        if (attemptsLeft > 0) {
          // window.frappe.boot is normally inlined into the page before the
          // bundle loads, but retry briefly in case it lands a beat late.
          retryTimer = setTimeout(() => tryConnect(attemptsLeft - 1), 250);
          return;
        }
        setStatus('offline');
        console.warn('Site name not available, socket connection will be skipped');
        return;
      }

      connect(siteName, port);
    };

    const connect = (siteName: string, port: string) => {
      console.log('Creating shared socket connection for site:', siteName);
      // Rebuilt here (createFrappeSocket keeps its own copy) so failures can
      // log the exact URL that was attempted.
      const attemptedUrl = `${window.location.protocol.replace(':', '')}://${window.location.hostname}${port ? `:${port}` : ''}/${siteName}`;
      const connection = createFrappeSocket({ siteName, port });

      connection.on('connect', () => {
        console.log('✅ Connected to Frappe websocket!');
        setStatus('connected');
      });

      connection.on('connect_error', (error) => {
        console.error('❌ Socket connection error:', error, '— attempted URL:', attemptedUrl);
        setStatus('offline');
      });

      connection.on('disconnect', (reason) => {
        console.warn('⚠️ Socket disconnected:', reason);
        setStatus('offline');
      });

      connection.on('tool_call_started', (data) => {
        console.log('📡 Realtime event - tool_call_started:', data);
      });

      // Flow real-time events forwarding
      const flowEvents = [
        'flow_node_start',
        'flow_node_end',
        'flow_paused',
        'flow_completed',
        'flow_failed',
        'flow_error',
      ];

      flowEvents.forEach((eventName) => {
        connection.on(eventName, (data) => {
          console.log(`📡 Realtime event - ${eventName}:`, data);
          window.dispatchEvent(new CustomEvent(`frappe:${eventName}`, { detail: data }));
        });
      });

      setSocket(connection);
      cleanupConnection = () => {
        console.log('Cleaning up shared socket connection');
        connection.disconnect();
      };
    };

    tryConnect(8);

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      cleanupConnection?.();
    };
  }, []);

  return (
    <SocketContext.Provider value={socket}>
      <SocketStatusContext.Provider value={status}>{children}</SocketStatusContext.Provider>
    </SocketContext.Provider>
  );
}
