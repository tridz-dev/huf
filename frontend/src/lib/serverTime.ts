import { useSyncExternalStore } from 'react';

/**
 * Frappe returns datetimes as naive strings ("2026-10-28 12:00:00") in the *site* time zone, which a
 * browser cannot know. Flow APIs send time-zone-aware UTC ISO strings ("...Z"); Frappe documents read
 * through the SDK are naive. `parseServerDate` handles both: strings that carry an offset are parsed
 * as is, naive ones are read in the site time zone (System Settings), which the server exposes via
 * `get_site_timezone`. Until that zone is known, naive strings fall back to the browser's zone.
 */

let siteTimeZone: string | null = null;
let loading: Promise<void> | null = null;
const listeners = new Set<() => void>();

export function loadSiteTimezone(): Promise<void> {
  if (siteTimeZone) return Promise.resolve();
  if (!loading) {
    // Imported lazily so the pure parsing helpers can be used (and tested) without a browser.
    loading = import('@/lib/frappe-sdk')
      .then(({ call }) => call.get('huf.ai.flow.api.get_site_timezone'))
      .then((res) => {
        const tz = res?.message;
        if (typeof tz === 'string' && isValidZone(tz)) {
          siteTimeZone = tz;
          listeners.forEach((fn) => fn());
        }
      })
      .catch(() => undefined)
      .finally(() => {
        loading = null;
      });
  }
  return loading;
}

/** Re-renders the caller once the site time zone is known, so naive times are shown correctly. */
export function useSiteTimezone(): string | null {
  void loadSiteTimezone();
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    () => siteTimeZone,
  );
}

/** Test hook. */
export function setSiteTimezoneForTests(tz: string | null) {
  siteTimeZone = tz;
  listeners.forEach((fn) => fn());
}

function isValidZone(tz: string): boolean {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

const HAS_OFFSET = /(Z|[+-]\d{2}:?\d{2})$/i;
const NAIVE = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.(\d+))?$/;

function zoneOffsetMs(utcMs: number, tz: string): number {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: tz,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(new Date(utcMs));
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value);
  const asUtc = Date.UTC(get('year'), get('month') - 1, get('day'), get('hour'), get('minute'), get('second'));
  return asUtc - Math.floor(utcMs / 1000) * 1000;
}

/** Parse a server datetime (naive site time or offset-carrying ISO) into a Date, or null. */
export function parseServerDate(value: string | Date | null | undefined): Date | null {
  if (!value) return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  const text = value.trim();
  if (HAS_OFFSET.test(text)) {
    const d = new Date(text.replace(' ', 'T'));
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const m = NAIVE.exec(text);
  if (!m) {
    const d = new Date(text);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const [, y, mo, d, h, mi, s, frac] = m;
  const ms = frac ? Number(`0.${frac}`) * 1000 : 0;
  if (!siteTimeZone) {
    const local = new Date(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s ?? 0), ms);
    return Number.isNaN(local.getTime()) ? null : local;
  }
  const wall = Date.UTC(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s ?? 0), Math.floor(ms));
  let utc = wall - zoneOffsetMs(wall, siteTimeZone);
  utc = wall - zoneOffsetMs(utc, siteTimeZone); // re-check across a DST edge
  return new Date(utc);
}

/** A Date as the naive site-time string Frappe filters compare against ("YYYY-MM-DD HH:mm:ss"). */
export function toServerDatetime(date: Date): string {
  const tz = siteTimeZone;
  if (!tz) {
    const p = (n: number) => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())} ${p(date.getHours())}:${p(date.getMinutes())}:${p(date.getSeconds())}`;
  }
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: tz,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(date);
  const g = (t: string) => parts.find((p) => p.type === t)?.value;
  return `${g('year')}-${g('month')}-${g('day')} ${g('hour')}:${g('minute')}:${g('second')}`;
}

/** Absolute time in the browser's zone, e.g. "Oct 28, 2026, 7:15 AM"; no seconds fractions. */
export function formatAbsoluteTime(value: string | Date | null | undefined): string {
  const d = parseServerDate(value);
  if (!d) return '';
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}
