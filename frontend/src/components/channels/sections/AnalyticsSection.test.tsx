// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('@/layouts/PageFrame', () => ({ PageFrame: ({ children, actions }: never) => <div>{actions}{children}</div> }));
vi.mock('../useChannelGateway', () => ({ useChannelGateway: () => 'GW-1' }));
vi.mock('@/services/channels/analyticsApi', () => ({ getAnalytics: vi.fn(), getRateCard: vi.fn(), saveRateCard: vi.fn() }));
vi.mock('@/components/ui/chart', () => ({
  ChartContainer: ({ children }: never) => <div>{children}</div>,
  ChartTooltip: () => null,
  ChartTooltipContent: () => null,
}));
vi.mock('recharts', () => ({ Bar: () => null, BarChart: () => null, CartesianGrid: () => null, XAxis: () => null, YAxis: () => null }));
import { getAnalytics, getRateCard } from '@/services/channels/analyticsApi';
import AnalyticsSection from './AnalyticsSection';

const data = (amount: number | null) => ({
  volume_by_day: [{ date: '2026-10-28', conversations: 3, inbound: 5, outbound: 4 }],
  ai_resolution_rate: 0.75,
  handoff_rate: 0.25,
  median_first_response_seconds: 42,
  broadcast_funnel: { sent: 10, delivered: 8, read: 5, failed: 2 },
  template_quality: [{ name: 'welcome', quality: 'GREEN', category: 'UTILITY' }],
  estimated_spend: { currency: 'USD', amount, is_estimate: true, basis: 'x', missing_rates: amount == null },
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getRateCard).mockResolvedValue({ ok: true, data: { currency: '', rows: [] } });
});

describe('AnalyticsSection', () => {
  it('renders KPIs, quality table and estimate label', async () => {
    vi.mocked(getAnalytics).mockResolvedValue({ ok: true, data: data(null) } as never);
    render(<AnalyticsSection />);
    expect(await screen.findByText('75%')).toBeTruthy();
    expect(screen.getByText('42s')).toBeTruthy();
    expect(screen.getByText('welcome')).toBeTruthy();
    expect(screen.getByText(/Estimate — you pay Meta directly/)).toBeTruthy();
    expect(screen.getByText(/rates are missing/)).toBeTruthy();
  });

  it('changes range and opens rate card editor', async () => {
    vi.mocked(getAnalytics).mockResolvedValue({ ok: true, data: data(12.5) } as never);
    render(<AnalyticsSection />);
    await screen.findByText('USD 12.50');
    await userEvent.click(screen.getByRole('button', { name: '7d' }));
    await waitFor(() => expect(getAnalytics).toHaveBeenCalledTimes(2));
    await userEvent.click(screen.getByRole('button', { name: 'Edit rate card' }));
    expect(await screen.findByLabelText('Rate card editor')).toBeTruthy();
  });
});
