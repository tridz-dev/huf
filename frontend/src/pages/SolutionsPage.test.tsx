// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import type { Intent, SolutionSummary } from '@/types/solutions';

const api = vi.hoisted(() => ({ listSolutions: vi.fn(), getIntents: vi.fn() }));
const gw = vi.hoisted(() => ({ getGateways: vi.fn() }));
vi.mock('@/services/solutionsApi', async (orig) => ({ ...(await orig<object>()), ...api }));
vi.mock('@/services/gatewayApi', async (orig) => ({ ...(await orig<object>()), ...gw }));
vi.mock('@/components/ui/select', async () => {
  const React = await import('react');
  type Ctx = { value?: string; onValueChange?: (v: string) => void };
  const C = React.createContext<Ctx>({});
  return {
    Select: ({ value, onValueChange, children }: React.PropsWithChildren<Ctx>) =>
      React.createElement(C.Provider, { value: { value, onValueChange } }, children),
    SelectTrigger: ({ 'aria-label': label }: { 'aria-label'?: string; children?: React.ReactNode }) => {
      const ctx = React.useContext(C);
      return null === ctx ? null : React.createElement('span', { 'data-select-label': label });
    },
    SelectValue: () => null,
    SelectContent: ({ children }: React.PropsWithChildren) => {
      const ctx = React.useContext(C);
      return React.createElement('select', { 'aria-label': 'Purpose', value: ctx.value, onChange: (e: React.ChangeEvent<HTMLSelectElement>) => ctx.onValueChange?.(e.target.value) }, children);
    },
    SelectItem: ({ value, children }: React.PropsWithChildren<{ value: string }>) => React.createElement('option', { value }, children),
  };
});
vi.mock('@/layouts/PageFrame', () => ({
  PageFrame: ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div>
      <h1>{title}</h1>
      {children}
    </div>
  ),
}));

import SolutionsPage from './SolutionsPage';
import { labels, purposeLabel } from '@/components/solutions/labels';

const intent = (id: string, name: string, icon = 'circle-help'): Intent => ({
  id, name, desc: `${name} desc`, icon, sample_name: name, entry: 'none', keywords: [], ref: '', suggested_templates: [], policy: [],
});
const INTENTS = [
  intent('answer', 'Answer questions'),
  intent('orders', 'Take orders', 'shopping-bag'),
  intent('support', 'Support & handoff', 'life-buoy'),
  intent('bookings', 'Bookings', 'calendar-days'),
  intent('updates', 'Send updates', 'bell'),
  intent('team', 'Team & internal', 'users'),
];
const sol = (over: Partial<SolutionSummary> = {}): SolutionSummary => ({
  name: 'SOL-1', title: 'Order desk', purpose: 'orders', status: 'Live', test_mode: false,
  runs_on: [{ gateway: 'GW-1', label: 'Bakery main', phone: '+1' }], shared: true, entry_count: 3,
  primary: { type: 'Agent', name: 'A1', label: 'Bakery assistant' }, chats_7d: 42, ...over,
});

function Where() {
  const l = useLocation();
  return <output data-testid="where">{l.pathname + l.search}</output>;
}
const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/solutions']}>
      <Routes>
        <Route path="/solutions" element={<SolutionsPage />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
  Element.prototype.scrollIntoView = () => {};
  api.getIntents.mockResolvedValue(INTENTS);
  gw.getGateways.mockResolvedValue([{ name: 'GW-1', provider: 'WhatsApp' }]);
});

describe('SolutionsPage', () => {
  it('renders cards from the API and opens one', async () => {
    api.listSolutions.mockResolvedValue([sol()]);
    renderPage();
    expect(await screen.findByText('Order desk')).toBeTruthy();
    expect(screen.getByText('Active')).toBeTruthy();
    expect(screen.getByText('Bakery main')).toBeTruthy();
    expect(screen.getByText('Shared')).toBeTruthy();
    expect(screen.getByText('42 chats this week')).toBeTruthy();
    expect(screen.queryByText(/No WhatsApp number/)).toBeNull();
    await userEvent.click(screen.getByText('Order desk'));
    expect(screen.getByTestId('where').textContent).toBe('/solutions/SOL-1');
  });

  it('calls the API with the chosen purpose', async () => {
    api.listSolutions.mockResolvedValue([sol()]);
    renderPage();
    await screen.findByText('Order desk');
    fireEvent.change(screen.getByLabelText(labels.purpose), { target: { value: 'orders' } });
    await waitFor(() => expect(api.listSolutions).toHaveBeenLastCalledWith('orders'));
  });

  it('shows the first-time view with six purposes and two exits', async () => {
    api.listSolutions.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText('Group what your WhatsApp numbers do')).toBeTruthy();
    for (const i of INTENTS) expect(screen.getByText(i.name)).toBeTruthy();
    await userEvent.click(screen.getByText('Take orders'));
    expect(screen.getByTestId('where').textContent).toBe('/solutions/new?purpose=orders');
  });

  it.each([
    ['I already have an agent or flow', '/solutions/new?mode=existing'],
    ['Start blank', '/solutions/new?mode=blank'],
  ])('exit "%s" navigates', async (text, url) => {
    api.listSolutions.mockResolvedValue([]);
    renderPage();
    await userEvent.click(await screen.findByText(text));
    expect(screen.getByTestId('where').textContent).toBe(url);
  });

  it('shows an error state', async () => {
    api.listSolutions.mockRejectedValue(new Error('boom'));
    renderPage();
    expect(await screen.findByText('boom')).toBeTruthy();
  });

  it('shows the no-number banner when no WhatsApp gateway exists', async () => {
    api.listSolutions.mockResolvedValue([sol()]);
    gw.getGateways.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText(/No WhatsApp number is connected/)).toBeTruthy();
  });

  it('takes its wording from labels.ts', async () => {
    api.listSolutions.mockResolvedValue([sol()]);
    renderPage();
    expect((await screen.findAllByText(labels.solutions)).length).toBeGreaterThan(0);
    expect(screen.getByText(labels.newSolution)).toBeTruthy();
    expect(screen.getByText(labels.activeSolutions)).toBeTruthy();
    expect(purposeLabel('nope')).toBe('Custom');
  });
});
