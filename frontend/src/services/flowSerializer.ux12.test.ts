import { describe, expect, it } from 'vitest';
import { deserializeFlow, serializeFlow } from './flowSerializer';

const base = (config: Record<string, unknown>, withTimeoutEdge = true) =>
  ({
    id: 'f', name: 'F', status: 'draft', version: 1, createdAt: new Date(), updatedAt: new Date(),
    nodes: [
      { id: 'start', type: 'trigger', position: { x: 0, y: 0 }, data: { label: 'T', nodeType: 'trigger', icon: 'webhook', triggerConfig: { type: 'webhook', method: 'POST', secret: 'x'.repeat(32) } } },
      { id: 'ask', type: 'action', position: { x: 0, y: 100 }, data: { label: 'Ask', nodeType: 'action', icon: 'x', actionConfig: { type: 'human.approval', message: 'ok?', approver_type: 'role', approver_role: 'System Manager', ...config } } },
      ...['yes', 'no', 'late'].map((id, i) => ({ id, type: 'end', position: { x: i * 100, y: 200 }, data: { label: id, nodeType: 'end', icon: 'flag', endConfig: {} } })),
    ],
    edges: [
      { id: 'e0', source: 'start', target: 'ask' },
      { id: 'e1', source: 'ask', target: 'yes', sourceHandle: 'approve', data: { route: 'approve' } },
      { id: 'e2', source: 'ask', target: 'no', sourceHandle: 'reject', data: { route: 'reject' } },
      ...(withTimeoutEdge ? [{ id: 'e3', source: 'ask', target: 'late', sourceHandle: 'timeout', data: { route: 'timeout' } }] : []),
    ],
  }) as never;

const ask = (flow: never) => serializeFlow(flow).nodes.find((n) => n.id === 'ask')?.config as Record<string, unknown>;

describe('Wait for approval in the saved flow', () => {
  it('a Timed out path is saved only while there is a time limit', () => {
    expect(ask(base({ timeout_ms: 1800000 })).timeout_next).toBe('late');
    const cleared = ask(base({}));
    expect(cleared).not.toHaveProperty('timeout_next');
    expect(cleared).not.toHaveProperty('timeout_ms');
  });

  it('the card title and the details go to the saved step and come back', () => {
    const details = [{ label: 'Amount', value: { $from: 'input.total' } }, { value: { $from: 'input.customer.name' } }];
    const config = ask(base({ title: 'Refund for {input.customer.name}', details }, false));
    expect(config.title).toBe('Refund for {input.customer.name}');
    expect(config.details).toEqual(details);
    const back = deserializeFlow('f', 'F', 'Draft', serializeFlow(base({ title: 'T', details }, false)));
    const cfg = back.nodes.find((n) => n.id === 'ask')?.data.actionConfig as Record<string, unknown>;
    expect(cfg.details).toEqual(details);
    expect(cfg.title).toBe('T');
  });
});
