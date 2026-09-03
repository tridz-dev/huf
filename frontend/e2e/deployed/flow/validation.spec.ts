import { test, expect } from '@playwright/test';
import { newApiContext, uniqueFlowName } from './flowApi';

/**
 * Point 9 — "does anything stop a user building a broken flow?"
 *
 * Asserted at the API layer on purpose. Save-time validation is a property of
 * the Flow Definition doctype, not of the builder UI, so testing it through a
 * browser is slower, flakier, and proves less: a green browser test could
 * simply mean the UI never sent the bad payload. These assertions pin what the
 * BACKEND accepts, which is what any client (UI, API, importer) can do.
 *
 * Every case below currently SAVES AND ACTIVATES. They are written as
 * assertions of today's behaviour so that adding validation makes them fail
 * loudly and deliberately.
 */

type Node = { id: string; type: string; config?: Record<string, unknown> };

function definition(id: string, nodes: Node[], entry: string) {
  return {
    schema_version: 1, id, version: 1, entry, nodes, edges: [],
    settings: { mode: 'normal', max_hops: 10 }, metadata: { name: id },
  };
}

const CASES: Array<{ name: string; nodes: Node[]; entry: string }> = [
  { name: 'no trigger node at all', nodes: [{ id: 'a', type: 'agent.run', config: {} }], entry: 'a' },
  { name: 'agent node with no agent selected', nodes: [{ id: 'a', type: 'agent.run', config: {} }], entry: 'a' },
  { name: 'tool node with no tool_name', nodes: [{ id: 'a', type: 'tool.call', config: {} }], entry: 'a' },
  { name: 'http node with no url', nodes: [{ id: 'a', type: 'http_request', config: {} }], entry: 'a' },
  {
    name: 'condition branching to a node that does not exist',
    nodes: [{ id: 'a', type: 'condition', config: { expression: 'True', true_node: 'ghost', false_node: 'ghost' } }],
    entry: 'a',
  },
  {
    name: 'orphaned, unreachable node',
    nodes: [{ id: 'a', type: 'trigger.webhook', config: {} }, { id: 'z', type: 'agent.run', config: {} }],
    entry: 'a',
  },
];

test.describe('save-time validation (point 9)', () => {
  for (const c of CASES) {
    test(`KNOWN GAP: a flow with ${c.name} saves AND activates`, async ({ baseURL }) => {
      const api = await newApiContext(new URL(baseURL!).origin);
      const flowId = uniqueFlowName('val').replace(/[^a-zA-Z0-9-]/g, '-');
      try {
        const res = await api.post('/api/resource/Flow Definition', {
          data: {
            flow_id: flowId, flow_name: flowId, status: 'Active',
            definition_json: JSON.stringify(definition(flowId, c.nodes, c.entry)),
          },
        });
        expect(res.ok(), `expected the backend to accept this today; got ${res.status()}`).toBeTruthy();
        const doc = (await api.get(`/api/resource/Flow Definition/${flowId}`)).json();
        expect((await doc).data.status).toBe('Active');
      } finally {
        await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
        await api.dispose();
      }
    });
  }

  // The single rule that IS enforced - proof the doctype validates *something*,
  // so the cases above are a deliberate gap rather than validation being absent.
  test('entry pointing at a missing node IS rejected', async ({ baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    const flowId = uniqueFlowName('val').replace(/[^a-zA-Z0-9-]/g, '-');
    try {
      const res = await api.post('/api/resource/Flow Definition', {
        data: {
          flow_id: flowId, flow_name: flowId, status: 'Active',
          definition_json: JSON.stringify(
            definition(flowId, [{ id: 'a', type: 'trigger.webhook', config: {} }], 'does-not-exist'),
          ),
        },
      });
      expect(res.ok()).toBeFalsy();
      expect(await res.text()).toContain('Entry node');
    } finally {
      await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });
});
