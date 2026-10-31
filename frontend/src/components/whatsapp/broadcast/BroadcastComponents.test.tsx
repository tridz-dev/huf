// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { act, render, screen, waitFor } from '@testing-library/react';

const socketRef: { current: unknown } = { current: null };
vi.mock('@/contexts/SocketContext', () => ({ useSocket: () => socketRef.current }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/whatsappApi', async (orig) => ({
  ...(await orig<typeof import('@/services/whatsappApi')>()),
  listTemplates: vi.fn(),
}));
vi.mock('./limitsApi', async (orig) => ({
  ...(await orig<typeof import('./limitsApi')>()),
  getBroadcastLimits: vi.fn(async () => ({ success: true, limits: [] }) as never),
}));
vi.mock('./broadcastApi', async (orig) => ({
  ...(await orig<typeof import('./broadcastApi')>()),
  createBroadcast: vi.fn(), addBroadcastRecipients: vi.fn(), attestBroadcastConsent: vi.fn(),
  previewBroadcast: vi.fn(), getBroadcastTemplateParams: vi.fn(), startBroadcast: vi.fn(), pauseBroadcast: vi.fn(), resumeBroadcast: vi.fn(), cancelBroadcast: vi.fn(),
  pauseAllBroadcasts: vi.fn(), listBroadcasts: vi.fn(), getBroadcast: vi.fn(), listBroadcastRecipients: vi.fn(),
  removeBroadcastRecipient: vi.fn(), deleteBroadcast: vi.fn(),
}));
import * as templatesApi from '@/services/whatsappApi';
import * as broadcastApi from './broadcastApi';
import { BroadcastTab } from './BroadcastTab';
import { BroadcastList } from './BroadcastList';
import { BroadcastWizard } from './BroadcastWizard';
import { BroadcastDetail } from './BroadcastDetail';
import { buildHeaderButtonParams, hasHeaderRow, locationValid } from './BroadcastWizard';

// jsdom has no top layer; answering ':modal' directly keeps Radix Select opening fast.
const originalMatches = Element.prototype.matches;
Element.prototype.matches = function (this: Element, selector: string) {
  return selector === ':modal' ? false : originalMatches.call(this, selector);
};
Object.assign(Element.prototype, {
  hasPointerCapture: () => false, setPointerCapture: () => {}, releasePointerCapture: () => {}, scrollIntoView: () => {},
});
/** Radix Select: open the combobox by its label, then click the option. */
const pick = async (user: ReturnType<typeof userEvent.setup> | typeof userEvent, label: string, option: string | RegExp) => {
  await user.click(await screen.findByRole('combobox', { name: label }));
  await user.click(await screen.findByRole('option', { name: option }));
};
const m = vi.mocked({ ...templatesApi, ...broadcastApi }, true);
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

describe('BroadcastDetail send_via', () => {
  it('shows the send path badge', async () => {
    m.getBroadcast.mockResolvedValue(ok({ broadcast: bc({ send_via: 'marketing_messages' }) }));
    m.listBroadcastRecipients.mockResolvedValue(ok({ recipients: [] }));
    render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
    expect(await screen.findByText('Marketing Messages API')).toBeInTheDocument();
  });
});

