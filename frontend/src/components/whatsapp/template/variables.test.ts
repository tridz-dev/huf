import { describe, expect, it } from 'vitest';
import {
  convertVariableType,
  extractVariables,
  fillDraftVariables,
  findVariableTokens,
  hasStrayBraces,
  insertVariable,
  remapSamples,
  renumberVariables,
} from './variables';

describe('variables', () => {
  it('finds numbered, named and invalid tokens', () => {
    const tokens = findVariableTokens('a {{1}} b {{ first_name }} c {{Bad Name}} {{0}}');
    expect(tokens.map((t) => [t.token, t.kind])).toEqual([
      ['1', 'number'],
      ['first_name', 'name'],
      ['Bad Name', 'invalid'],
      ['0', 'invalid'],
    ]);
  });

  it('extracts unique tokens by first appearance, optionally by type', () => {
    expect(extractVariables('{{2}} {{1}} {{2}}')).toEqual(['2', '1']);
    expect(extractVariables('{{a}} {{1}}', 'name')).toEqual(['a']);
    expect(extractVariables('plain')).toEqual([]);
  });

  it('detects stray braces', () => {
    expect(hasStrayBraces('ok {{1}}')).toBe(false);
    expect(hasStrayBraces('oops {{1}')).toBe(true);
    expect(hasStrayBraces('oops }} here')).toBe(true);
  });

  it('inserts the next number at the caret', () => {
    expect(insertVariable('Hi , bye', 3, 'number')).toEqual({ text: 'Hi {{1}}, bye', caret: 8, token: '1' });
    expect(insertVariable('Hi {{1}} {{3}}', null, 'number').token).toBe('4');
  });

  it('inserts a named placeholder that does not clash', () => {
    expect(insertVariable('Hi ', 3, 'name').token).toBe('variable_1');
    expect(insertVariable('Hi {{variable_1}} ', 100, 'name').text).toBe('Hi {{variable_1}} {{variable_2}}');
  });

  it('renumbers by first appearance and remaps samples', () => {
    const r = renumberVariables('{{3}} and {{ 1 }} and {{3}} {{x}}');
    expect(r.text).toBe('{{1}} and {{2}} and {{1}} {{x}}');
    expect(r.map).toEqual({ '3': '1', '1': '2' });
    expect(remapSamples({ '3': 'c', '1': 'a', 'header.1': 'h' }, r.map)).toEqual({ '1': 'c', '2': 'a', 'header.1': 'h' });
    expect(remapSamples({ 'header.2': 'h', '2': 'x' }, { '2': '1' }, 'header.')).toEqual({ 'header.1': 'h', '2': 'x' });
  });

  it('converts between numbered and named', () => {
    expect(convertVariableType('Hi {{1}} {{2}}', 'name').text).toBe('Hi {{variable_1}} {{variable_2}}');
    const back = convertVariableType('{{b}} {{a}}', 'number');
    expect(back.text).toBe('{{1}} {{2}}');
    expect(back.map).toEqual({ b: '1', a: '2' });
  });

  it('fills samples and leaves blanks visible', () => {
    expect(fillDraftVariables('Hi {{1}} {{2}}', { '1': 'Ann', '2': ' ' })).toBe('Hi Ann {{2}}');
    expect(fillDraftVariables('{{n}}', { 'header.n': 'X' }, 'header.')).toBe('X');
  });
});
