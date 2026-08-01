import { describe, it, expect, vi, beforeEach } from 'vitest';
import { forkConversation, type ForkMode } from './chatApi';

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }));

vi.mock('@/lib/frappe-sdk', () => ({
  db: {},
  call: {
    post: postMock,
  },
}));

describe('forkConversation', () => {
  beforeEach(() => {
    postMock.mockReset();
  });

  it('calls the fork_conversation endpoint with the correct payload', async () => {
    const mode: ForkMode = 'summary';
    postMock.mockResolvedValue({
      message: {
        success: true,
        conversation_id: 'CONV-FORK-001',
        title: 'Original Chat (Fork)',
      },
    });

    const result = await forkConversation({
      conversationId: 'CONV-001',
      mode,
      title: 'Custom Fork Title',
    });

    expect(postMock).toHaveBeenCalledWith('huf.ai.agent_chat.fork_conversation', {
      conversation_id: 'CONV-001',
      mode: 'summary',
      title: 'Custom Fork Title',
    });
    expect(result.success).toBe(true);
    expect(result.conversation_id).toBe('CONV-FORK-001');
    expect(result.title).toBe('Original Chat (Fork)');
  });

  it('works without an optional title', async () => {
    postMock.mockResolvedValue({
      message: {
        success: true,
        conversation_id: 'CONV-FORK-002',
        title: 'Untitled Chat (Fork)',
      },
    });

    const result = await forkConversation({
      conversationId: 'CONV-002',
      mode: 'full_history',
    });

    expect(postMock).toHaveBeenCalledWith('huf.ai.agent_chat.fork_conversation', {
      conversation_id: 'CONV-002',
      mode: 'full_history',
      title: undefined,
    });
    expect(result.title).toBe('Untitled Chat (Fork)');
  });
});
