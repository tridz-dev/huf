// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { gatewayFixture } from '@/components/whatsapp/overview/fixtures';

vi.mock('@/services/whatsappHealthApi', async (orig) => ({
  ...(await orig<typeof import('@/services/whatsappHealthApi')>()),
  getSetupStatus: vi.fn(),
  checkToken: vi.fn(),
}));
vi.mock('@/services/channelsApi', () => ({ listConversations: vi.fn() }));
import { getSetupStatus } from '@/services/whatsappHealthApi';
import { listConversations } from '@/services/channelsApi';
import { HomeDashboard } from './HomeDashboard';

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getSetupStatus).mockResolvedValue({
    ok: true,
    data: { success: true, connector_available: true, gateway: gatewayFixture({ reasons: [{ code: 'recent_error', severity: 'warning', message: 'Boom happened' }] }) },
  } as never);
  vi.mocked(listConversations).mockImplementation(async (_g, o) => ({
    ok: true,
    data: { items: Array(o?.status === 'ai' ? 2 : o?.status === 'handed_off' ? 1 : 5).fill({}), has_more: false },
  }) as never);
});

describe('HomeDashboard', () => {
  it('shows counters, needs-attention, actions and connection placeholders', async () => {
    render(<MemoryRouter><HomeDashboard gateway="GW-1" /></MemoryRouter>);
    await waitFor(() => expect(screen.getByTestId('counter-Conversations').textContent).toBe('5'));
    expect(screen.getByTestId('counter-AI-resolved').textContent).toBe('2');
    expect(screen.getByTestId('counter-Handed off').textContent).toBe('1');
    expect(screen.getByTestId('counter-Template sends').textContent).toBe('—');
    expect(await screen.findByText('Boom happened')).toBeTruthy();
    expect(screen.getByText('New broadcast')).toBeTruthy();
    expect(screen.getAllByText('Set up in Connections')).toHaveLength(3);
  });

  it('falls back to a dash when conversations are unavailable', async () => {
    vi.mocked(listConversations).mockResolvedValue({ ok: false, error: 'nope' } as never);
    render(<MemoryRouter><HomeDashboard gateway="GW-1" /></MemoryRouter>);
    await waitFor(() => expect(screen.getByTestId('counter-Handed off').textContent).toBe('—'));
  });
});
