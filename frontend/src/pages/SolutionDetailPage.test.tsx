// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { makeEntry, makeOverview } from '@/components/solutions/fixtures';

const api = vi.hoisted(() => ({
  getSolutionOverview: vi.fn(), listSolutions: vi.fn(), listEntryPoints: vi.fn(), listSolutionConversations: vi.fn(),
  pauseSolution: vi.fn(), resumeSolution: vi.fn(), goLive: vi.fn(), saveEntryPoint: vi.fn(), deleteEntryPoint: vi.fn(),
}));
vi.mock('@/services/solutionsApi', async (orig) => ({ ...(await orig<object>()), ...api }));
const seen = vi.hoisted(() => ({ templates: [] as Array<Record<string, unknown>>, chat: [] as Array<Record<string, unknown>> }));
vi.mock('@/components/whatsapp/TemplatesTab', () => ({
  TemplatesTab: (p: Record<string, unknown>) => { seen.templates.push(p); return <div>templates for {String(p.gateway)}</div>; },
}));
vi.mock('@/components/solutions/TestChat', () => ({
  TestChat: (p: Record<string, unknown>) => { seen.chat.push(p); return <div>test chat</div>; },
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { SolutionsApiError } from '@/services/solutionsApi';
import SolutionDetailPage from './SolutionDetailPage';

class RO { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/solutions/:name" element={<SolutionDetailPage />} />
        <Route path="/solutions" element={<div>list page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const two = [
  { gateway: 'gw1', label: 'Main', phone: '+1' },
  { gateway: 'gw2', label: 'Second', phone: '+2' },
];

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  seen.templates.length = 0;
  seen.chat.length = 0;
  api.getSolutionOverview.mockResolvedValue(makeOverview());
  api.listSolutions.mockResolvedValue([{ ...makeOverview(), name: 'orders' }, { ...makeOverview(), name: 'care', title: 'Care' }]);
  api.listEntryPoints.mockResolvedValue([makeEntry(), makeEntry({ name: 'ep2', match_type: 'Ad or link tag', match_values: ['spring'], priority: 2, cap_per_day: null })]);
  api.listSolutionConversations.mockResolvedValue([
    { contact: 'Ann', preview: 'Where is my order?', solution: 'orders', gateway: 'gw1', ts: '2026-10-24T10:00:00Z' },
  ]);
});
afterEach(cleanup);

describe('SolutionDetailPage', () => {
  it('shows a skeleton then the overview with breadcrumb', async () => {
    renderAt('/solutions/orders');
    expect(screen.getByTestId('solution-skeleton')).toBeInTheDocument();
    expect(await screen.findByText('Working: Orders is routing and replying normally.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Solutions' })).toHaveAttribute('href', '/solutions');
    expect(screen.getByText('Reach')).toBeInTheDocument();
    expect(screen.getByText('Activity')).toBeInTheDocument();
    expect(screen.getByText('Cost and limits')).toBeInTheDocument();
    expect(screen.getByRole('meter', { name: 'Daily limit used' })).toHaveAttribute('aria-valuenow', '40');
    expect(screen.getByRole('link', { name: 'Order agent' })).toHaveAttribute('href', '/agents/order-agent');
  });

  it('shows No limit set when the number has no ceiling', async () => {
    api.getSolutionOverview.mockResolvedValue(makeOverview({ cost: { sends_24h: 3, cap_share: 1, ceiling: null } }));
    renderAt('/solutions/orders');
    expect(await screen.findByText('No limit set')).toBeInTheDocument();
    expect(screen.queryByRole('meter')).toBeNull();
  });

  it('links a flow target to the flows route', async () => {
    api.getSolutionOverview.mockResolvedValue(makeOverview({ primary: { type: 'Flow', name: 'f1', label: 'Order flow' } }));
    renderAt('/solutions/orders');
    expect(await screen.findByRole('link', { name: 'Order flow' })).toHaveAttribute('href', '/flows/f1');
  });

  it('Check now refetches the overview', async () => {
    renderAt('/solutions/orders');
    await screen.findByText(/Working:/);
    fireEvent.click(screen.getByRole('button', { name: 'Check now' }));
    await waitFor(() => expect(api.getSolutionOverview).toHaveBeenCalledTimes(2));
  });

  it('pauses a live solution and refetches', async () => {
    api.pauseSolution.mockResolvedValue({});
    renderAt('/solutions/orders');
    fireEvent.click(await screen.findByRole('button', { name: 'Pause' }));
    await waitFor(() => expect(api.pauseSolution).toHaveBeenCalledWith('orders'));
    await waitFor(() => expect(api.getSolutionOverview).toHaveBeenCalledTimes(2));
  });

  it('resumes a paused solution', async () => {
    api.getSolutionOverview.mockResolvedValue(makeOverview({ status: 'Paused' }));
    api.resumeSolution.mockResolvedValue({});
    renderAt('/solutions/orders');
    fireEvent.click(await screen.findByRole('button', { name: 'Resume' }));
    await waitFor(() => expect(api.resumeSolution).toHaveBeenCalledWith('orders'));
  });

  it('go live explains and calls goLive after confirming', async () => {
    api.getSolutionOverview.mockResolvedValue(makeOverview({ status: 'Paused', test_mode: true }));
    api.goLive.mockResolvedValue({});
    renderAt('/solutions/orders');
    expect(screen.queryByRole('button', { name: 'Resume' })).toBeNull();
    fireEvent.click(await screen.findByRole('button', { name: 'Go live' }));
    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('Go live clears test mode');
    expect(api.goLive).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Go live' }));
    await waitFor(() => expect(api.goLive).toHaveBeenCalledWith('orders'));
  });

  it('renders the warn band naming the number and the sender', async () => {
    api.getSolutionOverview.mockResolvedValue(
      makeOverview({ health: { state: 'warn', gateway: 'gw1', quality: null, blame: { solution: 'care', share_pct: 80 } } }),
    );
    renderAt('/solutions/orders');
    const band = await screen.findByRole('status');
    expect(band).toHaveTextContent('Main +1 555 0100');
    expect(band).toHaveTextContent("Most of today's sends came from Care (80% of sends in the last 24 hours).");
    expect(band.textContent).not.toMatch(/rating/i);
  });

  it('Manage entry points opens the entry points tab', async () => {
    renderAt('/solutions/orders');
    fireEvent.click(await screen.findByRole('button', { name: 'Manage entry points' }));
    expect(await screen.findByText('refund')).toBeInTheDocument();
  });

  it('entry points tab lists rules and opens the sheet on row click', async () => {
    renderAt('/solutions/orders?tab=entries');
    expect(await screen.findByText('refund')).toBeInTheDocument();
    expect(screen.getByText(/Message contains/)).toBeInTheDocument();
    expect(screen.getByText('spring')).toBeInTheDocument();
    expect(screen.getByText('30')).toBeInTheDocument();
    fireEvent.click(screen.getByText('refund'));
    expect(await screen.findByRole('slider')).toHaveAttribute('aria-valuemax', '100');
    expect(screen.getByText('Maximum 100, set on Main')).toBeInTheDocument();
  });

  it('Add entry point opens create mode', async () => {
    renderAt('/solutions/orders?tab=entries');
    await screen.findByText('refund');
    fireEvent.click(screen.getByRole('button', { name: 'Add entry point' }));
    expect(await screen.findByLabelText('Match type')).toBeInTheDocument();
  });

  it('templates tab passes scopeSolution and the only gateway', async () => {
    renderAt('/solutions/orders?tab=templates');
    expect(await screen.findByText('templates for gw1')).toBeInTheDocument();
    expect(seen.templates.at(-1)).toMatchObject({ gateway: 'gw1', scopeSolution: 'orders' });
    expect(screen.getByRole('link', { name: 'Settings > WhatsApp' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Number')).toBeNull();
  });

  it('templates tab asks for a number when the solution runs on several', async () => {
    api.getSolutionOverview.mockResolvedValue(makeOverview({ runs_on: two }));
    renderAt('/solutions/orders?tab=templates');
    await screen.findByText('templates for gw1');
    fireEvent.change(screen.getByLabelText('Number'), { target: { value: 'gw2' } });
    expect(await screen.findByText('templates for gw2')).toBeInTheDocument();
    expect(seen.templates.at(-1)).toMatchObject({ gateway: 'gw2', scopeSolution: 'orders' });
  });

  it('conversations tab filters by this solution or all inboxes', async () => {
    renderAt('/solutions/orders?tab=convs');
    expect(await screen.findByText('Ann')).toBeInTheDocument();
    expect(screen.getByText('Where is my order?')).toBeInTheDocument();
    expect(api.listSolutionConversations).toHaveBeenLastCalledWith('orders');
    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'all' } });
    await waitFor(() => expect(api.listSolutionConversations).toHaveBeenLastCalledWith(null));
  });

  it('test chat tab passes the numbers, labels and keyword chips', async () => {
    renderAt('/solutions/orders?tab=test');
    expect(await screen.findByText('test chat')).toBeInTheDocument();
    await waitFor(() => expect(seen.chat.at(-1)?.chips).toEqual(['refund']));
    expect(seen.chat.at(-1)).toMatchObject({
      gateways: [{ name: 'gw1', label: 'Main', phone: '+1 555 0100' }],
      adChips: ['spring'],
      solutionLabels: expect.objectContaining({ care: 'Care', orders: 'Orders' }),
    });
  });

  it('shows not found', async () => {
    api.getSolutionOverview.mockRejectedValue(new SolutionsApiError('not_found', 'nope'));
    renderAt('/solutions/ghost');
    expect(await screen.findByText('Solution not found')).toBeInTheDocument();
  });

  it('shows not permitted', async () => {
    api.getSolutionOverview.mockRejectedValue(new SolutionsApiError('not_permitted', 'no'));
    renderAt('/solutions/orders');
    expect(await screen.findByText('You do not have access')).toBeInTheDocument();
  });

  it('shows a generic error and retries', async () => {
    api.getSolutionOverview.mockRejectedValueOnce(new SolutionsApiError('request_failed', 'Server hiccup'));
    renderAt('/solutions/orders');
    expect(await screen.findByText('Server hiccup')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText(/Working:/)).toBeInTheDocument();
  });
});
