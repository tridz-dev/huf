// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { render, screen, within } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('./limitsApi', async (orig) => ({
  ...(await orig<typeof import('./limitsApi')>()),
  getBroadcastLimits: vi.fn(), updateBroadcastLimits: vi.fn(),
}));
import * as api from './limitsApi';
import { BroadcastLimits } from './BroadcastLimits';

const m = vi.mocked(api, true);
const lim = (o: Partial<api.BroadcastLimit>): api.BroadcastLimit => ({
  key: 'k', label: 'Label', group: 'recipients', kind: 'setting', value: null, default: 10, effective: 10,
  source: 'default', editable: true, unit: null, min: 1, max: 100, note: null, ...o,
});
const rows = [
  lim({ key: 'max_batch', label: 'Largest batch', default: 200, effective: 200, value: null, min: 1, max: 1000, note: 'Messages per batch' }),
  lim({ key: 'template_approved', label: 'Approved templates only', group: 'meta', kind: 'meta', editable: false, default: true, effective: true, value: true, note: 'WhatsApp rule' }),
  lim({ key: 'require_typed_count', label: 'Type the count to confirm', group: 'confirmation', kind: 'safety', default: true, effective: true, value: true }),
  lim({ key: 'tick', label: 'Worker tick', group: 'safety', kind: 'internal', editable: false, default: 50, effective: 50, unit: 'seconds' }),
];
const ok = (limits: api.BroadcastLimit[]) => ({ success: true, limits }) as never;

beforeEach(() => {
  vi.clearAllMocks();
  m.getBroadcastLimits.mockResolvedValue(ok(rows));
});

describe('BroadcastLimits', () => {
  it('groups rows with badges, default, and read-only meta rows', async () => {
    render(<BroadcastLimits />);
    const batch = await screen.findByTestId('limit-max_batch');
    expect(within(batch).getByText('Huf setting')).toBeInTheDocument();
    expect(within(batch).getByText('Default: 200')).toBeInTheDocument();
    const meta = screen.getByTestId('limit-template_approved');
    expect(within(meta).getByText('Set by Meta')).toBeInTheDocument();
    expect(within(meta).getByText('Read only')).toBeInTheDocument();
    expect(within(screen.getByTestId('limit-tick')).getByText('Internal')).toBeInTheDocument();
    expect(within(screen.getByTestId('limit-require_typed_count')).getByText('Safety')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Set by Meta' })).toBeInTheDocument();
  });

  it('saves only changed values and refreshes from the response', async () => {
    m.updateBroadcastLimits.mockResolvedValue(ok([{ ...rows[0], value: 150, effective: 150, source: 'settings' }, ...rows.slice(1)]));
    const user = userEvent.setup();
    render(<BroadcastLimits />);
    const save = await screen.findByRole('button', { name: 'Save limits' });
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText('Largest batch'), '150');
    await user.click(save);
    expect(m.updateBroadcastLimits).toHaveBeenCalledWith({ max_batch: 150 });
    expect(await within(screen.getByTestId('limit-max_batch')).findByText('150')).toBeInTheDocument();
  });

  it('blocks save on out-of-range input', async () => {
    const user = userEvent.setup();
    render(<BroadcastLimits />);
    await user.type(await screen.findByLabelText('Largest batch'), '5000');
    expect(screen.getByText('Must be at most 1000')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save limits' })).toBeDisabled();
  });

  it('toggles a safety switch and resets a value to default', async () => {
    m.getBroadcastLimits.mockResolvedValue(ok([{ ...rows[0], value: 150, effective: 150, source: 'settings' }, rows[2]]));
    m.updateBroadcastLimits.mockResolvedValue(ok(rows));
    const user = userEvent.setup();
    render(<BroadcastLimits />);
    await user.click(await screen.findByRole('switch', { name: 'Type the count to confirm' }));
    await user.click(screen.getByRole('button', { name: 'Reset Largest batch' }));
    await user.click(screen.getByRole('button', { name: 'Save limits' }));
    expect(m.updateBroadcastLimits).toHaveBeenCalledWith({ require_typed_count: false, max_batch: null });
  });

  it('shows the server error when saving fails', async () => {
    m.updateBroadcastLimits.mockResolvedValue({ success: false, error: 'permission', message: 'Not allowed' } as never);
    const user = userEvent.setup();
    render(<BroadcastLimits />);
    await user.type(await screen.findByLabelText('Largest batch'), '9');
    await user.click(screen.getByRole('button', { name: 'Save limits' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });
});
