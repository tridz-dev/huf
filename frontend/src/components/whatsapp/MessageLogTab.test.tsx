// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';

// jsdom has no top layer; answering ':modal' directly keeps Radix Select opening fast.
const originalMatches = Element.prototype.matches;
Element.prototype.matches = function (this: Element, selector: string) {
  return selector === ':modal' ? false : originalMatches.call(this, selector);
};

vi.mock('./TemplateSend', () => ({ TemplateSend: () => null }));
vi.mock('./MessageDetailSheet', () => ({
  MessageDetailSheet: ({ item }: { item: { name: string } | null }) => (item ? <div>detail {item.name}</div> : null),
  StatusTicks: () => null,
}));
vi.mock('@/services/whatsappApi', async (orig) => ({
  ...(await orig<typeof import('@/services/whatsappApi')>()),
  listMessageLog: vi.fn(),
  listMessageLogFilters: vi.fn(),
}));
import { listMessageLog, listMessageLogFilters } from '@/services/whatsappApi';
import { MessageLogTab } from './MessageLogTab';

const item = (name: string, event: string | null) => ({
  name, message_id: null, direction: 'in', phone: '+1555', profile_name: null, content_type: 'text', text: `msg ${name}`,
  status: 'failed', error: null, template: null, creation: '2026-10-14 10:00:00', gateway: 'GW-1', agent: null, agent_run: null, event, sent_by: 'customer',
});

function Search() {
  return <output data-testid="search">{useLocation().search}</output>;
}
const open = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <MessageLogTab gateway="GW-1" bridgeAvailable />
      <Search />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  Element.prototype.scrollIntoView = vi.fn();
  vi.mocked(listMessageLogFilters).mockResolvedValue({ success: true, statuses: [], agents: [], templates: [] } as never);
  vi.mocked(listMessageLog).mockResolvedValue({ success: true, items: [item('m1', 'EV-1'), item('m2', null)], next_cursor: null, has_more: false } as never);
});

describe('MessageLogTab one-shot links', () => {
  it('stays collapsed without ?send=1', async () => {
    open('/?tab=messages');
    await screen.findByText('msg m1');
    expect(screen.queryByLabelText('To', { selector: '#whatsapp-send-to' })).toBeNull();
  });

  it('?send=1 opens the send panel and clears the param', async () => {
    open('/?tab=messages&gateway=GW-1&send=1');
    expect(await screen.findByLabelText('To', { selector: '#whatsapp-send-to' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('search')).not.toHaveTextContent('send='));
    expect(screen.getByTestId('search')).toHaveTextContent('gateway=GW-1');
  });

  it('?event= opens and highlights the matching row', async () => {
    open('/?tab=messages&event=EV-1');
    expect(await screen.findByText('detail m1')).toBeInTheDocument();
    expect(document.querySelector('[data-event="EV-1"]')).toHaveAttribute('aria-current', 'true');
    expect(screen.queryByText(/Event not in the loaded messages/)).toBeNull();
  });

  it('?event= that is not in the loaded page shows a hint', async () => {
    open('/?tab=messages&event=EV-404');
    expect(await screen.findByText(/Event not in the loaded messages/)).toBeInTheDocument();
    expect(screen.queryByText(/^detail/)).toBeNull();
  });
  it('filter placeholders use correct plurals', async () => {
    vi.mocked(listMessageLogFilters).mockResolvedValue({
      success: true, statuses: ['sent'], agents: [], templates: [],
    } as never);
    open('/?tab=messages');
    expect(await screen.findByText('All statuses')).toBeInTheDocument();
    expect(screen.getByText('All directions')).toBeInTheDocument();
    expect(screen.getByText('All agents')).toBeInTheDocument();
    expect(screen.getByText('All templates')).toBeInTheDocument();
    expect(screen.queryByText(/statuss/)).toBeNull();
  });

  it('shows a relative time with the full date on hover', async () => {
    open('/?tab=messages');
    await screen.findByText('msg m1');
    expect(screen.queryByText('2026-10-14 10:00:00')).toBeNull();
    expect(document.querySelector('time[title]')).not.toBeNull();
  });

  it('has no Gateway column and rows open with the keyboard', async () => {
    open('/?tab=messages');
    await screen.findByText('msg m1');
    expect(screen.queryByRole('columnheader', { name: 'Gateway' })).toBeNull();
    const row = screen.getAllByRole('row')[1];
    expect(row).toHaveAttribute('tabindex', '0');
    row.focus();
    await userEvent.keyboard('{Enter}');
    expect(await screen.findByText('detail m1')).toBeInTheDocument();
  });
});

describe('MessageLogTab solution column', () => {
  it('shows a Solution column and passes the filter to the API', async () => {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
  Element.prototype.scrollIntoView = () => {};
    vi.mocked(listMessageLogFilters).mockResolvedValue({ success: true, statuses: [], agents: [], templates: [], solutions: [{ name: 'S1', title: 'Orders' }] } as never);
    vi.mocked(listMessageLog).mockResolvedValue({
      success: true, items: [{ ...item('m1', null), solution: { name: 'S1', title: 'Orders' } }, { ...item('m2', null), solution: null }], next_cursor: null, has_more: false,
    } as never);
    open('/?tab=messages');
    await screen.findByText('msg m1');
    expect(screen.getByRole('columnheader', { name: 'Solution' })).toBeInTheDocument();
    expect(screen.getByText('Orders')).toBeInTheDocument();
    await userEvent.click(await screen.findByLabelText('Solution'));
    await userEvent.click(await screen.findByText('Orders', { selector: '[role="option"] *, [role="option"]' }));
    await waitFor(() => expect(vi.mocked(listMessageLog)).toHaveBeenLastCalledWith('GW-1', expect.objectContaining({ solution: 'S1' })));
  });

  it('hides the column when rows carry no solution field', async () => {
    open('/?tab=messages');
    await screen.findByText('msg m1');
    expect(screen.queryByRole('columnheader', { name: 'Solution' })).toBeNull();
  });
});
