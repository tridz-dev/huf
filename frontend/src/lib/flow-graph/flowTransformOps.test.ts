import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { TRANSFORM_OPS, TRANSFORM_OP_NAMES } from './flowTransformOps';
import { valueMode, textToValue, valueToText, templateVarsToText } from './flowValue';

const graphDir = resolve(__dirname, '../../../../huf/ai/graph');

describe('transform op parity with backend', () => {
  it('matches the REGISTRY keys in transforms.py', () => {
    const src = readFileSync(resolve(graphDir, 'transforms.py'), 'utf8');
    const block = src.slice(src.indexOf('REGISTRY:'));
    const body = block.slice(block.indexOf('{'), block.indexOf('\n}\n'));
    const names = [...body.matchAll(/^\s*"([a-z_]+)":/gm)].map((m) => m[1]);
    expect(names.length).toBeGreaterThan(15);
    expect([...TRANSFORM_OP_NAMES].sort()).toEqual([...names].sort());
  });

  it('matches $defs/TransformOp in graph_ir.schema.json', () => {
    const schema = JSON.parse(readFileSync(resolve(graphDir, 'graph_ir.schema.json'), 'utf8'));
    expect([...TRANSFORM_OP_NAMES].sort()).toEqual([...schema.$defs.TransformOp.enum].sort());
  });

  it('has unique names and optional params that exist', () => {
    expect(new Set(TRANSFORM_OP_NAMES).size).toBe(TRANSFORM_OPS.length);
    for (const o of TRANSFORM_OPS) for (const p of o.optional ?? []) expect(o.params).toContain(p);
  });
});

describe('flowValue', () => {
  it('detects modes', () => {
    expect(valueMode('x')).toBe('literal');
    expect(valueMode({ $from: 'input.a' })).toBe('reference');
    expect(valueMode({ $template: 'hi {n}', vars: {} })).toBe('template');
    expect(valueMode([1])).toBe('json');
  });

  it('round-trips a template with vars', () => {
    const v = { $template: 'Refund #{order}', vars: { order: { $from: 'input.order' } } };
    const rebuilt = textToValue('template', valueToText(v), templateVarsToText(v));
    expect(rebuilt).toEqual(v);
  });

  it('keeps invalid JSON as the raw string', () => {
    expect(textToValue('json', '[1,')).toBe('[1,');
    expect(textToValue('reference', 'a.b')).toEqual({ $from: 'a.b' });
  });
});
