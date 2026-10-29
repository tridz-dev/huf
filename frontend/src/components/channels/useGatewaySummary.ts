import { useEffect, useState } from 'react';
import { getSetupStatus } from '@/services/whatsappHealthApi';

export interface ChannelGateway {
  name: string;
  enabled: boolean;
  health?: string;
  /** Present once the backend reports it; absent gateways simply show no banner. */
  setup_stage?: string | null;
}

export interface GatewaySummary {
  gateways: ChannelGateway[];
  loading: boolean;
  error: string | null;
}

/** WhatsApp gateways from the existing get_setup_status() site summary. */
export function useGatewaySummary(): GatewaySummary {
  const [state, setState] = useState<GatewaySummary>({ gateways: [], loading: true, error: null });
  useEffect(() => {
    let cancelled = false;
    getSetupStatus().then((res) => {
      if (cancelled) return;
      if (res.ok) {
        setState({ gateways: (res.data.gateways ?? []) as ChannelGateway[], loading: false, error: null });
      } else {
        setState({ gateways: [], loading: false, error: res.error });
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return state;
}
