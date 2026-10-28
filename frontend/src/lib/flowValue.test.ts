import { describe, expect, it } from 'vitest';
import { insertReferenceIntoValue } from './flowValue';

describe('insertReferenceIntoValue', () => {
  it('an empty literal becomes the reference', () => {
    expect(insertReferenceIntoValue('', 'literal', 'input.url', 'input')).toEqual({ value: { $from: 'input.url' }, mode: 'reference' });
  });
  it('literal text becomes a template with the variable', () => {
    expect(insertReferenceIntoValue('Hi ', 'literal', 'n1', 'fetch')).toEqual({
      value: { $template: 'Hi {fetch}', vars: { fetch: { $from: 'n1' } } },
      mode: 'template',
    });
  });
  it('a reference is replaced', () => {
    expect(insertReferenceIntoValue({ $from: 'input' }, 'reference', 'n1', 'x').value).toEqual({ $from: 'n1' });
  });
  it('template appends and keeps names unique', () => {
    const t = { $template: '{a}', vars: { a: { $from: 'x' } } };
    const out = insertReferenceIntoValue(t, 'template', 'y', 'a').value as { $template: string; vars: Record<string, unknown> };
    expect(out.$template).toBe('{a}{a_2}');
    expect(out.vars).toEqual({ a: { $from: 'x' }, a_2: { $from: 'y' } });
  });
  it('json inserts at the caret', () => {
    expect(insertReferenceIntoValue({ k: '' }, 'json', 'n1', 'x', 0).value).toBeDefined();
  });
});
