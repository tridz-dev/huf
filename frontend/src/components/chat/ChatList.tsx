import { useEffect, } from 'react';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import {
  getConversations,
  type ChatListItem,
  type ConversationListParams,
} from '@/services/chatApi';
import { formatTimeAgo } from '@/utils/time';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';

type Chat = ChatListItem;

interface ChatListProps {
  selectedChatId: string | null;
  onSelectChat: (chatId: string) => void;
  onNewChat?: () => void;
  refreshKey?: number;
}

export function ChatList({ selectedChatId, onSelectChat, onNewChat, refreshKey }: ChatListProps) {
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
          timestamp: conv.timestamp ? formatTimeAgo(conv.timestamp) : undefined,
        })),
        hasMore: response.hasMore,
        total: response.total,
      };
    },
    pageSize: 20,
    initialParams:{
      filters:[["channel", "=", "Chat"]]
    }
  });

  useEffect(() => {
    if (typeof refreshKey === 'undefined') {
      return;
    }
    reset();
  }, [refreshKey, reset]);

  const handleNewChat = () => {
    onNewChat?.();
  };

  // const handleDeleteChat = (chatId: string, e: MouseEvent) => {
  //   e.stopPropagation();
  //   // TODO: Implement chat deletion
  //   console.log('Delete chat', chatId);
  // };

  return (
    <div className="flex flex-col w-64 h-full border-r border-border bg-sidebar">
      <div className="p-3">
        <Button
          className="w-full justify-start gap-2"
          variant="outline"
          size="sm"
          onClick={handleNewChat}
        >
          <Plus className="h-4 w-4" />
          New Chat
        </Button>
      </div>
      {/* Chat List */}
      <ScrollArea ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="space-y-1">
          {error ? (
            <div className="p-3 text-sm text-destructive text-center">
              Failed to load conversations
            </div>
          ) : (
            <>
              {/* Show skeleton loaders only on initial load when there are no chats */}
              {initialLoading && chats.length === 0 ? (
                <>
                  {Array.from({ length: 5 }).map((_, i) => (
                    <div
                      key={`skeleton-${i}`}
                      className="group relative flex items-center gap-3 p-3"
                    >
                      <div className="flex-1 min-w-0 space-y-2">
                        <Skeleton className="h-4 w-3/4" />
                        <Skeleton className="h-3 w-1/2" />
                      </div>
                    </div>
                  ))}
                </>
              ) : (
                <>
                  {chats.map((chat) => {
                    const isSelected = selectedChatId === chat.id;
                    return (
                      <div
                        key={chat.id}
                        onClick={() => onSelectChat(chat.id)}
                        className={cn(
                          'group relative flex items-center gap-3 p-3 cursor-pointer',
                          'transition-all duration-200 ease-in-out',
                          isSelected
                            ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                            : 'hover:bg-sidebar-accent/50 text-sidebar-foreground'
                        )}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2 mb-1">
                            <p className="text-sm font-medium truncate">{chat.title}</p>
                            {/* <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                              onClick={(e) => handleDeleteChat(chat.id, e)}
                            >
                              <Trash2 className="w-3 h-3" />
                            </Button> */}
                          </div>
                          {chat.agent && (
                            <p className="text-xs text-muted-foreground truncate">
                              {chat.agent}
                            </p>
                          )}
                          {chat.timestamp && (
                            <p className="text-xs text-muted-foreground mt-1">
                              {chat.timestamp}
                            </p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                  {chats.length === 0 && !initialLoading && (
                    <div className="p-3 text-sm text-muted-foreground text-center">
                      No conversations yet
                    </div>
                  )}
                </>
              )}
              {hasMore && (
                <div ref={sentinelRef} className="h-2 w-full opacity-0" aria-hidden="true" />
              )}
              {loadingMore && (
                <div className="p-3 space-y-2">
                  {Array.from({ length: 2 }).map((_, i) => (
                    <div
                      key={`loading-more-${i}`}
                      className="group relative flex items-center gap-3 p-3"
                    >
                      <div className="flex-1 min-w-0 space-y-2">
                        <Skeleton className="h-4 w-3/4" />
                        <Skeleton className="h-3 w-1/2" />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

