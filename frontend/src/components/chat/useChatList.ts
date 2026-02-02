import { useEffect } from 'react';
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
}

export function useChatList(options: UseChatListOptions = {}) {
  const { refreshKey, refreshOnRouteChange = false, enabled = true } = options;
  const location = useLocation();

  const {
    items: chats,
    initialLoading,
    loadingMore,
    hasMore,
    error,
    sentinelRef,
    scrollRef,
    reset,
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
    initialParams: {
      filters: [["channel", "=", "Chat"]]
    },
    enabled, // Pass through enabled option
  });

  // Refresh when refreshKey changes (for ChatList component)
  useEffect(() => {
    if (typeof refreshKey !== 'undefined') {
      reset();
    }
  }, [refreshKey, reset]);

  // Refresh when route changes (for ChatSidebarContent component)
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
  };
}
