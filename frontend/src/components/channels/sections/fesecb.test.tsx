// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

vi.mock('@/layouts/PageFrame', () => ({ PageFrame: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/whatsapp/TemplatesTab', () => ({
  TemplatesTab: (p: { gateway?: string; selectedName?: string; onSelect?: (n: string) => void }) => (
    <div><p>gw {p.gateway} sel {p.selectedName}</p><button onClick={() => p.onSelect?.('order_update')}>pick</button></div>
  ),
}));
vi.mock('@/components/whatsapp/broadcast/BroadcastList', () => ({
  BroadcastList: (p: { onNew: () => void; onOpen: (n: string) => void }) => (
    <div><button onClick={p.onNew}>new</button><button onClick={() => p.onOpen('BC-1')}>open</button></div>
  ),
}));
vi.mock('@/components/whatsapp/broadcast/BroadcastWizard', () => ({
  BroadcastWizard: (p: { onClose: () => void; onStarted: (n: string) => void }) => (
    <div>wizard<button onClick={p.onClose}>close</button><button onClick={() => p.onStarted('BC-2')}>start</button></div>
  ),
}));
vi.mock('@/components/whatsapp/broadcast/BroadcastDetail', () => ({
  BroadcastDetail: (p: { name: string; onBack: () => void }) => <div>detail {p.name}<button onClick={p.onBack}>back</button></div>,
}));
vi.mock('@/components/whatsapp/broadcast/BroadcastTab', () => ({ EmergencyStop: () => <div>emergency</div> }));

import TemplatesSection from './TemplatesSection';
import BroadcastsSection from './BroadcastsSection';

const Loc = () => <p data-testid="loc">{useLocation().pathname}</p>;
const app = (path: string) => (
  <MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/n/:gw">
        <Route path="templates/:name?" element={<TemplatesSection />} />
        <Route path="broadcasts/*" element={<BroadcastsSection />} />
      </Route>
    </Routes>
    <Loc />
  </MemoryRouter>
);

describe('Templates route', () => {
  it('param selects the template and selecting navigates', async () => {
    render(app('/n/g1/templates/foo'));
    expect(screen.getByText('gw g1 sel foo')).toBeTruthy();
    await userEvent.click(screen.getByText('pick'));
    expect(screen.getByTestId('loc').textContent).toBe('/n/g1/templates/order_update');
  });
});

describe('Broadcast sub-routes', () => {
  it('list -> new -> detail -> back', async () => {
    render(app('/n/g1/broadcasts'));
    expect(screen.getByText('emergency')).toBeTruthy();
    await userEvent.click(screen.getByText('new'));
    expect(screen.getByTestId('loc').textContent).toBe('/n/g1/broadcasts/new');
    await userEvent.click(screen.getByText('start'));
    expect(screen.getByTestId('loc').textContent).toBe('/n/g1/broadcasts/BC-2');
    expect(screen.getByText('detail BC-2')).toBeTruthy();
    await userEvent.click(screen.getByText('back'));
    expect(screen.getByTestId('loc').textContent).toBe('/n/g1/broadcasts');
  });
  it('opens detail from list', async () => {
    render(app('/n/g1/broadcasts'));
    await userEvent.click(screen.getByText('open'));
    expect(screen.getByTestId('loc').textContent).toBe('/n/g1/broadcasts/BC-1');
  });
});
