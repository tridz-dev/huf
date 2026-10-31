// @vitest-environment jsdom
import { useState } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FIXTURE_REGISTRY } from '@/lib/flow-gateway/registryFixture';
import type { GatewayRegistry } from '@/lib/flow-gateway/gatewayTrigger.types';
import type { FlowNode, FlowNodeData } from '@/types/flow.types';

let registryState: { registry: GatewayRegistry | null; loading: boolean; failed: boolean; reload: () => void } = { registry: FIXTURE_REGISTRY, loading: false, failed: false, reload: vi.fn() };
let nodes: FlowNode[] = [];
const updateNodeData = vi.fn();
let canManage = true;

vi.mock('@/hooks/flow/useGatewayRegistry', () => ({ useGatewayRegistry: () => registryState }));
vi.mock('@/hooks/flow/useFlowPermissions', () => ({ useFlowPermissions: () => ({ canManage, canExecuteCode: false }) }));
vi.mock('@/contexts/FlowContext', () => ({
  useFlowContext: () => ({
    activeFlow: { id: 'f', name: 'F', nodes, edges: [] },
    updateNodeData,
    getNode: (id: string) => nodes.find((n) => n.id === id),
  }),
}));

import { GatewayTriggerForm } from '../GatewayTriggerForm';
import { TriggerConfigForm } from '../TriggerConfigForm';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;

let saved: Record<string, unknown> = {};

function Harness({ initial, kind }: { initial: Record<string, unknown>; kind: 'gateway' | 'whatsapp' | 'telegram' }) {
  const [node, setNode] = useState<FlowNode>({ id: 't', type: 'trigger', position: { x: 0, y: 0 }, data: { label: 'T', nodeType: 'trigger', icon: 'x', triggerConfig: { type: kind, ...initial } } as FlowNodeData });
  nodes = [node];
  updateNodeData.mockImplementation((_id: string, fn: (d: FlowNodeData) => FlowNodeData) => {
    const next = fn(node.data);
    saved = next.triggerConfig as Record<string, unknown>;
    setNode({ ...node, data: next });
  });
  return <MemoryRouter><GatewayTriggerForm nodeId="t" kind={kind} /></MemoryRouter>;
}
const open = (kind: 'gateway' | 'whatsapp' | 'telegram', initial: Record<string, unknown> = {}) => {
  saved = { type: kind, ...initial };
  return render(<Harness kind={kind} initial={initial} />);
};
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 260)); });

beforeEach(() => {
  registryState = { registry: FIXTURE_REGISTRY, loading: false, failed: false, reload: vi.fn() };
  canManage = true;
});
afterEach(cleanup);

