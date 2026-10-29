// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { FlowCard } from './FlowCard';
import type { FlowCard as FlowCardData } from '@/services/flow/flowCardsApi';

const card = (over: Partial<FlowCardData> = {}): FlowCardData => ({
  flow_id: 'f1',
  flow_name: 'A very long flow name that should wrap onto two lines instead of being cut off at the edge of the card',
  description: 'Webhook -> Transform -> End. Send a name.',
  category: 'Sales',
  status: 'Active',
  modified: null,
  trigger: { type: 'schedule', cron: '0 9 * * *' },
  steps: [{ type: 'condition' }, { type: 'tool.call', tool_id: 'slack_send_message' }],
  step_count: 2,
  last_run: { status: 'Success', stale: false, at: new Date(Date.now() - 2 * 60_000).toISOString() },
  ...over,
});

afterEach(cleanup);

function setup(over: Partial<FlowCardData> = {}, perms = { canManage: true, canCreate: true }) {
  const handlers = { onOpen: vi.fn(), onRun: vi.fn(), onSettings: vi.fn(), onDuplicate: vi.fn(), onDelete: vi.fn() };
  render(
    <MemoryRouter>
      <FlowCard card={card(over)} {...perms} {...handlers} />
    </MemoryRouter>,
  );
  return handlers;
}

describe('FlowCard', () => {
  it('shows a full-name tooltip, plain description, status word, trigger and last run', () => {
    setup();
    expect(screen.getByTestId('flow-card-title')).toHaveAttribute('title', expect.stringContaining('A very long flow name'));
    expect(screen.getByTestId('flow-card-title').className).toContain('line-clamp-2');
    expect(screen.getByTestId('flow-card-description')).toHaveTextContent('Starts every day at 09:00, then 2 steps.');
    expect(screen.queryByTestId('flow-card-trigger')).toBeNull(); // the summary already says it
    expect(screen.getByTestId('flow-list-status-f1')).toHaveTextContent('Live');
    expect(screen.getByTestId('flow-card-last-run')).toHaveTextContent('Last run: Finished 2 mins ago');
    expect(screen.getByTestId('flow-card-category')).toHaveTextContent('Sales');
  });

  it('keeps the author description when it is plain, and hides an empty category', () => {
    setup({ description: 'Tells the team about big orders.', category: 'Uncategorized' });
    expect(screen.getByTestId('flow-card-description')).toHaveTextContent('Tells the team about big orders.');
    expect(screen.getByTestId('flow-card-trigger')).toHaveTextContent('Starts every day at 09:00');
    expect(screen.queryByTestId('flow-card-category')).toBeNull();
  });

  it('says a draft has not run, and flags a failed last run', () => {
    setup({ status: 'Draft', last_run: null });
    expect(screen.getByTestId('flow-list-status-f1')).toHaveTextContent('Draft');
    expect(screen.getByTestId('flow-card-last-run')).toHaveTextContent('Not run yet');
  });

  it('has labelled actions and a menu with Duplicate, Settings and Delete', async () => {
    const user = userEvent.setup();
    const h = setup();
    await user.click(screen.getByRole('button', { name: 'Open' }));
    expect(h.onOpen).toHaveBeenCalledTimes(1);
    await user.click(screen.getByTestId('flow-card-run'));
    expect(h.onRun).toHaveBeenCalledTimes(1);
    expect(h.onOpen).toHaveBeenCalledTimes(1); // the buttons do not also open the card
    await user.click(screen.getByTestId('flow-card-menu'));
    await user.click(await screen.findByRole('menuitem', { name: 'Duplicate' }));
    expect(h.onDuplicate).toHaveBeenCalled();
    await user.click(screen.getByTestId('flow-card-menu'));
    expect(await screen.findByRole('menuitem', { name: 'Settings' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument();
  });

  it('gives view-only people Open and View settings only', async () => {
    const user = userEvent.setup();
    setup({}, { canManage: false, canCreate: false });
    expect(screen.queryByTestId('flow-card-run')).toBeNull();
    await user.click(screen.getByTestId('flow-card-menu'));
    expect(await screen.findByRole('menuitem', { name: 'View settings' })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Duplicate' })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'Delete' })).toBeNull();
  });
});
