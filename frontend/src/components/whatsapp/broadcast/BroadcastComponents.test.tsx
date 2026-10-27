// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { act, render, screen, waitFor } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/whatsappApi', async (orig) => ({
  ...(await orig<typeof import('@/services/whatsappApi')>()),
  listTemplates: vi.fn(), createBroadcast: vi.fn(), addBroadcastRecipients: vi.fn(), attestBroadcastConsent: vi.fn(),
  previewBroadcast: vi.fn(), startBroadcast: vi.fn(), pauseBroadcast: vi.fn(), resumeBroadcast: vi.fn(), cancelBroadcast: vi.fn(),
  pauseAllBroadcasts: vi.fn(), listBroadcasts: vi.fn(), getBroadcast: vi.fn(), listBroadcastRecipients: vi.fn(),
}));
import * as api from '@/services/whatsappApi';
import { BroadcastTab } from './BroadcastTab';
import { BroadcastList } from './BroadcastList';
import { BroadcastWizard } from './BroadcastWizard';
import { BroadcastDetail } from './BroadcastDetail';

const m = vi.mocked(api, true);
const bc = (o: object = {}) => ({
  name: 'BCAST-1', title: 'Promo', status: 'Running', gateway: 'G', total: 10, queued: 4, sending: 0, sent: 3, delivered: 2, read: 0,
  failed: 1, deferred: 0, unknown: 0, skipped: 0, template_name: 'promo', ...o,
});
const ok = <T,>(v: T) => ({ success: true, ...v }) as never;

beforeEach(() => {
  vi.clearAllMocks();
  m.listBroadcasts.mockResolvedValue(ok({ broadcasts: [bc()] }));
  m.getBroadcast.mockResolvedValue(ok({ broadcast: bc() }));
  m.listBroadcastRecipients.mockResolvedValue(ok({ recipients: [{ name: 'r1', recipient: '15550001', status: 'failed', error_code: 131026, error_message: 'undeliverable' }] }));
});

