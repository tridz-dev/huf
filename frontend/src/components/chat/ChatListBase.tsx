import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { ChatListItem } from '@/services/chatApi';
import { useChatList } from './useChatList';
import { ChatListItems } from './ChatListItems';
import { cn } from '@/lib/utils';

interface ChatListBaseProps {
  selectedChatId: string | null;
  onSelectChat: (chatId: string) => void;
  onNewChat?: () => void;
  refreshKey?: number;
  refreshOnRouteChange?: boolean;
  onChatSelect?: () => void;
  // Rendering customization
  variant?: 'sidebar' | 'standalone';
  showNewChatButton?: boolean;
  newChatButtonClassName?: string;
  containerClassName?: string;
  renderItem: (chat: ChatListItem, isSelected: boolean, onClick: () => void) => React.ReactNode;
  renderSkeleton?: () => React.ReactNode;
  renderLoadingMore?: () => React.ReactNode;
  // Container wrapper (for sidebar vs standalone)
  renderContainer?: (children: React.ReactNode, scrollRef: React.RefObject<HTMLDivElement>) => React.ReactNode;
}

export function ChatListBase({
  selectedChatId,
  onSelectChat,
  onNewChat,
  refreshKey,
  refreshOnRouteChange = false,
  onChatSelect,
  variant = 'standalone',
  showNewChatButton = true,
  newChatButtonClassName,
  containerClassName,
  renderItem,
  renderSkeleton,
  renderLoadingMore,
  renderContainer,
}: ChatListBaseProps) {
  const { chats, initialLoading, loadingMore, hasMore, error, sentinelRef, scrollRef } = useChatList({
    refreshKey,
    refreshOnRouteChange,
  });

  const handleSelectChat = (chatId: string) => {
    onSelectChat(chatId);
    onChatSelect?.();
  };

  const defaultContainer = (children: React.ReactNode, scrollRef: React.RefObject<HTMLDivElement>) => {
    if (variant === 'sidebar') {
      return (
        <ScrollArea ref={scrollRef} className="flex-1">
          {children}
        </ScrollArea>
      );
    }
    return (
      <div className={cn('flex flex-col w-64 h-full border-r border-border bg-sidebar', containerClassName)}>
        {showNewChatButton && (
          <div className="p-3">
            <Button
              className={cn('w-full justify-start gap-2', newChatButtonClassName)}
              variant="outline"
              size="sm"
              onClick={onNewChat}
            >
              <Plus className="h-4 w-4" />
              New Chat
            </Button>
          </div>
        )}
        <ScrollArea ref={scrollRef} className="flex-1 overflow-y-auto">
          <div className="space-y-1">
            {children}
          </div>
        </ScrollArea>
      </div>
    );
  };

  const container = renderContainer || defaultContainer;

  const content = (
    <ChatListItems
      chats={chats}
      selectedChatId={selectedChatId}
      initialLoading={initialLoading}
      loadingMore={loadingMore}
      hasMore={hasMore}
      error={error}
      sentinelRef={sentinelRef}
      onSelectChat={handleSelectChat}
      renderItem={renderItem}
      renderSkeleton={renderSkeleton}
      renderLoadingMore={renderLoadingMore}
    />
  );

  return container(content, scrollRef);
}
