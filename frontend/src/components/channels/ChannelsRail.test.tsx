// @vitest-environment jsdom
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const api = vi.hoisted(() => ({ getSetupStatus: vi.fn() }));
const list = vi.hoisted(() => ({ listChannelGateways: vi.fn() }));
vi.mock('@/services/whatsappHealthApi', async (orig) => ({ ...(await orig<object>()), ...api }));
vi.mock('@/services/channelGatewaysApi', () => list);

vi.mock('@/components/whatsapp/TemplatesTab', () => ({ TemplatesTab: () => <div>templates tab</div> }));
vi.mock('@/components/whatsapp/broadcast/BroadcastList', () => ({ BroadcastList: () => <div>broadcast list</div> }));
vi.mock('@/components/whatsapp/broadcast/BroadcastTab', () => ({ EmergencyStop: () => <div>emergency</div> }));

import { ChannelsRoutes } from './routes';

beforeAll(() => {
  window.matchMedia = ((q: string) => ({
    matches: false, media: q, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
});

const setWidth = (w: number) => {
  Object.defineProperty(window, 'innerWidth', { value: w, configurable: true, writable: true });
};
const open = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/channels/*" element={<ChannelsRoutes />} />
      </Routes>
    </MemoryRouter>
  );

describe('ChannelsRail', () => {
  beforeEach(() => {
    localStorage.clear();
    list.listChannelGateways.mockResolvedValue({ ok: true, data: [] });
    setWidth(1280);
    api.getSetupStatus.mockResolvedValue({
      ok: true,
      data: { success: true, connector_available: true, gateways: [{ name: 'GW-1', enabled: true }] },
    });
  });

  it('renders all items, greyed channels, and marks the active one', async () => {
    open('/channels/whatsapp/n/GW-1/templates');
    for (const l of ['Home', 'Activity', 'Broadcasts', 'Templates', 'Automations', 'Connections', 'Numbers', 'Settings', 'Ask Hub', 'Back to Huf']) {
      expect(await screen.findByRole('link', { name: l })).toBeTruthy();
    }
    expect(screen.queryByText('P2')).toBeNull();
    const active = screen.getByRole('link', { name: 'Templates' });
    expect(active.className).toContain('bg-paper-deep');
    expect(active.querySelector('[data-testid="active-bar"]')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Home' }).querySelector('[data-testid="active-bar"]')).toBeNull();
    expect(screen.getByText('WhatsApp', { selector: 'div' })).toBeTruthy();
  });

  it('uses an overlay rail on mobile opened by the hamburger', async () => {
    setWidth(600);
    open('/channels/whatsapp/n/GW-1/home');
    await screen.findByRole('navigation', { name: 'Breadcrumb' });
    expect(screen.queryByRole('navigation', { name: 'Channels' })).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Toggle sidebar' }));
    });
    expect(screen.getByRole('navigation', { name: 'Channels' })).toBeTruthy();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Close menu' }));
    });
    expect(screen.queryByRole('navigation', { name: 'Channels' })).toBeNull();
  });

  it('enables a channel only when it has a gateway', async () => {
    list.listChannelGateways.mockResolvedValue({
      ok: true,
      data: [{ name: 'TG-1', provider: 'Telegram', channel: 'telegram', enabled: true }],
    });
    open('/channels/whatsapp/n/GW-1/home');
    expect(await screen.findByRole('link', { name: 'Telegram' })).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Slack' })).toBeNull();
    expect(screen.getByText('Slack').closest('[aria-disabled="true"]')).toBeTruthy();
    expect(screen.getByText('Teams').closest('[aria-disabled="true"]')).toBeTruthy();
  });

  it('hides Templates and Broadcasts for telegram and names the list Bots', async () => {
    list.listChannelGateways.mockResolvedValue({
      ok: true,
      data: [{ name: 'TG-1', provider: 'Telegram', channel: 'telegram', enabled: true }],
    });
    open('/channels/telegram/n/TG-1/home');
    expect(await screen.findByRole('link', { name: 'Bots' })).toBeTruthy();
    for (const l of ['Home', 'Activity', 'Automations', 'Connections', 'Settings']) {
      expect(screen.getByRole('link', { name: l })).toBeTruthy();
    }
    expect(screen.queryByRole('link', { name: 'Templates' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Broadcasts' })).toBeNull();
    expect(screen.getByText('Channels', { selector: 'span' })).toBeTruthy();
    expect(screen.getByText('Telegram', { selector: 'span' })).toBeTruthy();
  });
});
