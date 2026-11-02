import { apiCall, isApiError } from '@/lib/api';
import type { WhatsAppResult } from '@/services/whatsappApi';

/** Frozen contract (PLAN v2 section 3). Module is owned by the limits backend (api_limits.py). */
const MOD = 'huf.ai.whatsapp.broadcast.api_limits';

export type LimitKind = 'meta' | 'setting' | 'safety' | 'internal';
export type LimitGroup = 'meta' | 'recipients' | 'speed' | 'safety' | 'quality' | 'confirmation' | 'api';
export type LimitValue = number | boolean | string | null;

export interface BroadcastLimit {
  key: string;
  label: string;
  group: LimitGroup;
  kind: LimitKind;
  value: LimitValue;
  default: LimitValue;
  effective: LimitValue;
  source: 'default' | 'settings' | 'broadcast';
  unit?: string | null;
  min?: number | null;
  max?: number | null;
  note?: string | null;
  editable: boolean;
  as_of?: string | null;
}

async function limitsCall(method: 'get_broadcast_limits' | 'update_broadcast_limits', args: Record<string, unknown>, verb: 'GET' | 'POST'): Promise<WhatsAppResult<{ limits: BroadcastLimit[] }>> {
  try {
    const out = await apiCall<{ limits?: BroadcastLimit[] } | null>(`${MOD}.${method}`, args, { verb });
    return { limits: Array.isArray(out?.limits) ? out!.limits : [], success: true } as WhatsAppResult<{ limits: BroadcastLimit[] }>;
  } catch (e) {
    return { success: false, error: isApiError(e) ? e.code : 'request_failed', message: e instanceof Error ? e.message : 'Request failed.' };
  }
}

export const getBroadcastLimits = (broadcast?: string) =>
  limitsCall('get_broadcast_limits', broadcast ? { broadcast } : {}, 'GET');

/** `values[key] = null` resets that limit to its default. */
export const updateBroadcastLimits = (values: Record<string, LimitValue>) =>
  limitsCall('update_broadcast_limits', { values: JSON.stringify(values) }, 'POST');

/** Effective numeric limit or a fallback when the list is missing/unreadable. */
export function limitNumber(limits: BroadcastLimit[] | null, key: string, fallback: number): number {
  const v = limits?.find((l) => l.key === key)?.effective;
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
}

export function limitFlag(limits: BroadcastLimit[] | null, key: string, fallback: boolean): boolean {
  const v = limits?.find((l) => l.key === key)?.effective;
  return typeof v === 'boolean' ? v : typeof v === 'number' ? v !== 0 : fallback;
}
