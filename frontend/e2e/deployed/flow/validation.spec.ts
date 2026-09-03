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
 * Contract: validation is staged by status.
 *   - Draft is permissive: every broken flow below still saves as Draft, so
 *     half-built work in progress is never blocked.
 *   - Active is strict: activating (or saving an already-Active flow) with any
 *     of these problems is rejected with a specific, actionable message naming
 *     the offending node.
 */

type Node = { id: string; type: string; config?: Record<string, unknown> };
type Edge = { from: string; to: string };

function definition(id: string, nodes: Node[], entry: string, edges: Edge[] = []) {
  return {
    schema_version: 1, id, version: 1, entry, nodes, edges,
    settings: { mode: 'normal', max_hops: 10 }, metadata: { name: id },
  };
}

const CASES: Array<{ name: string; nodes: Node[]; entry: string; edges?: Edge[]; expect: string }> = [
  {
    name: 'no trigger node at all',
    nodes: [{ id: 'a', type: 'agent.run', config: { agent_name: 'some-agent' } }],
    entry: 'a',
    expect: "at least one node with a type starting with 'trigger.' is required",
  },
  {
    name: 'agent node with no agent selected',
    nodes: [{ id: 'a', type: 'trigger.webhook', config: {} }, { id: 'b', type: 'agent.run', config: {} }],
    entry: 'a',
    edges: [{ from: 'a', to: 'b' }],
    expect: "Node 'b' (agent.run) is missing required 'agent_name'",
  },
  {
    name: 'tool node with no tool_name',
    nodes: [{ id: 'a', type: 'trigger.webhook', config: {} }, { id: 'b', type: 'tool.call', config: {} }],
    entry: 'a',
    edges: [{ from: 'a', to: 'b' }],
    expect: "Node 'b' (tool.call) is missing required 'tool_name'",
  },
  {
    name: 'http node with no url',
    nodes: [{ id: 'a', type: 'trigger.webhook', config: {} }, { id: 'b', type: 'http_request', config: {} }],
    entry: 'a',
    edges: [{ from: 'a', to: 'b' }],
    expect: "Node 'b' (http_request) is missing required 'url'",
  },
  {
    name: 'condition branching to a node that does not exist',
    nodes: [
      { id: 'a', type: 'trigger.webhook', config: {} },
      { id: 'b', type: 'condition', config: { expression: 'True', true_node: 'ghost', false_node: 'ghost' } },
    ],
    entry: 'a',
    edges: [{ from: 'a', to: 'b' }],
    expect: "'true_node' pointing to 'ghost', which does not exist",
  },
  {
    name: 'orphaned, unreachable node',
    nodes: [
      { id: 'a', type: 'trigger.webhook', config: {} },
      { id: 'z', type: 'agent.run', config: { agent_name: 'some-agent' } },
    ],
    entry: 'a',
    expect: "unreachable from entry 'a': z",
  },
];

test.describe('save-time validation (point 9)', () => {
  for (const c of CASES) {
    test(`a flow with ${c.name} saves as Draft but is rejected on activation`, async ({ baseURL }) => {
      const api = await newApiContext(new URL(baseURL!).origin);
      const flowId = uniqueFlowName('val').replace(/[^a-zA-Z0-9-]/g, '-');
      try {
        const defn = definition(flowId, c.nodes, c.entry, c.edges ?? []);

        // Draft: permissive, must save despite the problem.
        const draftRes = await api.post('/api/resource/Flow Definition', {
          data: {
            flow_id: flowId, flow_name: flowId, status: 'Draft',
            definition_json: JSON.stringify(defn),
          },
        });
        expect(draftRes.ok(), `Draft save should succeed; got ${draftRes.status()}`).toBeTruthy();
        const draftDoc = await (await api.get(`/api/resource/Flow Definition/${flowId}`)).json();
        expect(draftDoc.data.status).toBe('Draft');

        // Active: strict, must be rejected with a specific, actionable message.
        const activateRes = await api.put(`/api/resource/Flow Definition/${flowId}`, {
          data: { status: 'Active' },
        });
        expect(activateRes.ok(), 'activation should be rejected').toBeFalsy();
        expect(await activateRes.text()).toContain(c.expect);

        // Confirm it did not silently activate.
        const afterDoc = await (await api.get(`/api/resource/Flow Definition/${flowId}`)).json();
        expect(afterDoc.data.status).toBe('Draft');
      } finally {
        await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
        await api.dispose();
      }
    });
  }

  // A flow with none of the above problems must still save and activate -
  // validation that blocks legitimate flows is worse than the gap it closes.
  test('a valid flow saves as Draft and activates cleanly', async ({ baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    const flowId = uniqueFlowName('val').replace(/[^a-zA-Z0-9-]/g, '-');
    try {
      const defn = definition(
        flowId,
        [
          { id: 'a', type: 'trigger.webhook', config: {} },
          { id: 'b', type: 'agent.run', config: { agent_name: 'some-agent' } },
          { id: 'c', type: 'end', config: {} },
        ],
        'a',
        [{ from: 'a', to: 'b' }, { from: 'b', to: 'c' }],
      );

      const draftRes = await api.post('/api/resource/Flow Definition', {
        data: { flow_id: flowId, flow_name: flowId, status: 'Draft', definition_json: JSON.stringify(defn) },
      });
      expect(draftRes.ok()).toBeTruthy();

      const activateRes = await api.put(`/api/resource/Flow Definition/${flowId}`, {
        data: { status: 'Active' },
      });
      expect(activateRes.ok(), `expected activation to succeed; got ${activateRes.status()}`).toBeTruthy();
      const doc = await (await api.get(`/api/resource/Flow Definition/${flowId}`)).json();
      expect(doc.data.status).toBe('Active');
    } finally {
      await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });

  // The pre-existing rule - proof the doctype validates *something* regardless
  // of status, so the cases above are additional gaps rather than the whole story.
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