describe('BroadcastList', () => {
  it('lists broadcasts and opens one', async () => {
    const onOpen = vi.fn();
    render(<BroadcastList gateway="G" onOpen={onOpen} onNew={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Open broadcast Promo' }));
    expect(onOpen).toHaveBeenCalledWith('BCAST-1');
  });
  it('shows empty state', async () => {
    m.listBroadcasts.mockResolvedValue(ok({ broadcasts: [] }));
    render(<BroadcastList gateway="G" onOpen={vi.fn()} onNew={vi.fn()} />);
    expect(await screen.findByText(/No broadcasts yet/)).toBeInTheDocument();
  });
});

describe('BroadcastDetail', () => {
  it('shows counts, error codes and pauses', async () => {
    m.pauseBroadcast.mockResolvedValue(ok({}));
    render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
    expect(await screen.findByText('131026')).toBeInTheDocument();
    expect(screen.getByTestId('count-sent')).toHaveTextContent('3');
    expect(screen.getByRole('progressbar', { name: 'Broadcast progress' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Pause' }));
    expect(m.pauseBroadcast).toHaveBeenCalledWith('BCAST-1');
  });
  it('filters recipients by status', async () => {
    render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
    await screen.findByText('131026');
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'failed');
    await waitFor(() => expect(m.listBroadcastRecipients).toHaveBeenLastCalledWith('BCAST-1', { status: 'failed', limit: 100 }));
  });
  it('polls every 5s while running, not when completed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
      await screen.findByText('131026');
      const n = m.getBroadcast.mock.calls.length;
      await act(async () => { await vi.advanceTimersByTimeAsync(5100); });
      expect(m.getBroadcast.mock.calls.length).toBeGreaterThan(n);
    } finally { vi.useRealTimers(); }
    m.getBroadcast.mockResolvedValue(ok({ broadcast: bc({ status: 'Completed' }) }));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      render(<BroadcastDetail name="BCAST-2" onBack={vi.fn()} />);
      await waitFor(() => expect(m.getBroadcast).toHaveBeenCalledWith('BCAST-2'));
      await act(async () => { await vi.advanceTimersByTimeAsync(100); });
      const n = m.getBroadcast.mock.calls.filter((c) => c[0] === 'BCAST-2').length;
      await act(async () => { await vi.advanceTimersByTimeAsync(11000); });
      expect(m.getBroadcast.mock.calls.filter((c) => c[0] === 'BCAST-2').length).toBe(n);
    } finally { vi.useRealTimers(); }
  });
  it('offers Resume when paused', async () => {
    m.getBroadcast.mockResolvedValue(ok({ broadcast: bc({ status: 'Paused' }) }));
    m.resumeBroadcast.mockResolvedValue(ok({}));
    render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Resume' }));
    expect(m.resumeBroadcast).toHaveBeenCalledWith('BCAST-1');
  });
  it('requires confirmation to cancel', async () => {
    m.cancelBroadcast.mockResolvedValue(ok({}));
    render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel broadcast' }));
    expect(m.cancelBroadcast).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Yes, cancel broadcast' }));
    expect(m.cancelBroadcast).toHaveBeenCalledWith('BCAST-1');
  });
});

describe('BroadcastTab kill switch', () => {
  it('needs a second click to stop everything', async () => {
    m.pauseAllBroadcasts.mockResolvedValue(ok({}));
    render(<BroadcastTab gateway="G" />);
    await userEvent.click(await screen.findByRole('button', { name: 'Stop all broadcasts' }));
    expect(m.pauseAllBroadcasts).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Confirm: stop all broadcasts' }));
    expect(m.pauseAllBroadcasts).toHaveBeenCalledWith('G');
  });
});

describe('BroadcastWizard', () => {
  const preview = (o: object = {}) => ({ recipients: 2, queued: 2, skipped: 0, category: 'MARKETING', within_limit: true, remaining_24h: 100, warnings: ['w1'], blocking: [], cost: { currency: 'USD', total: 0.1, by_country: {} }, confirm_required: true, consent_attested: true, ...o });
  beforeEach(() => {
    m.listTemplates.mockResolvedValue(ok({ templates: [
      { name: 'T1', template_name: 'promo', category: 'MARKETING', language_code: 'en', status: 'APPROVED' },
      { name: 'T2', template_name: 'draft', category: 'UTILITY', language_code: 'en', status: 'PENDING' },
    ] }));
    m.createBroadcast.mockResolvedValue(ok({ broadcast: 'BCAST-9', status: 'Draft', category: 'MARKETING' }));
    m.addBroadcastRecipients.mockResolvedValue(ok({ added: 2, skipped: [{ recipient: '1555', reason: 'opted_out' }], invalid: [{ recipient: 'abc', reason: 'invalid_number' }] }));
    m.attestBroadcastConsent.mockResolvedValue(ok({}));
    m.startBroadcast.mockResolvedValue(ok({}));
  });

  async function toPreview(user: ReturnType<typeof userEvent.setup>) {
    await user.selectOptions(await screen.findByLabelText('Approved template'), 'T1');
    expect(screen.getByText(/billed per delivered message/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.type(screen.getByLabelText(/Recipients/), '1555000111{enter}1555000222');
    await user.click(screen.getByRole('button', { name: 'Add recipients' }));
    expect(await screen.findByText(/recipients added/)).toBeInTheDocument();
    expect(screen.getByText(/abc: invalid_number/)).toBeInTheDocument();
    expect(screen.getByText(/opted_out/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    const next = screen.getByRole('button', { name: 'Next' });
    expect(next).toBeDisabled();
    await user.click(screen.getByLabelText(/I confirm every recipient/));
    await user.type(screen.getByLabelText(/Consent source/), 'signup form');
    await user.click(next);
  }

  it('lists only approved templates', async () => {
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    const sel = await screen.findByLabelText('Approved template');
    await waitFor(() => expect(sel.querySelectorAll('option').length).toBe(2));
  });

  it('walks to a typed-count confirmed start', async () => {
    m.previewBroadcast.mockResolvedValue(ok({ preview: preview() }));
    const onStarted = vi.fn();
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={onStarted} />);
    await toPreview(user);
    expect(m.attestBroadcastConsent).toHaveBeenCalledWith('BCAST-9', 'signup form');
    expect(await screen.findByText('w1')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    const start = screen.getByRole('button', { name: 'Start broadcast' });
    expect(start).toBeDisabled();
    await user.type(screen.getByLabelText(/Type 2 to confirm/), '3');
    expect(start).toBeDisabled();
    await user.clear(screen.getByLabelText(/Type 2 to confirm/));
    await user.type(screen.getByLabelText(/Type 2 to confirm/), '2');
    await user.click(start);
    expect(m.startBroadcast).toHaveBeenCalledWith('BCAST-9', '2');
    expect(onStarted).toHaveBeenCalledWith('BCAST-9');
  });

  it('blocking items disable proceeding', async () => {
    m.previewBroadcast.mockResolvedValue(ok({ preview: preview({ blocking: ['Template is paused'] }) }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await toPreview(user);
    expect(await screen.findByText('Template is paused')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });
});
