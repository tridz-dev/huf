import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type { ConversationAnalyticsResponse } from '@/types/conversationAnalytics.types';

export async function getConversationAnalytics(
  conversation: string
): Promise<ConversationAnalyticsResponse | null> {
  try {
    const result = await call.get('huf.ai.agent_conversation_analytics_api.get_conversation_analytics', {
      conversation,
    });
    return result.message as ConversationAnalyticsResponse;
  } catch (error) {
    handleFrappeError(error, 'Error fetching conversation analytics');
    return null;
  }
}
