import { describe, expect, it } from 'vitest';
import { ALL_TIME_RANGE, DEFAULT_RANGE, TIME_RANGE_OPTIONS, normalizeRange, rangeStart } from './executionsRange';

const NOW = new Date(2026, 2, 15, 14, 30, 45, 123);

describe('rangeStart', () => {
  it('starts "today" at local midnight', () => {
    expect(rangeStart('today', NOW)).toEqual(new Date(2026, 2, 15, 0, 0, 0, 0));
  });

  it('keeps the rolling windows', () => {
    expect(rangeStart('24h', NOW)?.getTime()).toBe(NOW.getTime() - 86_400_000);
    expect(rangeStart('7d', NOW)?.getTime()).toBe(NOW.getTime() - 7 * 86_400_000);
    expect(rangeStart('30d', NOW)?.getTime()).toBe(NOW.getTime() - 30 * 86_400_000);
  });

  it('is unbounded for "All time", including the older URL value', () => {
    expect(rangeStart(ALL_TIME_RANGE, NOW)).toBeNull();
    expect(rangeStart('all', NOW)).toBeNull();
  });

  it('uses the default window when no range, or an unknown one, is given', () => {
    const fallback = rangeStart(DEFAULT_RANGE, NOW);
    expect(rangeStart(undefined, NOW)).toEqual(fallback);
    expect(rangeStart('bogus', NOW)).toEqual(fallback);
  });
});

describe('Time filter options', () => {
  it('offers "Today"', () => {
    expect(TIME_RANGE_OPTIONS).toContainEqual({ label: 'Today', value: 'today' });
    expect(normalizeRange('today')).toBe('today');
  });

  it('has no option the list filter would drop as "no filter"', () => {
    expect(TIME_RANGE_OPTIONS.map((option) => option.value)).not.toContain('all');
  });
});
