import { parseServerTime, timeAgo } from './templateModel';

/** Full local date and time, for hover text. */
export function fullTime(value?: string | null): string {
  const date = parseServerTime(value);
  return date ? date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '';
}

/** Relative text ("3 min ago"); older than a week reads as a date. */
export function relativeTime(value?: string | null, now: Date = new Date()): string {
  const date = parseServerTime(value);
  if (!date) return '';
  if (now.getTime() - date.getTime() > 7 * 24 * 3600 * 1000) return date.toLocaleDateString(undefined, { dateStyle: 'medium' });
  return timeAgo(value, now);
}

/** The one way the WhatsApp console shows a point in time: relative text, full local time on hover. */
export function TimeStamp({ value, className }: { value?: string | null; className?: string }) {
  const date = parseServerTime(value);
  if (!date) return <span className={className}>&mdash;</span>;
  return (
    <time dateTime={date.toISOString()} title={fullTime(value)} className={className}>
      {relativeTime(value)}
    </time>
  );
}

/** Like TimeStamp, but reads naturally after a verb: "3 min ago" or "on 12 Oct 2026". */
export function TimeWhen({ value, className }: { value?: string | null; className?: string }) {
  const date = parseServerTime(value);
  if (!date) return null;
  const text = relativeTime(value);
  const relative = /ago$|^just now$/.test(text);
  return (
    <time dateTime={date.toISOString()} title={fullTime(value)} className={className}>
      {relative ? text : `on ${text}`}
    </time>
  );
}
