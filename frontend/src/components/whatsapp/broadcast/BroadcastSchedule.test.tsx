// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { render, screen } from '@testing-library/react';

vi.mock('@/contexts/SocketContext', () => ({ useSocket: () => null }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/whatsappApi', async (orig) => ({ ...(await orig<typeof import('@/services/whatsappApi')>()), listTemplates: vi.fn() }));
vi.mock('./limitsApi', async (orig) => ({ ...(await orig<typeof import('./limitsApi')>()), getBroadcastLimits: vi.fn() }));
vi.mock('./broadcastApi', async (orig) => ({
  ...(await orig<typeof import('./broadcastApi')>()),
  createBroadcast: vi.fn(), addBroadcastRecipients: vi.fn(), attestBroadcastConsent: vi.fn(), previewBroadcast: vi.fn(),
  getBroadcastTemplateParams: vi.fn(), startBroadcast: vi.fn(), deleteBroadcast: vi.fn(), scheduleBroadcast: vi.fn(),
  unscheduleBroadcast: vi.fn(), retryFailedRecipients: vi.fn(), getBroadcast: vi.fn(), listBroadcastRecipients: vi.fn(),
}));
import * as tplApi from '@/services/whatsappApi';
import * as bApi from './broadcastApi';
import * as lApi from './limitsApi';
import { BroadcastWizard } from './BroadcastWizard';
import { BroadcastDetail } from './BroadcastDetail';
import { toSiteDatetime } from './broadcastModel';

Element.prototype.matches = ((orig) => function (this: Element, s: string) { return s === ':modal' ? false : orig.call(this, s); })(Element.prototype.matches);
Object.assign(Element.prototype, { hasPointerCapture: () => false, setPointerCapture: () => {}, releasePointerCapture: () => {}, scrollIntoView: () => {} });

const m = vi.mocked({ ...tplApi, ...bApi, ...lApi }, true);
const ok = <T,>(v: T) => ({ success: true, ...v }) as never;
const bc = (o: object = {}) => ({
  name: 'BCAST-1', title: 'Promo', status: 'Draft', gateway: 'G', total: 10, queued: 4, sending: 0, sent: 3, delivered: 2, read: 0,
  failed: 0, deferred: 0, unknown: 0, skipped: 0, ...o,
});

beforeEach(() => {
  vi.clearAllMocks();
  m.getBroadcast.mockResolvedValue(ok({ broadcast: bc() }));
  m.listBroadcastRecipients.mockResolvedValue(ok({ recipients: [] }));
});

describe('toSiteDatetime', () => {
  it('formats datetime-local values for the server', () => {
    expect(toSiteDatetime('2030-01-02T09:30')).toBe('2030-01-02 09:30:00');
    expect(toSiteDatetime('')).toBe('');
  });
});

describe('BroadcastDetail scheduling', () => {
  it('shows the scheduled time and unschedules', async () => {
    m.getBroadcast.mockResolvedValue(ok({ broadcast: bc({ status: 'Scheduled', scheduled_at: '2030-01-02 09:30:00' }) }));
    m.unscheduleBroadcast.mockResolvedValue(ok({}));
    render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
    expect(await screen.findByText(/Scheduled for 2030-01-02 09:30:00/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Unschedule' }));
    expect(m.unscheduleBroadcast).toHaveBeenCalledWith('BCAST-1');
  });

  it('offers Retry failed (n) on a finished broadcast', async () => {
    m.getBroadcast.mockResolvedValue(ok({ broadcast: bc({ status: 'Completed', failed: 3 }) }));
    m.retryFailedRecipients.mockResolvedValue(ok({ broadcast: 'BCAST-2', added: 2 }));
    render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Retry failed (3)' }));
    expect(m.retryFailedRecipients).toHaveBeenCalledWith('BCAST-1');
  });

  it('hides Retry failed when nothing failed', async () => {
    m.getBroadcast.mockResolvedValue(ok({ broadcast: bc({ status: 'Completed', failed: 0 }) }));
    render(<BroadcastDetail name="BCAST-1" onBack={vi.fn()} />);
    await screen.findByText('Promo');
    expect(screen.queryByRole('button', { name: /Retry failed/ })).toBeNull();
  });
});

describe('BroadcastWizard schedule', () => {
  it('schedules instead of starting', async () => {
    m.listTemplates.mockResolvedValue(ok({ templates: [{ name: 'T1', template_name: 'promo', category: 'UTILITY', language_code: 'en', status: 'APPROVED' }] }));
    m.createBroadcast.mockResolvedValue(ok({ broadcast: 'B1', status: 'Draft' }));
    m.addBroadcastRecipients.mockResolvedValue(ok({ added: 2, skipped: [], invalid: [], skippedTotal: 0, invalidTotal: 0 }));
    m.attestBroadcastConsent.mockResolvedValue(ok({}));
    m.scheduleBroadcast.mockResolvedValue(ok({}));
    m.getBroadcastTemplateParams.mockResolvedValue(ok({ parameter_format: 'POSITIONAL', body: [], header: null, buttons: [] }));
    m.getBroadcastLimits.mockResolvedValue(ok({ limits: [{ key: 'require_typed_count', label: 'x', group: 'safety', kind: 'setting', value: false, default: false, effective: false, source: 'default', editable: true }] }));
    m.previewBroadcast.mockResolvedValue(ok({ preview: {
      recipients: 2, queued: 2, skipped: 0, category: 'UTILITY', within_limit: true, remaining_24h: 100, warnings: [], blocking: [],
      limits_in_effect: [], cost: null, confirm_required: false, consent_attested: true,
    } }));
    const user = userEvent.setup();
    const onStarted = vi.fn();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={onStarted} />);
    await user.click(await screen.findByRole('combobox', { name: 'Approved template' }));
    await user.click(await screen.findByRole('option', { name: /promo/ }));
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.type(screen.getByLabelText(/Recipients/), '1555000111');
    await user.click(screen.getByRole('button', { name: 'Add recipients' }));
    await screen.findByText(/recipients added/);
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    await user.click(screen.getByLabelText(/I confirm every recipient/));
    await user.type(screen.getByLabelText(/Consent source/), 'form');
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.click(screen.getByLabelText('Schedule for'));
    expect(screen.getByRole('button', { name: 'Schedule broadcast' })).toBeDisabled();
    await user.type(screen.getByLabelText('Schedule date and time'), '2030-01-02T09:30');
    expect(screen.getByText(/site timezone/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Schedule broadcast' }));
    expect(m.scheduleBroadcast).toHaveBeenCalledWith('B1', '2030-01-02 09:30:00', '2', []);
    expect(m.startBroadcast).not.toHaveBeenCalled();
    expect(onStarted).toHaveBeenCalledWith('B1');
  });
});
