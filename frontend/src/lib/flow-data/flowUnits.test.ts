import { describe, expect, it } from 'vitest';
import { durationWords, splitDuration, toSeconds } from './flowUnits';

const U = ['minutes', 'hours', 'days'] as const;

describe('waiting times', () => {
  it('picks the largest whole unit', () => {
    expect(splitDuration(1800, [...U])).toEqual({ amount: 30, unit: 'minutes' });
    expect(splitDuration(7200, [...U])).toEqual({ amount: 2, unit: 'hours' });
    expect(splitDuration(86400 * 3, [...U])).toEqual({ amount: 3, unit: 'days' });
    expect(splitDuration(5400, [...U])).toEqual({ amount: 90, unit: 'minutes' });
  });

  it('never goes below the smallest unit', () => {
    expect(splitDuration(30, [...U])).toEqual({ amount: 1, unit: 'minutes' });
  });

  it('converts back', () => {
    expect(toSeconds(2, 'hours')).toBe(7200);
    expect(toSeconds(1.5, 'hours')).toBe(5400);
  });

  it('says it in words', () => {
    expect(durationWords(3600, [...U])).toBe('1 hour');
    expect(durationWords(1800, [...U])).toBe('30 minutes');
  });
});
