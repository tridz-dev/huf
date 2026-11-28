/** The choices of "Keep saved data for" (state-set). `ttl_seconds` unset means the default, one day. */
export const KEEP_OPTIONS = [
  { value: 'day', label: '1 day', seconds: 86400 },
  { value: 'month', label: '30 days', seconds: 2592000 },
  { value: 'year', label: '1 year', seconds: 31536000 },
  { value: 'forever', label: 'Until removed', seconds: 0 },
] as const;

export type KeepValue = (typeof KEEP_OPTIONS)[number]['value'];

/** Which option a stored `ttl_seconds` is; a number that is none of them (an older value) is `null`. */
export function keepValueOf(ttl: unknown): KeepValue | null {
  if (ttl === undefined) return 'day';
  return KEEP_OPTIONS.find((o) => o.seconds === ttl)?.value ?? null;
}

/** Whether the site's ceiling (seconds, 0 = none) allows an option. */
export function keepAllowed(seconds: number, maxTtlSeconds: number | null): boolean {
  if (maxTtlSeconds === null) return true;
  return maxTtlSeconds === 0 ? true : seconds !== 0 && seconds <= maxTtlSeconds;
}

export function keepLimitReason(maxTtlSeconds: number): string {
  return `Your site keeps saved data for at most ${Math.floor(maxTtlSeconds / 86400)} days.`;
}
