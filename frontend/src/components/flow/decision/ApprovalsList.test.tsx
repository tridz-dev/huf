// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { PendingApproval } from '@/services/flowApi';
import { ApprovalsList } from './ApprovalsList';

const item = (run: string, message: string): PendingApproval =>
  ({ flow_run_id: run, flow_id: 'order', flow_name: 'Order approval', current_node_id: 'n', title: '', message, instructions: '', approval_type: 'role', started_at: null, waiting_since: null, view_link: '' }) as unknown as PendingApproval;

const renderList = (approvals: PendingApproval[]) =>
  render(<MemoryRouter><ApprovalsList approvals={approvals} deciding={new Set()} onDecide={() => {}} /></MemoryRouter>);

describe('ApprovalsList', () => {
  it('shows an identical sentence once under the heading, keeping Approve and Reject per row', () => {
    renderList([item('a', 'Approve the order?'), item('b', 'Approve the order?')]);
    expect(screen.getByTestId('flow-approval-group-heading').textContent).toBe('2 waiting: Order approval');
    expect(screen.getAllByText('Approve the order?')).toHaveLength(1);
    expect(screen.getByTestId('flow-approve-a')).toBeTruthy();
    expect(screen.getByTestId('flow-reject-b')).toBeTruthy();
  });
  it('keeps each row its own text when the sentences differ', () => {
    renderList([item('a', 'Approve order 1?'), item('b', 'Approve order 2?')]);
    expect(screen.getByTestId('flow-approval-message-a').textContent).toBe('Approve order 1?');
    expect(screen.getByTestId('flow-approval-message-b').textContent).toBe('Approve order 2?');
  });
});
