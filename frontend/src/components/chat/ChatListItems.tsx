import { Skeleton } from '@/components/ui/skeleton';
import type { ChatListItem } from '@/services/chatApi';

interface ChatListItemsProps {
  chats: ChatListItem[];
  selectedChatId: string | null;
  initialLoading: boolean;
  loadingMore: boolean;
  hasMore: boolean;
  error: Error | null;
  sentinelRef: React.RefObject<HTMLDivElement>;
  onSelectChat: (chatId: string) => void;
  renderItem: (chat: ChatListItem, isSelected: boolean, onClick: () => void) => React.ReactNode;
  renderSkeleton?: () => React.ReactNode;
  renderLoadingMore?: () => React.ReactNode;
}

export function ChatListItems({
  chats,
  selectedChatId,
  initialLoading,
  loadingMore,
  hasMore,
  error,
  sentinelRef,
  onSelectChat,
  renderItem,
  renderSkeleton,
  renderLoadingMore,
}: ChatListItemsProps) {
  const defaultSkeleton = () => (
    <div className="group relative flex items-center gap-3 p-3">
      <div className="flex-1 min-w-0 space-y-2">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    </div>
  );

  const defaultLoadingMore = () => (
    <div className="p-3 space-y-2">
      {Array.from({ length: 2 }).map((_, i) => (
        <div key={`loading-more-${i}`} className="group relative flex items-center gap-3 p-3">
          <div className="flex-1 min-w-0 space-y-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  );

  if (error) {
    return (
      <div className="p-3 text-sm text-destructive text-center">
        Failed to load conversations
      </div>
    );
  }

  if (initialLoading && chats.length === 0) {
    return (
      <>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={`skeleton-${i}`}>
            {renderSkeleton ? renderSkeleton() : defaultSkeleton()}
          </div>
        ))}
      </>
    );
  }

  return (
    <>
      {chats.map((chat) => {
        const isSelected = selectedChatId === chat.id;
        return (
          <div key={chat.id}>
            {renderItem(chat, isSelected, () => onSelectChat(chat.id))}
          </div>
        );
      })}
      {chats.length === 0 && !initialLoading && (
        <div className="p-3 text-sm text-muted-foreground text-center">
          No conversations yet
        </div>
      )}
      {hasMore && (
        <div ref={sentinelRef} className="h-2 w-full opacity-0" aria-hidden="true" />
      )}
      {loadingMore && (
        <div>
          {renderLoadingMore ? renderLoadingMore() : defaultLoadingMore()}
        </div>
      )}
    </>
  );
}
