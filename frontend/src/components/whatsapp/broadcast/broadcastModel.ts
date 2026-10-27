import type { Broadcast, BroadcastPreview, BroadcastStatus } from '@/services/whatsappApi';

export const ACTIVE_STATUSES: BroadcastStatus[] = ['Running', 'Queued'];
export const POLL_MS = 5000;

export const unwrapBroadcast = (r: { broadcast?: unknown } & Record<string, unknown>): Broadcast =>
  ((r.broadcast && typeof r.broadcast === 'object' ? r.broadcast : r) as unknown) as Broadcast;

export const unwrapPreview = (r: { preview?: BroadcastPreview } & Partial<BroadcastPreview>): BroadcastPreview =>
  (r.preview ?? r) as BroadcastPreview;

export function progressPercent(b: Broadcast): number {
  if (!b.total) return 0;
  const done = b.total - b.queued - b.sending - b.deferred;
  return Math.max(0, Math.min(100, Math.round((done / b.total) * 100)));
}

export const COUNT_KEYS = ['queued', 'sending', 'sent', 'delivered', 'read', 'failed', 'deferred', 'unknown', 'skipped'] as const;

export const isActive = (s: BroadcastStatus) => ACTIVE_STATUSES.includes(s);
