import { describe, expect, it } from 'vitest';
import { removeSteps } from './removeSteps';
import { makeFlowEdge } from '../../services/flowSerializer';
import type { FlowNode } from '../../types/flow.types';

const n = (id: string, nodeType: 'trigger' | 'action' | 'end' = 'action'): FlowNode =>
  ({ id, type: nodeType, position: { x: 0, y: 0 }, data: { label: id, nodeType, configured: true } }) as FlowNode;

describe('removeSteps', () => {
  const graph = { nodes: [n('t', 'trigger'), n('a'), n('b'), n('c'), n('e', 'end')], edges: [makeFlowEdge('t', 'a', 'next'), makeFlowEdge('a', 'b', 'next'), makeFlowEdge('b', 'c', 'next'), makeFlowEdge('c', 'e', 'next')] };

  it('removes every selected step, not only the first, and joins what is left', () => {
    const out = removeSteps(graph, ['a', 'b']);
    expect(out.nodes.map((x) => x.id)).toEqual(['t', 'c', 'e']);
    expect(out.edges.map((e) => `${e.source}>${e.target}`)).toEqual(['c>e', 't>c']);
  });

  it('skips a step that went with an earlier one', () => {
    const out = removeSteps(graph, ['b', 'c'], 'cascade');
    expect(out.nodes.map((x) => x.id)).toEqual(['t', 'a']);
  });

  it('removes nothing for an empty selection', () => {
    expect(removeSteps(graph, [])).toBe(graph);
  });
});
