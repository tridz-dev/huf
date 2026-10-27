import { describe, it, expect } from 'vitest';
import { isInvalidJsonString } from './flowHttpJson';

describe('isInvalidJsonString', () => {
  it('flags a non-empty string that fails to parse', () => {
    expect(isInvalidJsonString('{"a": 1,}')).toBe(true);
    expect(isInvalidJsonString('{"a": 1')).toBe(true);
    expect(isInvalidJsonString('plain text body')).toBe(true);
  });

  it('accepts valid JSON strings', () => {
    expect(isInvalidJsonString('{"a": 1}')).toBe(false);
    expect(isInvalidJsonString('[1, 2]')).toBe(false);
    expect(isInvalidJsonString('"quoted"')).toBe(false);
  });

  it('does not flag empty or whitespace-only strings', () => {
    expect(isInvalidJsonString('')).toBe(false);
    expect(isInvalidJsonString('   ')).toBe(false);
  });

  it('does not flag non-string values (already-parsed objects, undefined)', () => {
    expect(isInvalidJsonString({ a: 1 })).toBe(false);
    expect(isInvalidJsonString(undefined)).toBe(false);
    expect(isInvalidJsonString(null)).toBe(false);
  });
});
