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
  ['code.run', { id: 'n', type: 'code.run', config: { code: "print('hi')\nresult = inputs['n'] * 2", profile: 'Flow Scratch', inputs: { n: { $from: 'input.n' }, label: 'x' }, timeout_s: 20 }, next: 'o' }],
  ['code.run without timeout', { id: 'n', type: 'code.run', config: { code: 'result = 1', profile: 'Flow Scratch', inputs: {} }, next: 'o' }],
  ['wait for a while', { id: 'n', type: 'wait', config: { mode: 'duration', duration: { value: 2, unit: 'days' } }, next: 'o' }],
  ['wait until a time', { id: 'n', type: 'wait', config: { mode: 'until', until: { $from: 'input.when' }, time_zone: 'Asia/Kolkata' }, next: 'o' }],
  ['wait until continued, no limit', { id: 'n', type: 'wait', config: { mode: 'resume' }, next: 'o' }],
  ['wait until continued, with a Timed out path', { id: 'n', type: 'wait', config: { mode: 'resume', resume: { timeout_ms: 3600000, timeout_next: 'o' } }, next: 'o' }],
  ['doc.get by name', { id: 'n', type: 'doc.get', config: { doctype: 'ToDo', name: 'T-1', fields: ['status'], on_missing: 'empty' }, next: 'o' }],
  ['doc.get by filters', { id: 'n', type: 'doc.get', config: { doctype: 'ToDo', filters: { status: 'Open' } }, next: 'o' }],
  ['doc.update', { id: 'n', type: 'doc.update', config: { doctype: 'ToDo', name: 'T-1', values: { status: 'Closed' } }, next: 'o' }],
  ['flow.call waiting', { id: 'n', type: 'flow.call', config: { flow_id: 'onboarding', input: { who: { $from: 'input.who' } }, mode: 'wait' }, next: 'o' }],
  ['tool.call with retry', { id: 'n', type: 'tool.call', config: { tool_id: 'http_request', input: { url: 'https://x.test' }, retry: { attempts: 3, backoff: 'exponential', delay_seconds: 120, max_delay_seconds: 3600 } }, next: 'o' }],
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

  it('code.run always serialises inputs as an object and drops an unset time limit', () => {
    const flow = deserializeFlow('f1', 'F', 'Draft', graph([{ id: 'n', type: 'code.run', config: { code: 'result = 1', profile: 'Flow Scratch' }, next: 'o' }, { id: 'o', type: 'output', config: {} }]));
    const cfg = flow.nodes[0].data.actionConfig as { type: string; timeout_s?: number };
    expect(cfg.type).toBe('code-run');
    const got = serializeFlow(flow).nodes[0];
    expect(got.config).toEqual({ code: 'result = 1', profile: 'Flow Scratch', inputs: {} });
  });

  it('flags new nodes unconfigured until required fields are set', () => {
    const flow = deserializeFlow('f1', 'F', 'Draft', graph([
      { id: 'a', type: 'state.get', config: {} },
      { id: 'b', type: 'doc.create', config: { doctype: 'ToDo', fields: {} } },
      { id: 'c', type: 'code.run', config: { code: '', profile: 'Flow Scratch', inputs: {} } },
      { id: 'd', type: 'code.run', config: { code: 'result = 1', profile: 'Flow Scratch', inputs: {} } },
    ]));
    expect(flow.nodes[0].data.configured).toBe(false);
    expect(flow.nodes[1].data.configured).toBe(true);
    expect(flow.nodes[2].data.configured).toBe(false);
    expect(flow.nodes[3].data.configured).toBe(true);
  });

  it('stop has no next, and the flow-level error handler round-trips (and is dropped if its step is gone)', () => {
    const g = graph([{ id: 'a', type: 'doc.get', config: { doctype: 'ToDo', name: 'T-1' }, next: 's' }, { id: 's', type: 'stop', config: { message: 'x' } }, { id: 'h', type: 'code.run', config: { code: 'result = 1', profile: 'Flow Scratch', inputs: {} } }]);
    g.error_handler = { next: 'h' };
    const flow = deserializeFlow('f1', 'F', 'Draft', g);
    expect(flow.errorHandler).toBe('h');
    const out = serializeFlow(flow);
    expect(out.error_handler).toEqual({ next: 'h' });
    expect(out.nodes.find((n) => n.id === 's')).not.toHaveProperty('next');
    expect(out.contract.permission_envelope.read).toEqual([{ doctype: 'ToDo' }]);
    expect(serializeFlow({ ...flow, errorHandler: 'gone' })).not.toHaveProperty('error_handler');
    expect(serializeFlow({ ...flow, errorHandler: undefined })).not.toHaveProperty('error_handler');
  });
});
