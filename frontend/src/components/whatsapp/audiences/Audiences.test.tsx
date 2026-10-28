// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('./audiencesApi', async (orig) => ({
  ...(await orig<typeof import('./audiencesApi')>()),
  listAudiences: vi.fn(), getAudience: vi.fn(), createAudience: vi.fn(), updateAudience: vi.fn(), deleteAudience: vi.fn(),
  importMembers: vi.fn(), getImportStatus: vi.fn(), removeMembers: vi.fn(), listMembers: vi.fn(), previewAudienceSelection: vi.fn(),
}));
import * as api from './audiencesApi';
import { AudiencesPage } from './AudiencesPage';
import { AudiencePicker } from './AudiencePicker';
import { MemberTable } from './MemberTable';
import { ImportMembersDialog } from './ImportMembersDialog';
import { csvToObjects } from './csv';

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
  name: 'AUD-1', title: 'VIPs', consent_source: 'Website form', consent_basis: 'opt-in form', consent_purposes: ['marketing'],
  member_count: 12, suppressed_count: 2, ...o,
});

beforeEach(() => {
  vi.clearAllMocks();
  m.listAudiences.mockResolvedValue(ok({ audiences: [aud(), aud({ name: 'AUD-2', title: 'Newsletter' })] }));
  m.getAudience.mockResolvedValue(ok({ audience: aud({ tags: [{ tag: 'vip', count: 3 }, { tag: 'new', count: 1 }], used_by: [], can_see_numbers: true }) }));
  m.listMembers.mockResolvedValue(ok({
    members: [
      { recipient: '919812345678', display_name: 'Asha', tags: ['vip'], suppressed: null },
      { recipient: '919800000000', display_name: null, tags: [], suppressed: 'opted_out' },
    ], total: 2, masked: false,
  }));
  m.previewAudienceSelection.mockResolvedValue(ok({
    counts: { total: 20, dupes: 3, excluded: 0, suppressed: 2, blocked_by_purpose: 0, final: 15 },
    per_audience: [], blocked: [],
  }));
});

describe('csv helpers', () => {
  it('parses quotes', () => {
    const { headers, rows } = csvToObjects('phone,name\r\n9198,"Doe, J"\n');
    expect(headers).toEqual(['phone', 'name']);
    expect(rows[0].name).toBe('Doe, J');
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
      gateway: 'G', consent_source: 'Checkout', consent_basis: 'checkout', consent_purposes: ['marketing'], consent_attested: true,
    });
  });
});

describe('MemberTable', () => {
  it('shows server numbers, suppression reason, removes', async () => {
    const user = userEvent.setup();
    m.removeMembers.mockResolvedValue(ok({ removed: 1, member_count: 1, suppressed_count: 1 }));
    render(<MemberTable audience="AUD-1" />);
    expect(await screen.findByText('919812345678')).toBeTruthy();
    expect(screen.getByText('Opted out')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Show numbers' })).toBeNull();
    await user.click(screen.getAllByRole('button', { name: /^Remove/ })[0]);
    await waitFor(() => expect(m.removeMembers).toHaveBeenCalledWith('AUD-1', ['919812345678']));
  });

  it('shows server-masked numbers without a reveal toggle or remove', async () => {
    m.listMembers.mockResolvedValue(ok({
      members: [{ recipient: '********5678', display_name: 'Asha', tags: [], suppressed: null }], total: 1, masked: true,
    }));
    render(<MemberTable audience="AUD-1" />);
    expect(await screen.findByText('********5678')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Show numbers|Remove/ })).toBeNull();
    expect(screen.getByText(/Numbers are hidden/)).toBeTruthy();
  });

  it('sends flat list_members params', async () => {
    render(<MemberTable audience="AUD-1" />);
    await screen.findByText('919812345678');
    expect(m.listMembers).toHaveBeenCalledWith('AUD-1', { search: undefined, tags: undefined, suppressed: undefined }, 1, 50);
  });
});

