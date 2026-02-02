import { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Clock4, Users } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '../ui/accordion';
import { Skeleton } from '../ui/skeleton';
import { cn } from '@/lib/utils';
import type { ChatListItem, AgentWithCount } from '@/services/chatApi';
import {
  getAgentsWithConversationCounts,
  getConversationsByAgent,
} from '@/services/chatApi';
import { formatTimeAgo } from '@/utils/time';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import { useChatList } from './useChatList';
import ChatAvatar from './ChatAvatar';
import { getInitials } from '@/utils/getInitials';
import { toDate, startOfDay } from '@/utils/time';

function getRecentBucketLabel(ts?: string): string {
  const d = toDate(ts);
  if (!d) return 'OLDER';

  const now = new Date();
  const today = startOfDay(now).getTime();
  const thatDay = startOfDay(d).getTime();
  const diffDays = Math.floor((today - thatDay) / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'TODAY';
  if (diffDays === 1) return 'YESTERDAY';
  if (diffDays <= 7) return 'THIS WEEK';
  return 'OLDER';
}

export default function ChatListing() {
  const navigate = useNavigate();
  const { chatId: routeChatId } = useParams<{ chatId?: string }>();
  const selectedChatId = routeChatId && routeChatId !== 'new' ? routeChatId : null;

  const [agents, setAgents] = useState<AgentWithCount[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [openAgents, setOpenAgents] = useState<string[]>([]);

  const [activeTab, setActiveTab] = useState('agent');

  // Fetch agents with counts on mount
  useEffect(() => {
    let cancelled = false;

    async function fetchAgents() {
      setAgentsLoading(true);
      try {
        const agentsData = await getAgentsWithConversationCounts();
        if (!cancelled) {
          setAgents(agentsData);
        }
      } catch (error) {
        console.error('Error fetching agents:', error);
      } finally {
        if (!cancelled) {
          setAgentsLoading(false);
        }
      }
    }

    fetchAgents();

    return () => {
      cancelled = true;
    };
  }, []);

  // Handle accordion open/close
  const handleAccordionChange = useCallback((value: string[]) => {
    setOpenAgents(value);
  }, []);

  const handleSelectChat = (chatId: string) => {
    navigate(`/chat/${chatId}`);
  };

  return (
    <div className="h-full min-h-screen min-w-96 bg-sidebar p-4 space-y-4 overflow-y-auto">
      <ChatListHeader />
      <Tabs defaultValue="agent" value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="w-full">
          {LIST_TABS.map((tab) => (
            <TabsTrigger
              key={tab.value}
              className="w-1/2 space-x-2 text-xs font-medium"
              value={tab.value}
            >
              <tab.icon className="w-3 h-3" />
              <span>{tab.label}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="agent">
          {agentsLoading ? (
            <div className="space-y-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={`agent-skel-${i}`} className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Skeleton className="h-7 w-7 rounded-full" />
                    <Skeleton className="h-4 w-40" />
                  </div>
                  <div className="ml-3 pl-3 border-l border-zinc-200 space-y-2">
                    <Skeleton className="h-10 w-full rounded-md" />
                    <Skeleton className="h-10 w-full rounded-md" />
                  </div>
                </div>
              ))}
            </div>
          ) : agents.length === 0 ? (
            <div className="p-3 text-sm text-muted-foreground text-center">No agents with conversations</div>
          ) : (
            <Accordion
              type="multiple"
              className="space-y-4"
              onValueChange={handleAccordionChange}
            >
              {agents.map((agent) => (
                <AgentConversationItem
                  key={agent.name}
                  agent={agent}
                  selectedChatId={selectedChatId}
                  onSelectChat={handleSelectChat}
                  isOpen={openAgents.includes(agent.name)}
                />
              ))}
            </Accordion>
          )}
        </TabsContent>

        <TabsContent value="recents">
          <RecentsConversationList
            selectedChatId={selectedChatId}
            onSelectChat={handleSelectChat}
            isActive={activeTab === 'recents'}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// Component for individual agent conversation list with infinite scroll
function AgentConversationItem({
  agent,
  selectedChatId,
  onSelectChat,
  isOpen,
}: {
  agent: AgentWithCount;
  selectedChatId: string | null;
  onSelectChat: (chatId: string) => void;
  isOpen: boolean;
}) {
  const {
    items: conversations,
    initialLoading,
    loadingMore,
    hasMore,
    loadMore,
  } = useInfiniteScroll(
    {
      fetchFn: async (params) => {
        const response = await getConversationsByAgent(agent.name, {
          limit: params.limit || 20,
          start: params.start || 0,
        });
        return {
          data: response.data.map((chat) => ({
            ...chat,
            timestampLabel: chat.timestamp ? formatTimeAgo(chat.timestamp) : undefined,
          })),
          hasMore: response.hasMore,
        };
      },
      initialParams: {},
      pageSize: 20,
      autoLoad: isOpen, // Only load when accordion is open
      autoLoadMore: false, // Use "Load More" button instead of automatic infinite scroll
      enabled: isOpen, // Only enable when open
    }
  );

  return (
    <AccordionItem value={agent.name} className="border-b-0">
      <AccordionTrigger
        className="group gap-2 mb-1 py-1 px-1 hover:bg-zinc-200 cursor-pointer select-none rounded-lg"
        arrowPosition="left"
      >
        <div className="flex-1 flex gap-x-2 items-center">
          <ChatAvatar variant="listing_ai">{getInitials(agent.agent_name)}</ChatAvatar>
          <span className="text-sm font-medium truncate text-zinc-500 group-hover:text-zinc-900 transition-colors">
            {agent.agent_name}
          </span>
        </div>
        <span className="text-[10px] text-zinc-400 bg-zinc-200 px-1.5 py-0.5 rounded-full border border-zinc-200 ml-auto">
          {agent.conversationCount}
        </span>
      </AccordionTrigger>

      <AccordionContent className="space-y-0.5 ml-3 pl-3 border-l border-zinc-200 overflow-hidden transition-all duration-300 opacity-100">
        {initialLoading ? (
          <div className="space-y-2 p-2">
            <Skeleton className="h-10 w-full rounded-md" />
            <Skeleton className="h-10 w-full rounded-md" />
          </div>
        ) : conversations.length === 0 && agent.conversationCount === 0 ? (
          <div className="p-2 text-xs text-muted-foreground">No conversations</div>
        ) : conversations.length === 0 && agent.conversationCount > 0 ? (
          <div className="space-y-2 p-2">
            <Skeleton className="h-10 w-full rounded-md" />
            <Skeleton className="h-10 w-full rounded-md" />
          </div>
        ) : (
          <>
            {conversations.map((chat) => {
              const isSelected = selectedChatId === chat.id;
              return (
                <button
                  key={chat.id}
                  type="button"
                  onClick={() => onSelectChat(chat.id)}
                  className={cn(
                    'group flex w-full text-left flex-col p-2 rounded-md cursor-pointer transition-all border-l-2',
                    isSelected
                      ? 'bg-zinc-200 border-indigo-500'
                      : 'bg-transparent border-transparent hover:bg-zinc-200 hover:border-zinc-200'
                  )}
                >
                  <span className="text-xs font-medium truncate text-zinc-900">{chat.title}</span>
                  <p className="text-[10px] text-zinc-400 truncate mt-0.5 group-hover:text-zinc-500">
                    {chat.timestampLabel ?? ''}
                  </p>
                </button>
              );
            })}
            {hasMore && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation(); // Prevent accordion from closing
                  loadMore();
                }}
                disabled={loadingMore}
                className={cn(
                  'w-full text-xs text-zinc-500 hover:text-zinc-900 py-2 px-2 text-center transition-colors',
                  loadingMore && 'opacity-50 cursor-not-allowed'
                )}
              >
                {loadingMore ? 'Loading...' : 'Load More'}
              </button>
            )}
          </>
        )}
      </AccordionContent>
    </AccordionItem>
  );
}

function RecentsConversationList({
  selectedChatId,
  onSelectChat,
  isActive,
}: {
  selectedChatId: string | null;
  onSelectChat: (chatId: string) => void;
  isActive: boolean;
}) {
  const {
    chats: conversations,
    initialLoading,
    loadingMore,
    hasMore,
    error,
    sentinelRef,
  } = useChatList({
    enabled: isActive, // Only load when tab is active
    refreshOnRouteChange: false, // Don't refresh on route change for this use case
  });

  const byRecents = useMemo(() => {
    const map = new Map<string, ChatListItem[]>();
    for (const chat of conversations) {
      const label = getRecentBucketLabel(chat.timestamp);
      const list = map.get(label);
      if (list) list.push(chat);
      else map.set(label, [chat]);
    }

    const order = ['TODAY', 'YESTERDAY', 'THIS WEEK', 'OLDER'] as const;
    return order.map((label) => [label, map.get(label) ?? []] as const);
  }, [conversations]);

  if (error) {
    return (
      <div className="p-3 text-sm text-destructive text-center">Failed to load conversations</div>
    );
  }

  if (initialLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={`recent-skel-${i}`} className="flex p-3 gap-2 items-center rounded-lg border">
            <Skeleton className="h-8 w-8 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
            </div>
            <Skeleton className="h-3 w-10" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {byRecents.every(([, items]) => items.length === 0) ? (
        <div className="p-3 text-sm text-muted-foreground text-center">No conversations yet</div>
      ) : (
        <>
          {byRecents.map(([label, items]) => {
            if (items.length === 0) return null;
            return (
              <div key={label}>
                <span className="px-2 text-xs font-medium text-zinc-400 uppercase tracking-wider">
                  {label}
                </span>
                <div className="mt-2 space-y-1">
                  {items.map((chat) => {
                    const isSelected = selectedChatId === chat.id;
                    return (
                      <button
                        key={chat.id}
                        type="button"
                        onClick={() => onSelectChat(chat.id)}
                        className={cn(
                          'flex w-full text-left p-3 gap-2 items-center rounded-lg cursor-pointer transition-all border',
                          isSelected
                            ? 'bg-zinc-200 border-zinc-200'
                            : 'border-transparent bg-transparent hover:bg-zinc-200'
                        )}
                      >
                        <div className="flex flex-1 gap-2 items-center min-w-0">
                          <ChatAvatar variant="chat_ai">{getInitials(chat.agent)}</ChatAvatar>
                          <div className="mb-1 min-w-0">
                            <span className="text-sm font-medium truncate text-zinc-900 block">
                              {chat.title}
                            </span>
                            <p className="text-xs truncate text-zinc-500">{chat.agent}</p>
                          </div>
                        </div>
                        <span className="mt-1.5 text-[10px] text-zinc-400 flex-shrink-0 justify-self-end self-start">
                          {chat.timestampLabel ?? ''}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
          {hasMore && (
            <div ref={sentinelRef} className="h-2 w-full opacity-0" aria-hidden="true" />
          )}
          {loadingMore && (
            <div className="p-2 text-xs text-muted-foreground text-center">Loading more...</div>
          )}
        </>
      )}
    </div>
  );
}

function ChatListHeader() {
  return (
    <div className="">
      <div>
        <h1 className="font-semibold text-lg tracking-tight">Workspaces</h1>
      </div>
    </div>
  );
}

const LIST_TABS = [
  {
    value: 'agent',
    label: 'By Agent',
    icon: Users,
  },
  {
    value: 'recents',
    label: 'Recents',
    icon: Clock4,
  },
];
