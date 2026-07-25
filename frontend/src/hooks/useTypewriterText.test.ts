import { describe, it, expect } from 'vitest';
import { getTypewriterSlice } from './useTypewriterText';

describe('getTypewriterSlice', () => {
  it('returns progressively longer prefixes', () => {
    expect(getTypewriterSlice('Hello', 0)).toBe('');
    expect(getTypewriterSlice('Hello', 1)).toBe('H');
    expect(getTypewriterSlice('Hello', 3)).toBe('Hel');
    expect(getTypewriterSlice('Hello', 5)).toBe('Hello');
  });

  it('never exceeds the target text length', () => {
    expect(getTypewriterSlice('Hi', 10)).toBe('Hi');
  });

  it('handles negative indices safely', () => {
    expect(getTypewriterSlice('Hi', -1)).toBe('');
  });
});
