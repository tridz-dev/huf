import { useEffect, useRef, type Dispatch, type SetStateAction } from 'react';
import {
  getAgentRunStatus,
  getPendingConversationRuns,
  type ChatMessage,
} from '@/services/chatApi';
import {
  applyPolledRunStatus,
  filterMessagesForConversation,
  hasStaleConversationItems,
  mergePendingRunsIntoMessages,
} from './chatMessageList.mappers';
import type { MessageType } from './types';

interface UsePendingRunHydrationOptions {
  chatId: string | null;
  conversationItems: ChatMessage[];
  initialLoading: boolean;
  setMessages: Dispatch<SetStateAction<MessageType[]>>;
}

/**
 * Hydrate pending Agent Run rows into the chat UI after reload or chat switch.
 * Immediately reconciles each open run via get_agent_run_status so the client
 * does not wait for the socket grace period.
 */
export function usePendingRunHydration({
  chatId,
  conversationItems,
  initialLoading,
  setMessages,
}: UsePendingRunHydrationOptions) {
  const hydratedChatRef = useRef<string | null>(null);
  const chatIdRef = useRef(chatId);
  chatIdRef.current = chatId;

  useEffect(() => {
    hydratedChatRef.current = null;
  }, [chatId]);

  useEffect(() => {
    if (!chatId || initialLoading) {
      return;
    }

    if (hasStaleConversationItems(conversationItems, chatId)) {
      return;
    }

    if (hydratedChatRef.current === chatId) {
      return;
    }

    const itemsForChat = filterMessagesForConversation(conversationItems, chatId);
    const targetChatId = chatId;
    let cancelled = false;

    const hydrate = async () => {
      const pendingRuns = await getPendingConversationRuns(targetChatId);
      if (cancelled || chatIdRef.current !== targetChatId) return;

      if (pendingRuns.length > 0) {
        setMessages((prev) =>
          mergePendingRunsIntoMessages(prev, pendingRuns, itemsForChat)
        );

        await Promise.all(
          pendingRuns.map(async (run) => {
            try {
              const status = await getAgentRunStatus(run.name);
              if (cancelled || chatIdRef.current !== targetChatId || !status?.status) {
                return;
              }
              setMessages((prev) => applyPolledRunStatus(prev, status, targetChatId));
            } catch (error) {
              console.error('Error reconciling pending agent run:', error);
            }
          })
        );
      }

      if (!cancelled && chatIdRef.current === targetChatId) {
        hydratedChatRef.current = targetChatId;
      }
    };

    void hydrate();

    return () => {
      cancelled = true;
    };
  }, [chatId, conversationItems, initialLoading, setMessages]);
}
