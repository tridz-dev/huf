// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { deserializeFlow, edgeRoute, serializeFlow } from '@/services/flowSerializer';
import { branchHandlesFor } from '@/lib/flow/flowBranches';
import { validateNode } from '@/lib/flow-graph/flowValidation';
import type { BackendFlowGraph } from '@/services/flowApi';

const graph = {
  start: 't',
  nodes: [
    { id: 't', type: 'trigger.app', config: { app: 'x' }, next: 'h', _position: { x: 0, y: 0 } },
    { id: 'h', type: 'handoff', config: { target: 'support', timeout_ms: 60000, timeout_next: 'late' }, next: 'done', _position: { x: 0, y: 150 } },
    { id: 'late', type: 'output', config: { value: 'late' }, _position: { x: 200, y: 300 } },
    { id: 'done', type: 'output', config: { value: 'ok' }, _position: { x: 0, y: 300 } },
  ],
} as unknown as BackendFlowGraph;

describe('handoff Timed out path', () => {
  it('draws timeout_next as a Timed out edge and saves it back from that edge', () => {
    const flow = deserializeFlow('f', 'F', 'Draft', graph);
    const timeout = flow.edges.filter((e) => e.source === 'h' && edgeRoute(e) === 'timeout');
    expect(timeout.map((e) => e.target)).toEqual(['late']);
    const h = flow.nodes.find((n) => n.id === 'h')!;
    expect(h.data.actionConfig).not.toHaveProperty('timeout_next');
    expect(branchHandlesFor('unknown', h.data.actionConfig as Record<string, unknown>).map((b) => b.route)).toEqual(['next', 'timeout']);
    const saved = serializeFlow(flow).nodes.find((n) => n.id === 'h')!;
    expect(saved.config).toMatchObject({ timeout_next: 'late' });
    expect(saved.next).toBe('done');
  });

  it('has no Timed out path without a time limit', () => {
    expect(branchHandlesFor('unknown', { type: 'unknown', backend_type: 'handoff' })).toEqual([]);
  });
});

describe('trigger.app validation', () => {
  const trig = (cfg: Record<string, unknown>) => ({ id: 't', data: { label: 'App trigger', nodeType: 'trigger', triggerConfig: { type: 'app', ...cfg } } });
  it('asks for the app when it is blank', () => {
    expect(validateNode(trig({ app: '' }), []).map((i) => i.field)).toEqual(['app']);
    expect(validateNode(trig({ app: 'happiol' }), [])).toEqual([]);
  });
});
