// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ searchFlowUsers: vi.fn(), checkFlowUsers: vi.fn() }));
vi.mock('@/services/flow/formOptionsApi', () => api);

import { ApproverUsersField } from './ApproverUsersField';

afterEach(cleanup);
beforeEach(() => {
  api.searchFlowUsers.mockReset();
  api.checkFlowUsers.mockReset();
  api.checkFlowUsers.mockResolvedValue([]);
});

describe('ApproverUsersField', () => {
  it('shows the address of each person and says who has no approver role yet', async () => {
    api.searchFlowUsers.mockResolvedValue([
      { name: 'ada@example.com', email: 'ada@example.com', full_name: 'Ada Lovelace', label: 'Ada Lovelace (ada@example.com)', has_approver_role: true },
      { name: 'bob@example.com', email: 'bob@example.com', full_name: 'Bob', label: 'Bob (bob@example.com)', has_approver_role: false },
    ]);
    render(<ApproverUsersField value={[]} onChange={() => undefined} testId="ap" Err={null} />);
    fireEvent.focus(screen.getByTestId('ap-search'));
    await screen.findByTestId('ap-option-ada@example.com');
    expect(screen.getByTestId('ap-option-ada@example.com').textContent).toContain('ada@example.com');
    expect(screen.queryByTestId('ap-norole-ada@example.com')).toBeNull();
    expect(screen.getByTestId('ap-norole-bob@example.com').textContent).toBe('Has no approver role yet');
  });

  it('does not look people up for a read-only viewer', async () => {
    render(<ApproverUsersField value={['ada@example.com']} onChange={() => undefined} testId="ap" Err={null} disabled />);
    await waitFor(() => expect(screen.getByTestId('ap-chip-ada@example.com')).toBeTruthy());
    expect(api.checkFlowUsers).not.toHaveBeenCalled();
    expect(api.searchFlowUsers).not.toHaveBeenCalled();
  });
});
