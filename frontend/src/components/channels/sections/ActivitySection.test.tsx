// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/layouts/PageFrame', () => ({ PageFrame: ({ children, actions }: never) => <div>{actions}{children}</div> }));
vi.mock('@/components/whatsapp/MessageDetailSheet', () => ({
  MessageDetailSheet: ({ item }: { item: { name: string } | null }) => (item ? <div>detail {item.name}</div> : null),
  StatusTicks: () => null,
  ErrorBadge: () => null,
}));
vi.mock('@/services/whatsappApi', async (orig) => ({
  ...(await orig<typeof import('@/services/whatsappApi')>()),
  listMessageLog: vi.fn(),
  listMessageLogFilters: vi.fn(),
}));
vi.mock('@/services/channelsApi', () => ({ listConversations: vi.fn(), getConversation: vi.fn(), returnToAi: vi.fn(), closeConversation: vi.fn() }));
vi.mock('../useChannelGateway', () => ({ useChannelGateway: () => 'GW-1', useChannel: () => 'whatsapp' }));
import { listMessageLog, listMessageLogFilters } from '@/services/whatsappApi';
import { listConversations } from '@/services/channelsApi';
import ActivitySection from './ActivitySection';

const item = (name: string, event: string) => ({
  name, message_id: null, direction: 'in', phone: '+1555', profile_name: null, content_type: 'text', text: `msg ${name}`,
  status: 'failed', error: null, template: null, creation: '2026-10-14 10:00:00', gateway: 'GW-1', agent: null, agent_run: null, event, sent_by: 'customer',
});

beforeEach(() => {
  vi.clearAllMocks();
  Element.prototype.scrollIntoView = vi.fn();
  vi.mocked(listMessageLogFilters).mockResolvedValue({ success: true, statuses: [], agents: [], templates: [] } as never);
  vi.mocked(listMessageLog).mockResolvedValue({ success: true, items: [item('m1', 'EV-1')], next_cursor: null, has_more: false } as never);
  vi.mocked(listConversations).mockResolvedValue({
    ok: true,
    data: { has_more: false, items: [{ name: 'C1', contact_name: 'Asha', last_message_preview: 'hello there', status: 'handed_off', within_24h: true, modified: '2026-10-14 10:00:00' }] },
  } as never);
});

describe('ActivitySection', () => {
  it('has no send panel and opens ?event= deep link', async () => {
    render(<MemoryRouter initialEntries={['/?send=1&event=EV-1']}><ActivitySection /></MemoryRouter>);
    await userEvent.click(screen.getByRole('button', { name: 'Messages' }));
    await waitFor(() => expect(screen.getByText('detail m1')).toBeTruthy());
    expect(screen.queryByText(/send a message/i)).toBeNull();
  });

  it('defaults to conversations', async () => {
    render(<MemoryRouter><ActivitySection /></MemoryRouter>);
    expect(await screen.findByText('Asha')).toBeTruthy();
    expect(screen.getAllByText('Handed off').length).toBeGreaterThan(1);
    expect(screen.getByText('24h')).toBeTruthy();
  });
});

describe('conversation filter', () => {
  it('passes status to the list call', async () => {
    render(<MemoryRouter><ActivitySection /></MemoryRouter>);
    await screen.findByText('Asha');
    await userEvent.click(screen.getByRole('button', { name: 'Closed' }));
    await waitFor(() => expect(listConversations).toHaveBeenLastCalledWith('GW-1', { status: 'closed' }));
  });
});
