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

describe('GatewaysPage field standard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function expectNoRawLabels(root: ParentNode) {
    const labels = Array.from(root.querySelectorAll('label'));
    for (const l of labels) {
      // A Field label has htmlFor and never wraps a control.
      expect(l.getAttribute('for'), l.textContent ?? '').toBeTruthy();
      expect(l.querySelector('input,select,button,textarea,[role="combobox"],[role="switch"]')).toBeNull();
    }
  }

  function expectStandardHeights(root: ParentNode) {
    const bad = /(^|\s)(h-(7|8|9|10)|text-xs)(\s|$)/;
    root
      .querySelectorAll('input:not([readonly]),select,textarea,[role="combobox"],[role="switch"],button[type="submit"]')
      .forEach((el) => expect(el.className, el.outerHTML.slice(0, 80)).not.toMatch(bad));
  }

  it('config modal has no raw labels, standard heights, copy-field and switch fields', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /Configure gateway/i }));
    const dialog = await screen.findByRole('dialog');
    expectNoRawLabels(dialog);
    expectStandardHeights(dialog);
    expect(dialog.querySelector('[data-field-label]')).not.toBeNull();
    // Webhook copy row is the shared CopyField.
    expect(screen.getByRole('button', { name: 'Copy Live Inbound Webhook Endpoint' })).toBeInTheDocument();
    expect(screen.getByLabelText('Live Inbound Webhook Endpoint')).toHaveAttribute('readonly');
    // Both switches sit inside a Field.
    for (const name of ['Gateway Status', 'Require @mention in rooms']) {
      expect(screen.getByRole('switch', { name }).closest('[data-field-label]')).toBeNull();
      expect(screen.getByRole('switch', { name }).closest('div.flex.min-w-0.flex-col')).not.toBeNull();
    }
    // Mention switch is a FieldAction beside the labelled lifetime Field.
    const row = screen.getByRole('spinbutton').closest('[data-field-row]');
    expect(row?.children).toHaveLength(2);
    expect(row?.querySelector('[aria-hidden="true"][data-field-label]')).not.toBeNull();
  });

  it('pairing row is a FieldRow with a Field and a FieldAction', async () => {
    const user = userEvent.setup();
    renderPage('/gateways?tab=pending-access');
    const input = await screen.findByPlaceholderText('PAIR-XXXX');
    const row = input.closest('[data-field-row]') as HTMLElement;
    expect(row).not.toBeNull();
    expect(row.children).toHaveLength(2);
    expect(row.children[0].querySelector('[data-field-label] label')).toHaveTextContent('Approve by pairing code');
    const action = row.children[1];
    expect(action.querySelector('[data-field-label][aria-hidden="true"]')).not.toBeNull();
    expect(action.querySelector('button[type="submit"]')).not.toBeNull();
    expectNoRawLabels(document.body);
    expectStandardHeights(row.closest('form')!);
    void user;
  });

  it('create-gateway form uses Fields with standard heights', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /Add gateway/i }));
    const input = await screen.findByPlaceholderText('e.g. Support Inbox on WhatsApp');
    const row = input.closest('[data-field-row]') as HTMLElement;
    expect(row.children).toHaveLength(3);
    expectNoRawLabels(document.body);
    expectStandardHeights(row);
  });
});
