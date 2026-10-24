// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('@/services/solutionsApi', () => ({ simulateRoute: vi.fn() }));

import { simulateRoute } from '@/services/solutionsApi';
import { TestChat } from './TestChat';
import type { RouteDecision } from '@/types/solutions';

const mock = vi.mocked(simulateRoute);
const gateways = [{ name: 'gw1', label: 'Main', phone: '+1 555' }];
const labels = { bakery: 'Bakery', support: 'Support desk' };

function decision(over: Partial<RouteDecision> = {}): RouteDecision {
  return {
    solution: 'bakery', target_type: 'Agent', agent: 'Cake agent', flow: null, binding: 'b1',
    reason: 'keyword',
    pin: { solution: 'bakery', expires_at: new Date(Date.now() + 24 * 3_600_000 - 1000).toISOString() },
    trace: [{ k: 'skip', t: 'No referral tag' }, { k: 'win', t: 'Keyword cake matched' }],
    reply_text: null, ...over,
  };
}

function renderChat() {
  return render(<TestChat gateways={gateways} chips={['cake please', '1']} adChips={['promo']} solutionLabels={labels} />);
}
async function say(text: string) {
  fireEvent.change(screen.getByLabelText('Message'), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
}

describe('TestChat', () => {
  beforeEach(() => {
    mock.mockReset();
  });
  afterEach(cleanup);

  it('renders the decision and trace', async () => {
    mock.mockResolvedValue(decision());
    renderChat();
    await say('cake');
    expect(await screen.findByText('Routed to Bakery')).toBeInTheDocument();
    expect(screen.getByText('Bakery · Cake agent')).toBeInTheDocument();
    expect(screen.getByText('Keyword cake matched').closest('li')).toHaveAttribute('data-kind', 'win');
    expect(screen.getByText('No referral tag').closest('li')).toHaveAttribute('data-kind', 'skip');
    expect(mock.mock.calls[0][0]).toMatchObject({ gateway: 'gw1', text: 'cake', state: {} });
  });

  it('shows the pin after a routed decision and feeds it back', async () => {
    mock.mockResolvedValue(decision());
    renderChat();
    expect(screen.getByText(/No pin yet/)).toBeInTheDocument();
    await say('cake');
    expect(await screen.findByText('24h left')).toBeInTheDocument();
    await say('again');
    await waitFor(() => expect(mock).toHaveBeenCalledTimes(2));
    expect(mock.mock.calls[1][0].state.pin).toEqual({ solution: 'bakery', hours_left: 24 });
  });

  it('expires the pin with Skip 25 hours', async () => {
    mock.mockResolvedValue(decision());
    renderChat();
    await say('cake');
    fireEvent.click(await screen.findByRole('button', { name: 'Skip 25 hours' }));
    expect(screen.getByText('expired')).toBeInTheDocument();
    expect(screen.getByText(/pin expired/)).toBeInTheDocument();
    await say('hi');
    await waitFor(() => expect(mock).toHaveBeenCalledTimes(2));
    expect(mock.mock.calls[1][0].state.pin).toEqual({ solution: 'bakery', hours_left: 0 });
  });

  it('hand-off updates the local pin and trace', async () => {
    mock.mockResolvedValue(decision());
    renderChat();
    await say('cake');
    await screen.findByText('24h left');
    fireEvent.change(screen.getByLabelText('Hand off to'), { target: { value: 'support' } });
    fireEvent.click(screen.getByRole('button', { name: 'Hand off' }));
    expect(screen.getByText('Handed off from Bakery to Support desk')).toBeInTheDocument();
    expect(screen.getByText('Handoff rewrote the pin: Bakery → Support desk')).toBeInTheDocument();
    const card = screen.getByText('Chat pin').closest('div')!;
    expect(within(card).getByText('Support desk', { selector: '[class*=badge], div, span' })).toBeInTheDocument();
    expect(mock).toHaveBeenCalledTimes(1);
  });

  it('passes keyword_beats_pin in the request', async () => {
    mock.mockResolvedValue(decision());
    renderChat();
    fireEvent.click(screen.getByLabelText(/Keyword beats the pin/));
    await say('cake');
    await waitFor(() => expect(mock).toHaveBeenCalled());
    expect(mock.mock.calls[0][0].keyword_beats_pin).toBe(true);
  });

  it('shows the triage prompt, then sends triage_pending on the answer', async () => {
    mock.mockResolvedValueOnce(
      decision({ solution: null, reason: 'triage_prompt', pin: null, reply_text: 'Reply 1 for cakes, 2 for support', trace: [] }),
    );
    mock.mockResolvedValueOnce(decision({ reason: 'triage_answer' }));
    renderChat();
    await say('hello');
    expect(await screen.findByText('Reply 1 for cakes, 2 for support')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '1' }));
    await waitFor(() => expect(mock).toHaveBeenCalledTimes(2));
    expect(mock.mock.calls[1][0]).toMatchObject({ text: '1', state: { triage_pending: true } });
  });

  it('sends the ad tag as ref', async () => {
    mock.mockResolvedValue(decision({ reason: 'referral' }));
    renderChat();
    fireEvent.click(screen.getByRole('button', { name: 'Tap ad promo' }));
    await waitFor(() => expect(mock).toHaveBeenCalled());
    expect(mock.mock.calls[0][0]).toMatchObject({ ref: 'promo', text: '' });
    expect(screen.getByText('(taps ad, tag promo)')).toBeInTheDocument();
  });

  it('shows an error message', async () => {
    mock.mockRejectedValue(new Error('Boom'));
    renderChat();
    await say('cake');
    const a = await screen.findByRole('alert');
    expect(a.textContent).toContain('Boom');
  });

  it('Clear chat resets everything', async () => {
    mock.mockResolvedValue(decision());
    renderChat();
    await say('cake');
    await screen.findByText('24h left');
    fireEvent.click(screen.getByRole('button', { name: 'Clear chat' }));
    expect(screen.getByText('No messages yet')).toBeInTheDocument();
    expect(screen.getByText(/No pin yet/)).toBeInTheDocument();
    expect(screen.queryByText('Keyword cake matched')).toBeNull();
  });
});
