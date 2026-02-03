import { useEffect, useState } from 'react';

import { getConversation } from '@/services/chatApi';
import { getAgent } from '@/services/agentApi';

export function useChatAgentIdentity(chatId: string | null, searchParams: URLSearchParams) {
  const [agentName, setAgentName] = useState<string>('');
  const [agentColor, setAgentColor] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadFromConversation(conversationId: string) {
      try {
        const conversation = await getConversation(conversationId);
        if (!conversation?.agent) return;

        if (!cancelled) setAgentName(conversation.agent);

        try {
          const agentData = await getAgent(conversation.agent);
          if (!cancelled) setAgentColor(agentData.agent_color || null);
        } catch (error) {
          console.error('Failed to load agent color', error);
          if (!cancelled) setAgentColor(null);
        }
      } catch (error) {
        console.error('Failed to load conversation agent', error);
      }
    }

    async function loadFromQueryParam() {
      const agentFromQuery = searchParams.get('agent') ?? '';
      if (!cancelled) setAgentName(agentFromQuery);

      if (!agentFromQuery) {
        if (!cancelled) setAgentColor(null);
        return;
      }

      try {
        const agentData = await getAgent(agentFromQuery);
        if (!cancelled) setAgentColor(agentData.agent_color || null);
      } catch (error) {
        console.error('Failed to load agent color', error);
        if (!cancelled) setAgentColor(null);
      }
    }

    if (chatId) loadFromConversation(chatId);
    else loadFromQueryParam();

    return () => {
      cancelled = true;
    };
  }, [chatId, searchParams]);

  return { agentName, agentColor };
}

