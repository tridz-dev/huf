// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { render, screen } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/whatsappApi', async (orig) => ({ ...(await orig<typeof import('@/services/whatsappApi')>()), listTemplates: vi.fn() }));
vi.mock('../limitsApi', async (orig) => ({ ...(await orig<typeof import('../limitsApi')>()), getBroadcastLimits: vi.fn() }));
vi.mock('../broadcastApi', async (orig) => ({
  ...(await orig<typeof import('../broadcastApi')>()),
  createBroadcast: vi.fn(), addBroadcastRecipients: vi.fn(), attestBroadcastConsent: vi.fn(), previewBroadcast: vi.fn(),
  getBroadcastTemplateParams: vi.fn(), startBroadcast: vi.fn(), deleteBroadcast: vi.fn(),
}));
vi.mock('../../audiences/audiencesApi', async (orig) => ({ ...(await orig<typeof import('../../audiences/audiencesApi')>()), listAudiences: vi.fn(), getAudience: vi.fn() }));
vi.mock('./audienceSelectionApi', () => ({ setBroadcastAudiences: vi.fn(), getBroadcastAudiences: vi.fn(), previewAudienceSelectionForGateway: vi.fn() }));
import * as tplApi from '@/services/whatsappApi';
import * as bApi from '../broadcastApi';
import * as lApi from '../limitsApi';
import * as aApi from '../../audiences/audiencesApi';
import * as sApi from './audienceSelectionApi';
import { BroadcastWizard } from '../BroadcastWizard';

Element.prototype.matches = ((orig) => function (this: Element, s: string) { return s === ':modal' ? false : orig.call(this, s); })(Element.prototype.matches);
Object.assign(Element.prototype, { hasPointerCapture: () => false, setPointerCapture: () => {}, releasePointerCapture: () => {}, scrollIntoView: () => {} });

const m = vi.mocked({ ...tplApi, ...bApi, ...lApi, ...aApi, ...sApi }, true);
const ok = <T,>(v: T) => ({ success: true, ...v }) as never;
const counts = { total: 10, dupes: 1, excluded: 0, suppressed: 2, blocked_by_purpose: 0, final: 7 };
const consent = (o: object = {}) => ({ satisfied: true, attested: true, manual_rows: 0, audiences: [{ audience: 'A1', title: 'VIP list', attested: true }], ...o });
const setResult = (o: object = {}) => ok({ counts, per_audience: [], blocked: [], added: 7, skipped: [], invalid: [], queued: 7, consent: consent(), ...o });

async function pickList(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('combobox', { name: 'Approved template' }));
  await user.click(await screen.findByRole('option', { name: /promo/ }));
  await user.click(screen.getByRole('button', { name: 'Next' }));
  await user.click(await screen.findByRole('combobox', { name: 'Add an audience' }));
  await user.click(await screen.findByRole('option', { name: /VIP list/ }));
}

beforeEach(() => {
  vi.clearAllMocks();
  m.listTemplates.mockResolvedValue(ok({ templates: [{ name: 'T1', template_name: 'promo', category: 'MARKETING', language_code: 'en', status: 'APPROVED' }] }));
  m.createBroadcast.mockResolvedValue(ok({ broadcast: 'B1', status: 'Draft' }));
  m.addBroadcastRecipients.mockResolvedValue(ok({ added: 2, skipped: [], invalid: [], skippedTotal: 0, invalidTotal: 0 }));
  m.attestBroadcastConsent.mockResolvedValue(ok({}));
  m.previewBroadcast.mockResolvedValue(ok({ preview: { recipients: 7, queued: 7, skipped: 0, category: 'MARKETING', within_limit: true, remaining_24h: 9, warnings: [], blocking: [], limits_in_effect: [], cost: null, confirm_required: true, consent_attested: true } }));
  m.getBroadcastTemplateParams.mockResolvedValue(ok({ parameter_format: 'POSITIONAL', body: [], header: null, buttons: [] }));
  m.getBroadcastLimits.mockResolvedValue(ok({ limits: [] }));
  m.listAudiences.mockResolvedValue(ok({ audiences: [{ name: 'A1', title: 'VIP list', member_count: 10, suppressed_count: 2 }], total: 1 }));
  m.getAudience.mockResolvedValue(ok({ audience: { tags: [] } }));
  m.previewAudienceSelectionForGateway.mockResolvedValue(ok({ counts, per_audience: [], blocked: [] }));
  m.setBroadcastAudiences.mockResolvedValue(setResult());
});

describe('wizard audiences', () => {
  it('previews counts with the template category and applies the lists', async () => {
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await pickList(user);
    expect(await screen.findByText('Will receive 7')).toBeInTheDocument();
    expect(m.previewAudienceSelectionForGateway).toHaveBeenLastCalledWith('G', [{ audience: 'A1', tags: [], tag_filter_mode: 'any', exclude: false }], 'MARKETING');
    await user.click(screen.getByRole('button', { name: 'Add recipients' }));
    expect(await screen.findByText(/recipients added from saved lists/)).toBeInTheDocument();
    expect(m.setBroadcastAudiences).toHaveBeenCalledWith('B1', [expect.objectContaining({ audience: 'A1' })]);
    expect(m.addBroadcastRecipients).not.toHaveBeenCalled();
  });

  it('skips the attestation checkbox when the lists cover consent', async () => {
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await pickList(user);
    await user.click(screen.getByRole('button', { name: 'Add recipients' }));
    await user.click(await screen.findByRole('button', { name: 'Continue' }));
    expect(screen.getByText(/Consent covered by: VIP list/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/I confirm every recipient/)).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(m.attestBroadcastConsent).not.toHaveBeenCalled();
    expect(m.previewBroadcast).toHaveBeenCalledWith('B1');
  });

  it('keeps the attestation when manual numbers are combined with lists', async () => {
    m.setBroadcastAudiences.mockResolvedValue(setResult({ consent: consent({ satisfied: false, manual_rows: 2 }) }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await pickList(user);
    await user.type(screen.getByLabelText(/Recipients/), '1555000111');
    await user.click(screen.getByRole('button', { name: 'Add recipients' }));
    await user.click(await screen.findByRole('button', { name: 'Continue' }));
    expect(m.addBroadcastRecipients).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText(/I confirm every recipient/)).toBeInTheDocument();
  });

  it('shows a list blocked by purpose as an error and blocks Add recipients', async () => {
    m.previewAudienceSelectionForGateway.mockResolvedValue(ok({
      counts: { ...counts, blocked_by_purpose: 10, final: 0 }, per_audience: [],
      blocked: [{ code: 'audience_purpose_mismatch', audience: 'A1', message: 'VIP list has not agreed to marketing messages' }],
    }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await pickList(user);
    expect(await screen.findByText(/has not agreed to marketing messages/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add recipients' })).toBeDisabled();
  });

  it('reports a list blocked at apply time and stays on the step', async () => {
    m.setBroadcastAudiences.mockResolvedValue(setResult({ added: 0, blocked: [{ code: 'audience_purpose_mismatch', audience: 'A1', message: 'VIP list cannot receive this message type' }] }));
    const user = userEvent.setup();
    render(<BroadcastWizard gateway="G" onClose={vi.fn()} onStarted={vi.fn()} />);
    await pickList(user);
    await user.click(screen.getByRole('button', { name: 'Add recipients' }));
    expect(await screen.findByText('VIP list cannot receive this message type', { selector: '[role="alert"]' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Continue' })).toBeNull();
  });
});
