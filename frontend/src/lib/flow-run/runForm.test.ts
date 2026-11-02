import { describe, expect, it } from 'vitest';
import { fieldsFromSample, fieldsFromSchema, payloadFromForm, runFormFields, valuesFromPayload } from './runForm';

const SAMPLE = { name: 'Ada Lovelace', email: 'ada@example.com', amount: 120, paid: true, address: { city: 'London' }, items: [1, 2] };

describe('fieldsFromSample', () => {
  it('labels each field in words, flattens small objects and leaves lists out of the form', () => {
    const fields = fieldsFromSample(SAMPLE);
    expect(fields.map((f) => f.label)).toEqual(['Name', 'Email', 'Amount', 'Paid', 'Address > City']);
    expect(fields.map((f) => f.kind)).toEqual(['text', 'text', 'number', 'yesno', 'text']);
    expect(fields.find((f) => f.id === 'address.city')?.example).toBe('London');
  });
  it('skips internal keys and ignores non-objects', () => {
    expect(fieldsFromSample({ _trigger: 'x', a: 'b' }).map((f) => f.id)).toEqual(['a']);
    expect(fieldsFromSample(null)).toEqual([]);
    expect(fieldsFromSample([1])).toEqual([]);
  });
});

describe('fieldsFromSchema', () => {
  it('uses titles, types and examples from the declared input', () => {
    const fields = fieldsFromSchema({
      type: 'object',
      properties: { amount: { type: 'number', title: 'Order amount', example: 42 }, note: { type: 'string' }, ok: { type: 'boolean' }, tags: { type: 'array' } },
    });
    expect(fields.map((f) => [f.label, f.kind, f.example])).toEqual([
      ['Order amount', 'number', '42'],
      ['Note', 'text', ''],
      ['Ok', 'yesno', false],
    ]);
  });
  it('prefers the declared fields over the sample', () => {
    expect(runFormFields({ properties: { x: { type: 'string' } } }, SAMPLE).map((f) => f.id)).toEqual(['x']);
    expect(runFormFields({ type: 'object' }, SAMPLE).length).toBe(5);
  });
});

describe('payload round trip', () => {
  const fields = fieldsFromSample(SAMPLE);
  it('prefills from a payload and writes it back unchanged', () => {
    const values = valuesFromPayload(fields, SAMPLE);
    expect(values.name).toBe('Ada Lovelace');
    expect(values.paid).toBe(true);
    expect(payloadFromForm(SAMPLE, fields, values)).toEqual(SAMPLE);
  });
  it('turns number boxes back into numbers, keeps lists, and drops emptied boxes', () => {
    const values = { ...valuesFromPayload(fields, SAMPLE), amount: '250', email: '', paid: false, 'address.city': 'Paris' };
    expect(payloadFromForm(SAMPLE, fields, values)).toEqual({ name: 'Ada Lovelace', amount: 250, paid: false, address: { city: 'Paris' }, items: [1, 2] });
  });
  it('keeps text in a number box as text instead of losing it', () => {
    const values = { ...valuesFromPayload(fields, SAMPLE), amount: 'about 5' };
    expect(payloadFromForm(SAMPLE, fields, values).amount).toBe('about 5');
  });
});
