/** Default time window of the Executions tabs. */
export const DEFAULT_RANGE = '24h';

/**
 * Value of the "All time" option. It cannot be `'all'`: the list hook treats
 * that as "no filter" and drops it, which would fall back to the default window.
 */
export const ALL_TIME_RANGE = 'all-time';

export const TIME_RANGE_OPTIONS = [
  { label: 'Today', value: 'today' },
  { label: 'Last 24h', value: '24h' },
  { label: 'Last 7d', value: '7d' },
  { label: 'Last 30d', value: '30d' },
  { label: 'All time', value: ALL_TIME_RANGE },
];

const DAY_MS = 24 * 60 * 60 * 1000;

/** Rolling window length in ms for the "Last N" options. */
const ROLLING_RANGE_MS: Record<string, number> = {
  '24h': DAY_MS,
  '7d': 7 * DAY_MS,
  '30d': 30 * DAY_MS,
};

/** A range value from the URL or filter state as one of the option values (`all` is the older "All time"). */
export function normalizeRange(value: string | null | undefined): string {
  if (value === 'all') return ALL_TIME_RANGE;
  return TIME_RANGE_OPTIONS.some((option) => option.value === value) ? (value as string) : DEFAULT_RANGE;
}

/** Earliest start time the range includes; `null` means unbounded ("All time"). "Today" starts at local midnight. */
export function rangeStart(value: string | null | undefined, now: Date = new Date()): Date | null {
  const range = normalizeRange(value);
  if (range === ALL_TIME_RANGE) return null;
  if (range === 'today') return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return new Date(now.getTime() - ROLLING_RANGE_MS[range]);
}
