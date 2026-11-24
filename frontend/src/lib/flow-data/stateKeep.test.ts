import { describe, expect, it } from 'vitest';
import { keepAllowed, keepLimitReason, keepValueOf } from './stateKeep';

describe('stateKeep', () => {
  it('maps stored seconds to an option, default one day', () => {
    expect(keepValueOf(undefined)).toBe('day');
    expect(keepValueOf(2592000)).toBe('month');
    expect(keepValueOf(0)).toBe('forever');
    expect(keepValueOf(7200)).toBeNull();
  });
  it('applies the site ceiling', () => {
    expect(keepAllowed(0, 31536000)).toBe(false);
    expect(keepAllowed(31536000, 31536000)).toBe(true);
    expect(keepAllowed(31536000, 2592000)).toBe(false);
    expect(keepAllowed(0, 0)).toBe(true);
    expect(keepAllowed(0, null)).toBe(true);
  });
  it('words the limit in days', () => {
    expect(keepLimitReason(2592000)).toBe('Your site keeps saved data for at most 30 days.');
  });
});
