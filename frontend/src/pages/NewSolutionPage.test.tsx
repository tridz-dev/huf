// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

const api = vi.hoisted(() => ({
  createSolution: vi.fn(),
  goLive: vi.fn(),
  getIntents: vi.fn(),
  getNumberSummary: vi.fn(),
  getGateways: vi.fn(),
  getAgents: vi.fn(),
  getFlowDefinitions: vi.fn(),
  listTemplates: vi.fn(),
  chat: vi.fn(),
  toast: vi.fn(),
}));

vi.mock('@/services/solutionsApi', async () => {
  const actual = await vi.importActual<typeof import('@/services/solutionsApi')>('@/services/solutionsApi');
  return { ...actual, createSolution: api.createSolution, goLive: api.goLive, getIntents: api.getIntents, getNumberSummary: api.getNumberSummary };
});
vi.mock('@/services/gatewayApi', () => ({ getGateways: api.getGateways }));
vi.mock('@/services/agentApi', () => ({ getAgents: api.getAgents }));
vi.mock('@/services/flowApi', () => ({ getFlowDefinitions: api.getFlowDefinitions }));
vi.mock('@/services/whatsappApi', () => ({
  listTemplates: api.listTemplates,
  errorText: (r: { message?: string }) => r.message ?? 'error',
}));
vi.mock('sonner', () => ({ toast: { success: api.toast, error: api.toast } }));
vi.mock('@/layouts/PageFrame', () => ({ PageFrame: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/solutions/TestChat', () => ({
  TestChat: (props: unknown) => {
    api.chat(props);
    return <div>test chat</div>;
  },
}));

import NewSolutionPage from './NewSolutionPage';
import { SolutionsApiError } from '@/services/solutionsApi';

const intents = [
  { id: 'orders', name: 'Take orders', desc: 'Orders desc', icon: 'shopping-bag', sample_name: 'Order desk', entry: 'keywords', keywords: ['order', 'menu'], ref: 'weekend', suggested_templates: ['order_ready'], policy: ['Daily cap: 400'] },
  { id: 'updates', name: 'Send updates', desc: 'Outbound only', icon: 'bell', sample_name: 'Order updates', entry: 'none', keywords: [], ref: '', suggested_templates: ['order_ready'], policy: ['Templates only'] },
  { id: 'answer', name: 'Answer questions', desc: 'FAQ', icon: 'circle-help', sample_name: 'Shop FAQ', entry: 'catchall', keywords: [], ref: '', suggested_templates: [], policy: [] },
];
const gw = (name: string) => ({ name, gateway_name: name, provider: 'WhatsApp', is_enabled: 1 });
const tpl = (n: string, extra = {}) => ({ name: n, template_name: n, status: 'APPROVED', template: `${n} body`, used_by: [], shared: false, ...extra });

function Where() {
  const l = useLocation();
  return <div data-testid="where">{l.pathname}</div>;
}
function renderAt(url = '/solutions/new') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/solutions/new" element={<NewSolutionPage />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}
const name = () => screen.getByLabelText('Name') as HTMLInputElement;
const next = () => fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
const lastChat = () => api.chat.mock.calls[api.chat.mock.calls.length - 1][0];

beforeEach(() => {
  Object.values(api).forEach((m) => m.mockReset());
  api.getIntents.mockResolvedValue(intents);
  api.getGateways.mockResolvedValue([gw('gw1'), gw('gw2'), { ...gw('tg'), provider: 'Telegram' }]);
  api.getNumberSummary.mockImplementation(async (g: string) => ({
    gateway: g, label: g === 'gw1' ? 'Main counter' : 'Catering line', phone: '+1 555',
    solutions: g === 'gw1' ? [{ name: 'a', title: 'Bakery', status: 'Live', usage_pct: 1, sends_24h: 1 }] : [],
    routing_order: [], quality: { rating: g === 'gw1' ? 'High' : null, source: 'meta' }, blame: null,
  }));
  api.getAgents.mockResolvedValue([{ name: 'ag1', agent_name: 'Care agent' }]);
  api.getFlowDefinitions.mockResolvedValue([{ name: 'fl1', flow_name: 'Quote flow' }]);
  api.listTemplates.mockResolvedValue({ success: true, templates: [tpl('welcome'), tpl('order_ready', { shared: true, used_by: [{ solution: 's1', title: 'Bakery' }] }), tpl('pending_one', { status: 'PENDING' })] });
  api.createSolution.mockResolvedValue({ name: 'sol-1', title: 'Order desk' });
  api.goLive.mockResolvedValue({ name: 'sol-1' });
});
afterEach(cleanup);

