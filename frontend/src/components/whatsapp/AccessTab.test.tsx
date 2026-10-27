// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), message: vi.fn() } }));
vi.mock('@/services/gatewayAccessApi', () => ({
  listGatewayAccessEntries: vi.fn(),
  approveGatewayPairing: vi.fn(),
  revokeGatewayAccessEntry: vi.fn(),
  blockGatewayAccessEntry: vi.fn(),
  unblockGatewayAccessEntry: vi.fn(),
  restoreGatewayAccessEntry: vi.fn(),
  addGatewayAccessEntry: vi.fn(),
}));
import { toast } from 'sonner';
import {
  addGatewayAccessEntry, approveGatewayPairing, blockGatewayAccessEntry, listGatewayAccessEntries,
  restoreGatewayAccessEntry, revokeGatewayAccessEntry, unblockGatewayAccessEntry,
} from '@/services/gatewayAccessApi';
import { AccessTab } from './AccessTab';

const entry = (over: Record<string, unknown> = {}) => ({
  name: 'GAE-1', gateway: 'GW-1', provider: 'WhatsApp', entry_type: 'Sender', external_id: '15551234567',
  pairing_code: 'PAIR-ABCD2345', state: 'Pending', creation: '2026-10-21 10:00:00', ...over,
});

const list = vi.mocked(listGatewayAccessEntries);

beforeEach(() => {
  vi.clearAllMocks();
  list.mockResolvedValue([entry()] as never);
});

