import { useEffect, useState } from 'react';
import { listChannelGateways } from '@/services/channelGatewaysApi';
import { getSetupStatus } from '@/services/whatsappHealthApi';
import type { ChannelKey } from './channelsMeta';
import { useChannel } from './useChannelGateway';

export interface ChannelGateway {
  name: string;
  enabled: boolean;
  health?: string;
  /** Present once the backend reports it; absent gateways simply show no banner. */
  setup_stage?: string | null;
  provider?: string;
  channel?: string;
}

export interface GatewaySummary {
  gateways: ChannelGateway[];
  loading: boolean;
  error: string | null;
}

export interface AllGateways {
  byChannel: Record<ChannelKey, ChannelGateway[]>;
  loading: boolean;
  error: string | null;
}

const EMPTY: Record<ChannelKey, ChannelGateway[]> = { whatsapp: [], telegram: [], slack: [], teams: [] };

/**
 * Gateways grouped by channel. WhatsApp always comes from get_setup_status() (richer rows); the
 * other channels come from list_channel_gateways(). If that call is missing or fails, only
 * WhatsApp is populated.
 */
export function useAllGateways(): AllGateways {
  const [state, setState] = useState<AllGateways>({ byChannel: EMPTY, loading: true, error: null });
  useEffect(() => {
    let cancelled = false;
    void Promise.all([getSetupStatus(), listChannelGateways()]).then(([wa, all]) => {
      if (cancelled) return;
      const byChannel: Record<ChannelKey, ChannelGateway[]> = { whatsapp: [], telegram: [], slack: [], teams: [] };
      if (wa.ok) byChannel.whatsapp = (wa.data.gateways ?? []) as ChannelGateway[];
      else if (all.ok) byChannel.whatsapp = all.data.filter((g) => g.channel === 'whatsapp') as ChannelGateway[];
      if (all.ok) {
        for (const g of all.data) {
          if (g.channel !== 'whatsapp' && g.channel in byChannel) {
            byChannel[g.channel as ChannelKey].push(g as ChannelGateway);
          }
        }
      }
      setState({ byChannel, loading: false, error: wa.ok || all.ok ? null : wa.error });
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return state;
}

/** Gateways of the channel in the current path (or the given one). */
export function useGatewaySummary(channel?: ChannelKey): GatewaySummary {
  const current = useChannel();
  const { byChannel, loading, error } = useAllGateways();
  const ch = channel ?? current;
  return { gateways: byChannel[ch], loading, error: byChannel[ch].length ? null : error };
}
