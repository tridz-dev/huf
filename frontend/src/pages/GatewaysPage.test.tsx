// @vitest-environment jsdom
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';

vi.mock('@/contexts/UserContext', () => ({ useUser: () => ({ user: { name: 'u@example.com' } }) }));
vi.mock('@/layouts/PageFrame', () => ({
  PageFrame: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('./IntegrationSettingsListingPage', () => ({ IntegrationSettingsListingPage: () => <div>listing</div> }));
vi.mock('@/components/integrations/IntegrationSettingsHeaderActions', () => ({
  IntegrationSettingsHeaderActions: () => null,
}));
vi.mock('@/lib/frappe-sdk', () => ({ db: {} }));
vi.mock('@/services/integrationApi', () => ({
  getIntegrationSettings: vi.fn().mockResolvedValue([]),
}));
vi.mock('@/services/gatewayAccessApi', () => ({
  listGatewayAccessEntries: vi.fn().mockResolvedValue([]),
  approveGatewayPairing: vi.fn(),
  revokeGatewayAccessEntry: vi.fn(),
}));
vi.mock('@/services/gatewayApi', () => ({
  getGateways: vi.fn().mockResolvedValue([
    {
      name: 'gw-1',
      gateway_name: 'Support line',
      provider: 'Telegram',
      is_enabled: 0,
      mention_required: 0,
      direct_policy: 'Pairing',
    },
  ]),
  getAvailableAgents: vi.fn().mockResolvedValue([]),
  getAvailableFlows: vi.fn().mockResolvedValue([]),
  updateGateway: vi.fn(),
  deleteGateway: vi.fn(),
}));

import GatewaysPage from './GatewaysPage';

const originalMatches = Element.prototype.matches;
beforeAll(() => {
  Element.prototype.matches = function (selector: string) {
    if (selector === ':modal') return false;
    return originalMatches.call(this, selector);
  };
  // jsdom lacks these; Radix needs them.
  Element.prototype.hasPointerCapture ||= () => false;
  Element.prototype.scrollIntoView ||= () => {};
});
afterAll(() => {
  Element.prototype.matches = originalMatches;
});

function Search() {
  const loc = useLocation();
  return <div data-testid="search">{loc.search}</div>;
}

function renderPage(url = '/gateways') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <GatewaysPage />
      <Search />
    </MemoryRouter>
  );
}

describe('GatewaysPage shell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('syncs the active tab with ?tab= and supports keyboard navigation', async () => {
    const user = userEvent.setup();
    renderPage('/gateways?tab=pending-access');
    const pending = await screen.findByRole('tab', { name: /Pending access/ });
    expect(pending).toHaveAttribute('aria-selected', 'true');

    await user.click(screen.getByRole('tab', { name: 'Gateways' }));
    expect(screen.getByTestId('search').textContent).toBe('');
    expect(screen.getByRole('tab', { name: 'Gateways' })).toHaveAttribute('aria-selected', 'true');

    screen.getByRole('tab', { name: 'Gateways' }).focus();
    await user.keyboard('{ArrowRight}{ArrowRight}');
    await waitFor(() =>
      expect(screen.getByTestId('search').textContent).toBe('?tab=credentials')
    );
  });

  it('falls back to the default tab for an unknown ?tab= value', async () => {
    renderPage('/gateways?tab=bogus');
    expect(await screen.findByRole('tab', { name: 'Gateways' })).toHaveAttribute('aria-selected', 'true');
  });

  async function openModal(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole('button', { name: /Configure gateway/i }));
    return screen.findByRole('dialog');
  }

  it('opens the config dialog and closes it with Escape', async () => {
    const user = userEvent.setup();
    renderPage();
    const dialog = await openModal(user);
    expect(dialog).toHaveTextContent('Support line');
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('closes the config dialog via Cancel', async () => {
    const user = userEvent.setup();
    renderPage();
    await openModal(user);
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('toggles the gateway status and mention switches', async () => {
    const user = userEvent.setup();
    renderPage();
    await openModal(user);
    const status = screen.getByRole('switch', { name: 'Gateway Status' });
    expect(status).toHaveAttribute('aria-checked', 'false');
    await user.click(status);
    expect(screen.getByRole('switch', { name: 'Gateway Status' })).toHaveAttribute('aria-checked', 'true');

    const mention = screen.getByRole('switch', { name: 'Require @mention in rooms' });
    expect(mention).toHaveAttribute('aria-checked', 'false');
    await user.click(mention);
    expect(screen.getByRole('switch', { name: 'Require @mention in rooms' })).toHaveAttribute('aria-checked', 'true');
  });
});
