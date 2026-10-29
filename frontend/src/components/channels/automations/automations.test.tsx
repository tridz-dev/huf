// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

const api = vi.hoisted(() => ({
  getGateway: vi.fn(), updateGateway: vi.fn(), getRules: vi.fn(), saveRules: vi.fn(), getEco: vi.fn(),
  getNumberSummary: vi.fn(), listSolutions: vi.fn(), getAgents: vi.fn(),
}));
vi.mock('@/services/gatewayApi', async (orig) => ({ ...(await orig<object>()), getGateway: api.getGateway, updateGateway: api.updateGateway }));
vi.mock('@/services/channelsRulesApi', async (orig) => ({ ...(await orig<object>()), getRules: api.getRules, saveRules: api.saveRules, getEcosystemApps: api.getEco }));
vi.mock('@/services/solutionsApi', async (orig) => ({ ...(await orig<object>()), getNumberSummary: api.getNumberSummary, listSolutions: api.listSolutions }));
vi.mock('@/services/agentApi', async (orig) => ({ ...(await orig<object>()), getAgents: api.getAgents }));
vi.mock('@/layouts/PageFrame', () => ({ PageFrame: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/whatsapp/overview/SolutionsOnNumberCard', () => ({ SolutionsOnNumberCard: () => <div>solutions-card</div> }));
vi.mock('@/components/whatsapp/overview/RoutingOrderCard', () => ({ RoutingOrderCard: () => <div>routing-order-card</div> }));

import AutomationsSection from '../sections/AutomationsSection';
import { move, renumber } from './rulesModel';

const Loc = () => <output data-testid="loc">{useLocation().pathname}</output>;
const open = (tab = '') =>
  render(
    <MemoryRouter initialEntries={[`/channels/whatsapp/n/GW-1/automations${tab}`]}>
      <Routes><Route path="/channels/whatsapp/n/:gw/automations/:tab?" element={<AutomationsSection />} /></Routes>
      <Loc />
    </MemoryRouter>,
  );

const rule = (o = {}) => ({ rule_type: 'keyword', match_value: 'a', attribute: '', target_type: 'human', target: '', priority: 1, enabled: 1, ...o });

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.getGateway.mockResolvedValue({ name: 'GW-1', business_hours: [], handoff_target: 'none', handoff_message: 'hi' });
  api.updateGateway.mockResolvedValue({});
  api.getRules.mockResolvedValue([rule({ match_value: 'first', priority: 1 }), rule({ match_value: 'second', priority: 2 })]);
  api.saveRules.mockImplementation(async (_g: string, r: unknown[]) => r);
  api.getEco.mockResolvedValue({ helpdesk: false, crm: true });
  api.getNumberSummary.mockResolvedValue({ solutions: [], routing_order: [] });
  api.listSolutions.mockResolvedValue([]);
  api.getAgents.mockResolvedValue([]);
});

describe('Automations', () => {
  it('defaults to agents tab and routes tabs in-path', async () => {
    open();
    expect(await screen.findByText('solutions-card')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('link', { name: 'Routing rules' }));
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/channels/whatsapp/n/GW-1/automations/rules'));
  });
  it.each([['/hours', /Add hours/], ['/run-as', /Never Administrator/]])('renders reused panel %s', async (p, t) => {
    open(p);
    expect((await screen.findAllByText(t)).length).toBeGreaterThan(0);
  });
  it('reorders and saves rules with renumbered priority', async () => {
    open('/rules');
    await screen.findByLabelText('Rule 1 match');
    fireEvent.click(screen.getByLabelText('Move rule 1 down'));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.saveRules).toHaveBeenCalled());
    const [gw, rules] = api.saveRules.mock.calls[0];
    expect(gw).toBe('GW-1');
    expect(rules.map((r: { match_value: string; priority: number }) => [r.match_value, r.priority])).toEqual([['second', 1], ['first', 2]]);
  });
  it('adds a rule and blocks save until a target is chosen', async () => {
    open('/rules');
    await screen.findByLabelText('Rule 1 match');
    fireEvent.click(screen.getByRole('button', { name: /Add rule/ }));
    expect(screen.getByLabelText('Rule 3 match')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Rule 3');
    expect(api.saveRules).not.toHaveBeenCalled();
  });
  it('move/renumber helpers', () => {
    const r = [rule({ match_value: 'x' }), rule({ match_value: 'y' })] as never[];
    expect(move(r, 0, -1)).toBe(r);
    expect(renumber(move(r, 0, 1)).map((x: { priority: number }) => x.priority)).toEqual([1, 2]);
  });
  it('saves handoff and disables uninstalled apps', async () => {
    open('/handoff');
    const trigger = await screen.findByLabelText('Handoff target');
    fireEvent.change(await screen.findByDisplayValue('hi'), { target: { value: 'bye' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.updateGateway).toHaveBeenCalledWith('GW-1', { handoff_target: 'none', handoff_message: 'bye' }));
    expect(trigger).toBeInTheDocument();
  });
});
