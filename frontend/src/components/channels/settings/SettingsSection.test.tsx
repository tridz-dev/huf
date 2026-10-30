// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { gatewayFixture } from '@/components/whatsapp/overview/fixtures';

const api = vi.hoisted(() => ({
  getSetupStatus: vi.fn(), checkToken: vi.fn(), getGateway: vi.fn(), updateGateway: vi.fn(),
}));
vi.mock('@/services/whatsappHealthApi', async (orig) => ({ ...(await orig<object>()), getSetupStatus: api.getSetupStatus, checkToken: api.checkToken }));
vi.mock('@/services/gatewayApi', async (orig) => ({ ...(await orig<object>()), getGateway: api.getGateway, updateGateway: api.updateGateway }));
vi.mock('@/layouts/PageFrame', () => ({ PageFrame: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/whatsapp/AccessTab', () => ({ AccessTab: ({ gateway }: { gateway: string }) => <div>access-tab {gateway}</div> }));

import SettingsSection from '../sections/SettingsSection';
import { validateRunAs } from './model';

const Loc = () => <output data-testid="loc">{useLocation().pathname}</output>;
const open = (section = '') =>
  render(
    <MemoryRouter initialEntries={[`/channels/whatsapp/n/GW-1/settings${section}`]}>
      <Routes><Route path="/channels/whatsapp/n/:gw/settings/:section?" element={<SettingsSection />} /></Routes>
      <Loc />
    </MemoryRouter>,
  );

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.getSetupStatus.mockResolvedValue({ ok: true, data: { success: true, connector_available: true, accounts: [], gateway: gatewayFixture() } });
  api.getGateway.mockResolvedValue({ name: 'GW-1', is_enabled: 1, business_hours: [] });
  api.updateGateway.mockResolvedValue({});
});

describe('Settings sections', () => {
  it('defaults to connection', async () => {
    open();
    expect(await screen.findByText('Gateway')).toBeInTheDocument();
  });
  it.each([
    ['/credentials', /Credentials|Access token/i],
    ['/policy', /Outside the 24-hour window|Replies after 24 hours/],
    ['/access', /access-tab GW-1/],
    ['/run-as', /Never Administrator/],
    ['/hours', /Add hours/],
    ['/danger', /Disable gateway/],
  ])('renders %s', async (path, text) => {
    open(path);
    expect((await screen.findAllByText(text)).length).toBeGreaterThan(0);
  });
  it('renders replies', async () => {
    open('/replies');
    expect(await screen.findByRole('button', { name: 'Save' })).toBeInTheDocument();
  });
  it('navigates in-shell via the sub-nav', async () => {
    open();
    await screen.findByText('Gateway');
    fireEvent.click(screen.getByRole('link', { name: 'Business hours' }));
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/channels/whatsapp/n/GW-1/settings/hours'));
  });
  it('run-as rejects Administrator client-side', async () => {
    open('/run-as');
    fireEvent.change(await screen.findByLabelText('Run as user'), { target: { value: 'Administrator' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText(/cannot be used/)).toBeInTheDocument();
    expect(api.updateGateway).not.toHaveBeenCalled();
  });
  it('run-as saves a normal user', async () => {
    open('/run-as');
    fireEvent.change(await screen.findByLabelText('Run as user'), { target: { value: 'bot@x.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.updateGateway).toHaveBeenCalledWith('GW-1', expect.objectContaining({ run_as_user: 'bot@x.com' })));
  });
  it('danger confirms before disabling', async () => {
    open('/danger');
    fireEvent.click(await screen.findByRole('button', { name: 'Disable gateway' }));
    expect(api.updateGateway).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole('button', { name: 'Disable' }));
    await waitFor(() => expect(api.updateGateway).toHaveBeenCalledWith('GW-1', { is_enabled: 0 }));
  });
  it('hours saves holiday rows and the optional ERPNext list name', async () => {
    open('/hours');
    fireEvent.click(await screen.findByRole('button', { name: 'Add holiday' }));
    fireEvent.change(screen.getByLabelText('Holiday date 1'), { target: { value: '2026-11-02' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add holiday' }));
    fireEvent.change(screen.getByLabelText('Holiday date 2'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.updateGateway).toHaveBeenCalledWith('GW-1', expect.objectContaining({
      holidays: [{ holiday_date: '2026-11-02', description: '' }], holiday_list: '',
    })));
  });
  it('validateRunAs', () => {
    expect(validateRunAs(' guest ')).not.toBeNull();
    expect(validateRunAs('a@b.c')).toBeNull();
  });
});
