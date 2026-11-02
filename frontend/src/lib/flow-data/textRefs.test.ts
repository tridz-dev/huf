import { describe, expect, it } from 'vitest';
import { serializeValue, parseValue } from './chips';
import { fromTextRefs, promptToValue, toTextRefs, valueToPrompt } from './textRefs';

describe('message placeholders', () => {
  it('plain text stays plain text', () => {
    expect(toTextRefs('Approve this refund?')).toBe('Approve this refund?');
    expect(fromTextRefs('Approve this refund?')).toBe('Approve this refund?');
  });

  it('placeholders become chips and back, unchanged', () => {
    const text = 'Refund {input.amount} for {input.customer.name}? Items: {joined:n1.items}, {count:n1.items} in all. {input.amount}';
    const value = toTextRefs(text) as { $template: string; vars: Record<string, { $from: string }> };
    expect(value.$template).toContain('{amount}');
    expect(Object.values(value.vars).map((v) => v.$from)).toEqual(['input.amount', 'input.customer.name', 'n1.items', 'n1.items']);
    expect(fromTextRefs(value)).toBe(text);
  });

  it('survives the chip input (parse then serialize)', () => {
    const text = 'Total {input.total}.';
    const through = serializeValue(parseValue(toTextRefs(text)));
    expect(fromTextRefs(through)).toBe(text);
  });

  it('a whole value that is one chip is one placeholder', () => {
    expect(fromTextRefs({ $from: 'n1.result' })).toBe('{n1.result}');
  });

  it('typed braces are kept as braces', () => {
    expect(fromTextRefs({ $template: 'Use {{code}} for {who}', vars: { who: { $from: 'input.name' } } })).toBe('Use {code} for {input.name}');
  });

  it('empty is unset', () => {
    expect(fromTextRefs('')).toBeUndefined();
    expect(fromTextRefs(undefined)).toBeUndefined();
  });

  it('a summary-table chip keeps its wording', () => {
    const v = toTextRefs('Order: {table:input.order}') as { vars: Record<string, unknown> };
    expect(Object.keys(v.vars)[0]).toMatch(/^table_/);
    expect(fromTextRefs(v)).toBe('Order: {table:input.order}');
  });
});

describe('agent prompt', () => {
  it('a prompt without data is plain text', () => {
    expect(promptToValue('Summarise this', undefined)).toBe('Summarise this');
    expect(valueToPrompt('Summarise this')).toEqual({ prompt: 'Summarise this', prompt_bindings: undefined });
  });

  it('prompt and bindings are a template', () => {
    const value = promptToValue('Summarise {ticket}', { ticket: { $from: 'input.ticket' } });
    expect(value).toEqual({ $template: 'Summarise {ticket}', vars: { ticket: { $from: 'input.ticket' } } });
    expect(valueToPrompt(value)).toEqual({ prompt: 'Summarise {ticket}', prompt_bindings: { ticket: { $from: 'input.ticket' } } });
  });

  it('typed braces stay literal', () => {
    expect(valueToPrompt('Reply as {json}')).toEqual({ prompt: 'Reply as {{json}}', prompt_bindings: undefined });
    expect(promptToValue('Reply as {{json}}', undefined)).toEqual({ $template: 'Reply as {{json}}', vars: {} });
  });

  it('round-trips through the chip input', () => {
    const stored = { prompt: 'Hi {name}, total {total}', prompt_bindings: { name: { $from: 'input.n' }, total: { $from: 'input.t' } } };
    const shown = serializeValue(parseValue(promptToValue(stored.prompt, stored.prompt_bindings)));
    expect(valueToPrompt(shown)).toEqual(stored);
  });

  it('one chip alone becomes a placeholder with a binding', () => {
    expect(valueToPrompt({ $from: 'input.ticket.text' })).toEqual({ prompt: '{text}', prompt_bindings: { text: { $from: 'input.ticket.text' } } });
  });
});