describe('GatewayTriggerForm', () => {
  it('asks for the number first, in plain words, and shows only the options the server describes for WhatsApp', () => {
    open('whatsapp');
    expect(screen.getByText('Which WhatsApp number?')).toBeTruthy();
    expect(screen.getByTestId('flow-gateway-select').textContent).toContain('Pick a WhatsApp number');
    expect(screen.queryByTestId('flow-gateway-filter-summary')).toBeNull(); // the picker already says it
    expect(screen.getByTestId('flow-param-keywords')).toBeTruthy();
    expect(screen.queryByTestId('flow-param-chat_scope')).toBeNull(); // WhatsApp has no groups
    expect(screen.getByTestId('flow-param-first_message_only')).toBeTruthy();
    expect(screen.getByTestId('flow-gateway-notes').textContent).toContain('STOP');
  });

  it('never shows internal words', () => {
    open('whatsapp');
    const text = screen.getByTestId('flow-gateway-trigger-whatsapp').textContent ?? '';
    expect(text).not.toMatch(/gateway|provider|payload|webhook|sender_id|input\.|trigger\./i);
  });

  it('maps each option type to its control', async () => {
    open('telegram', { gateway: 'Sales Bot' });
    // tags -> word list with an Add button
    expect(screen.getByTestId('flow-param-keywords-editor')).toBeTruthy();
    expect(screen.getByTestId('flow-param-keywords-add')).toBeTruthy();
    // people -> word list too
    expect(screen.getByTestId('flow-param-only_senders-add')).toBeTruthy();
    // multiselect -> one checkbox per choice
    expect(screen.getByTestId('flow-param-message_kinds-option-voice')).toBeTruthy();
    // select, text, boolean
    expect(screen.getByTestId('flow-param-chat_scope').getAttribute('role')).toBe('combobox');
    expect(screen.getByTestId('flow-param-starts_with').tagName).toBe('INPUT');
    expect(screen.getByTestId('flow-param-has_attachment').getAttribute('role')).toBe('switch');
    // Telegram's own
    expect(screen.getByTestId('flow-param-commands-add')).toBeTruthy();
  });

  it('adds a keyword, saves it as a {key, value} pair and shows it on the summary', async () => {
    open('whatsapp', { gateway: 'Support WhatsApp' });
    fireEvent.change(screen.getByTestId('flow-param-keywords'), { target: { value: 'order' } });
    fireEvent.click(screen.getByTestId('flow-param-keywords-add'));
    await flush();
    expect(saved.params).toEqual([{ key: 'keywords', value: ['order'] }]);
    expect(screen.getByTestId('flow-gateway-filter-summary').textContent).toBe('Support · Only messages that contain "order"');
    fireEvent.change(screen.getByTestId('flow-param-keywords'), { target: { value: 'refund, help' } });
    fireEvent.keyDown(screen.getByTestId('flow-param-keywords'), { key: 'Enter' });
    await flush();
    expect(saved.params).toEqual([{ key: 'keywords', value: ['order', 'refund', 'help'] }]);
    fireEvent.click(screen.getByTestId('flow-param-keywords-remove-0'));
    await flush();
    expect(saved.params).toEqual([{ key: 'keywords', value: ['refund', 'help'] }]);
  });

  it('switching an option back to its default removes it, and an empty list is not kept', async () => {
    open('telegram', { gateway: 'Sales Bot', params: [{ key: 'has_attachment', value: true }] });
    fireEvent.click(screen.getByTestId('flow-param-has_attachment'));
    await flush();
    expect(saved.params).toBeUndefined();
  });

  it('checks choices of a multiselect', async () => {
    open('whatsapp', { gateway: 'Support WhatsApp' });
    fireEvent.click(screen.getByTestId('flow-param-message_kinds-option-voice').querySelector('button')!);
    await flush();
    expect(saved.params).toEqual([{ key: 'message_kinds', value: ['voice'] }]);
  });

  it('honors show_when: the mention option follows where the trigger listens', async () => {
    open('telegram', { gateway: 'Sales Bot', params: [{ key: 'chat_scope', value: 'direct' }] });
    expect(screen.queryByTestId('flow-param-only_when_mentioned')).toBeNull();
    cleanup();
    open('telegram', { gateway: 'Sales Bot', params: [{ key: 'chat_scope', value: 'groups' }] });
    expect(screen.getByTestId('flow-param-only_when_mentioned')).toBeTruthy();
  });

  it('keeps the rare options under More options, open only when one is set', async () => {
    open('whatsapp', { gateway: 'Support WhatsApp' });
    const toggle = screen.getByTestId('flow-gateway-more-toggle');
    expect(screen.queryByTestId('flow-param-allow_parallel')).toBeNull();
    fireEvent.click(toggle);
    expect(screen.getByTestId('flow-param-allow_parallel')).toBeTruthy();
    expect(screen.getByTestId('flow-param-max_runs_per_sender_per_hour').getAttribute('type')).toBe('number');
    cleanup();
    open('whatsapp', { gateway: 'Support WhatsApp', params: [{ key: 'allow_parallel', value: true }] });
    expect(screen.getByTestId('flow-param-allow_parallel')).toBeTruthy();
  });

  it('says "Connect a number" with a link when none is connected', () => {
    registryState = { ...registryState, registry: { ...FIXTURE_REGISTRY, gateways: [] } };
    open('whatsapp');
    expect(screen.getByTestId('flow-gateway-none').textContent).toContain('No WhatsApp number is connected yet');
    const link = screen.getByTestId('flow-gateway-connect');
    expect(link.textContent).toBe('Connect a number');
    expect(link.getAttribute('href')).toBe('/channels/whatsapp/setup');
  });

  it('a Telegram bot, not a number, for Telegram', () => {
    registryState = { ...registryState, registry: { ...FIXTURE_REGISTRY, gateways: [] } };
    open('telegram');
    expect(screen.getByTestId('flow-gateway-connect').textContent).toBe('Connect a bot');
  });

  it('the generic trigger offers every kind of channel and names it', () => {
    open('gateway', { gateway: 'Team Slack' });
    expect(screen.getByText('Which channel?')).toBeTruthy();
    expect(screen.getByTestId('flow-gateway-filter-summary').textContent).toBe('When someone messages Team chat (Slack)');
    expect(screen.getByTestId('flow-param-chat_scope')).toBeTruthy();
    expect(screen.queryByTestId('flow-param-commands')).toBeNull();
  });

  it('shows a retry when the channels cannot be loaded', () => {
    registryState = { registry: null, loading: false, failed: true, reload: vi.fn() };
    open('whatsapp');
    fireEvent.click(screen.getByTestId('flow-gateway-retry'));
    expect(registryState.reload).toHaveBeenCalled();
  });

  it('a viewer sees the options but cannot change them', () => {
    canManage = false;
    open('whatsapp', { gateway: 'Support WhatsApp' });
    expect(screen.getByTestId('flow-param-has_attachment').hasAttribute('disabled')).toBe(true);
  });

  it('a viewer (the server refuses the channel list) still reads which messages start the flow, with no error and nothing to change', () => {
    canManage = false;
    registryState = { registry: null, loading: false, failed: true, reload: vi.fn() };
    open('whatsapp', { gateway: 'Support WhatsApp', params: [{ key: 'keywords', value: ['order'] }] });
    expect(screen.getByTestId('flow-gateway-filter-summary').textContent).toBe('Support WhatsApp · Only messages that contain "order"');
    expect(screen.queryByTestId('flow-gateway-load-failed')).toBeNull();
    expect(screen.queryByTestId('flow-gateway-select')).toBeNull();
    expect(screen.queryByTestId('flow-gateway-retry')).toBeNull();
  });

  it('the trigger panel routes the three kinds to this form', () => {
    for (const kind of ['gateway', 'whatsapp', 'telegram'] as const) {
      nodes = [{ id: 't', type: 'trigger', position: { x: 0, y: 0 }, data: { label: 'T', nodeType: 'trigger', icon: 'x', triggerConfig: { type: kind } } as FlowNodeData }];
      const { unmount } = render(<MemoryRouter><TriggerConfigForm nodeId="t" /></MemoryRouter>);
      expect(screen.getByTestId(`flow-gateway-trigger-${kind}`)).toBeTruthy();
      unmount();
    }
  });
});
