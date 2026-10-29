// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../services/flowApi', () => ({
  getPendingApprovals: vi.fn(),
  approveFlowRun: vi.fn(),
  rejectFlowRun: vi.fn(),
}));
vi.mock('../contexts/UserContext', () => ({ useUser: () => ({ isAuthenticated: true }) }));
vi.mock('@/lib/serverTime', () => ({ formatAbsoluteTime: () => 'now', useSiteTimezone: () => 'UTC' }));
vi.mock('@/utils/time', () => ({ formatTimeAgo: () => 'just now' }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import { approveFlowRun, getPendingApprovals, rejectFlowRun } from '../services/flowApi';
import { ApprovalsBell } from './ApprovalsBell';

const item = (id: string) => ({
  flow_run_id: id, flow_id: 'flow-1', flow_name: 'Ship', current_node_id: 'ask', title: 'Approval Required',
  message: 'Ship it?', instructions: 'Ship it?', approval_type: 'role', started_at: null, waiting_since: null, view_link: '',
});

async function openBell() {
  render(<MemoryRouter><ApprovalsBell /></MemoryRouter>);
  await waitFor(() => expect(getPendingApprovals).toHaveBeenCalled());
  fireEvent.click(screen.getByTestId('flow-approvals-bell'));
}

describe('ApprovalsBell decisions', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows success only when the answer shows the run moved, and reads the list again', async () => {
    vi.mocked(getPendingApprovals).mockResolvedValueOnce([item('r1')]).mockResolvedValueOnce([item('r1')]).mockResolvedValue([]);
    vi.mocked(approveFlowRun).mockResolvedValue({ flow_run_id: 'r1', status: 'Success', current_node_id: 'done' });
    await openBell();
    fireEvent.click(await screen.findByTestId('flow-approve-r1'));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Approved. The flow will continue.'));
    expect(toast.error).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByTestId('flow-approval-r1')).toBeNull());
  });

  it('is an error, not a success, when the answer still shows the run waiting at the same step', async () => {
    vi.mocked(getPendingApprovals).mockResolvedValue([item('r1')]);
    vi.mocked(approveFlowRun).mockResolvedValue({ flow_run_id: 'r1', status: 'Waiting Approval', current_node_id: 'ask' });
    await openBell();
    fireEvent.click(await screen.findByTestId('flow-approve-r1'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Could not approve', expect.objectContaining({ description: expect.stringContaining('nothing was recorded') })));
    expect(toast.success).not.toHaveBeenCalled();
    // the list was read again after the answer (first read on mount, then on open, then after the decision)
    await waitFor(() => expect(vi.mocked(getPendingApprovals).mock.calls.length).toBeGreaterThanOrEqual(3));
  });

  it('shows the server refusal as an error and does not double-send while a decision is on its way', async () => {
    vi.mocked(getPendingApprovals).mockResolvedValue([item('r1')]);
    let release: (v: unknown) => void = () => {};
    vi.mocked(rejectFlowRun).mockImplementation(() => new Promise((resolve) => { release = resolve as (v: unknown) => void; }) as never);
    await openBell();
    const reject = await screen.findByTestId('flow-reject-r1');
    fireEvent.click(reject);
    fireEvent.click(reject);
    expect(rejectFlowRun).toHaveBeenCalledTimes(1);
    expect(reject).toBeDisabled();
    release({ flow_run_id: 'r1', status: 'Running', current_node_id: 'no' });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Rejected. The flow will follow its rejected path.'));
    await waitFor(() => expect(screen.getByTestId('flow-reject-r1')).not.toBeDisabled());
  });
});
