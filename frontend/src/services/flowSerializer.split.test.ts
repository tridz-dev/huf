import { describe, expect, it } from 'vitest';
import type { Flow, FlowNode } from '@/types/flow.types';
import type { BackendFlowGraph } from './flowApi';
import { deserializeFlow, serializeFlow } from './flowSerializer';

const graph = {
  schema_version: '1.0.0', profile: 'flow', fingerprint: 'x', entry: ['t'], contract: {},
  nodes: [
    { id: 't', type: 'trigger.webhook', config: { method: 'POST', secret: 's' }, next: 's1' },
    { id: 's1', type: 'split', _label: 'A/B', config: { holdout: 10, salt: 'v1', options: [
      { label: 'Arm A', node_id: 'a', weight: 70 }, { label: 'Arm B', node_id: 'b', weight: 30 },
    ] } },
    { id: 'a', type: 'output', config: {} },
    { id: 'b', type: 'output', config: {} },
  ],
} as unknown as BackendFlowGraph;

describe('split node round-trip', () => {
  it('loads as a split card with weighted branch edges and saves back unchanged', () => {
    const flow = deserializeFlow('f', 'F', 'Draft', graph);
    const node = flow.nodes.find((n) => n.id === 's1') as FlowNode;
    expect(node.data.actionConfig).toEqual({ type: 'split', holdout: 10, salt: 'v1' });
    const arms = flow.edges.filter((e) => e.source === 's1');
    expect(arms.map((e) => [e.target, e.label, e.data?.weight])).toEqual([['a', 'Arm A', 70], ['b', 'Arm B', 30]]);

    const out = serializeFlow(flow as Flow).nodes.find((n) => n.id === 's1')!;
    expect(out.type).toBe('split');
    expect(out.next).toBeUndefined();
    expect(out.config).toEqual(graph.nodes[1].config);
  });
});
