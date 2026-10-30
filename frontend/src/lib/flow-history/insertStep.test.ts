import { describe, it, expect } from 'vitest';
import { insertSpot, insertStep } from './insertStep';
import { makeFlowEdge } from '../../services/flowSerializer';
import type { FlowNode } from '../../types/flow.types';

const n = (id: string, y: number, nodeType: 'trigger' | 'action' | 'end' = 'action', cfg?: Record<string, unknown>): FlowNode =>
  ({ id, type: nodeType, position: { x: 0, y }, data: { label: id, nodeType, configured: true, actionConfig: cfg as never } }) as FlowNode;

describe('insertStep', () => {
  const g = { nodes: [n('t', 0, 'trigger'), n('a', 150), n('b', 300)], edges: [makeFlowEdge('t', 'a', 'next'), makeFlowEdge('a', 'b', 'next')] };

  it('goes after the selected step and moves what followed down a row', () => {
    const spot = insertSpot(g, 'a')!;
    expect(spot).toEqual({ sourceId: 'a', route: 'next' });
    const out = insertStep(g, spot, 'transform', { type: 'transform', op: 'lower', input: {} }) as Exclude<ReturnType<typeof insertStep>, string | null>;
    expect(out.edges.find((e) => e.source === 'a')!.target).toBe(out.newId);
    expect(out.edges.find((e) => e.source === out.newId)!.target).toBe('b');
    expect(out.nodes.find((x) => x.id === 'b')!.position.y).toBe(450);
    expect(out.nodes.find((x) => x.id === out.newId)!.position.y).toBe(300);
  });

  it('with nothing selected goes at the end of the flow', () => {
    expect(insertSpot(g, null)).toEqual({ sourceId: 'b', route: 'next' });
    const out = insertStep(g, insertSpot(g, null)!, 'transform', { type: 'transform', op: 'lower', input: {} }) as Exclude<ReturnType<typeof insertStep>, string | null>;
    expect(out.edges).toHaveLength(3);
    expect(out.nodes.find((x) => x.id === 'b')!.position.y).toBe(300);
  });

  it('has nowhere to go without a trigger, or after an End', () => {
    expect(insertSpot({ nodes: [], edges: [] }, null)).toBeNull();
    const done = { nodes: [n('t', 0, 'trigger'), n('e', 150, 'end')], edges: [makeFlowEdge('t', 'e', 'next')] };
    expect(insertSpot(done, 'e')).toBeNull();
  });

  it('uses the first free exit of a branching step', () => {
    const c = { nodes: [n('t', 0, 'trigger'), n('c', 150, 'action', { type: 'condition' }), n('y', 300)], edges: [makeFlowEdge('t', 'c', 'next'), makeFlowEdge('c', 'y', 'true')] };
    expect(insertSpot(c, 'c')).toEqual({ sourceId: 'c', route: 'false' });
  });
});
