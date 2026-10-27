// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('./TemplateSend', () => ({ TemplateSend: ({ gateway, to }: { gateway?: string; to: string }) => <div>send template {gateway} {to}</div> }));
import type { MessageLogItem } from '@/services/whatsappApi';
import { ErrorBadge, MessageDetailSheet, StatusTicks } from './MessageDetailSheet';

const item = (over: Partial<MessageLogItem> = {}): MessageLogItem => ({
  name: 'WM-1', message_id: 'wamid.ABC', direction: 'out', phone: '+15551234567', profile_name: null, content_type: 'text',
  text: 'Your order shipped', status: 'delivered', error: null, template: null, creation: '2026-10-21 10:00:00', gateway: 'GW-1',
  agent: null, agent_run: null, event: null, sent_by: 'agent', ...over,
});

const open = (i: MessageLogItem | null, extra: { agentTitle?: string; gateway?: string } = {}) => {
  const onClose = vi.fn();
  render(<MemoryRouter><MessageDetailSheet item={i} onClose={onClose} {...extra} /></MemoryRouter>);
  return onClose;
};

describe('MessageDetailSheet', () => {
  it('renders nothing without an item', () => {
    open(null);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows an outgoing message with its timeline and fields', () => {
    open(item({ template: 'order_update' }), { agentTitle: 'Support bot', gateway: 'GW-1' });
    expect(screen.getByText('Message sent')).toBeInTheDocument();
    expect(screen.getByText('Your order shipped')).toBeInTheDocument();
    expect(screen.getByText('Sent')).toBeInTheDocument();
    expect(screen.getByText('Delivered')).toBeInTheDocument();
    expect(screen.getByText('Read')).toBeInTheDocument();
    expect(screen.getByText('order_update')).toBeInTheDocument();
    expect(screen.getByText('Support bot')).toBeInTheDocument();
    expect(screen.getByText('wamid.ABC')).toBeInTheDocument();
    expect(screen.getByText('send template GW-1 +15551234567')).toBeInTheDocument();
  });

  it('shows an incoming message with ticks, the profile name and no timeline', () => {
    open(item({ direction: 'in', status: 'received', profile_name: 'Ann', sent_by: 'customer', message_id: null }));
    expect(screen.getByText('Message received')).toBeInTheDocument();
    expect(screen.getByText('Ann · +15551234567')).toBeInTheDocument();
    expect(screen.getByText('Received')).toBeInTheDocument();
    expect(screen.queryByRole('list')).toBeNull();
    expect(screen.getByText('Customer')).toBeInTheDocument();
    expect(screen.queryByText('None')).toBeNull();
    expect(screen.getAllByText('\u2014').length).toBe(2);
  });

  it('falls back to a placeholder for non-text content', () => {
    open(item({ text: null, content_type: 'image' }));
    expect(screen.getByText('[image]')).toBeInTheDocument();
  });

  it('explains a failed delivery in plain words', async () => {
    open(item({ status: 'failed', error: 'error 131047: Re-engagement message' }));
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Window closed');
    expect(alert).toHaveTextContent('131047');
    expect(alert).toHaveTextContent('Send an approved template instead');
    expect(alert).not.toHaveTextContent('error 131047: Re-engagement message');
    await userEvent.click(screen.getByText('Technical details'));
    expect(alert).toHaveTextContent('error 131047: Re-engagement message');
    expect(screen.getByText('Failed')).toBeInTheDocument();
    expect(screen.queryByText('Read')).toBeNull();
  });

  it('links to the agent run and gateway event only when present', () => {
    open(item({ agent_run: 'run 1', event: 'EV-1' }));
    expect(screen.getByRole('link', { name: 'Open agent run' })).toHaveAttribute('href', '/executions/run%201');
    expect(screen.getByRole('link', { name: 'View full event record' })).toHaveAttribute('href', '/app/gateway-event/EV-1');
  });

  it('hides the links when there is no run or event', () => {
    open(item());
    expect(screen.queryByRole('link', { name: 'Open agent run' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'View full event record' })).toBeNull();
  });
});

describe('small pieces', () => {
  it('ErrorBadge renders nothing without an error', () => {
    const { container } = render(<ErrorBadge error="" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('StatusTicks labels the status', () => {
    render(<StatusTicks status="read" />);
    expect(screen.getByText('Read')).toBeInTheDocument();
  });
});