describe('BroadcastDetail', () => {
  it('shows counts, error codes and pauses', async () => {
    m.pauseBroadcast.mockResolvedValue(ok({}));
    render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
    expect(await screen.findByText('undeliverable')).toBeInTheDocument();
    expect(screen.queryByText('131026')).toBeNull();
    expect(screen.queryByText('Error code')).toBeNull();
    expect(screen.getByTestId('count-sent')).toHaveTextContent('3');
    expect(screen.getByRole('progressbar', { name: 'Broadcast progress' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Pause' }));
    expect(m.pauseBroadcast).toHaveBeenCalledWith('BCAST-1');
  });
  it('filters recipients by status', async () => {
    render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
    await screen.findByText('undeliverable');
    await pick(userEvent, 'Status', 'failed');
    await waitFor(() => expect(m.listBroadcastRecipients).toHaveBeenLastCalledWith('BCAST-1', { status: 'failed', limit: 100 }));
  });
  it('polls every 5s while running, not when completed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
      await screen.findByText('undeliverable');
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
    m.addBroadcastRecipients.mockResolvedValue(ok({ added: 2, skipped: [{ recipient: '1555', reason: 'opted_out' }], invalid: [{ recipient: 'abc', reason: 'invalid_number' }], skippedTotal: 700, invalidTotal: 1 }));
    m.attestBroadcastConsent.mockResolvedValue(ok({}));
    m.startBroadcast.mockResolvedValue(ok({}));
    m.getBroadcastTemplateParams.mockResolvedValue(ok({ parameter_format: 'POSITIONAL', body: [], header: null, buttons: [] }));
  });

  async function toPreview(user: ReturnType<typeof userEvent.setup>) {
    await pick(user, 'Approved template', /promo/);
    expect(screen.getByText(/billed per delivered message/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.type(screen.getByLabelText(/Recipients/), '1555000111{enter}1555000222');
    await user.click(screen.getByRole('button', { name: 'Add recipients' }));
    expect(await screen.findByText(/recipients added/)).toBeInTheDocument();
    expect(screen.getByText(/abc: Not a valid phone number/)).toBeInTheDocument();
    expect(screen.getByText(/Asked not to receive messages/)).toBeInTheDocument();
    expect(screen.getByText(/700 skipped \(showing 1\)/)).toBeInTheDocument();
    expect(screen.getByText(/1 invalid:/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    const next = screen.getByRole('button', { name: 'Next' });
    expect(next).toBeDisabled();
    await user.click(screen.getByLabelText(/I confirm every recipient/));
    await user.type(screen.getByLabelText(/Consent source/), 'signup form');
    await user.click(next);
  }

  it('lists only approved templates', async () => {
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await userEvent.click(await screen.findByRole('combobox', { name: 'Approved template' }));
    await waitFor(() => expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual(['promo (en)']));
  });

  it('walks to a typed-count confirmed start', async () => {
    m.previewBroadcast.mockResolvedValue(ok({ preview: preview() }));
    const onStarted = vi.fn();
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={onStarted} />);
    await toPreview(user);
    expect(m.attestBroadcastConsent).toHaveBeenCalledWith('BCAST-9', 'signup form');
    expect(await screen.findByText('w1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: /w1/ }));
    await user.click(screen.getByRole('button', { name: 'Next' }));
    const start = screen.getByRole('button', { name: 'Start broadcast' });
    expect(start).toBeDisabled();
    await user.type(screen.getByLabelText(/Type 2 to confirm/), '3');
    expect(start).toBeDisabled();
    await user.clear(screen.getByLabelText(/Type 2 to confirm/));
    await user.type(screen.getByLabelText(/Type 2 to confirm/), '2');
    await user.click(start);
    expect(m.startBroadcast).toHaveBeenCalledWith('BCAST-9', '2', ['w1']);
    expect(onStarted).toHaveBeenCalledWith('BCAST-9');
  });

  it('shows send-via only for MARKETING and sends the choice', async () => {
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await screen.findByRole('combobox', { name: 'Approved template' });
    expect(screen.queryByRole('combobox', { name: 'Send via' })).not.toBeInTheDocument();
    await pick(user, 'Approved template', /promo/);
    expect(await screen.findByRole('combobox', { name: 'Send via' })).toHaveTextContent('Cloud API (messages)');
    expect(screen.getByText(/falls back to the Cloud API/)).toBeInTheDocument();
    await pick(user, 'Send via', /Marketing Messages API/);
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.type(screen.getByLabelText(/Recipients/), '1555000111');
    await user.click(screen.getByRole('button', { name: 'Add recipients' }));
    await screen.findByText(/recipients added/);
    expect(m.createBroadcast).toHaveBeenCalledWith(expect.objectContaining({ send_via: 'marketing_messages' }));
  });

  it('renders preview warnings (e.g. +1 numbers) in a prominent alert', async () => {
    m.previewBroadcast.mockResolvedValue(ok({ preview: preview({ warnings: ['+1 (US) numbers are excluded for MARKETING'] }) }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await toPreview(user);
    const w = await screen.findByText(/US\) numbers are excluded/);
    expect(w.closest('[role="alert"]')).not.toBeNull();
  });

  it('blocking items disable proceeding', async () => {
    m.previewBroadcast.mockResolvedValue(ok({ preview: preview({ blocking: ['Template is paused'] }) }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await toPreview(user);
    expect(await screen.findByText('Template is paused')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  describe('template variables', () => {
    const named = { parameter_format: 'NAMED', body: [{ name: 'first_name', sample: 'Ada' }, { name: 'city' }], header: null, buttons: [] };
    it('collects NAMED defaults, passes them as a dict, and maps per-recipient values', async () => {
      m.getBroadcastTemplateParams.mockResolvedValue(ok(named));
      const user = userEvent.setup();
      render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
      await pick(user, 'Approved template', /promo/);
      const f = await screen.findByLabelText('Default value for {{first_name}}');
      expect(f).toHaveAttribute('placeholder', 'e.g. Ada');
      await user.type(f, 'friend');
      await user.click(screen.getByRole('button', { name: 'Next' }));
      expect(screen.getByText(/Columns: phone, first_name, city/)).toBeInTheDocument();
      await user.type(screen.getByLabelText(/Recipients/), '1555000111,Bob,Paris{enter}1555000222\t Eve{enter}1555000333');
      await user.click(screen.getByRole('button', { name: 'Add recipients' }));
      await screen.findByText(/recipients added/);
      expect(m.createBroadcast).toHaveBeenCalledWith(expect.objectContaining({ body_params: { first_name: 'friend' } }));
      expect(m.addBroadcastRecipients).toHaveBeenCalledWith('BCAST-9', { recipients: [
        { recipient: '1555000111', params: { body: { first_name: 'Bob', city: 'Paris' } } },
        { recipient: '1555000222', params: { body: { first_name: 'Eve' } } },
        { recipient: '1555000333' },
      ] });
    });
    it('passes an ordered list for POSITIONAL templates', async () => {
      m.getBroadcastTemplateParams.mockResolvedValue(ok({ parameter_format: 'POSITIONAL', body: [{ index: 1 }, { index: 2 }], header: null, buttons: [] }));
      const user = userEvent.setup();
      render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
      await pick(user, 'Approved template', /promo/);
      await user.type(await screen.findByLabelText('Default value for {{2}}'), 'two');
      await user.click(screen.getByRole('button', { name: 'Next' }));
      await user.type(screen.getByLabelText(/Recipients/), '1555000111,a,b');
      await user.click(screen.getByRole('button', { name: 'Add recipients' }));
      await screen.findByText(/recipients added/);
      expect(m.createBroadcast).toHaveBeenCalledWith(expect.objectContaining({ body_params: ['', 'two'] }));
      expect(m.addBroadcastRecipients).toHaveBeenCalledWith('BCAST-9', { recipients: [{ recipient: '1555000111', params: { body: ['a', 'b'] } }] });
    });
    it('collects required header and button values and sends them', async () => {
      m.getBroadcastTemplateParams.mockResolvedValue(ok({
        ...named,
        header: { type: 'IMAGE', required: true },
        buttons: [{ index: 0, sub_type: 'url', required: true, label: 'Shop' }],
      }));
      m.createBroadcast.mockResolvedValue(ok({ broadcast: 'BCAST-9' }));
      m.addBroadcastRecipients.mockResolvedValue(ok({ added: 1, skipped: [], invalid: [], skippedTotal: 0, invalidTotal: 0 }));
      const user = userEvent.setup();
      render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
      await pick(user, 'Approved template', /promo/);
      const header = await screen.findByLabelText(/Header image link/);
      expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
      await user.type(header, 'https://x.test/a.png');
      expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
      await user.type(screen.getByLabelText(/Link suffix for button "Shop"/), 'summer');
      expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled();
      await user.click(screen.getByRole('button', { name: 'Next' }));
      await user.type(screen.getByLabelText(/Recipients/), '1555000111');
      await user.click(screen.getByRole('button', { name: 'Add recipients' }));
      await waitFor(() => expect(m.createBroadcast).toHaveBeenCalledWith(expect.objectContaining({
        header_params: ['https://x.test/a.png'], button_params: [{ index: 0, sub_type: 'url', text: 'summer' }],
      })));
    });
    it('discards the draft when the wizard is closed before starting', async () => {
      m.createBroadcast.mockResolvedValue(ok({ broadcast: 'BCAST-9' }));
      m.addBroadcastRecipients.mockResolvedValue(ok({ added: 1, skipped: [], invalid: [], skippedTotal: 0, invalidTotal: 0 }));
      m.deleteBroadcast.mockResolvedValue(ok({ deleted: true }));
      const onClose = vi.fn();
      const user = userEvent.setup();
      render(<BroadcastWizard gateway="G" onClose={onClose} onStarted={vi.fn()} />);
      await pick(user, 'Approved template', /promo/);
      await user.click(await screen.findByRole('button', { name: 'Next' }));
      await user.type(screen.getByLabelText(/Recipients/), '1555000111');
      await user.click(screen.getByRole('button', { name: 'Add recipients' }));
      await user.click(await screen.findByRole('button', { name: 'Discard draft' }));
      await waitFor(() => expect(m.deleteBroadcast).toHaveBeenCalledWith('BCAST-9'));
      expect(onClose).toHaveBeenCalled();
    });
    it('blocking message about missing variables disables Start', async () => {
      m.previewBroadcast.mockResolvedValue(ok({ preview: preview({ blocking: ['2 recipient(s) are missing values for: first_name'] }) }));
      const user = userEvent.setup();
      render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
      await toPreview(user);
      expect(await screen.findByText(/missing values for: first_name/)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
      expect(m.startBroadcast).not.toHaveBeenCalled();
    });
  });
});

describe('BroadcastDetail draft management', () => {
  const draft = () => m.getBroadcast.mockResolvedValue(ok({ broadcast: bc({ status: 'Draft', sent: 0, delivered: 0, failed: 0 }) }));
  it('removes one recipient from a draft', async () => {
    draft();
    m.removeBroadcastRecipient.mockResolvedValue(ok({ removed: 1 }));
    render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Remove 15550001' }));
    expect(m.removeBroadcastRecipient).toHaveBeenCalledWith('BCAST-1', '15550001');
  });
  it('does not offer remove or delete once started', async () => {
    render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
    await screen.findByText('undeliverable');
    expect(screen.queryByRole('button', { name: /Remove/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Delete draft' })).toBeNull();
  });
  it('asks before deleting a draft, then goes back', async () => {
    draft();
    m.deleteBroadcast.mockResolvedValue(ok({ deleted: true }));
    const onBack = vi.fn();
    render(<BroadcastDetail name="BCAST-1" onBack={onBack} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete draft' }));
    expect(m.deleteBroadcast).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Yes, delete draft' }));
    expect(m.deleteBroadcast).toHaveBeenCalledWith('BCAST-1');
    await waitFor(() => expect(onBack).toHaveBeenCalled());
  });
  it('shows more recipients when the page is full', async () => {
    const many = Array.from({ length: 100 }, (_, i) => ({ name: `r${i}`, recipient: `1555${i}`, status: 'sent' }));
    m.listBroadcastRecipients.mockResolvedValue(ok({ recipients: many }));
    render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Show more' }));
    await waitFor(() => expect(m.listBroadcastRecipients).toHaveBeenLastCalledWith('BCAST-1', { status: undefined, limit: 200 }));
  });
});

describe('buildHeaderButtonParams', () => {
  const tpl = {
    parameter_format: 'POSITIONAL', body: [],
    header: { type: 'IMAGE', required: true },
    buttons: [
      { index: 0, sub_type: 'url', required: true, label: 'Shop' },
      { index: 1, sub_type: 'copy_code', required: true, label: 'Code' },
      { index: 2, sub_type: 'quick_reply', required: false, label: 'Stop' },
    ],
  } as never;
  it('builds header and button params in the backend shape', () => {
    expect(buildHeaderButtonParams(tpl, ' https://x.test/a.png ', { 0: 'summer', 1: 'SAVE10', 2: 'x' })).toEqual({
      header_params: ['https://x.test/a.png'],
      button_params: [{ index: 0, sub_type: 'url', text: 'summer' }, { index: 1, sub_type: 'copy_code', code: 'SAVE10' }],
    });
  });
  it('returns nothing when nothing was filled', () => {
    expect(buildHeaderButtonParams(tpl, '', {})).toEqual({});
    expect(buildHeaderButtonParams(null, 'x', {})).toEqual({});
  });
});

describe('BroadcastWizard once recipients are added', () => {
  it('cannot go back to change template values (the draft keeps them)', async () => {
    m.createBroadcast.mockResolvedValue(ok({ broadcast: 'BCAST-9' }));
    m.addBroadcastRecipients.mockResolvedValue(ok({ added: 1, skipped: [], invalid: [], skippedTotal: 0, invalidTotal: 0 }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await pick(user, 'Approved template', /promo/);
    await user.click(await screen.findByRole('button', { name: 'Next' }));
    await user.type(screen.getByLabelText(/Recipients/), '1555000111');
    await user.click(screen.getByRole('button', { name: 'Add recipients' }));
    await user.click(await screen.findByRole('button', { name: 'Continue' }));
    expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled();
  });
});

describe('location header', () => {
  const tpl = { parameter_format: 'POSITIONAL', body: [], header: { type: 'LOCATION', required: true }, buttons: [] } as never;
  const loc = { latitude: '12.97', longitude: '77.59', name: ' HQ ', address: '' };
  it('builds a location header and validates ranges', () => {
    expect(buildHeaderButtonParams(tpl, '', {}, loc)).toEqual({ header_params: [{ type: 'location', latitude: 12.97, longitude: 77.59, name: 'HQ' }] });
    expect(buildHeaderButtonParams(tpl, '', {}, { ...loc, latitude: '' })).toEqual({});
    expect(locationValid(loc)).toBe(true);
    expect(locationValid({ ...loc, latitude: '91' })).toBe(false);
    expect(locationValid({ ...loc, longitude: '-181' })).toBe(false);
    expect(locationValid({ ...loc, longitude: 'abc' })).toBe(false);
  });
  it('blocks Next until the location is valid, then sends it', async () => {
    m.getBroadcastTemplateParams.mockResolvedValue(ok({ parameter_format: 'POSITIONAL', body: [], header: { type: 'LOCATION', required: true }, buttons: [] }));
    m.createBroadcast.mockResolvedValue(ok({ broadcast: 'BCAST-9' }));
    m.addBroadcastRecipients.mockResolvedValue(ok({ added: 1, skipped: [], invalid: [], skippedTotal: 0, invalidTotal: 0 }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await pick(user, 'Approved template', /promo/);
    const lat = await screen.findByLabelText('Latitude');
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    await user.type(lat, '95');
    expect(screen.getByText('Enter a number between -90 and 90')).toBeInTheDocument();
    await user.clear(lat); await user.type(lat, '12.5');
    await user.type(screen.getByLabelText('Longitude'), '77.5');
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.type(screen.getByLabelText(/Recipients/), '1555000111');
    await user.click(screen.getByRole('button', { name: 'Add recipients' }));
    await waitFor(() => expect(m.createBroadcast).toHaveBeenCalledWith(expect.objectContaining({ header_params: [{ type: 'location', latitude: 12.5, longitude: 77.5 }] })));
  });
});

describe('per-recipient header-row CSV', () => {
  it('detects a pasted header line', () => {
    expect(hasHeaderRow('phone,header,button_url_0\n1555,https://x.test/a.png,summer')).toBe(true);
    expect(hasHeaderRow('  Recipient;x')).toBe(true);
    expect(hasHeaderRow('1555000111,Bob')).toBe(false);
  });
  it('sends a pasted CSV with a header line as csv_text', async () => {
    m.getBroadcastTemplateParams.mockResolvedValue(ok({ parameter_format: 'POSITIONAL', body: [], header: null, buttons: [] }));
    m.createBroadcast.mockResolvedValue(ok({ broadcast: 'BCAST-9' }));
    m.addBroadcastRecipients.mockResolvedValue(ok({ added: 1, skipped: [], invalid: [], skippedTotal: 0, invalidTotal: 0 }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await pick(user, 'Approved template', /promo/);
    await user.click(await screen.findByRole('button', { name: 'Next' }));
    await user.click(screen.getByLabelText(/Recipients/));
    await user.paste('phone,header\n1555000111,https://x.test/a.png');
    await user.click(screen.getByRole('button', { name: 'Add recipients' }));
    await waitFor(() => expect(m.addBroadcastRecipients).toHaveBeenCalledWith('BCAST-9', { csvText: 'phone,header\n1555000111,https://x.test/a.png' }));
  });
});

describe('BroadcastDetail realtime', () => {
  type Handler = (d: unknown) => void;
  const fakeSocket = (connected: boolean) => {
    const handlers = new Map<string, Handler[]>();
    return {
      connected, emit: vi.fn(),
      on: (e: string, h: Handler) => handlers.set(e, [...(handlers.get(e) ?? []), h]),
      off: (e: string, h: Handler) => handlers.set(e, (handlers.get(e) ?? []).filter((x) => x !== h)),
      fire: (e: string, d?: unknown) => (handlers.get(e) ?? []).forEach((h) => h(d)),
    };
  };
  afterEach(() => { socketRef.current = null; });
  it('shows Polling without a socket', async () => {
    render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
    expect(await screen.findByText('Polling')).toBeInTheDocument();
  });
  it('shows Live, subscribes to the document room and applies pushed counts', async () => {
    const sock = fakeSocket(true);
    socketRef.current = sock;
    render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
    expect(await screen.findByText('Live')).toBeInTheDocument();
    expect(sock.emit).toHaveBeenCalledWith('doc_subscribe', 'WhatsApp Broadcast', 'BCAST-1');
    expect(screen.getByTestId('count-sent')).toHaveTextContent('3');
    act(() => sock.fire('wa_broadcast_progress', { broadcast: 'BCAST-1', status: 'Running', sent: 7, total: 10, queued: 0, sending: 0, delivered: 2, read: 0, failed: 1, deferred: 0, unknown: 0, skipped: 0 }));
    await waitFor(() => expect(screen.getByTestId('count-sent')).toHaveTextContent('7'));
    const before = m.listBroadcastRecipients.mock.calls.length;
    act(() => sock.fire('wa_broadcast_progress', { broadcast: 'OTHER', sent: 99 }));
    expect(screen.getByTestId('count-sent')).toHaveTextContent('7');
    act(() => sock.fire('disconnect'));
    expect(await screen.findByText('Polling')).toBeInTheDocument();
    await waitFor(() => expect(m.listBroadcastRecipients.mock.calls.length).toBeGreaterThan(before), { timeout: 4000 }); // rows re-read after the push
  });
});

