import { describe, it, expect } from 'vitest';
import { serializeFlow, deserializeFlow } from '@/services/flowSerializer';
import type { BackendFlowGraph, BackendNode } from '@/services/flowApi';

function graph(nodes: BackendNode[]): BackendFlowGraph {
  return {
    schema_version: '1.0.0',
    profile: 'flow',
    fingerprint: 'f',
    entry: nodes[0].id,
    nodes,
    contract: {
      input_schema: {},
      output_schema: {},
      applies_when: [],
      permission_envelope: { read: [], write: [], http: 'none', code: 'none' },
      limits: {
        max_nodes: 100, max_rows: 1000, max_output_bytes: 1_000_000, max_parallel_calls: 10,
        max_foreach_iterations: 100, max_external_calls: 10, max_writes: 100, max_wall_time_ms: 60_000,
        fail_closed: true,
      },
    },
  };
}

const TEMPLATE = { $template: 'cart:{sender}', vars: { sender: { $from: 'input.sender_id' } } };

const CASES: Array<[string, BackendNode]> = [
  ['state.get', { id: 'n', type: 'state.get', config: { key: TEMPLATE, default: 'none' }, next: 'o' }],
  ['state.set', { id: 'n', type: 'state.set', config: { key: TEMPLATE, value: { $from: 'a.b' }, ttl_seconds: 3600 }, next: 'o' }],
  ['state.delete', { id: 'n', type: 'state.delete', config: { key: 'k' }, next: 'o' }],
  ['doc.create', { id: 'n', type: 'doc.create', config: { doctype: 'ToDo', fields: { description: TEMPLATE, status: 'Open' } }, next: 'o' }],
  ['transform lower', { id: 'n', type: 'transform', config: { op: 'lower', input: { text: { $from: 'input.text' } } }, next: 'o' }],
  ['transform replace', { id: 'n', type: 'transform', config: { op: 'replace', input: { text: 'a', find: 'a', with: 'b', count: 1 } }, next: 'o' }],
  ['transform concat', { id: 'n', type: 'transform', config: { op: 'concat', input: { parts: ['a', { $from: 'x.y' }], separator: '-' } }, next: 'o' }],
  ['unknown type', { id: 'n', type: 'future.node' as never, config: { a: 1 }, next: 'o' }],
];

describe('new node round trip', () => {
  it.each(CASES)('%s survives deserialize -> serialize unchanged', (_name, node) => {
    const input = graph([node, { id: 'o', type: 'output', config: {} }]);
    const flow = deserializeFlow('f1', 'F', 'Draft', input);
    const out = serializeFlow(flow);
    const got = out.nodes.find((n) => n.id === 'n')!;
    expect(got.type).toBe(node.type);
    expect(got.config).toEqual(node.config);
    expect(got.next).toBe('o');
  });

  it('never rewrites an unknown backend type as tool.call', () => {
    const flow = deserializeFlow('f1', 'F', 'Draft', graph([{ id: 'n', type: 'future.node' as never, config: {} }]));
    expect(flow.nodes[0].data.actionConfig).toMatchObject({ type: 'unknown', backend_type: 'future.node' });
    expect(serializeFlow(flow).nodes[0].type).toBe('future.node');
  });

  it('flags new nodes unconfigured until required fields are set', () => {
    const flow = deserializeFlow('f1', 'F', 'Draft', graph([
      { id: 'a', type: 'state.get', config: {} },
      { id: 'b', type: 'doc.create', config: { doctype: 'ToDo', fields: {} } },
    ]));
    expect(flow.nodes[0].data.configured).toBe(false);
    expect(flow.nodes[1].data.configured).toBe(true);
  });
});
