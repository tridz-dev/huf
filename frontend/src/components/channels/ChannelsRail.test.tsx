// @vitest-environment jsdom
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const api = vi.hoisted(() => ({ getSetupStatus: vi.fn() }));
vi.mock('@/services/whatsappHealthApi', async (orig) => ({ ...(await orig<object>()), ...api }));

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
    expect(screen.getAllByText('P2')).toHaveLength(3);
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
});
