import { describe, it, expect } from 'vitest';
import { TRANSFORM_OPS } from './flowTransformOps';
import { TRANSFORM_HELP, transformParamHelp, conditionHelp, DOC_EVENT_HELP, CONDITION_EXAMPLES } from './flowHelp';
import { DOC_EVENTS } from './flowTrigger';

describe('flow help copy', () => {
  it('describes every transform operation with a summary and an example', () => {
    for (const op of TRANSFORM_OPS) {
      expect(TRANSFORM_HELP[op.name], op.name).toBeTruthy();
      expect(TRANSFORM_HELP[op.name].summary.length).toBeGreaterThan(10);
      expect(TRANSFORM_HELP[op.name].example.length).toBeGreaterThan(5);
    }
  });
  it('gives every transform field a plain label and a hint', () => {
    for (const op of TRANSFORM_OPS) {
      for (const p of op.params) {
        const h = transformParamHelp(op.name, p);
        expect(h.label, `${op.name}.${p}`).not.toBe(p === h.label && p.includes('_') ? p : '');
        expect(h.hint, `${op.name}.${p}`).toBeTruthy();
      }
    }
  });
  it('explains every data event', () => {
    for (const e of DOC_EVENTS) expect(DOC_EVENT_HELP[e]).toBeTruthy();
  });
  it('mentions Insert data only for people who can edit', () => {
    expect(conditionHelp(true)).toMatch(/Insert data/);
    expect(conditionHelp(false)).not.toMatch(/Insert data/);
    expect(CONDITION_EXAMPLES.length).toBeGreaterThan(2);
  });
});
