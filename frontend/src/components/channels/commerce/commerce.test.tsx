// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('@/layouts/PageFrame', () => ({ PageFrame: ({ children }: never) => <div>{children}</div> }));
vi.mock('@/contexts/PermissionsContext', () => ({ useIsHufAdmin: () => true }));
vi.mock('@/lib/clipboard', () => ({ copyText: vi.fn().mockResolvedValue(true) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/gatewayApi', () => ({
  getGateway: vi.fn().mockResolvedValue({ catalog_id: 'CAT1', payment_provider: 'razorpay', cart_recovery_hours: 2 }),
  updateGateway: vi.fn().mockResolvedValue({}),
}));
vi.mock('@/services/channels/channelsApi', () => ({ getEcosystem: vi.fn() }));
vi.mock('@/services/channels/commerceApi', () => ({
  syncCatalogNow: vi.fn(), listOrders: vi.fn(), getOrder: vi.fn(), createPaymentLink: vi.fn(), submitTemplatesPack: vi.fn(),
  listWaFlows: vi.fn(), listFlowResponses: vi.fn(), listConversationOrders: vi.fn(),
}));
import { getEcosystem } from '@/services/channels/channelsApi';
import * as api from '@/services/channels/commerceApi';
import CommerceSection from '../sections/CommerceSection';
import { OrderCard } from './OrderCard';
import { methodUrl } from '@/lib/api';
import { copyText } from '@/lib/clipboard';

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/channels/:channel/n/:gw/commerce/:tab?" element={<CommerceSection />} /></Routes>
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getEcosystem).mockResolvedValue({ ok: true, data: { erpnext: { installed: true, version: '15', enabled_for_whatsapp: true } } } as never);
  vi.mocked(api.listOrders).mockResolvedValue({ ok: true, data: [{ name: 'WO-1', contact_handle: '155', total: 50, currency: 'INR', status: 'Draft', payment_status: 'Unpaid', creation: '2026-10-29 10:00:00' }] });
  vi.mocked(api.listFlowResponses).mockResolvedValue({ ok: true, data: [] });
});

describe('Commerce', () => {
  it('routes tabs and falls back to catalog', async () => {
    renderAt('/channels/whatsapp/n/GW/commerce/payments');
    expect(await screen.findByLabelText('Payment provider')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Payments' }).getAttribute('aria-current')).toBe('page');
  });

  it('unknown tab shows catalog', async () => {
    renderAt('/channels/whatsapp/n/GW/commerce/zzz');
    expect(await screen.findByLabelText('Catalog ID')).toBeTruthy();
  });

  it('sync button shows result counts', async () => {
    vi.mocked(api.syncCatalogNow).mockResolvedValue({ ok: true, data: { success: true, items: 10, synced: 9, failed: 1, skipped: 2, errors: ['bad'] } });
    renderAt('/channels/whatsapp/n/GW/commerce/catalog');
    await userEvent.click(await screen.findByRole('button', { name: /Sync from ERPNext now/ }));
    const r = await screen.findByRole('status', { name: 'Sync result' });
    expect(r.textContent).toContain('10');
    expect(r.textContent).toContain('bad');
    expect(api.syncCatalogNow).toHaveBeenCalledWith('GW');
  });

  it('shows add-on card when ERPNext is absent', async () => {
    vi.mocked(getEcosystem).mockResolvedValue({ ok: true, data: { erpnext: { installed: false, version: null, enabled_for_whatsapp: false } } } as never);
    renderAt('/channels/whatsapp/n/GW/commerce/catalog');
    expect(await screen.findByRole('link', { name: 'Add to Huf' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Sync from ERPNext/ })).toBeNull();
  });

  it('order drawer creates and copies the payment link', async () => {
    vi.mocked(api.getOrder).mockResolvedValue({ ok: true, data: { name: 'WO-1', total: 50, currency: 'INR', status: 'Draft', items: [{ item_name: 'Tea', qty: 2, price: 25, currency: 'INR' }] } });
    vi.mocked(api.createPaymentLink).mockResolvedValue({ ok: true, data: { success: true, url: 'https://rzp.io/x' } });
    renderAt('/channels/whatsapp/n/GW/commerce/orders');
    await userEvent.click(await screen.findByRole('button', { name: 'Open order WO-1' }));
    expect(await screen.findByText(/Tea × 2/)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Create payment link' }));
    expect(api.createPaymentLink).toHaveBeenCalledWith('WO-1');
    await userEvent.click(await screen.findByRole('button', { name: /Copy link/ }));
    await waitFor(() => expect(copyText).toHaveBeenCalledWith('https://rzp.io/x'));
  });

  it('renders webhook URLs without secrets', async () => {
    renderAt('/channels/whatsapp/n/GW%201/commerce/payments');
    const rz = (await screen.findByLabelText('Razorpay webhook URL')) as HTMLInputElement;
    expect(rz.value).toBe(`${window.location.origin}${methodUrl('huf.ai.channels.commerce.payments.razorpay_webhook')}?gateway=GW%201`);
    expect((screen.getByLabelText('Stripe webhook URL') as HTMLInputElement).value).toContain('stripe_webhook?gateway=GW%201');
  });

  it('automations submit pack lists results', async () => {
    vi.mocked(api.submitTemplatesPack).mockResolvedValue({ ok: true, data: { success: true, results: { order_confirmed: { success: true }, cart_reminder: { success: false, error: 'dup' } } } });
    renderAt('/channels/whatsapp/n/GW/commerce/automations');
    await userEvent.click(await screen.findByRole('button', { name: 'Submit utility templates pack' }));
    expect(await screen.findByText('order_confirmed')).toBeTruthy();
    expect(screen.getByText('dup')).toBeTruthy();
  });

  it('flows table lists flows and refresh re-fetches', async () => {
    vi.mocked(api.listWaFlows).mockResolvedValue({ ok: true, data: [{ name: 'F1', flow_id: '9', flow_name: 'Survey', status: 'PUBLISHED' }] });
    renderAt('/channels/whatsapp/n/GW/commerce/flows');
    expect(await screen.findByText('Survey')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(api.listWaFlows).toHaveBeenLastCalledWith('GW', 1));
  });

  it('order card renders for a conversation with orders and not otherwise', async () => {
    vi.mocked(api.listConversationOrders).mockResolvedValueOnce({ ok: true, data: [{ name: 'WO-1', total: 50, currency: 'INR', status: 'Paid' }] });
    const { container, rerender } = render(<MemoryRouter><OrderCard conversation="C1" /></MemoryRouter>);
    expect(await screen.findByText('WO-1')).toBeTruthy();
    vi.mocked(api.listConversationOrders).mockResolvedValueOnce({ ok: true, data: [] });
    rerender(<MemoryRouter><OrderCard conversation="C2" /></MemoryRouter>);
    await waitFor(() => expect(container.querySelector('[data-order-card]')).toBeNull());
  });
});
