import { parseServerDate } from '@/lib/serverTime';

/** "Under 1 s", "12 s", "3 min 5 s", "2 h 1 min", "1 d 4 h": how long something took, never "0s" or "121m 4s". */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms) || ms < 0) return '';
  const s = Math.floor(ms / 1000);
  if (s < 1) return 'Under 1 s';
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return s % 60 ? `${m} min ${s % 60} s` : `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return m % 60 ? `${h} h ${m % 60} min` : `${h} h`;
  const d = Math.floor(h / 24);
  return h % 24 ? `${d} d ${h % 24} h` : `${d} d`;
}

/** How long a run took, from its start and finish; empty when either is missing. */
export function runDuration(start: string | null | undefined, end: string | null | undefined): string {
  const a = parseServerDate(start);
  const b = parseServerDate(end);
  return a && b ? formatDuration(b.getTime() - a.getTime()) : '';
}

/** "20 minutes", "2 hours", "3 days": how long a run has been stuck, for a sentence ("stuck for 2 hours"). */
export function spokenDuration(ms: number): string {
  const m = Math.max(0, Math.floor(ms / 60000));
  const unit = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`;
  if (m < 1) return 'a moment';
  if (m < 60) return unit(m, 'minute');
  const h = Math.floor(m / 60);
  if (h < 24) return unit(h, 'hour');
  return unit(Math.floor(h / 24), 'day');
}

/** Milliseconds since a server time; 0 when unknown. */
export function sinceMs(value: string | null | undefined, now: number = Date.now()): number {
  const d = parseServerDate(value);
  return d ? Math.max(0, now - d.getTime()) : 0;
}

/** "5:15 PM" for today, "Oct 29, 5:15 PM" for this year, with the year otherwise: the person's own clock. */
export function friendlyClock(value: string | Date | null | undefined, now: Date = new Date()): string {
  const d = parseServerDate(value);
  if (!d) return '';
  const time = d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  if (d.toDateString() === now.toDateString()) return time;
  const date = d.toLocaleDateString(undefined, d.getFullYear() === now.getFullYear() ? { month: 'short', day: 'numeric' } : { month: 'short', day: 'numeric', year: 'numeric' });
  return `${date}, ${time}`;
}
