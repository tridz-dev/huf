// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { render, screen } from '@testing-library/react';

vi.mock('@/contexts/PermissionsContext', () => ({ useIsHufAdmin: () => true }));
vi.mock('@/services/channelsApi', () => ({ getConversation: vi.fn(), returnToAi: vi.fn(), closeConversation: vi.fn() }));
import { getConversation, returnToAi } from '@/services/channelsApi';
import { ConversationThread } from './ConversationThread';

beforeEach(() => {
  vi.mocked(getConversation).mockResolvedValue({
    ok: true,
    data: {
      conversation: { name: 'C1', contact_name: 'Asha', status: 'handed_off', handoff_doctype: 'HD Ticket', handoff_name: '42', within_24h: true },
      messages: [
        { direction: 'in', text: 'need help', creation: '2026-10-14 10:00:00', sent_by: 'customer', agent_run: 'R1', agent: null },
        { direction: 'out', text: 'on it', creation: '2026-10-14 10:01:00', sent_by: 'agent', agent_run: 'R1', agent: 'Support' },
      ],
      tool_calls: [{ name: 'T1', agent_run: 'R1', tool: 'handoff_to_human', status: 'Success', creation: '' }],
    },
  } as never);
  vi.mocked(returnToAi).mockResolvedValue({ ok: true, data: { conversation_status: 'ai' } } as never);
});

describe('ConversationThread', () => {
  it('shows tool-call chip, handoff chip and no composer', async () => {
    const { container } = render(<ConversationThread name="C1" />);
    expect(await screen.findByText('on it')).toBeTruthy();
    expect(screen.getByText(/handoff_to_human/)).toBeTruthy();
    const link = screen.getByRole('link', { name: /Open in Help Desk/ });
    expect(link.getAttribute('href')).toBe('/app/hd-ticket/42');
    expect(container.querySelector('textarea, input')).toBeNull();
  });

  it('Return to AI calls reply api', async () => {
    render(<ConversationThread name="C1" />);
    await userEvent.click(await screen.findByRole('button', { name: 'Return to AI' }));
    expect(returnToAi).toHaveBeenCalledWith('C1');
  });
});
