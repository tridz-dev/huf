/** Default time window of the Executions tabs. */
export const DEFAULT_RANGE = '24h';

export const TIME_RANGE_OPTIONS = [
  { label: 'Last 24h', value: '24h' },
  { label: 'Last 7d', value: '7d' },
  { label: 'Last 30d', value: '30d' },
  { label: 'All time', value: 'all' },
];

/** Window length in ms for each range option; `null` means unbounded ("All time"). */
export const TIME_RANGE_MS: Record<string, number | null> = {
  '24h': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
  '30d': 30 * 24 * 60 * 60 * 1000,
  all: null,
};
