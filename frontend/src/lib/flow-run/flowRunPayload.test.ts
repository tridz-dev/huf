import { describe, expect, it } from 'vitest';
import { parsePayload } from './flowRunPayload';

describe('parsePayload', () => {
  it('treats blank as an empty object', () => {
    expect(parsePayload('  ')).toEqual({ value: {}, error: null });
  });
  it('accepts objects', () => {
    expect(parsePayload('{"a":1}').value).toEqual({ a: 1 });
  });
  it('rejects invalid JSON and non-objects', () => {
    expect(parsePayload('{a').error).toMatch(/valid JSON/);
    expect(parsePayload('[1]').error).toMatch(/object/);
    expect(parsePayload('5').error).toMatch(/object/);
  });
});
