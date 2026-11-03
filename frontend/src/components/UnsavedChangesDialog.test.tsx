// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider, useBlocker, useNavigate } from 'react-router-dom';

import { UnsavedChangesDialog } from '@/components/UnsavedChangesDialog';

function AgentEditRoute() {
  const blocker = useBlocker(true);
  const navigate = useNavigate();

  return (
    <>
      <p>Agent edit page</p>
      <button type="button" onClick={() => navigate(-1)}>
        Back
      </button>
      <UnsavedChangesDialog blocker={blocker} />
    </>
  );
}

function renderAgentEditRoute() {
  const router = createMemoryRouter(
    [
      { path: '/agents', element: <p>Agents list</p> },
      { path: '/agents/:id', element: <AgentEditRoute /> },
    ],
    {
      initialEntries: ['/agents', '/agents/agent-1'],
      initialIndex: 1,
    }
  );

  return render(<RouterProvider router={router} />);
}

describe('UnsavedChangesDialog', () => {
  it('proceeds with Agent edit-page Back navigation when Leave is selected', async () => {
    const user = userEvent.setup();
    renderAgentEditRoute();

    await user.click(screen.getByRole('button', { name: 'Back' }));
    expect(await screen.findByText(/Leave without saving/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Leave' }));

    expect(await screen.findByText('Agents list')).toBeInTheDocument();
    expect(screen.queryByText('Agent edit page')).not.toBeInTheDocument();
  });

  it('resets the blocked navigation and stays on the Agent edit page when Cancel is selected', async () => {
    const user = userEvent.setup();
    renderAgentEditRoute();

    await user.click(screen.getByRole('button', { name: 'Back' }));
    expect(await screen.findByText(/Leave without saving/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(await screen.findByText('Agent edit page')).toBeInTheDocument();
    expect(screen.queryByText(/Leave without saving/)).not.toBeInTheDocument();
    expect(screen.queryByText('Agents list')).not.toBeInTheDocument();
  });
});
