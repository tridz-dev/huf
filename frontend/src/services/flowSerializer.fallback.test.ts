import { describe, it, expect } from 'vitest';
import { serializeFlow, deserializeFlow } from '@/services/flowSerializer';
import type { BackendFlowGraph, BackendNode } from '@/services/flowApi';

function graph(nodes: BackendNode[]): BackendFlowGraph {
  return {
    schema_version: '1.0.0', profile: 'flow', fingerprint: 'f', entry: nodes[0].id, nodes,
    contract: {
      input_schema: {}, output_schema: {}, applies_when: [],
      permission_envelope: { read: [], write: [], http: 'none', code: 'none' },
      limits: {
        max_nodes: 100, max_rows: 1000, max_output_bytes: 1_000_000, max_parallel_calls: 10,
        max_foreach_iterations: 100, max_external_calls: 10, max_writes: 100, max_wall_time_ms: 60_000,
        fail_closed: true,
      },
    },
  };
}

const COND: BackendNode = {
  id: 'c', type: 'condition',
  config: { expression: { op: 'eq', left: { $from: 'input.x' }, right: 1 }, on_true: 't', on_false: 'f', fallback_next: 'fb' },
};
const outs = ['t', 'f', 'fb'].map((id) => ({ id, type: 'output', config: {} }) as BackendNode);

describe('condition fallback_next round trip', () => {
  it('survives deserialize -> serialize unchanged', () => {
    const flow = deserializeFlow('f1', 'F', 'Draft', graph([COND, ...outs]));
    const got = serializeFlow(flow).nodes.find((n) => n.id === 'c')!;
    expect(got.config).toEqual(COND.config);
  });

  it('is shown as a Fallback edge and dropped when that edge is removed', () => {
    const flow = deserializeFlow('f1', 'F', 'Draft', graph([COND, ...outs]));
    const fb = flow.edges.filter((e) => e.source === 'c' && e.target === 'fb');
    expect(fb).toHaveLength(1);
    flow.edges = flow.edges.filter((e) => e !== fb[0]);
    const got = serializeFlow(flow).nodes.find((n) => n.id === 'c')!;
    expect(got.config.fallback_next).toBeUndefined();
  });
});
