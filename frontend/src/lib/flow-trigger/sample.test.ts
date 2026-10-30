import { describe, expect, it } from 'vitest';
import { MASK, MAX_SAMPLE_BYTES, inferFields, parseSampleText, redactSample } from './sample';

describe('redactSample', () => {
  it('hides secrets at any depth and keeps the rest', () => {
    const out = redactSample({ name: 'Ada', password: 'x', auth: { api_key: 'k', ok: 1 }, Authorization: 'Bearer y' }) as Record<string, unknown>;
    expect(out).toEqual({ name: 'Ada', password: MASK, auth: { api_key: MASK, ok: 1 }, Authorization: MASK });
  });
  it('shortens text, keeps up to 20 list items, and stays under 8 KB', () => {
    const out = redactSample({ note: 'x'.repeat(500), items: [1, 2, 3, 4, 5, 6, 7] }) as { note: string; items: number[] };
    expect(out.note).toHaveLength(200);
    expect(out.items).toHaveLength(7);
    const huge = Object.fromEntries(Array.from({ length: 300 }, (_, i) => [`field_${i}`, 'y'.repeat(190)]));
    expect(new TextEncoder().encode(JSON.stringify(redactSample(huge))).length).toBeLessThanOrEqual(MAX_SAMPLE_BYTES);
  });
});

describe('parseSampleText', () => {
  it('accepts an object, wraps other JSON, rejects text', () => {
    expect(parseSampleText('{"a":1}')).toEqual({ a: 1 });
    expect(parseSampleText('[1,2]')).toEqual({ value: [1, 2] });
    expect(parseSampleText('not json')).toBeNull();
  });
});

describe('inferFields', () => {
  it('lists fields with friendly names and plain example values', () => {
    const fields = inferFields({ customer_name: 'Ada', orderTotal: 120, address: { city: 'London' }, items: [1, 2, 3], note: null });
    expect(fields).toEqual([
      { label: 'Customer name', example: 'Ada' },
      { label: 'Order total', example: '120' },
      { label: 'Address > City', example: 'London' },
      { label: 'Items', example: '3 items' },
      { label: 'Note', example: 'empty' },
    ]);
  });
  it('never shows code paths', () => {
    expect(JSON.stringify(inferFields({ a: { b: { c: { d: 1 } } } }))).not.toMatch(/input\[|\$from|\./);
  });
});

describe('lists in a pinned sample', () => {
  it('keeps all 20 items when they fit, so a picker can say "Agents (20)"', () => {
    const agents = Array.from({ length: 20 }, (_, i) => ({ name: `Agent ${i}`, role: `Helps with task number ${i}` }));
    const safe = redactSample({ agents, total: 20 }) as { agents: unknown[]; total: number };
    expect(safe.agents).toHaveLength(20);
    expect(new TextEncoder().encode(JSON.stringify(safe)).length).toBeLessThanOrEqual(MAX_SAMPLE_BYTES);
  });

  it('keeps fewer items, not fewer fields, when 20 big ones would not fit', () => {
    const rows = Array.from({ length: 20 }, () => Object.fromEntries(Array.from({ length: 10 }, (_, k) => [`field_${k}`, 'x'.repeat(190)])));
    const safe = redactSample({ rows }) as { rows?: unknown[] };
    expect(new TextEncoder().encode(JSON.stringify(safe)).length).toBeLessThanOrEqual(MAX_SAMPLE_BYTES);
    expect(Array.isArray(safe.rows)).toBe(true);
  });
});
