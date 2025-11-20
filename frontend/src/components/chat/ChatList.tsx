import type { MouseEvent } from 'react';
import { Trash2, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
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
}

export function ChatList({ selectedChatId, onSelectChat, onNewChat }: ChatListProps) {
  const {
    items: chats,
    initialLoading,
    loadingMore,
    hasMore,
    error,
    sentinelRef,
    scrollRef,
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
  });

  const handleNewChat = () => {
    onNewChat?.();
  };

  const handleDeleteChat = (chatId: string, e: MouseEvent) => {
    e.stopPropagation();
    // TODO: Implement chat deletion
    console.log('Delete chat', chatId);
  };

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
          {initialLoading ? (
            <div className="p-3 text-sm text-muted-foreground text-center">Loading...</div>
          ) : error ? (
            <div className="p-3 text-sm text-destructive text-center">
              Failed to load conversations
            </div>
          ) : chats.length === 0 ? (
            <div className="p-3 text-sm text-muted-foreground text-center">No conversations yet</div>
          ) : (
            chats.map((chat) => {
              const isSelected = selectedChatId === chat.id;
              return (
                <div
                  key={chat.id}
                  onClick={() => onSelectChat(chat.id)}
                  className={cn(
                    'group relative flex items-center gap-3 p-3 cursor-pointer transition-colors',
                    isSelected
                      ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                      : 'hover:bg-sidebar-accent/50 text-sidebar-foreground'
                  )}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <p className="text-sm font-medium truncate">{chat.title}</p>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={(e) => handleDeleteChat(chat.id, e)}
                      >
                        <Trash2 className="w-3 h-3" />
                      </Button>
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
            })
          )}
          {hasMore && (
            <div ref={sentinelRef} className="h-2 w-full opacity-0" aria-hidden="true" />
          )}
          {loadingMore && (
            <div className="p-3 text-xs text-muted-foreground text-center">Loading more...</div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

