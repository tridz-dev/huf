// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('./formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('./formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('./formTestKit')).catalogMock());
vi.mock('@/hooks/flow/useGatewayRegistry', () => ({
  useGatewayRegistry: () => ({
    registry: {
      gateways: [
        { name: 'wa-main', label: 'Main WhatsApp', provider: 'WhatsApp', enabled: true, connection_state: 'connected' },
        { name: 'tg-bot', label: 'Telegram bot', provider: 'telegram', enabled: true, connection_state: 'connected' },
      ],
    },
    loading: false,
    failed: false,
    reload: () => {},
  }),
}));

import { SendMessageForm } from '../SendMessageForm';
import { latest, renderForm } from './formTestKit';
import { sendMessageIssues, sendOutcomeSummary } from '@/lib/flow-send/sendMessage';
import { validateNode } from '@/lib/flow-graph/flowValidation';
import { deserializeFlow, serializeFlow } from '@/services/flowSerializer';
import type { Flow } from '@/types/flow.types';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;
afterEach(cleanup);

const fields = (cfg: Record<string, unknown>) => sendMessageIssues(cfg).map(([f]) => f);
const valid = { gateway: 'wa-main', recipient: '+10000000000', category: 'service', template: 'welcome' };

describe('send message validation', () => {
  it('a complete step has no issues', () => {
    expect(sendMessageIssues(valid)).toEqual([]);
    expect(sendMessageIssues({ ...valid, template: undefined, text: 'Hi' })).toEqual([]);
  });

  it('needs a gateway, a recipient and a category', () => {
    expect(fields({ template: 'x' })).toEqual(['gateway', 'recipient', 'category']);
    expect(fields({ ...valid, category: 'promo' })).toEqual(['category']);
  });

  it('needs exactly one of template and text', () => {
    expect(fields({ ...valid, template: '' })).toEqual(['template']);
    expect(fields({ ...valid, text: 'Hi' })).toEqual(['text']);
  });

  it('variables must be non-empty token names', () => {
    expect(fields({ ...valid, variables: ['name', ''] })).toEqual(['variables']);
    expect(fields({ ...valid, variables: ['name'] })).toEqual([]);
  });

  it('a blocked send reads with its reason; other outputs are left alone', () => {
    expect(sendOutcomeSummary({ status: 'blocked', reason: 'freq_cap' })).toBe('Not sent, blocked: freq cap');
    expect(sendOutcomeSummary({ status: 'previewed' })).toContain('not sent');
    expect(sendOutcomeSummary({ status: 'ok' })).toBeNull();
  });
});

describe('send message in the builder check', () => {
  it('names the missing fields on the step', () => {
    const issues = validateNode({ id: 's', data: { label: 'Send', nodeType: 'action', actionConfig: { type: 'send-message', template: 'x' } } }, [{ source: 's', target: 'end' }]);
    expect(issues.filter((i) => i.kind === 'send.message').map((i) => i.field)).toEqual(['gateway', 'recipient', 'category']);
  });
});

describe('send message serialisation', () => {
  it('round-trips as a send.message node with only the set keys', () => {
    const flow = {
      id: 'f', name: 'F', status: 'draft',
      nodes: [
        { id: 't', type: 'trigger', position: { x: 0, y: 0 }, data: { label: 'T', nodeType: 'trigger', icon: 'x', triggerConfig: { type: 'webhook', method: 'POST', secret: 's' } } },
        { id: 's', type: 'action', position: { x: 0, y: 100 }, data: { label: 'Send', nodeType: 'action', icon: 'Send', actionConfig: { type: 'send-message', ...valid, text: undefined, variables: ['name'] } } },
      ],
      edges: [{ id: 'e', source: 't', target: 's' }],
    } as unknown as Flow;
    const graph = serializeFlow(flow);
    const node = graph.nodes.find((n) => n.id === 's')!;
    expect(node.type).toBe('send.message');
    expect(node.config).toEqual({ ...valid, variables: ['name'] });
    const back = deserializeFlow('f', 'F', 'Draft', graph).nodes.find((n) => n.id === 's')!;
    expect(back.data.actionConfig).toEqual({ type: 'send-message', ...valid, variables: ['name'] });
  });
});

describe('SendMessageForm', () => {
  it('offers only WhatsApp gateways and saves the choice', async () => {
    renderForm(SendMessageForm, { type: 'send-message', template: '', category: 'service' });
    fireEvent.click(await screen.findByTestId('flow-field-test-gateway'));
    expect(screen.getByTestId('flow-field-test-gateway-option-wa-main')).toBeTruthy();
    expect(screen.queryByTestId('flow-field-test-gateway-option-tg-bot')).toBeNull();
    fireEvent.click(screen.getByTestId('flow-field-test-gateway-option-wa-main'));
    expect(latest.gateway).toBe('wa-main');
  });

  it('shows template fields by default and the text field for a text step', () => {
    renderForm(SendMessageForm, { type: 'send-message', template: '' });
    expect(screen.getByTestId('flow-field-test-variables')).toBeTruthy();
    expect(screen.queryByTestId('flow-field-test-text')).toBeNull();
    cleanup();
    renderForm(SendMessageForm, { type: 'send-message', text: 'Hi' });
    expect(screen.getByTestId('flow-field-test-text')).toBeTruthy();
    expect(screen.queryByTestId('flow-field-test-template')).toBeNull();
  });

  it('a blank language is not saved', () => {
    renderForm(SendMessageForm, { type: 'send-message', template: '', language: 'en' });
    fireEvent.change(screen.getByTestId('flow-field-test-language'), { target: { value: ' ' } });
    expect('language' in latest).toBe(false);
  });
});
