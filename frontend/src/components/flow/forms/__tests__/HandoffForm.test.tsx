// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const policy = vi.hoisted(() => ({ current: null as null | Record<string, unknown> }));
vi.mock('@/embed/bridge', async (original) => ({ ...(await original<object>()), embedPolicy: () => policy.current }));
vi.mock('@/contexts/FlowContext', async () => (await import('./formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('./formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('./formTestKit')).catalogMock());
vi.mock('@/hooks/flow/useGatewayRegistry', () => ({
  useGatewayRegistry: () => ({
    registry: { gateways: [{ name: 'other-app', label: 'Other', provider: 'WhatsApp' }] },
    loading: false, failed: false, reload: () => {},
  }),
}));
vi.mock('@/services/flow/gatewayTriggerApi', () => ({
  getAppFlowGateways: vi.fn().mockResolvedValue({
    restricted: true,
    gateways: [{ name: 'wa-app', label: 'App WhatsApp', provider: 'WhatsApp', enabled: true, connection_state: 'connected' }],
  }),
}));

import { defaultActionConfig } from '@/lib/flow-history/actionDefaults';
import { SchemaNodeForm } from '../SchemaNodeForm';
import { latest, renderForm } from './formTestKit';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;
afterEach(() => { cleanup(); policy.current = null; });

const APP = { publish: 'host', test: 'dry_run', can_edit: true, can_test: true, can_approve: false };
const step = { type: 'unknown', backend_type: 'handoff' };

describe('handoff step in the embedded editor of an app flow', () => {
  it('offers only the channels the app lists and keeps the step member-only', async () => {
    policy.current = APP;
    renderForm(SchemaNodeForm, { ...step, conversation: 'c1', message: 'hi' });
    expect(latest).toEqual({ ...step, recipient: '$member', message: '' });
    for (const hidden of ['conversation', 'recipient', 'message']) expect(screen.queryByTestId(`flow-field-test-${hidden}`)).toBeNull();
    const picker = screen.getByTestId('flow-field-test-gateway') as HTMLButtonElement;
    await waitFor(() => expect(picker.disabled).toBe(false));
    fireEvent.click(picker);
    expect(screen.queryByTestId('flow-field-test-gateway-option-other-app')).toBeNull();
    fireEvent.click(screen.getByTestId('flow-field-test-gateway-option-wa-app'));
    expect(latest.gateway).toBe('wa-app');
  });

  it('a freshly added step is already member-only', () => {
    expect(defaultActionConfig('handoff')).toEqual(step);
    policy.current = APP;
    expect(defaultActionConfig('handoff')).toEqual({ ...step, recipient: '$member', message: '' });
  });

  it('outside an app flow the free fields stay and nothing is filled in', () => {
    renderForm(SchemaNodeForm, step);
    expect(latest).toEqual(step);
    for (const field of ['conversation', 'gateway', 'recipient', 'message']) expect(screen.getByTestId(`flow-field-test-${field}`)).toBeTruthy();
  });
});
