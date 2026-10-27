import { describe, expect, it } from 'vitest';
import { expandUrlExample } from './urlExample';

describe('expandUrlExample', () => {
  const url = 'https://example.com/track/{{1}}';
  it('appends a bare value to the link prefix', () => {
    expect(expandUrlExample(url, 'abc123')).toBe('https://example.com/track/abc123');
    expect(expandUrlExample(url, '/abc')).toBe('https://example.com/track/abc');
  });
  it('leaves absolute links, empty values and static links alone', () => {
    expect(expandUrlExample(url, 'https://example.com/track/9')).toBe('https://example.com/track/9');
    expect(expandUrlExample(url, '')).toBe('');
    expect(expandUrlExample('https://example.com/x', 'abc')).toBe('abc');
  });
});
