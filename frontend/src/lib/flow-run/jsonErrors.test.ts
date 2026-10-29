import { describe, it, expect } from 'vitest';
import { describeJsonProblem, formatJsonText } from './jsonErrors';

describe('describeJsonProblem', () => {
  it('is null for valid JSON', () => {
    expect(describeJsonProblem('{"a": [1, 2]}')).toBeNull();
    expect(describeJsonProblem('42')).toBeNull();
  });
  it('points at a missing comma by line', () => {
    expect(describeJsonProblem('{\n  "a": 1\n  "b": 2\n}')).toEqual({ line: 2, message: 'Missing comma after line 2.' });
  });
  it('points at an extra trailing comma', () => {
    expect(describeJsonProblem('{\n  "a": 1,\n}')).toEqual({ line: 2, message: 'Remove the extra comma at the end of line 2.' });
  });
  it('explains single quotes', () => {
    const p = describeJsonProblem("{'a': 1}");
    expect(p?.message).toContain('double quotes');
  });
  it('explains a missing closing bracket', () => {
    expect(describeJsonProblem('{"a": 1')?.message).toContain('closing } or ]');
  });
  it('never shows the parser wording', () => {
    for (const bad of ['{"a" 1}', '{a: 1}', '[1,,2]', 'nope']) {
      const m = describeJsonProblem(bad)?.message ?? '';
      expect(m).not.toMatch(/Unexpected|position|token|JSON\.parse/i);
      expect(m.length).toBeGreaterThan(10);
    }
  });
});

describe('formatJsonText', () => {
  it('pretty prints valid text and refuses invalid', () => {
    expect(formatJsonText('{"a":[1,2]}')).toBe('{\n  "a": [\n    1,\n    2\n  ]\n}');
    expect(formatJsonText('{"a":')).toBeNull();
  });
});
