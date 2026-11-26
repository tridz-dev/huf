// @vitest-environment jsdom
// Reloading a conversation whose only runs were stopped while queued still shows the user's messages.
import { forwardRef } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { MessageType } from '../types';

vi.mock('@/lib/frappe-sdk', () => ({
  db: {
    getDocList: vi.fn().mockResolvedValue([{ name: 'r1', prompt: 'my question', creation: '2026-01-01 10:00:00' }]),
  },
}));
vi.mock('@/services/chatApi', () => ({
  getConversationMessages: vi.fn().mockResolvedValue({ data: [], hasMore: false }),
  getConversation: vi.fn().mockResolvedValue({}),
  getPendingConversationRuns: vi.fn().mockResolvedValue([]),
  getAgentRunStatus: vi.fn(),
  createAgentRunFeedback: vi.fn(),
  hostFromConversation: () => null,
}));
vi.mock('@/hooks/useChatSocket', () => ({ useChatSocket: vi.fn() }));
vi.mock('@/lib/clientToolDispatcher', () => ({ resetClientToolCallTracking: vi.fn() }));
vi.mock('../useChatAgentIdentity', () => ({ useChatAgentIdentity: () => ({ agentName: 'A' }) }));
vi.mock('../confirmation/useToolConfirmations', () => ({ useToolConfirmations: () => ({ confirmations: {} }) }));
vi.mock('../confirmation/PendingConfirmationCards', () => ({ PendingConfirmationCards: () => null }));
vi.mock('../realtime/useFrontendToolCall', () => ({ useFrontendToolCall: () => vi.fn() }));
vi.mock('../useRunStatusPolling', () => ({ useRunStatusPolling: vi.fn() }));
vi.mock('../useConversationTitleFallback', () => ({
  useConversationTitlePostSuccessFallback: vi.fn(),
  dispatchConversationTitleUpdated: vi.fn(),
}));
vi.mock('../useChatScrollToBottom', () => ({
  useChatScrollToBottom: () => ({ scrollContainerRef: { current: null }, scrollToBottomAfterPaint: vi.fn() }),
}));
vi.mock('../ChatInput', () => ({ ChatInput: forwardRef(() => null) }));
vi.mock('../EmptyChatState', () => ({ ColdStartHero: () => null, StarterPromptGrid: () => null }));
vi.mock('../OutputsCard', () => ({ OutputsCard: () => null }));
vi.mock('../ChatMessage', () => ({
  ChatMessage: ({ message }: { message: MessageType }) => <p>{message.error ?? message.versions[0].content}</p>,
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { ChatMessageList } from '../ChatMessageList';

describe('reload after stopping queued runs', () => {
  it('shows the user message and the cancelled state', async () => {
    vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} });
    render(
      <MemoryRouter>
        <ChatMessageList chatId="c1" />
      </MemoryRouter>,
    );
    expect(await screen.findByText('my question')).toBeInTheDocument();
    expect(screen.getByText('Cancelled by user')).toBeInTheDocument();
  });
});