async function ready() {
  renderAt();
  await screen.findByText('Take orders');
  await screen.findByText(/Already used by Bakery/);
}

describe('NewSolutionPage', () => {
  it('step 1 renders purposes, modes and gateways with usage and quality', async () => {
    await ready();
    expect(screen.getByText('Use an agent or flow I already have')).toBeInTheDocument();
    expect(screen.getByText('No purpose, start blank')).toBeInTheDocument();
    expect(screen.getByText('Main counter')).toBeInTheDocument();
    expect(screen.getByText('High quality')).toBeInTheDocument();
    expect(screen.getByText('Nobody uses it yet.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
  });

  it('purpose prefills name until edited, keywords and templates', async () => {
    await ready();
    fireEvent.click(screen.getByText('Take orders'));
    expect(name().value).toBe('Order desk');
    fireEvent.change(name(), { target: { value: 'My shop' } });
    fireEvent.click(screen.getByText('Send updates'));
    expect(name().value).toBe('My shop');
    fireEvent.click(screen.getByText('Take orders'));
    next();
    expect(screen.getAllByText('order').length).toBeGreaterThan(0);
    expect(screen.getAllByText('menu').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('Ad or link tag')).toHaveValue('weekend');
    expect(screen.getByTestId('customer-preview')).toHaveTextContent('Reply with a word like order to reach My shop.');
    next();
    await screen.findByText('Suggested');
    expect(screen.queryByText('pending_one')).toBeNull();
    const names = screen.getAllByText(/^(welcome|order_ready)$/).map((e) => e.textContent);
    expect(names[0]).toBe('order_ready');
    expect(screen.getByText('Shared')).toBeInTheDocument();
    expect(screen.getByText('We suggest these settings for Take orders')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review on Main counter' })).toHaveAttribute('href', '/whatsapp?gateway=gw1&tab=settings');
  });

  it('keywords can be added and removed; draft template shows Draft', async () => {
    await ready();
    fireEvent.click(screen.getByText('Take orders'));
    next();
    fireEvent.change(screen.getByLabelText('Keywords (message contains)'), { target: { value: 'Pizza' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(screen.getByText('pizza')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Remove order' }));
    expect(screen.queryByText('order')).toBeNull();
    next();
    await screen.findByText('welcome');
    fireEvent.click(screen.getByText(/Draft a new template/));
    expect(screen.getByText('Draft')).toBeInTheDocument();
  });

  it('none-inbound purpose: note, then add entry points anyway', async () => {
    await ready();
    fireEvent.click(screen.getByText('Send updates'));
    next();
    expect(screen.getByTestId('none-inbound-note')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Add entry points anyway' }));
    expect(screen.getByLabelText('Keywords (message contains)')).toBeInTheDocument();
  });

  it('existing mode builds payload mode=existing', async () => {
    await ready();
    fireEvent.click(screen.getByText('Use an agent or flow I already have'));
    fireEvent.change(screen.getByLabelText('Answered by'), { target: { value: 'Flow:fl1' } });
    fireEvent.change(name(), { target: { value: 'Quotes' } });
    next(); next(); next();
    fireEvent.click(screen.getByRole('button', { name: 'Go live' }));
    await waitFor(() => expect(api.createSolution).toHaveBeenCalled());
    expect(api.createSolution.mock.calls[0][0]).toEqual({
      title: 'Quotes', mode: 'existing', existing_target: { type: 'Flow', name: 'fl1' },
      gateway: 'gw1', entries: [{ match_type: 'Catch-all', match_values: [] }], inbound: true, templates: [], test_mode: false,
    });
  });

  it('blank mode payload has no purpose', async () => {
    await ready();
    fireEvent.click(screen.getByText('No purpose, start blank'));
    fireEvent.change(name(), { target: { value: 'Plain' } });
    next(); next(); next();
    fireEvent.click(screen.getByRole('button', { name: 'Go live' }));
    await waitFor(() => expect(api.createSolution).toHaveBeenCalled());
    const p = api.createSolution.mock.calls[0][0];
    expect(p.mode).toBe('blank');
    expect(p).not.toHaveProperty('purpose');
    expect(p).not.toHaveProperty('existing_target');
  });

  it('query params preselect purpose and gateway', async () => {
    renderAt('/solutions/new?purpose=orders&gateway=gw2');
    await screen.findByText('Take orders');
    await waitFor(() => expect(name().value).toBe('Order desk'));
    expect(screen.getByTestId('gateway-gw2')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled();
  });

  it('query mode=existing preselects the existing mode', async () => {
    renderAt('/solutions/new?mode=existing');
    expect(await screen.findByLabelText('Answered by')).toBeInTheDocument();
  });

  it('full payload for an intent, with draft template; test step passes draft to TestChat', async () => {
    await ready();
    fireEvent.click(screen.getByText('Take orders'));
    next(); next();
    await screen.findByText('Suggested');
    fireEvent.click(screen.getByText('welcome'));
    fireEvent.click(screen.getByText(/Draft a new template/));
    next();
    await screen.findByText('test chat');
    expect(lastChat().draft).toEqual({
      title: 'Order desk', gateway: 'gw1', intent: 'orders', inbound: true, catch_all: false,
      entries: [{ match_type: 'Keyword', match_values: ['order', 'menu'] }, { match_type: 'Ad or link tag', match_values: ['weekend'] }],
    });
    expect(api.createSolution).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Go live' }));
    await waitFor(() => expect(api.createSolution).toHaveBeenCalledTimes(1));
    expect(api.createSolution.mock.calls[0][0]).toEqual({
      title: 'Order desk', purpose: 'orders', mode: 'intent', gateway: 'gw1',
      entries: [{ match_type: 'Keyword', match_values: ['order', 'menu'] }, { match_type: 'Ad or link tag', match_values: ['weekend'] }],
      inbound: true, templates: ['order_ready', 'welcome'],
      draft_template: { name: 'order_desk_quote', language: 'en', category: 'UTILITY', status: 'Draft' },
      test_mode: false,
    });
  });

  it('go live calls create, then go_live, then navigates with a toast', async () => {
    await ready();
    fireEvent.click(screen.getByText('Take orders'));
    next(); next(); next();
    fireEvent.click(screen.getByRole('button', { name: 'Go live' }));
    await screen.findByTestId('where');
    expect(screen.getByTestId('where')).toHaveTextContent('/solutions/sol-1');
    expect(api.goLive).toHaveBeenCalledWith('sol-1');
    expect(api.createSolution.mock.invocationCallOrder[0]).toBeLessThan(api.goLive.mock.invocationCallOrder[0]);
    expect(api.toast).toHaveBeenCalled();
  });

  it('test mode skips go_live', async () => {
    await ready();
    fireEvent.click(screen.getByText('Take orders'));
    next(); next(); next();
    fireEvent.click(screen.getByLabelText(/Keep it in test mode after saving/));
    fireEvent.click(screen.getByRole('button', { name: 'Go live' }));
    await screen.findByTestId('where');
    expect(api.createSolution.mock.calls[0][0].test_mode).toBe(true);
    expect(api.goLive).not.toHaveBeenCalled();
  });

  it('shows API errors and stays on the page', async () => {
    api.createSolution.mockRejectedValue(new SolutionsApiError('not_permitted', 'nope'));
    await ready();
    fireEvent.click(screen.getByText('Take orders'));
    next(); next(); next();
    fireEvent.click(screen.getByRole('button', { name: 'Go live' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/permission/);
    expect(api.goLive).not.toHaveBeenCalled();
    expect(screen.queryByTestId('where')).toBeNull();
  });

  it('shows invalid_payload and shared_template messages', async () => {
    api.createSolution.mockRejectedValue(new SolutionsApiError('invalid_payload', 'title is required'));
    await ready();
    fireEvent.click(screen.getByText('Take orders'));
    next(); next(); next();
    fireEvent.click(screen.getByRole('button', { name: 'Go live' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('title is required');
  });

  it('Back returns to the previous step', async () => {
    await ready();
    fireEvent.click(screen.getByText('Take orders'));
    next();
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.getByLabelText('Name')).toBeInTheDocument();
  });
});
