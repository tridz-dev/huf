import { call } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

export interface ChannelGatewayRow {
  name: string;
  provider: string;
  channel: string;
  enabled: boolean;
  health?: string | null;
  setup_stage?: string | null;
}

export type ChannelGatewaysResult = { ok: true; data: ChannelGatewayRow[] } | { ok: false; error: string };

/** All gateways across channels (huf.ai.channels.status_api.list_channel_gateways). */
export async function listChannelGateways(): Promise<ChannelGatewaysResult> {
  try {
    const res = await call.get('huf.ai.channels.status_api.list_channel_gateways', {});
    const body = res && typeof res === 'object' && 'message' in res ? (res as { message: unknown }).message : res;
    const rows = Array.isArray(body) ? body : (body as { gateways?: unknown } | null)?.gateways;
    return { ok: true, data: Array.isArray(rows) ? (rows as ChannelGatewayRow[]) : [] };
  } catch (e) {
    return { ok: false, error: getFrappeErrorMessage(e) };
  }
}
