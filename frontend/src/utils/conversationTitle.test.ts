import { describe, it, expect } from 'vitest';
import { isDefaultConversationTitle } from './conversationTitle';

describe('isDefaultConversationTitle', () => {
  it('returns true for chat default titles', () => {
    expect(isDefaultConversationTitle('Chat with Demo Agent')).toBe(true);
    expect(isDefaultConversationTitle('Conversation with Demo Agent')).toBe(true);
    expect(isDefaultConversationTitle('Streaming chat with Demo Agent')).toBe(true);
  });

  it('returns false for custom titles', () => {
    expect(isDefaultConversationTitle('Invoice follow-up')).toBe(false);
    expect(isDefaultConversationTitle('')).toBe(false);
  });
});
