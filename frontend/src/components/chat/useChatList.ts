import { useEffect, useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import {
  getConversations,
  type ChatListItem,
  type ConversationListParams,
} from '@/services/chatApi';
import { formatTimeAgo } from '@/utils/time';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';

type Chat = ChatListItem;

interface UseChatListOptions {
  refreshKey?: number;
  refreshOnRouteChange?: boolean;
  enabled?: boolean;
  /**
   * When set, scopes the chat list to conversations belonging to this HUF
   * Project. Omit (undefined) to keep the existing global/unscoped behavior.
   * Changing this value resets pagination and reloads from the first page.
   */
  project?: string;
}

export function useChatList(options: UseChatListOptions = {}) {
  const { refreshKey, refreshOnRouteChange = false, enabled = true, project } = options;
  const location = useLocation();

  // Memoized so identity only changes when project actually changes -
  // useInfiniteScroll resets pagination whenever initialParams changes.
  const initialParams = useMemo(
    () => ({
      filters: (project
        ? [["channel", "=", "Chat"], ["project", "=", project]]
        : [["channel", "=", "Chat"]]) as ConversationListParams['filters'],
    }),
    [project]
  );

  const {
    items: chats,
    initialLoading,
    loadingMore,
    hasMore,
    error,
    sentinelRef,
    scrollRef,
    reset,
    addItem,
  } = useInfiniteScroll<ConversationListParams, Chat>({
    fetchFn: async (params) => {
      const response = await getConversations(params);
      return {
        data: response.data.map((conv) => ({
          ...conv,
          timestampLabel: conv.timestamp ? formatTimeAgo(conv.timestamp) : undefined,
        })),
        hasMore: response.hasMore,
        total: response.total,
      };
    },
    pageSize: 20,
    initialParams,
    enabled, // Pass through enabled option
  });

  // Refresh when refreshKey changes (for ChatList component)
  useEffect(() => {
    if (typeof refreshKey !== 'undefined') {
      reset();
    }
  }, [refreshKey, reset]);

  // Refresh when route changes (for the chat rail's history list)
  useEffect(() => {
    if (refreshOnRouteChange) {
      reset();
    }
  }, [location.pathname, refreshOnRouteChange, reset]);

  return {
    chats,
    initialLoading,
    loadingMore,
    hasMore,
    error,
    sentinelRef,
    scrollRef,
    addItem,
    /** Re-fetches from the first page - e.g. after a conversation is moved
     * in/out of the Project this list is scoped to. */
    refresh: reset,
  };
}
