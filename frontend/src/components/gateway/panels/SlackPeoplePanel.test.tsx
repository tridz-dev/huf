// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/gateways/slackIdentityApi', () => ({
  listSlackLinks: vi.fn(),
  linkSlackUser: vi.fn(),
  unlinkSlackUser: vi.fn(),
}));

import { listSlackLinks, linkSlackUser, unlinkSlackUser } from '@/services/gateways/slackIdentityApi';
import { SlackPeoplePanel } from './SlackPeoplePanel';

const link = {
  name: 'GIL-1',
  gateway: 'gw',
  team_id: 'T1',
  external_id: 'U1',
  user: 'a@b.com',
  state: 'Linked',
  source: 'Admin',
  display_label: 'Alice',
  linked_at: null,
  linked_by: null,
};

const renderPanel = () => render(<SlackPeoplePanel gateway={{ name: 'gw' } as never} />);

describe('SlackPeoplePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listSlackLinks).mockResolvedValue([link]);
  });

  it('lists links with state', async () => {
    renderPanel();
    expect(await screen.findByText('Alice')).toBeTruthy();
    expect(screen.getByText('Linked')).toBeTruthy();
  });

  it('links a person', async () => {
    renderPanel();
    await screen.findByText('Alice');
    await userEvent.type(screen.getByLabelText('Workspace ID'), 'T1');
    await userEvent.type(screen.getByLabelText('Slack user ID'), 'U2');
    await userEvent.type(screen.getByLabelText('Huf user (email)'), 'c@d.com');
    await userEvent.click(screen.getByRole('button', { name: 'Link person' }));
    await waitFor(() => expect(linkSlackUser).toHaveBeenCalledWith('gw', 'T1', 'U2', 'c@d.com'));
  });

  it('unlinks a person', async () => {
    renderPanel();
    await userEvent.click(await screen.findByRole('button', { name: /Remove link for Alice/ }));
    await waitFor(() => expect(unlinkSlackUser).toHaveBeenCalledWith('GIL-1'));
  });
});
