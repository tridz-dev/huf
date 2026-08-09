import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { MessageSquare } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ChatListItem } from '@/services/chatApi';
import { Skeleton } from '../../ui/skeleton';
import { useChatList } from '../useChatList';
import ConversationTitle, { type ConversationTitleRef } from '../ConversationTitle';
import ConversationMenu from '../ConversationMenu';

const UNTITLED_CONVERSATION_TITLE = 'Untitled Chat';

function isUntitledConversationTitle(title: string): boolean {
  return !title || title === UNTITLED_CONVERSATION_TITLE;
}

export interface ChatRailHistoryProps {
  selectedChatId: string | null;
  pinnedChats?: ChatListItem[];
  onRename: (conversationId: string) => void;
  onFork: (conversationId: string, title: string, agentName: string) => void;
  titleRefs: React.MutableRefObject<Map<string, ConversationTitleRef>>;
  animatingConversationId?: string | null;
  onAddItemReady?: (addItem: (item: ChatListItem) => void) => void;
}

interface ConversationRowProps {
  chat: ChatListItem;
  isSelected: boolean;
  onRename: (conversationId: string) => void;
  onFork: (conversationId: string, title: string, agentName: string) => void;
  titleRefs: React.MutableRefObject<Map<string, ConversationTitleRef>>;
  animatingConversationId?: string | null;
}

function ConversationRow({
  chat,
  isSelected,
  onRename,
  onFork,
  titleRefs,
  animatingConversationId,
}: ConversationRowProps) {
  return (
    <ConversationMenu
      onRename={() => onRename(chat.id)}
      onFork={() => onFork(chat.id, chat.title, chat.agent)}
    >
      <Link
        to={`/chat/${chat.id}`}
        onClick={(e) => {
          // Only prevent navigation if the click is directly on a menu item
          // Check if the event originated from within the context menu portal
          const target = e.target as HTMLElement;
          const isFromMenu = target.closest('[data-radix-portal]') ||
                            target.closest('[role="menuitem"]') ||
                            e.nativeEvent.composedPath?.().some((el) =>
                              (el as HTMLElement | null)?.getAttribute?.('role') === 'menuitem'
                            );
          if (isFromMenu) {
            e.preventDefault();
            e.stopPropagation();
          }
        }}
        className={cn(
          'group flex h-chat-row items-center gap-[9px] rounded-chat-row px-2 text-[13px] transition-colors',
          isSelected ? 'bg-chat-row-selected' : 'hover:bg-chat-row-hover'
        )}
      >
        <MessageSquare
          className={cn('h-[15px] w-[15px] shrink-0', isSelected ? 'text-steel' : 'text-steel-soft')}
        />
        <ConversationTitle
          ref={(el) => {
            if (el) titleRefs.current.set(chat.id, el);
            else titleRefs.current.delete(chat.id);
          }}
          variant="recents_list"
          value={chat.title}
          conversationId={chat.id}
          animate={animatingConversationId === chat.id}
          className={cn('min-w-0 flex-1 truncate', isUntitledConversationTitle(chat.title) && 'italic text-steel-soft')}
        />
      </Link>
    </ConversationMenu>
  );
}

export function ChatRailHistory({
  selectedChatId,
  pinnedChats = [],
  onRename,
  onFork,
  titleRefs,
  animatingConversationId,
  onAddItemReady,
}: ChatRailHistoryProps) {
  const {
    chats,
    initialLoading,
    loadingMore,
    hasMore,
    error,
    sentinelRef,
    scrollRef,
    addItem,
  } = useChatList({ refreshOnRouteChange: false });

  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Point scrollRef at the rail's own scroll container so the infinite-scroll
  // sentinel observer attaches to the element that actually scrolls.
  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollRef.current = scrollContainerRef.current;
    }
  }, [scrollRef]);

  useEffect(() => {
    if (addItem && onAddItemReady) {
      onAddItemReady(addItem);
    }
  }, [addItem, onAddItemReady]);

  const hasPinned = pinnedChats.length > 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-2">
      {hasPinned && (
        <>
          <div className="flex h-6 flex-none items-center px-2 text-[11px] text-steel-soft">Pinned</div>
          {pinnedChats.map((chat) => (
            <ConversationRow
              key={chat.id}
              chat={chat}
              isSelected={selectedChatId === chat.id}
              onRename={onRename}
              onFork={onFork}
              titleRefs={titleRefs}
              animatingConversationId={animatingConversationId}
            />
          ))}
        </>
      )}

      <div className={cn('flex h-6 flex-none items-center px-2 text-[11px] text-steel-soft', hasPinned && 'mt-1.5')}>
        Recents
      </div>

      <div ref={scrollContainerRef} className="flex min-h-0 flex-1 flex-col overflow-y-auto" id="chat-rail-scroll">
        {error ? (
          <div className="px-2 text-[13px] text-destructive">Could not load conversations</div>
        ) : initialLoading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <div key={`chat-rail-skel-${i}`} className="flex h-chat-row items-center px-2">
              <Skeleton className="h-3 w-2/3" />
            </div>
          ))
        ) : chats.length === 0 ? (
          <div className="px-2 text-[13px] text-steel-soft">No conversations yet</div>
        ) : (
          <>
            {chats.map((chat) => (
              <ConversationRow
                key={chat.id}
                chat={chat}
                isSelected={selectedChatId === chat.id}
                onRename={onRename}
                onFork={onFork}
                titleRefs={titleRefs}
                animatingConversationId={animatingConversationId}
              />
            ))}
            {hasMore && <div ref={sentinelRef} className="h-2 w-full opacity-0" aria-hidden="true" />}
            {loadingMore && (
              <div className="px-2 text-[11px] text-steel-soft">Loading more…</div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
