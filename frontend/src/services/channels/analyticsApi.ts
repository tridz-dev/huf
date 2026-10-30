import { call } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

const BASE = 'huf.ai.channels.analytics';

export interface VolumeDay { date: string; conversations: number; inbound: number; outbound: number }
export interface EstimatedSpend {
  currency: string | null;
  amount: number | null;
  is_estimate: true;
  basis: string;
  missing_rates: boolean;
}
export interface Analytics {
  volume_by_day: VolumeDay[];
  ai_resolution_rate: number | null;
  handoff_rate: number | null;
  median_first_response_seconds: number | null;
  broadcast_funnel: { sent: number; delivered: number; read: number; failed: number };
  template_quality: { name: string; quality: string | null; category: string | null }[];
  estimated_spend: EstimatedSpend;
}
export interface RateRow { market: string; category: string; rate: number | null; effective_from?: string | null }
export interface RateCard { currency: string; rows: RateRow[] }

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string };

async function run<T>(verb: 'get' | 'post', method: string, args: Record<string, unknown>): Promise<ApiResult<T>> {
  try {
    const res = verb === 'post' ? await call.post(`${BASE}.${method}`, args) : await call.get(`${BASE}.${method}`, args);
    const body = (res && typeof res === 'object' && 'message' in res ? (res as { message: unknown }).message : res) as T;
    return { ok: true, data: body };
  } catch (e) {
    return { ok: false, error: getFrappeErrorMessage(e) };
  }
}

export const getAnalytics = (gateway: string, from_date: string, to_date: string) =>
  run<Analytics>('get', 'get_analytics', { gateway, from_date, to_date });
export const getRateCard = () => run<RateCard>('get', 'get_rate_card', {});
export const saveRateCard = (currency: string, rows: RateRow[]) =>
  run<RateCard>('post', 'save_rate_card', { currency, rows: JSON.stringify(rows) });
