// @vitest-environment jsdom
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

const api = vi.hoisted(() => ({ getSetupStatus: vi.fn() }));
const list = vi.hoisted(() => ({ listChannelGateways: vi.fn() }));
vi.mock('@/services/whatsappHealthApi', async (orig) => ({ ...(await orig<object>()), ...api }));
vi.mock('@/services/channelGatewaysApi', () => list);

vi.mock('@/contexts/UserContext', () => ({ useUser: () => ({ user: { name: 'ops@example.com' } }) }));

import { ChannelsRoutes } from './routes';

beforeAll(() => {
  window.matchMedia = ((q: string) => ({
    matches: false, media: q, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
});

function Loc() {
  return <output data-testid="loc">{useLocation().pathname}</output>;
}
const summary = (gateways: { name: string; enabled: boolean; setup_stage?: string }[]) =>
  api.getSetupStatus.mockResolvedValue({ ok: true, data: { success: true, connector_available: true, gateways } });

const open = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/channels/*" element={<ChannelsRoutes />} />
      </Routes>
      <Loc />
    </MemoryRouter>
  );

describe('channels resolver', () => {
  beforeEach(() => {
    api.getSetupStatus.mockReset();
    list.listChannelGateways.mockReset();
    list.listChannelGateways.mockResolvedValue({ ok: false, error: 'not found' });
    localStorage.clear();
  });

  it('/channels goes to whatsapp then setup with zero gateways', async () => {
    summary([]);
    open('/channels');
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/channels/whatsapp/setup'));
  });

  it('goes to the only gateway home', async () => {
    summary([{ name: 'GW-1', enabled: true }]);
    open('/channels/whatsapp');
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/channels/whatsapp/n/GW-1/home'));
  });

  it('picks the first enabled gateway of two', async () => {
    summary([
      { name: 'GW-1', enabled: false },
      { name: 'GW-2', enabled: true },
    ]);
    open('/channels/whatsapp');
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/channels/whatsapp/n/GW-2/home'));
  });

  it('prefers the last-used gateway', async () => {
    localStorage.setItem('huf:channels:whatsapp:lastGateway', 'GW-2');
    summary([
      { name: 'GW-1', enabled: true },
      { name: 'GW-2', enabled: true },
    ]);
    open('/channels/whatsapp');
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/channels/whatsapp/n/GW-2/home'));
  });

  it('shows the setup banner when the gateway is pre-live and tolerates a missing field', async () => {
    summary([{ name: 'GW-1', enabled: true, setup_stage: 'receiving' }]);
    open('/channels/whatsapp/n/GW-1/home');
    expect(await screen.findByText(/Finish setup to go live \(4 of 6\)/)).toBeTruthy();
  });

  it('shows no banner without setup_stage', async () => {
    summary([{ name: 'GW-1', enabled: true }]);
    open('/channels/whatsapp/n/GW-1/home');
    await screen.findByRole('navigation', { name: 'Breadcrumb' });
    expect(screen.queryByText(/Finish setup/)).toBeNull();
  });

  const tg = (rows: { name: string; enabled: boolean }[]) =>
    list.listChannelGateways.mockResolvedValue({
      ok: true,
      data: rows.map((r) => ({ ...r, provider: 'Telegram', channel: 'telegram' })),
    });

  it('resolves telegram to its own gateway, ignoring whatsapp', async () => {
    summary([{ name: 'GW-1', enabled: true }]);
    tg([{ name: 'TG-1', enabled: true }]);
    open('/channels/telegram');
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/channels/telegram/n/TG-1/home'));
  });

  it('uses the per-channel last-used gateway', async () => {
    localStorage.setItem('huf:channels:telegram:lastGateway', 'TG-2');
    localStorage.setItem('huf:channels:whatsapp:lastGateway', 'GW-1');
    summary([{ name: 'GW-1', enabled: true }]);
    tg([{ name: 'TG-1', enabled: true }, { name: 'TG-2', enabled: true }]);
    open('/channels/telegram');
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/channels/telegram/n/TG-2/home'));
  });

  it('sends a channel with no gateways to its setup and unknown channels to whatsapp', async () => {
    summary([{ name: 'GW-1', enabled: true }]);
    open('/channels/slack');
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/channels/slack/setup'));
  });

  it('falls back to whatsapp-only when the list call fails', async () => {
    summary([{ name: 'GW-1', enabled: true }]);
    open('/channels/whatsapp');
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/channels/whatsapp/n/GW-1/home'));
  });
});
