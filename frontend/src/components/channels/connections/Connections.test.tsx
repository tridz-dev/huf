// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/layouts/PageFrame', () => ({ PageFrame: ({ children }: never) => <div>{children}</div> }));
vi.mock('@/contexts/PermissionsContext', () => ({ useIsHufAdmin: () => true }));
vi.mock('@/services/channels/channelsApi', () => ({ getEcosystem: vi.fn() }));
import { getEcosystem } from '@/services/channels/channelsApi';
import ConnectionsSection from '../sections/ConnectionsSection';

beforeEach(() => {
  vi.mocked(getEcosystem).mockResolvedValue({
    ok: true,
    data: {
      helpdesk: { installed: true, version: '1.2.0', enabled_for_whatsapp: true },
      crm: { installed: true, version: '1.0.0', enabled_for_whatsapp: false },
      erpnext: { installed: false, version: null, enabled_for_whatsapp: false },
      lms: { installed: false, version: null, enabled_for_whatsapp: false },
      ravan: { installed: false, version: null, enabled_for_whatsapp: false },
    },
  } as never);
});

describe('ConnectionsSection', () => {
  it('renders connected / installed / absent states', async () => {
    render(<MemoryRouter><ConnectionsSection /></MemoryRouter>);
    const hd = await screen.findByRole('region', { name: 'Help Desk' });
    expect(hd.getAttribute('data-state')).toBe('connected');
    expect(within(hd).getByText('Connected')).toBeTruthy();
    expect(within(hd).getByText(/v1\.2\.0/)).toBeTruthy();
    const crm = screen.getByRole('region', { name: 'CRM' });
    expect(within(crm).getByText('Installed — not connected')).toBeTruthy();
    const erp = screen.getByRole('region', { name: 'ERPNext' });
    expect(within(erp).getByText('Not installed')).toBeTruthy();
    expect(within(erp).getByRole('link', { name: 'Add to Huf' }).getAttribute('href')).toBe('/apps');
    expect(screen.getByText('P3')).toBeTruthy();
    expect(screen.getByRole('region', { name: 'Ravan' })).toBeTruthy();
  });

  it('test handoff explains instead of creating', async () => {
    render(<MemoryRouter><ConnectionsSection /></MemoryRouter>);
    const hd = await screen.findByRole('region', { name: 'Help Desk' });
    await userEvent.click(within(hd).getByRole('button', { name: 'Test handoff' }));
    await waitFor(() => expect(screen.getByText(/Nothing is created from this screen/)).toBeTruthy());
  });
});
