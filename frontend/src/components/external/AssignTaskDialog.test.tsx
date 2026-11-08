// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/external/agentsApi', () => ({
  assignExternalTask: vi.fn(() => Promise.resolve({ session: 'SESS-0001', seq: 1 })),
}));

import { assignExternalTask } from '@/services/external/agentsApi';
import { AssignTaskDialog } from './AssignTaskDialog';

describe('AssignTaskDialog', () => {
  beforeEach(() => {
    vi.mocked(assignExternalTask).mockClear();
  });

  it('sends the trimmed task for the connection and closes on success', async () => {
    const onOpenChange = vi.fn();
    render(
      <AssignTaskDialog
        open
        onOpenChange={onOpenChange}
        connection="EXT-0001"
        agentName="Support agent"
      />,
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('What should your connected app do?'), '  Summarise today\'s tickets  ');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(assignExternalTask).toHaveBeenCalledTimes(1);
    expect(assignExternalTask).toHaveBeenCalledWith('EXT-0001', "Summarise today's tickets");
  });

  it('keeps Send disabled while the task is empty', async () => {
    render(
      <AssignTaskDialog open onOpenChange={() => {}} connection="EXT-0001" agentName="Support agent" />,
    );

    expect(screen.getByRole('button', { name: 'Send' }).hasAttribute('disabled')).toBe(true);
    expect(assignExternalTask).not.toHaveBeenCalled();
  });
});
