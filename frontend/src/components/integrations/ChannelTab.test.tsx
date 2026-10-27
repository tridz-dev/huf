// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { ChannelTab } from './ChannelTab';

const api = vi.hoisted(() => ({
  preview: vi.fn(),
  gateway: {
  name: 'GW-1',
  gateway_name: 'My gateway',
  provider: 'Telegram',
  is_enabled: 1,
  integration_settings: 'IS-1',
  default_target_type: 'Agent',
  default_agent: 'A1',
  execution_user: 'svc@x.test',
  mention_required: 0,
  pairing_ttl_minutes: 60,
},
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/frappe-sdk', () => ({ call: { post: vi.fn() } }));
vi.mock('@/services/integrationApi', () => ({
  getIntegrationSetting: vi.fn().mockResolvedValue({}),
  setupTelegramWebhook: vi.fn(),
}));
vi.mock('@/services/gatewayApi', () => ({
  getGateways: vi.fn().mockResolvedValue([api.gateway]),
  getAvailableAgents: vi.fn().mockResolvedValue([{ name: 'A1', agent_name: 'Agent one' }]),
  getAvailableFlows: vi.fn().mockResolvedValue([]),
  getGatewayReadinessPreview: (...a: unknown[]) => api.preview(...a),
  updateGateway: vi.fn(),
  deleteGateway: vi.fn(),
}));

async function renderTab() {
  const view = render(
    <MemoryRouter>
      <ChannelTab settingId="IS-1" isNew={false} />
    </MemoryRouter>,
  );
  await screen.findByText('Run as user');
  await waitFor(() => expect(api.preview).toHaveBeenCalled());
  return view;
}

beforeEach(() => {
  api.preview.mockReset();
  api.gateway.provider = 'Telegram';
  api.preview.mockResolvedValue({ ready: true, blocking_count: 0, checks: [] });
});

describe('ChannelTab structure', () => {
  it('uses Field primitives and no raw label elements', async () => {
    const { container } = await renderTab();
    const raw = Array.from(container.querySelectorAll('label')).filter(
      // CopyField (ui primitive) renders its own Label for the webhook URL.
      (l) => !l.closest('[data-field-label]') && l.textContent !== 'Webhook URL',
    );
    expect(raw).toHaveLength(0);
    expect(screen.getByLabelText('Run as user')).toBeInTheDocument();
    expect(screen.getByLabelText('Pairing code lifetime (minutes)')).toBeInTheDocument();
    expect(screen.getByLabelText('Require @mention in rooms')).toHaveAttribute('role', 'switch');
    expect(screen.getByLabelText('Webhook URL')).toHaveAttribute('readonly');
  });

  it('puts the pairing and mention fields, and the test row, in FieldRows', async () => {
    const { container } = await renderTab();
    const rows = Array.from(container.querySelectorAll('[data-field-row]'));
    const pairing = screen.getByLabelText('Pairing code lifetime (minutes)');
    const mention = screen.getByLabelText('Require @mention in rooms');
    const row = rows.find((r) => r.contains(pairing));
    expect(row).toBeTruthy();
    expect(row!.contains(mention)).toBe(true);
    const send = screen.getByRole('button', { name: /send/i });
    const testRow = rows.find((r) => r.contains(send))!;
    expect(testRow.querySelectorAll('[data-field-label][aria-hidden="true"]')).toHaveLength(1);
  });

  it('has no h-* height overrides on controls', async () => {
    const { container } = await renderTab();
    for (const el of container.querySelectorAll('input, button[role="combobox"]')) {
      expect(el.className).not.toMatch(/(^|\s)h-\d/);
    }
  });
});

describe('ChannelTab readiness banner', () => {
  it('shows a count when not ready', async () => {
    api.preview.mockResolvedValue({
      ready: false,
      blocking_count: 2,
      checks: [{ id: 'a', label: 'A', done: false }],
    });
    await renderTab();
    expect(await screen.findByText('2 things left before this channel can receive messages')).toBeInTheDocument();
  });

  it('never prints "undefined" when blocking_count is missing', async () => {
    api.preview.mockResolvedValue({ ready: false, checks: [{ id: 'a', label: 'A', done: false }] });
    const { container } = await renderTab();
    await screen.findByText('1 thing left before this channel can receive messages');
    expect(container.textContent).not.toMatch(/undefined/);
  });

  it('hides the banner when no count can be determined', async () => {
    api.preview.mockResolvedValue({ ready: false });
    const { container } = await renderTab();
    await waitFor(() => expect(container.textContent).not.toMatch(/left before this channel/));
    expect(container.textContent).not.toMatch(/undefined/);
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('ChannelTab Teams gating', () => {
  it('renders the setup guide only for Microsoft Teams', async () => {
    await renderTab();
    expect(screen.queryByText('Microsoft Teams setup guide')).toBeNull();
    expect(screen.queryByText(/Teams test send needs a conversation/)).toBeNull();
  });

  it('renders the guide and test-send note for Microsoft Teams', async () => {
    api.gateway.provider = 'Microsoft Teams';
    await renderTab();
    expect(await screen.findByText('Microsoft Teams setup guide')).toBeInTheDocument();
    expect(screen.getAllByText(/Teams test send needs a conversation/).length).toBeGreaterThan(0);
  });

  it('shows a subtle note when readiness cannot be loaded', async () => {
    api.gateway.provider = 'Microsoft Teams';
    api.preview.mockRejectedValue(new Error('boom'));
    await renderTab();
    expect(await screen.findByText(/Could not load setup status/)).toBeInTheDocument();
  });
});
