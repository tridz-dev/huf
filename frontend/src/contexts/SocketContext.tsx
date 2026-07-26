import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import type { Socket } from 'socket.io-client';
import { toast } from 'sonner';
import { createFrappeSocket } from '../utils/socket';

type FrappeWindow = Window & {
  frappe?: { boot?: { sitename?: string; socketio_port?: string } };
};

const SocketContext = createContext<Socket | null>(null);

export function useSocket(): Socket | null {
  return useContext(SocketContext);
}

export function SocketProvider({ children }: { children: ReactNode }) {
  const [socket, setSocket] = useState<Socket | null>(null);

  useEffect(() => {
    const connectionDescription =
      'Some features may be disabled or not work as expected. Please refresh the page to retry.';

    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let cleanupConnection: (() => void) | undefined;

    const tryConnect = (attemptsLeft: number) => {
      if (cancelled) return;

      const siteName = (window as FrappeWindow).frappe?.boot?.sitename;
      const hasPort = !!window.location?.port;
      const port = (hasPort ? (window as FrappeWindow).frappe?.boot?.socketio_port : '') ?? '';

      if (!siteName) {
        if (attemptsLeft > 0) {
          // window.frappe.boot is normally inlined into the page before the
          // bundle loads, but retry briefly in case it lands a beat late.
          retryTimer = setTimeout(() => tryConnect(attemptsLeft - 1), 250);
          return;
        }
        toast.error('Socket connection failed', {
          id: 'socket-connection-failed',
          description: connectionDescription,
          duration: 5000,
        });
        console.warn('Site name not available, socket connection will be skipped');
        return;
      }

      connect(siteName, port);
    };

    const connect = (siteName: string, port: string) => {
      console.log('Creating shared socket connection for site:', siteName);
      const connection = createFrappeSocket({ siteName, port });

      connection.on('connect', () => {
        console.log('✅ Connected to Frappe websocket!');
      });

      connection.on('connect_error', (error) => {
        console.error('❌ Socket connection error:', error);
        toast.error('Socket connection failed', {
          id: 'socket-connection-failed',
          description: connectionDescription,
          duration: 5000,
        });
      });

      connection.on('disconnect', (reason) => {
        console.warn('⚠️ Socket disconnected:', reason);
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

  return <SocketContext.Provider value={socket}>{children}</SocketContext.Provider>;
}
