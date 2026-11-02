import { useCallback, useEffect, useRef, useState } from 'react';
import { getSetupStatus, type GatewayHealthStatus } from '@/services/whatsappHealthApi';

export const SETUP_POLL_MS = 3000;

export interface SetupStatus {
  loaded: boolean;
  error: string | null;
  stage: string | null;
  gateway: GatewayHealthStatus | null;
  refresh: () => Promise<void>;
}

/** Loads get_setup_status(gateway) once, then every 3s while `poll` is true. */
export function useSetupStatus(gateway: string | undefined, poll: boolean): SetupStatus {
  const [state, setState] = useState<{ loaded: boolean; error: string | null; gateway: GatewayHealthStatus | null }>({
    loaded: !gateway,
    error: null,
    gateway: null,
  });
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    if (!gateway) return;
    const res = await getSetupStatus(gateway);
    if (!alive.current) return;
    if (res.ok) setState({ loaded: true, error: null, gateway: res.data.gateway ?? null });
    else setState((s) => ({ ...s, loaded: true, error: res.error }));
  }, [gateway]);

  useEffect(() => {
    alive.current = true;
    if (!gateway) {
      setState({ loaded: true, error: null, gateway: null });
      return () => {
        alive.current = false;
      };
    }
    setState({ loaded: false, error: null, gateway: null });
    void refresh();
    return () => {
      alive.current = false;
    };
  }, [gateway, refresh]);

  useEffect(() => {
    if (!gateway || !poll) return;
    const id = setInterval(() => void refresh(), SETUP_POLL_MS);
    return () => clearInterval(id);
  }, [gateway, poll, refresh]);

  return { ...state, stage: state.gateway?.setup_stage ?? null, refresh };
}
