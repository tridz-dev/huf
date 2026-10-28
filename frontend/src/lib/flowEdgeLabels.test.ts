import { describe, expect, it } from 'vitest';
import { followRenamedTarget } from './flowEdgeLabels';
import type { FlowEdge } from '../types/flow.types';

const opt = (id: string, target: string, label: string): FlowEdge =>
  ({ id, source: 'r', target, label, sourceHandle: 'option', data: { route: 'option' } }) as FlowEdge;

describe('followRenamedTarget', () => {
  it('renames labels that still equal the old title', () => {
    const edges = [opt('a', 't1', 'Urgent'), opt('b', 't2', 'Routine')];
    const out = followRenamedTarget(edges, 't1', 'Urgent', 'Escalate');
    expect(out[0].label).toBe('Escalate');
    expect(out[1].label).toBe('Routine');
  });
  it('leaves a label the user edited', () => {
    const edges = [opt('a', 't1', 'is it urgent')];
    expect(followRenamedTarget(edges, 't1', 'Urgent', 'Escalate')).toBe(edges);
  });
  it('ignores non-option edges', () => {
    const e = { id: 'x', source: 'c', target: 't1', label: 'Urgent', data: { route: 'true' } } as FlowEdge;
    expect(followRenamedTarget([e], 't1', 'Urgent', 'Escalate')[0].label).toBe('Urgent');
  });
});