describe('AccessTab', () => {
  it('loads the waiting queue for the gateway first', async () => {
    render(<AccessTab gateway="GW-1" />);
    expect(await screen.findByText('15551234567')).toBeInTheDocument();
    expect(list).toHaveBeenCalledWith({ gateway: 'GW-1', state: 'Pending' });
    expect(screen.getByText('PAIR-ABCD2345')).toBeInTheDocument();
    expect(screen.getByText('Person')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Decline' })).toBeInTheDocument();
  });

  it('shows a friendly empty state per tab', async () => {
    list.mockResolvedValue([]);
    const user = userEvent.setup();
    render(<AccessTab gateway="GW-1" />);
    expect(await screen.findByText('No one is waiting for approval.')).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Approved' }));
    expect(await screen.findByText('No approved senders yet.')).toBeInTheDocument();
    expect(list).toHaveBeenLastCalledWith({ gateway: 'GW-1', state: 'Approved' });
    await user.click(screen.getByRole('tab', { name: 'Removed' }));
    expect(await screen.findByText('No one has been removed or declined.')).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Blocked' }));
    expect(await screen.findByText('No one is blocked.')).toBeInTheDocument();
    expect(list).toHaveBeenLastCalledWith({ gateway: 'GW-1', state: 'Blocked' });
    await user.click(screen.getByRole('tab', { name: 'Opted out' }));
    expect(await screen.findByText('No one has opted out.')).toBeInTheDocument();
  });

  it('approves a request, reloads and warns when the welcome message was not sent', async () => {
    vi.mocked(approveGatewayPairing).mockResolvedValue({ notification_status: 'Notification not sent' } as never);
    const user = userEvent.setup();
    render(<AccessTab gateway="GW-1" />);
    await user.click(await screen.findByRole('button', { name: 'Approve' }));
    expect(approveGatewayPairing).toHaveBeenCalledWith('GAE-1');
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Access approved'));
    expect(toast.message).toHaveBeenCalledWith('The welcome message could not be sent.');
    expect(list).toHaveBeenCalledTimes(2);
  });

  it('does not warn when the welcome message went out', async () => {
    vi.mocked(approveGatewayPairing).mockResolvedValue({ notification_status: 'sent' } as never);
    const user = userEvent.setup();
    render(<AccessTab gateway="GW-1" />);
    await user.click(await screen.findByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(toast.message).not.toHaveBeenCalled();
  });

  it('declines a waiting request', async () => {
    vi.mocked(revokeGatewayAccessEntry).mockResolvedValue({ name: 'GAE-1', state: 'Revoked' });
    const user = userEvent.setup();
    render(<AccessTab gateway="GW-1" />);
    await user.click(await screen.findByRole('button', { name: 'Decline' }));
    expect(revokeGatewayAccessEntry).toHaveBeenCalledWith('GAE-1');
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Request declined'));
  });

  it('offers Remove access, not Approve, for an approved group and Restore for a removed entry', async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([entry({ state: 'Approved', entry_type: 'Room', approved_by: 'admin@example.com', display_label: 'Team' })] as never);
    render(<AccessTab gateway="GW-1" />);
    await user.click(await screen.findByRole('tab', { name: 'Approved' }));
    expect(await screen.findByText('Group')).toBeInTheDocument();
    expect(screen.getByText('by admin@example.com')).toBeInTheDocument();
    expect(screen.getByText('Team')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Remove access' })).toBeInTheDocument();

    list.mockResolvedValue([entry({ state: 'Revoked' })] as never);
    await user.click(screen.getByRole('tab', { name: 'Removed' }));
    expect(await screen.findByRole('button', { name: 'Restore access' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove access' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
  });

  it('asks before removing access and says they can ask again', async () => {
    vi.mocked(revokeGatewayAccessEntry).mockResolvedValue({ name: 'GAE-1', state: 'Revoked' });
    list.mockResolvedValue([entry({ state: 'Approved' })] as never);
    const user = userEvent.setup();
    render(<AccessTab gateway="GW-1" />);
    await user.click(await screen.findByRole('tab', { name: 'Approved' }));
    await user.click(await screen.findByRole('button', { name: 'Remove access' }));
    expect(screen.getByText(/can ask for access again after a day/)).toBeInTheDocument();
    expect(revokeGatewayAccessEntry).not.toHaveBeenCalled();
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Remove access' }));
    await waitFor(() => expect(revokeGatewayAccessEntry).toHaveBeenCalledWith('GAE-1'));
    expect(toast.success).toHaveBeenCalledWith('Access removed');
  });

  it('blocks after confirming, and unblocks without asking', async () => {
    vi.mocked(blockGatewayAccessEntry).mockResolvedValue({ name: 'GAE-1', state: 'Blocked' });
    vi.mocked(unblockGatewayAccessEntry).mockResolvedValue({ name: 'GAE-1', state: 'Revoked' });
    const user = userEvent.setup();
    render(<AccessTab gateway="GW-1" />);
    await user.click(await screen.findByRole('button', { name: 'Block' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Block' }));
    await waitFor(() => expect(blockGatewayAccessEntry).toHaveBeenCalledWith('GAE-1'));

    list.mockResolvedValue([entry({ state: 'Blocked', revoked_by: 'admin@example.com' })] as never);
    await user.click(screen.getByRole('tab', { name: 'Blocked' }));
    await user.click(await screen.findByRole('button', { name: 'Unblock' }));
    await waitFor(() => expect(unblockGatewayAccessEntry).toHaveBeenCalledWith('GAE-1'));
  });

  it('restores a removed person and warns when the welcome was not sent', async () => {
    vi.mocked(restoreGatewayAccessEntry).mockResolvedValue({ name: 'GAE-1', state: 'Approved', notification_status: 'welcome message not sent' });
    list.mockResolvedValue([entry({ state: 'Revoked' })] as never);
    const user = userEvent.setup();
    render(<AccessTab gateway="GW-1" />);
    await user.click(await screen.findByRole('tab', { name: 'Removed' }));
    await user.click(await screen.findByRole('button', { name: 'Restore access' }));
    await waitFor(() => expect(restoreGatewayAccessEntry).toHaveBeenCalledWith('GAE-1'));
    expect(toast.success).toHaveBeenCalledWith('Access restored');
    expect(toast.message).toHaveBeenCalledWith('The welcome message could not be sent.');
  });

  it('opted-out people have no actions', async () => {
    list.mockResolvedValue([entry({ state: 'Opted out' })] as never);
    const user = userEvent.setup();
    render(<AccessTab gateway="GW-1" />);
    await user.click(await screen.findByRole('tab', { name: 'Opted out' }));
    await screen.findByText('15551234567');
    const row = screen.getByText('15551234567').closest('tr')!;
    expect(within(row).queryAllByRole('button')).toHaveLength(0);
  });

  it('adds a number by hand', async () => {
    vi.mocked(addGatewayAccessEntry).mockResolvedValue({ name: 'GAE-9', state: 'Approved', external_id: '919876543210' });
    const user = userEvent.setup();
    render(<AccessTab gateway="GW-1" />);
    await user.click(await screen.findByRole('button', { name: 'Add number' }));
    const dialog = screen.getByRole('dialog');
    await user.type(within(dialog).getByLabelText('Phone number'), '919876543210');
    await user.type(within(dialog).getByLabelText('Name (optional)'), 'Riya');
    await user.click(within(dialog).getByRole('button', { name: 'Add number' }));
    await waitFor(() =>
      expect(addGatewayAccessEntry).toHaveBeenCalledWith({ gateway: 'GW-1', externalId: '919876543210', displayLabel: 'Riya' }),
    );
  });

  it('shows the error with a retry when the list fails', async () => {
    list.mockRejectedValueOnce(new Error('Permission denied'));
    const user = userEvent.setup();
    render(<AccessTab gateway="GW-1" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Permission denied');
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('15551234567')).toBeInTheDocument();
  });

  it('reports an action failure and keeps the row', async () => {
    vi.mocked(approveGatewayPairing).mockRejectedValue(new Error('Already handled'));
    const user = userEvent.setup();
    render(<AccessTab gateway="GW-1" />);
    await user.click(await screen.findByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Already handled'));
    expect(screen.getByText('15551234567')).toBeInTheDocument();
  });

  it('reloads for another gateway', async () => {
    const { rerender } = render(<AccessTab gateway="GW-1" />);
    await screen.findByText('15551234567');
    rerender(<AccessTab gateway="GW-2" />);
    await waitFor(() => expect(list).toHaveBeenLastCalledWith({ gateway: 'GW-2', state: 'Pending' }));
  });
});
