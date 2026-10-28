// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('./audiencesApi', async (orig) => ({
  ...(await orig<typeof import('./audiencesApi')>()),
  listAudiences: vi.fn(), getAudience: vi.fn(), createAudience: vi.fn(), updateAudience: vi.fn(), deleteAudience: vi.fn(),
  importMembers: vi.fn(), removeMembers: vi.fn(), listMembers: vi.fn(), previewAudienceSelection: vi.fn(),
}));
import * as api from './audiencesApi';
import { AudiencesPage } from './AudiencesPage';
import { AudiencePicker } from './AudiencePicker';
import { MemberTable } from './MemberTable';
import { ImportMembersDialog } from './ImportMembersDialog';
import { csvToObjects, maskPhone } from './csv';

const originalMatches = Element.prototype.matches;
Element.prototype.matches = function (this: Element, selector: string) {
  return selector === ':modal' ? false : originalMatches.call(this, selector);
};
Object.assign(Element.prototype, {
  hasPointerCapture: () => false, setPointerCapture: () => {}, releasePointerCapture: () => {}, scrollIntoView: () => {},
});
const pick = async (user: ReturnType<typeof userEvent.setup>, label: string, option: string | RegExp) => {
  await user.click(await screen.findByRole('combobox', { name: label }));
  await user.click(await screen.findByRole('option', { name: option }));
};
const m = vi.mocked(api, true);
const ok = <T,>(v: T) => ({ success: true, ...v }) as never;
const aud = (o: object = {}) => ({
  name: 'AUD-1', title: 'VIPs', consent_source: 'Website form', consent_basis: 'opt_in_form', consent_purposes: ['marketing'],
  member_count: 12, suppressed_count: 2, ...o,
});

beforeEach(() => {
  vi.clearAllMocks();
  m.listAudiences.mockResolvedValue(ok({ audiences: [aud(), aud({ name: 'AUD-2', title: 'Newsletter' })] }));
  m.getAudience.mockResolvedValue(ok({ audience: aud(), tags: ['vip', 'new'] }));
  m.listMembers.mockResolvedValue(ok({
    members: [
      { name: 'M1', recipient: '919812345678', display_name: 'Asha', tags: ['vip'] },
      { name: 'M2', recipient: '919800000000', tags: [], suppressed: true, suppressed_reason: 'STOP' },
    ], total: 2, tags: ['vip'],
  }));
  m.previewAudienceSelection.mockResolvedValue(ok({ total: 20, dupes: 3, suppressed: 2, blocked_by_purpose: 0, final: 15, per_audience: [] }));
});

describe('csv helpers', () => {
  it('parses quotes and masks phones', () => {
    const { headers, rows } = csvToObjects('phone,name\r\n9198,"Doe, J"\n');
    expect(headers).toEqual(['phone', 'name']);
    expect(rows[0].name).toBe('Doe, J');
    expect(maskPhone('919812345678')).toMatch(/5678$/);
  });
});

describe('AudiencesPage', () => {
  it('lists audiences with counts and requires consent fields to create', async () => {
    const user = userEvent.setup();
    render(<AudiencesPage gateway="G" />);
    expect((await screen.findAllByText(/12 contacts, 2 opted out/))[0]).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'New audience' }));
    await user.type(await screen.findByLabelText(/^Name/), 'Fresh');
    await user.click(screen.getByRole('button', { name: 'Create audience' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Say where these contacts agreed to hear from you.');
    expect(m.createAudience).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText(/^Where did they agree/), 'Checkout');
    await pick(user, 'How did they agree?', 'Checkout');
    await user.click(screen.getByLabelText('Marketing'));
    await user.click(screen.getByLabelText(/I confirm everyone/));
    m.createAudience.mockResolvedValue(ok({ audience: aud() }));
    await user.click(screen.getByRole('button', { name: 'Create audience' }));
    await waitFor(() => expect(m.createAudience).toHaveBeenCalled());
    expect(m.createAudience.mock.calls[0][0]).toMatchObject({
      gateway: 'G', consent_source: 'Checkout', consent_basis: 'checkout', consent_purposes: ['marketing'], attest: true,
    });
  });
});

describe('MemberTable', () => {
  it('masks numbers, shows suppression reason, removes', async () => {
    const user = userEvent.setup();
    m.removeMembers.mockResolvedValue(ok({ removed: 1 }));
    render(<MemberTable audience="AUD-1" />);
    expect(await screen.findByText(/5678$/)).toBeTruthy();
    expect(screen.queryByText('919812345678')).toBeNull();
    expect(screen.getByText(/Opted out: STOP/)).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Show numbers' }));
    expect(screen.getByText('919812345678')).toBeTruthy();
    await user.click(screen.getAllByRole('button', { name: /^Remove/ })[0]);
    await waitFor(() => expect(m.removeMembers).toHaveBeenCalledWith('AUD-1', ['919812345678']));
  });
});

describe('ImportMembersDialog', () => {
  it('maps columns and sends conflict mode', async () => {
    const user = userEvent.setup();
    m.importMembers.mockResolvedValue(ok({ added: 1, updated: 0, skipped: 0, invalid: 0 }));
    render(<ImportMembersDialog audience="AUD-1" title="VIPs" onClose={() => {}} onDone={() => {}} />);
    await user.click(screen.getByLabelText('Or paste CSV'));
    await user.paste('mobile,full name,tags\n919812345678,Asha,vip');
    await pick(user, 'If a contact is already in this audience', 'Update name and values');
    await user.click(screen.getByRole('button', { name: 'Import contacts' }));
    await waitFor(() => expect(m.importMembers).toHaveBeenCalled());
    expect(m.importMembers.mock.calls[0][0]).toMatchObject({
      audience: 'AUD-1', on_conflict: 'update', mapping: { phone: 'mobile', name: 'full name', tags: 'tags' },
    });
    expect(await screen.findByText(/1 added/)).toBeTruthy();
  });
});

describe('AudiencePicker', () => {
  it('shows live counts and sends selection with tags and exclude', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<AudiencePicker gateway="G" value={[{ audience: 'AUD-1', tags: [], exclude: false }]} onChange={onChange} />);
    expect(await screen.findByText('Will receive 15')).toBeTruthy();
    await user.click(await screen.findByRole('button', { name: 'vip' }));
    expect(onChange).toHaveBeenCalledWith([{ audience: 'AUD-1', tags: ['vip'], exclude: false }]);
    await user.click(screen.getByLabelText('Exclude VIPs'));
    expect(onChange).toHaveBeenLastCalledWith([{ audience: 'AUD-1', tags: [], exclude: true }]);
    expect(m.previewAudienceSelection).toHaveBeenCalledWith({ selection: [{ audience: 'AUD-1', tags: [], exclude: false }], template: undefined });
  });
});
