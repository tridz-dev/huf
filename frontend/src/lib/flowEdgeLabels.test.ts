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

import { branchColumnShift, subtreeIds } from './flowEdgeLabels';

describe('branchColumnShift', () => {
  it('moves a target that shares a column with a sibling branch', () => {
    expect(branchColumnShift(600, [600])).toBe(280);
    expect(branchColumnShift(600, [600, 880])).toBe(560);
  });
  it('leaves a target that already has room', () => {
    expect(branchColumnShift(300, [600])).toBe(0);
  });
});

describe('subtreeIds', () => {
  it('collects the node and everything below it', () => {
    const edges = [{ source: 'a', target: 'b' }, { source: 'b', target: 'c' }, { source: 'x', target: 'y' }];
    expect(subtreeIds('b', edges)).toEqual(new Set(['b', 'c']));
  });
});