describe('ImportMembersDialog', () => {
  const paste = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.click(screen.getByLabelText('Or paste CSV'));
    await user.paste('mobile,full name,tags,city\n919812345678,Asha,vip,Pune');
  };

  it('maps columns, params as a column list, and sends conflict mode', async () => {
    const user = userEvent.setup();
    m.importMembers.mockResolvedValue(ok({ queued: false, added: 1, updated: 0, skipped_total: 0, invalid_total: 0, member_count: 1, suppressed_count: 0 }));
    render(<ImportMembersDialog audience="AUD-1" title="VIPs" onClose={() => {}} onDone={() => {}} />);
    await paste(user);
    await user.click(screen.getByLabelText('Use city as a template value'));
    await pick(user, 'If a contact is already in this audience', 'Stop if any contact already exists');
    await user.click(screen.getByRole('button', { name: 'Import contacts' }));
    await waitFor(() => expect(m.importMembers).toHaveBeenCalled());
    expect(m.importMembers.mock.calls[0][0]).toMatchObject({
      audience: 'AUD-1', on_conflict: 'fail', mapping: { phone: 'mobile', name: 'full name', tags: 'tags', params: ['city'] },
    });
    expect(await screen.findByText(/1 added/)).toBeTruthy();
  });

  it('polls get_import_status when the import is queued', async () => {
    const user = userEvent.setup();
    const onDone = vi.fn();
    m.importMembers.mockResolvedValue(ok({ queued: true, job_id: 'J1', rows: 20000 }));
    m.getImportStatus
      .mockResolvedValueOnce(ok({ job_id: 'J1', audience: 'AUD-1', status: 'running', processed: 500, total: 20000 }))
      .mockResolvedValue(ok({
        job_id: 'J1', audience: 'AUD-1', status: 'done', processed: 20000, total: 20000,
        result: { added: 19990, updated: 0, skipped_total: 5, invalid_total: 5 },
      }));
    render(<ImportMembersDialog audience="AUD-1" title="VIPs" onClose={() => {}} onDone={onDone} />);
    await paste(user);
    await user.click(screen.getByRole('button', { name: 'Import contacts' }));
    expect(await screen.findByText(/Importing in the background/)).toBeTruthy();
    expect(await screen.findByText(/500 of 20000/, undefined, { timeout: 4000 })).toBeTruthy();
    expect(await screen.findByText(/19990 added/, undefined, { timeout: 4000 })).toBeTruthy();
    expect(m.getImportStatus).toHaveBeenCalledWith('AUD-1', 'J1');
    expect(onDone).toHaveBeenCalled();
  });

  it('shows the error of a failed background import', async () => {
    const user = userEvent.setup();
    m.importMembers.mockResolvedValue(ok({ queued: true, job_id: 'J2', rows: 20000 }));
    m.getImportStatus.mockResolvedValue(ok({ job_id: 'J2', audience: 'AUD-1', status: 'failed', processed: 0, total: 20000, error: 'boom' }));
    render(<ImportMembersDialog audience="AUD-1" title="VIPs" onClose={() => {}} onDone={() => {}} />);
    await paste(user);
    await user.click(screen.getByRole('button', { name: 'Import contacts' }));
    expect(await screen.findByText('boom', undefined, { timeout: 4000 })).toBeTruthy();
  });
});

describe('AudiencePicker', () => {
  it('uses the server preview for a broadcast and sends selection with tags and exclude', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<AudiencePicker gateway="G" broadcast="BC-1" value={[{ audience: 'AUD-1', tags: [], exclude: false }]} onChange={onChange} />);
    expect(await screen.findByText('Will receive 15')).toBeTruthy();
    expect(screen.queryByText(/Estimate from audience sizes/)).toBeNull();
    await user.click(await screen.findByRole('button', { name: 'vip' }));
    expect(onChange).toHaveBeenCalledWith([{ audience: 'AUD-1', tags: ['vip'], exclude: false }]);
    await user.click(screen.getByLabelText('Exclude VIPs'));
    expect(onChange).toHaveBeenLastCalledWith([{ audience: 'AUD-1', tags: [], exclude: true }]);
    expect(m.previewAudienceSelection).toHaveBeenCalledWith('BC-1', [{ audience: 'AUD-1', tags: [], exclude: false }]);
  });

  it('shows purpose-mismatch blocks from the server', async () => {
    m.previewAudienceSelection.mockResolvedValue(ok({
      counts: { total: 12, dupes: 0, excluded: 0, suppressed: 0, blocked_by_purpose: 12, final: 0 },
      per_audience: [{ audience: 'AUD-1', matched: 12, added: 0, blocked_by_purpose: true }],
      blocked: [{ code: 'audience_purpose_mismatch', audience: 'AUD-1', message: 'VIPs was not collected for marketing messages.' }],
    }));
    render(<AudiencePicker gateway="G" broadcast="BC-1" value={[{ audience: 'AUD-1' }]} onChange={() => {}} />);
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'VIPs was not collected for marketing messages.');
  });

  it('falls back to an estimate from audience sizes without a broadcast', async () => {
    render(<AudiencePicker gateway="G" value={[{ audience: 'AUD-1' }, { audience: 'AUD-2', exclude: true }]} onChange={() => {}} />);
    expect(await screen.findByText('About Will receive 10')).toBeTruthy();
    expect(screen.getByText(/Estimate from audience sizes/)).toBeTruthy();
    expect(m.previewAudienceSelection).not.toHaveBeenCalled();
  });
});
