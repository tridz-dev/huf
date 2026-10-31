// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Edge, Node } from 'reactflow';
import type { FlowNodeData } from '@/types/flow.types';
import { setGatewayRegistry } from '@/lib/flow-gateway/registryStore';
import { FIXTURE_REGISTRY } from '@/lib/flow-gateway/registryFixture';
import { cardTitle, stepAriaLabel, stepOrder, useNodeFacts } from './nodeFacts';

vi.mock('@/lib/flow/flowIntegrations', async (orig) => ({ ...(await orig<typeof import('@/lib/flow/flowIntegrations')>()), useIntegrationStatus: () => null }));

describe('stepAriaLabel', () => {
  it('says where the step is, what it is and how it stands', () => {
    expect(stepAriaLabel(3, 7, 'Send email', 'Needs setup')).toBe('Step 3 of 7: Send email, needs setup');
    expect(stepAriaLabel(1, 1, 'Webhook', 'Done')).toBe('Step 1 of 1: Webhook, done');
  });
});

describe('stepOrder', () => {
  it('numbers steps top to bottom, then left to right', () => {
    const order = stepOrder([
      { id: 'c', position: { x: 400, y: 410 } },
      { id: 'a', position: { x: 250, y: 100 } },
      { id: 'b2', position: { x: 395, y: 250 } },
      { id: 'b1', position: { x: 105, y: 250 } },
    ]);
    expect([...order.entries()].sort((x, y) => x[1] - y[1]).map(([id]) => id)).toEqual(['a', 'b1', 'b2', 'c']);
  });
  it('treats steps a few pixels apart in height as one row', () => {
    const order = stepOrder([{ id: 'r', position: { x: 300, y: 252 } }, { id: 'l', position: { x: 100, y: 258 } }]);
    expect(order.get('l')).toBe(1);
  });
});

describe('cardTitle', () => {
  it('shows "Start here" for the trigger nobody chose yet and the label otherwise', () => {
    expect(cardTitle({ label: 'Select trigger', nodeType: 'trigger', configured: false })).toBe('Start here');
    expect(cardTitle({ label: 'Webhook', nodeType: 'trigger', configured: true, triggerConfig: { type: 'webhook' } as never })).toBe('Webhook');
    expect(cardTitle({ label: 'Send', nodeType: 'action', configured: true })).toBe('Send');
  });
});

describe('useNodeFacts: a chat trigger on a switched-off number', () => {
  it('says Needs setup once the channel list arrives, not Ready, so the card agrees with the header', () => {
    setGatewayRegistry(null);
    const trigger = { id: 't', type: 'trigger', position: { x: 0, y: 0 }, data: { label: 'WhatsApp', nodeType: 'trigger', configured: true, triggerConfig: { type: 'whatsapp', gateway: 'Support WhatsApp' } } } as unknown as Node<FlowNodeData>;
    const nodes = [trigger];
    const edges: Edge[] = [];
    const { result } = renderHook(() => useNodeFacts(nodes, edges, null, () => undefined));
    expect(result.current.get('t')?.status.kind).toBe('ready');
    const off = { ...FIXTURE_REGISTRY, gateways: FIXTURE_REGISTRY.gateways.map((g) => (g.name === 'Support WhatsApp' ? { ...g, enabled: false } : g)) };
    act(() => setGatewayRegistry(off));
    expect(result.current.get('t')?.status.kind).toBe('needs-setup');
    expect(result.current.get('t')?.firstIssue).toContain('switched off');
    act(() => setGatewayRegistry(null));
  });
});
