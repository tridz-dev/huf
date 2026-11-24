import { describe, expect, it } from 'vitest';
import type { Flow, FlowEdge, FlowNode } from '@/types/flow.types';
import { deserializeFlow, makeFlowEdge, serializeFlow } from './flowSerializer';

const node = (id: string, extra: Partial<FlowNode> = {}): FlowNode =>
  ({ id, type: 'action', position: { x: 0, y: 0 }, data: { label: id, nodeType: 'action' }, ...extra } as FlowNode);

function switchFlow(edges: FlowEdge[]): Flow {
  const nodes = [
    node('start', { data: { label: 'Start', nodeType: 'trigger' } as FlowNode['data'] }),
    node('step', { data: { label: 'Choose', nodeType: 'action', actionConfig: { type: 'router-decision' } } as unknown as FlowNode['data'] }),
    node('urgent'),
    node('routine'),
    node('fallback'),
  ];
  return { id: 'f1', name: 'F', status: 'draft', nodes, edges, createdAt: new Date(0), updatedAt: new Date(0), version: 1 } as unknown as Flow;
}

describe('router.decision rules round-trip', () => {
  it('keeps each rule check and the otherwise path through serialize and deserialize', () => {
    const edges: FlowEdge[] = [
      { ...makeFlowEdge('start', 'step', 'next') },
      makeFlowEdge('step', 'urgent', 'option', { label: 'Urgent', index: 0, expression: "input['vip'] == True" }),
      makeFlowEdge('step', 'routine', 'option', { label: 'Routine', index: 1, expression: '' }),
      makeFlowEdge('step', 'fallback', 'default'),
    ];
    const flow = switchFlow(edges);
    const graph = serializeFlow(flow);
    const step = (graph as unknown as { nodes: Array<{ id: string; config: Record<string, unknown> }> }).nodes.find((n) => n.id === 'step');
    expect(step?.config.options).toEqual([
      { label: 'Urgent', node_id: 'urgent', expression: "input['vip'] == True" },
      { label: 'Routine', node_id: 'routine', expression: '' },
    ]);
    expect(step?.config.default).toBe('fallback');

    const back = deserializeFlow(flow.id, flow.name, 'Draft', graph);
    const rules = back.edges.filter((e) => e.source === 'step' && e.data?.route === 'option');
    expect(rules.map((e) => [e.label, e.target, e.data?.expression])).toEqual([
      ['Urgent', 'urgent', "input['vip'] == True"],
      ['Routine', 'routine', ''],
    ]);
    expect(back.edges.some((e) => e.source === 'step' && e.target === 'fallback' && e.data?.route === 'default')).toBe(true);
  });
});
