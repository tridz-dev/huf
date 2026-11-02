// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { validateNode } from './flowValidation';

const approval = (cfg: Record<string, unknown>) => ({
  id: 'ask',
  data: { label: 'Wait for approval', nodeType: 'action', actionConfig: { type: 'human.approval', message: 'ok?', approver_type: 'role', approver_role: 'System Manager', ...cfg } },
});
const end = (endConfig: unknown) => ({ id: 'end', data: { label: 'End', nodeType: 'end', endConfig } });
const fields = (node: Parameters<typeof validateNode>[0]) => validateNode(node, [{ source: 'ask', target: 'x', sourceHandle: 'approve', data: { route: 'approve' } }, { source: 'ask', target: 'y', sourceHandle: 'reject', data: { route: 'reject' } }]).map((i) => i.field);

describe('card and outcome limits', () => {
  it('a title over 120 characters and a label over 60 are named in words', () => {
    expect(fields(approval({ title: 'x'.repeat(121) }))).toContain('title');
    expect(fields(approval({ details: [{ label: 'y'.repeat(61), value: 'a' }] }))).toContain('details');
    expect(fields(approval({ title: 'Fine', details: [{ label: 'Total', value: 'a' }] }))).not.toContain('title');
  });

  it('an outcome label over 60 characters is named', () => {
    expect(validateNode(end({ outcome: { label: 'z'.repeat(61) } }), []).map((i) => i.field)).toEqual(['outcome']);
    expect(validateNode(end({ outcome: { label: 'Approved', tone: 'good' } }), [])).toEqual([]);
  });

  it('"Replace with" may stay empty in a replace step', () => {
    const node = { id: 't', data: { label: 'Change data', nodeType: 'action', actionConfig: { type: 'transform', op: 'replace', input: { text: 'a-b', find: '-' } } } };
    expect(validateNode(node, [])).toEqual([]);
  });
});
