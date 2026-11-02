// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const health = vi.hoisted(() => ({ getSetupStatus: vi.fn() }));
vi.mock('@/services/whatsappHealthApi', async (orig) => ({ ...(await orig<object>()), ...health }));
const sapi = vi.hoisted(() => ({
  saveWhatsAppCredentials: vi.fn(),
  latestInboundText: vi.fn(),
  bindAgent: vi.fn(),
  savePolicy: vi.fn(),
}));
vi.mock('./setupApi', async (orig) => ({ ...(await orig<object>()), ...sapi }));
vi.mock('@/services/gatewayApi', async (orig) => ({
  ...(await orig<object>()),
  getAvailableAgents: vi.fn().mockResolvedValue([]),
}));
vi.mock('@/contexts/UserContext', () => ({ useUser: () => ({ user: { name: 'ops@example.com' } }) }));

import { SetupWizard } from './SetupWizard';

const status = (stage: string) => ({
  ok: true,
  data: { success: true, connector_available: true, gateway: { name: 'GW-1', setup_stage: stage, webhook_url: 'https://x/hook', policy: {} } },
});
const flush = async () => {
  await act(async () => {
    await Promise.resolve();
  });
};
const open = (props = {}) =>
  render(
    <MemoryRouter>
      <SetupWizard {...props} />
    </MemoryRouter>,
  );

describe('SetupWizard', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    sapi.latestInboundText.mockResolvedValue(null);
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it.each([
    ['not_connected', 1],
    ['connected_unverified', 3],
    ['receiving', 4],
    ['live_unrouted', 5],
  ])('resumes at the step implied by %s', async (stage, step) => {
    health.getSetupStatus.mockResolvedValue(status(stage));
    open({ gateway: 'GW-1' });
    await flush();
    expect(screen.getByText(new RegExp(`^Step ${step} of 6`))).toBeTruthy();
    expect(screen.getByRole('listitem', { current: 'step' })).toBeTruthy();
  });

  it('shows the facebook path disabled and the Hub card', async () => {
    open();
    expect((screen.getAllByRole('button', { name: 'Connect with Facebook' })[0] as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('Ask Hub instead')).toBeTruthy();
  });

  it('polls every 3s and advances from webhook to test when Meta verifies', async () => {
    health.getSetupStatus.mockResolvedValue(status('connected_unverified'));
    open({ gateway: 'GW-1' });
    await flush();
    expect(screen.getByText(/Waiting for Meta to verify/)).toBeTruthy();
    health.getSetupStatus.mockResolvedValue(status('receiving'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(screen.getByText(/^Step 4 of 6/)).toBeTruthy();
    health.getSetupStatus.mockResolvedValue(status('live_unrouted'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(screen.getByText(/^Step 5 of 6/)).toBeTruthy();
  });

  it('submits the credentials and hands the new gateway to the caller', async () => {
    sapi.saveWhatsAppCredentials.mockResolvedValue({ ok: true, gateway: 'GW-NEW' });
    const onGatewayCreated = vi.fn();
    open({ onGatewayCreated });
    fireEvent.click(screen.getByRole('button', { name: 'I have a Meta app' }));
    const type = (label: string | RegExp, v: string) => fireEvent.change(screen.getByLabelText(label), { target: { value: v } });
    type('Name for this number', 'Support');
    type('Phone number ID', '111');
    type(/WhatsApp Business Account ID/, '222');
    type('App ID', '333');
    type('Access token', 'EAAtoken');
    type('App secret', 'shh');
    expect((screen.getByLabelText('Access token') as HTMLInputElement).type).toBe('password');
    expect((screen.getByLabelText('App secret') as HTMLInputElement).type).toBe('password');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save and check' }));
    });
    expect(sapi.saveWhatsAppCredentials).toHaveBeenCalledTimes(1);
    const arg = sapi.saveWhatsAppCredentials.mock.calls[0][0];
    expect(arg).toMatchObject({ name: 'Support', executionUser: 'ops@example.com' });
    expect(arg.credentials).toMatchObject({ phone_number_id: '111', business_account_id: '222', app_id: '333', access_token: 'EAAtoken', app_secret: 'shh' });
    expect(arg.credentials.webhook_verify_token).toMatch(/^huf-/);
    expect(onGatewayCreated).toHaveBeenCalledWith('GW-NEW');
  });

  it('shows the save error and stays on credentials', async () => {
    sapi.saveWhatsAppCredentials.mockResolvedValue({ ok: false, error: 'Meta rejected the token' });
    open();
    fireEvent.click(screen.getByRole('button', { name: 'I have a Meta app' }));
    for (const l of ['Name for this number', 'Phone number ID', /WhatsApp Business Account ID/, 'App ID', 'Access token', 'App secret'])
      fireEvent.change(screen.getByLabelText(l), { target: { value: 'x' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save and check' }));
    });
    expect(screen.getByRole('alert').textContent).toContain('Meta rejected the token');
  });
});
