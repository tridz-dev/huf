import { useEffect, useMemo, useRef } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, MessageSquare } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ChatListItem } from '@/services/chatApi';
import { useLocalStorageBoolean } from '@/hooks/useLocalStorageBoolean';
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
  /**
   * When set, scopes Recents to this HUF Project (passed through to
   * useChatList) and switches the collapse-state localStorage keys to the
   * project-scoped variant. Omit for the global/unscoped rail.
   */
  project?: string;
  onRename: (conversationId: string) => void;
  onFork: (conversationId: string, title: string, agentName: string) => void;
  titleRefs: React.MutableRefObject<Map<string, ConversationTitleRef>>;
  animatingConversationId?: string | null;
  onAddItemReady?: (addItem: (item: ChatListItem) => void) => void;
  /** Fired after a conversation is pinned/unpinned from a row's menu, so the
   * caller (ChatRail) can refetch the Pinned section for this scope. */
  onPinChange?: (conversationId: string, isPinned: boolean) => void;
}

interface ConversationRowProps {
  chat: ChatListItem;
  isSelected: boolean;
  isPinned: boolean;
  onRename: (conversationId: string) => void;
  onFork: (conversationId: string, title: string, agentName: string) => void;
  titleRefs: React.MutableRefObject<Map<string, ConversationTitleRef>>;
  animatingConversationId?: string | null;
  onProjectChange?: (conversationId: string, project: string | null) => void;
  onPinChange?: (conversationId: string, isPinned: boolean) => void;
}

function ConversationRow({
  chat,
  isSelected,
  isPinned,
  onRename,
  onFork,
  titleRefs,
  animatingConversationId,
  onProjectChange,
  onPinChange,
}: ConversationRowProps) {
  return (
    <ConversationMenu
      conversationId={chat.id}
      isPinned={isPinned}
      currentProject={chat.project ?? null}
      onRename={() => onRename(chat.id)}
      onFork={() => onFork(chat.id, chat.title, chat.agent)}
      onProjectChange={onProjectChange}
      onPinChange={onPinChange}
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

interface SectionHeaderProps {
  label: string;
  expanded: boolean;
  onToggle: () => void;
  className?: string;
}

// Shared collapse toggle for the Pinned and Recents section labels. A plain
// button rather than a details/summary pair, so it keeps the same 6px-tall
// label row the rail already used before either section was collapsible.
function SectionHeader({ label, expanded, onToggle, className }: SectionHeaderProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      className={cn(
        'flex h-6 flex-none items-center gap-1 rounded-chat-row px-2 text-[11px] text-steel-soft transition-colors hover:text-ink',
        className
      )}
    >
      <ChevronRight className={cn('h-3 w-3 shrink-0 transition-transform', expanded && 'rotate-90')} />
      {label}
    </button>
  );
}

export function ChatRailHistory({
  selectedChatId,
  pinnedChats = [],
  project,
  onRename,
  onFork,
  titleRefs,
  animatingConversationId,
  onAddItemReady,
  onPinChange,
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
    refresh,
  } = useChatList({ refreshOnRouteChange: false, project });

  // A12: a conversation moved in/out of a Project (via ConversationMenu)
  // may enter or leave this list's scope - re-fetch from the first page
  // rather than trying to patch a single row in place.
  const handleProjectChange = () => {
    refresh();
  };

  // A conversation pinned/unpinned from a row's menu changes which section
  // it belongs in - refresh Recents immediately (so it re-partitions without
  // a reload) and let the caller know so it can refetch Pinned.
  const handlePinChange = (conversationId: string, isPinned: boolean) => {
    refresh();
    onPinChange?.(conversationId, isPinned);
  };

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

  // §19 collapse-state-persistence: Pinned/Recents each persist their
  // expand/collapse choice separately for the global vs. project-scoped
  // rail, so collapsing Recents globally doesn't also collapse it inside
  // every project.
  const scopeKey = project ? 'project' : 'global';
  const [pinnedExpanded, setPinnedExpanded] = useLocalStorageBoolean(
    `huf.sidebar.${scopeKey}.pinned.expanded`,
    true
  );
  const [recentsExpanded, setRecentsExpanded] = useLocalStorageBoolean(
    `huf.sidebar.${scopeKey}.recents.expanded`,
    true
  );

  // A conversation shown under Pinned must not also appear under Recents.
  const pinnedIds = useMemo(() => new Set(pinnedChats.map((chat) => chat.id)), [pinnedChats]);
  const recentChats = useMemo(() => chats.filter((chat) => !pinnedIds.has(chat.id)), [chats, pinnedIds]);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-2">
      {hasPinned && (
        <>
          <SectionHeader
            label="Pinned"
            expanded={pinnedExpanded}
            onToggle={() => setPinnedExpanded(!pinnedExpanded)}
          />
          {pinnedExpanded &&
            pinnedChats.map((chat) => (
              <ConversationRow
                key={chat.id}
                chat={chat}
                isSelected={selectedChatId === chat.id}
                isPinned
                onRename={onRename}
                onFork={onFork}
                titleRefs={titleRefs}
                animatingConversationId={animatingConversationId}
                onProjectChange={handleProjectChange}
                onPinChange={handlePinChange}
              />
            ))}
        </>
      )}

      <SectionHeader
        label="Recents"
        expanded={recentsExpanded}
        onToggle={() => setRecentsExpanded(!recentsExpanded)}
        className={hasPinned ? 'mt-1.5' : undefined}
      />

      {recentsExpanded && (
        <div ref={scrollContainerRef} className="flex min-h-0 flex-1 flex-col overflow-y-auto" id="chat-rail-scroll">
          {error ? (
            <div className="px-2 text-[13px] text-destructive">Could not load conversations</div>
          ) : initialLoading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <div key={`chat-rail-skel-${i}`} className="flex h-chat-row items-center px-2">
                <Skeleton className="h-3 w-2/3" />
              </div>
            ))
          ) : recentChats.length === 0 ? (
            <div className="px-2 text-[13px] text-steel-soft">No conversations yet</div>
          ) : (
            <>
              {recentChats.map((chat) => (
                <ConversationRow
                  key={chat.id}
                  chat={chat}
                  isSelected={selectedChatId === chat.id}
                  isPinned={false}
                  onRename={onRename}
                  onFork={onFork}
                  titleRefs={titleRefs}
                  animatingConversationId={animatingConversationId}
                  onProjectChange={handleProjectChange}
                  onPinChange={handlePinChange}
                />
              ))}
              {hasMore && <div ref={sentinelRef} className="h-2 w-full opacity-0" aria-hidden="true" />}
              {loadingMore && (
                <div className="px-2 text-[11px] text-steel-soft">Loading more…</div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
