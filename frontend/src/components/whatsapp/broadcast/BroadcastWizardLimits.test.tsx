// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { render, screen } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/whatsappApi', async (orig) => ({ ...(await orig<typeof import('@/services/whatsappApi')>()), listTemplates: vi.fn() }));
vi.mock('./limitsApi', async (orig) => ({ ...(await orig<typeof import('./limitsApi')>()), getBroadcastLimits: vi.fn() }));
vi.mock('./broadcastApi', async (orig) => ({
  ...(await orig<typeof import('./broadcastApi')>()),
  createBroadcast: vi.fn(), addBroadcastRecipients: vi.fn(), attestBroadcastConsent: vi.fn(), previewBroadcast: vi.fn(),
  getBroadcastTemplateParams: vi.fn(), startBroadcast: vi.fn(), deleteBroadcast: vi.fn(),
}));
import * as tplApi from '@/services/whatsappApi';
import * as bApi from './broadcastApi';
import * as lApi from './limitsApi';
import { BroadcastWizard } from './BroadcastWizard';

Element.prototype.matches = ((orig) => function (this: Element, s: string) { return s === ':modal' ? false : orig.call(this, s); })(Element.prototype.matches);
Object.assign(Element.prototype, { hasPointerCapture: () => false, setPointerCapture: () => {}, releasePointerCapture: () => {}, scrollIntoView: () => {} });

const m = vi.mocked({ ...tplApi, ...bApi, ...lApi }, true);
const ok = <T,>(v: T) => ({ success: true, ...v }) as never;
const L = (key: string, effective: lApi.LimitValue, label = key): lApi.BroadcastLimit => ({
  key, label, group: 'safety', kind: 'setting', value: effective, default: effective, effective, source: 'default', editable: true,
});
const pv = (o: object = {}) => ({
  recipients: 2, queued: 2, skipped: 0, category: 'UTILITY', within_limit: true, remaining_24h: 100, warnings: [], blocking: [],
  limits_in_effect: [], cost: null, confirm_required: true, consent_attested: true, ...o,
});

async function toPreview(user: ReturnType<typeof userEvent.setup>) {
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
}

beforeEach(() => {
  vi.clearAllMocks();
  m.listTemplates.mockResolvedValue(ok({ templates: [{ name: 'T1', template_name: 'promo', category: 'UTILITY', language_code: 'en', status: 'APPROVED' }] }));
  m.createBroadcast.mockResolvedValue(ok({ broadcast: 'B1', status: 'Draft' }));
  m.addBroadcastRecipients.mockResolvedValue(ok({ added: 2, skipped: [], invalid: [], skippedTotal: 0, invalidTotal: 0 }));
  m.attestBroadcastConsent.mockResolvedValue(ok({}));
  m.startBroadcast.mockResolvedValue(ok({}));
  m.getBroadcastTemplateParams.mockResolvedValue(ok({ parameter_format: 'POSITIONAL', body: [], header: null, buttons: [] }));
  m.getBroadcastLimits.mockResolvedValue(ok({ limits: [L('require_typed_count', true)] }));
});

describe('wizard limits', () => {
  it('requires acknowledging each warning and sends their codes', async () => {
    m.previewBroadcast.mockResolvedValue(ok({ preview: pv({ warnings: [
      { code: 'quality_red', message: 'Number quality is low', limit_key: 'warn_on_red' },
      { code: 'over_budget', message: 'Over your daily budget', limit_key: null },
    ] }) }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await toPreview(user);
    const next = screen.getByRole('button', { name: 'Next' });
    expect(next).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: /Number quality is low/ }));
    expect(next).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: /Over your daily budget/ }));
    await user.click(next);
    await user.type(screen.getByLabelText(/Type 2 to confirm/), '2');
    await user.click(screen.getByRole('button', { name: 'Start broadcast' }));
    expect(m.startBroadcast).toHaveBeenCalledWith('B1', '2', ['quality_red', 'over_budget']);
  });

  it('lists blocking reasons and blocks Next', async () => {
    m.previewBroadcast.mockResolvedValue(ok({ preview: pv({ blocking: [{ code: 'no_recipients', message: 'Nobody to send to', limit_key: null }] }) }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await toPreview(user);
    expect(await screen.findByText('Nobody to send to')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  it('shows the limits applied to this broadcast', async () => {
    m.getBroadcastLimits.mockResolvedValue(ok({ limits: [L('require_typed_count', true), L('max_recipients_default', 1000, 'Default recipient cap')] }));
    m.previewBroadcast.mockResolvedValue(ok({ preview: pv({ limits_in_effect: ['max_recipients_default'] }) }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await toPreview(user);
    expect(await screen.findByText('Limits applied to this broadcast')).toBeInTheDocument();
    expect(await screen.findByText('Default recipient cap: 1000')).toBeInTheDocument();
  });

  it('does not call an unknown Meta limit "no limit"', async () => {
    m.getBroadcastLimits.mockResolvedValue(ok({ limits: [
      L('require_typed_count', true),
      { ...L('messaging_tier_24h', null, 'Unique contacts per 24 hours'), kind: 'meta', editable: false },
      L('max_recipients_ceiling', null, 'Highest recipient cap'),
    ] }));
    m.previewBroadcast.mockResolvedValue(ok({ preview: pv({ limits_in_effect: ['messaging_tier_24h', 'max_recipients_ceiling'] }) }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await toPreview(user);
    expect(await screen.findByText('Unique contacts per 24 hours: not known yet')).toBeInTheDocument();
    expect(await screen.findByText('Highest recipient cap: no limit')).toBeInTheDocument();
  });

  it('hides the typed-count gate when the limit is off', async () => {
    m.getBroadcastLimits.mockResolvedValue(ok({ limits: [L('require_typed_count', false)] }));
    m.previewBroadcast.mockResolvedValue(ok({ preview: pv() }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await toPreview(user);
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.queryByLabelText(/Type 2 to confirm/)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Start broadcast' }));
    expect(m.startBroadcast).toHaveBeenCalledWith('B1', '2', []);
  });

  it('re-reviews when the server says warnings changed', async () => {
    m.startBroadcast.mockResolvedValue({ success: false, error: 'warnings_changed', message: 'changed' } as never);
    m.previewBroadcast.mockResolvedValue(ok({ preview: pv() }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await toPreview(user);
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.type(screen.getByLabelText(/Type 2 to confirm/), '2');
    await user.click(screen.getByRole('button', { name: 'Start broadcast' }));
    expect(await screen.findByText(/review the warnings again/)).toBeInTheDocument();
    expect(m.previewBroadcast).toHaveBeenCalledTimes(2);
  });

  it('re-reviews when the recipient list changed before the start', async () => {
    m.startBroadcast.mockResolvedValue({ success: false, error: 'recipients_changed', message: 'changed' } as never);
    m.previewBroadcast.mockResolvedValue(ok({ preview: pv() }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await toPreview(user);
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.type(screen.getByLabelText(/Type 2 to confirm/), '2');
    await user.click(screen.getByRole('button', { name: 'Start broadcast' }));
    expect(await screen.findByText(/recipient list changed/)).toBeInTheDocument();
  });
});
