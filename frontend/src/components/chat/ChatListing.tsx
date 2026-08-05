import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Clock4, PanelLeftClose, Plus, Search, Users } from 'lucide-react';
import { toast } from 'sonner';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '../ui/accordion';
import { Skeleton } from '../ui/skeleton';
import { cn } from '@/lib/utils';
import type { ChatListItem, AgentWithCount } from '@/services/chatApi';
import {
  getAgentsWithConversationCounts,
  getConversationsByAgent,
  getConversation,
} from '@/services/chatApi';
import { formatTimeAgo } from '@/utils/time';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import { useChatList } from './useChatList';
import ChatAvatar from './ChatAvatar';
import { getInitials } from '@/utils/getInitials';
import { toDate, startOfDay } from '@/utils/time';
import { ChatAgentPicker } from './ChatAgentPicker';
import { Button } from '../ui/button';
import { SidebarTrigger } from '../ui/sidebar';
// import { DEFAULT_AGENT_COLOR } from '@/data/color';
import { getAgent } from '@/services/agentApi';
import ConversationTitle, { type ConversationTitleRef } from './ConversationTitle';
import ConversationMenu from './ConversationMenu';
import { ForkConversationDialog } from './ForkConversationDialog';
import {
  type ConversationTitleUpdatedDetail,
  useConversationTitleSwitchFallback,
} from './useConversationTitleFallback';

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

const UNTITLED_CONVERSATION_TITLE = 'Untitled Chat';

function isUntitledConversationTitle(title: string): boolean {
  return !title || title === UNTITLED_CONVERSATION_TITLE;
}

export default function ChatListing({ onClose }: { onClose?: () => void }) {
  const navigate = useNavigate();
  const { chatId: routeChatId } = useParams<{ chatId?: string }>();
  const selectedChatId = routeChatId && routeChatId !== 'new' ? routeChatId : null;

  const [agents, setAgents] = useState<AgentWithCount[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  
  // Persist open agents state in sessionStorage
  const [openAgents, setOpenAgents] = useState<string[]>(() => {
    try {
      const saved = sessionStorage.getItem('chat-listing-open-agents');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  const [activeTab, setActiveTab] = useState('recents');
  const [animatingConversationId, setAnimatingConversationId] = useState<string | null>(null);
  const [selectedConversationTitle, setSelectedConversationTitle] = useState<string | null>(null);
  const [selectedAutonamingEnabled, setSelectedAutonamingEnabled] = useState(false);

  // Fork dialog state
  const [forkDialogOpen, setForkDialogOpen] = useState(false);
  const [forkDialogConversationId, setForkDialogConversationId] = useState<string | null>(null);
  const [forkDialogTitle, setForkDialogTitle] = useState<string>('');
  const [forkDialogAgentName, setForkDialogAgentName] = useState<string>('');

  // Ref map to store refs for each conversation title
  const titleRefs = useRef<Map<string, ConversationTitleRef>>(new Map());
  
  // Refs to store addItem functions from child components
  const recentsAddItemRef = useRef<((item: ChatListItem) => void) | null>(null);
  const agentAddItemRefs = useRef<Map<string, (item: ChatListItem) => void>>(new Map());

  // Callback to handle rename action
  const handleRename = useCallback((conversationId: string) => {
    const titleRef = titleRefs.current.get(conversationId);
    if (titleRef) {
      titleRef.activateInput();
    }
  }, []);

  // Callback to handle fork action
  const handleFork = useCallback((conversationId: string, title: string, agentName: string) => {
    setForkDialogConversationId(conversationId);
    setForkDialogTitle(title || 'Untitled Chat');
    setForkDialogAgentName(agentName);
    setForkDialogOpen(true);
  }, []);

  const handleForked = useCallback((newConversationId: string, agentName: string) => {
    navigate(`/chat/${newConversationId}`);
    window.dispatchEvent(
      new CustomEvent('huf:conversation-created', {
        detail: { conversationId: newConversationId, agentName },
      })
    );
  }, [navigate]);

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
        if (!cancelled) {
          toast.error('Failed to load agents', {
            description: error instanceof Error ? error.message : 'An error occurred while fetching agents. Please try again.',
            duration: 5000,
          });
        }
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

  useEffect(() => {
    if (!selectedChatId) {
      setSelectedConversationTitle(null);
      setSelectedAutonamingEnabled(false);
      return;
    }

    let cancelled = false;

    const conversationId = selectedChatId;

    async function loadSelectedConversation() {
      try {
        const conversationDoc = await getConversation(conversationId);
        if (cancelled || !conversationDoc) return;

        setSelectedConversationTitle(conversationDoc.title ?? null);

        if (conversationDoc.agent) {
          const agentData = await getAgent(conversationDoc.agent);
          if (!cancelled) {
            setSelectedAutonamingEnabled(agentData.autonaming_of_conversation_title !== 0);
          }
        }
      } catch (error) {
        console.error('Error loading selected conversation:', error);
      }
    }

    void loadSelectedConversation();

    return () => {
      cancelled = true;
    };
  }, [selectedChatId]);

  useConversationTitleSwitchFallback({
    conversationId: selectedChatId,
    currentTitle: selectedConversationTitle,
    autonamingEnabled: selectedAutonamingEnabled,
  });

  const applyTitleUpdate = useCallback(async (detail: ConversationTitleUpdatedDetail) => {
    const { conversationId, title, animate } = detail;

    if (animate && conversationId === selectedChatId) {
      setAnimatingConversationId(conversationId);
      const duration = Math.max(title.length * 35 + 200, 500);
      window.setTimeout(() => {
        setAnimatingConversationId((current) => (current === conversationId ? null : current));
      }, duration);
    }

    if (conversationId === selectedChatId) {
      setSelectedConversationTitle(title);
    }

    try {
      const conversationDoc = await getConversation(conversationId);
      if (!conversationDoc) return;

      const conversationItem: ChatListItem = {
        id: conversationId,
        title,
        agent: conversationDoc.agent || '',
        timestamp: conversationDoc.last_activity || conversationDoc.modified,
        timestampLabel: conversationDoc.last_activity || conversationDoc.modified
          ? formatTimeAgo(conversationDoc.last_activity || conversationDoc.modified)
          : undefined,
      };

      if (recentsAddItemRef.current) {
        recentsAddItemRef.current(conversationItem);
      }

      const agentName = conversationDoc.agent;
      if (agentName && agentAddItemRefs.current.has(agentName)) {
        const agentAddItem = agentAddItemRefs.current.get(agentName);
        agentAddItem?.(conversationItem);
      }
    } catch (error) {
      console.error('Error updating conversation title in list:', error);
    }
  }, [selectedChatId]);

  // Listen for conversation title updates
  useEffect(() => {
    const handleTitleUpdated = (event: Event) => {
      const customEvent = event as CustomEvent<ConversationTitleUpdatedDetail>;
      void applyTitleUpdate(customEvent.detail);
    };

    window.addEventListener('huf:conversation-title-updated', handleTitleUpdated);
    return () => {
      window.removeEventListener('huf:conversation-title-updated', handleTitleUpdated);
    };
  }, [applyTitleUpdate]);

  // Listen for new conversation events
  useEffect(() => {
    const handleNewConversation = async (event: CustomEvent<{ conversationId: string; agentName?: string }>) => {
      const { conversationId, agentName } = event.detail;
      
      try {
        // Fetch conversation details
        const conversationDoc = await getConversation(conversationId);
        if (!conversationDoc) {
          console.error('Failed to fetch conversation:', conversationId);
          return;
        }

        // Map to ChatListItem format
        const conversationItem: ChatListItem = {
          id: conversationDoc.name,
          title: conversationDoc.title || 'Untitled Chat',
          agent: conversationDoc.agent || '',
          timestamp: conversationDoc.last_activity || conversationDoc.modified,
          timestampLabel: conversationDoc.last_activity || conversationDoc.modified 
            ? formatTimeAgo(conversationDoc.last_activity || conversationDoc.modified) 
            : undefined,
        };

        // Add to the list based on which tab is currently active
        if (activeTab === 'recents') {
          // Add to recents list if recents tab is active
          if (recentsAddItemRef.current) {
            recentsAddItemRef.current(conversationItem);
          }
        } else if (activeTab === 'agent' && agentName) {
          // Add to agent-specific list if agents tab is active and agent name is provided
          if (agentAddItemRefs.current.has(agentName)) {
            const agentAddItem = agentAddItemRefs.current.get(agentName);
            if (agentAddItem) {
              agentAddItem(conversationItem);
            }
          }
          
          // Open agent accordion if not already open
          if (!openAgents.includes(agentName)) {
            const newOpenAgents = [...openAgents, agentName];
            setOpenAgents(newOpenAgents);
            try {
              sessionStorage.setItem('chat-listing-open-agents', JSON.stringify(newOpenAgents));
            } catch (error) {
              console.error('Failed to save open agents to sessionStorage:', error);
            }
          }
        }

        // Update agent counts
        try {
          const agentsData = await getAgentsWithConversationCounts();
          setAgents(agentsData);
        } catch (error) {
          console.error('Error refreshing agent counts:', error);
        }
      } catch (error) {
        console.error('Error adding conversation to list:', error);
      }
    };

    const listener = handleNewConversation as unknown as EventListener;
    window.addEventListener('huf:conversation-created', listener);
    
    return () => {
      window.removeEventListener('huf:conversation-created', listener);
    };
  }, [openAgents, activeTab]);

  // Handle accordion open/close and persist to sessionStorage
  const handleAccordionChange = useCallback((value: string[]) => {
    setOpenAgents(value);
    try {
      sessionStorage.setItem('chat-listing-open-agents', JSON.stringify(value));
    } catch (error) {
      console.error('Failed to save open agents to sessionStorage:', error);
    }
  }, []);

  const handleAgentSelect = useCallback((agentId: string) => {
    // Automatically navigate to new chat when agent is selected
    navigate(`/chat/new?agent=${agentId}`);
  }, [navigate]);

  return (
    <div className="h-full min-w-80 bg-sidebar flex flex-col overflow-hidden border-r border-line">
      <div className="shrink-0 px-3 pt-3 pb-2 sticky top-0 z-1 bg-sidebar">
        <ChatListHeader onAgentSelect={handleAgentSelect} onClose={onClose} />
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto px-3 pb-3 bg-sidebar [&::-webkit-scrollbar]:w-0 [-ms-overflow-style:none] [scrollbar-width:none]" id="chat-listing-scroll">
        <Tabs defaultValue="recents" value={activeTab} onValueChange={setActiveTab} className="space-y-2">
        <div className="sticky top-0 z-1 bg-sidebar">
          <TabsList variant="pill" layout="grid" cols={2} size="compact" className="w-full">
            {LIST_TABS.map((tab) => (
              <TabsTrigger
                key={tab.value}
                className="w-full space-x-1.5"
                value={tab.value}
              >
                <tab.icon className="w-3 h-3" />
                <span>{tab.label}</span>
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <TabsContent value="agent" className="mt-0">
          {agentsLoading ? (
            <div className="space-y-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={`agent-skel-${i}`} className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Skeleton className="h-7 w-7 rounded-full" />
                    <Skeleton className="h-4 w-40" />
                  </div>
                  <div className="ml-3 pl-3 border-l border-line space-y-2">
                    <Skeleton className="h-10 w-full rounded" />
                    <Skeleton className="h-10 w-full rounded" />
                  </div>
                </div>
              ))}
            </div>
          ) : agents.length === 0 ? (
            <div className="p-3 text-sm font-body text-steel-soft text-center">No agents with conversations</div>
          ) : (
            <Accordion
              type="multiple"
              value={openAgents}
              className="space-y-2"
              onValueChange={handleAccordionChange}
            >
              {agents.map((agent) => (
                <AgentConversationItem
                  key={agent.name}
                  agent={agent}
                  selectedChatId={selectedChatId}
                  isOpen={openAgents.includes(agent.name)}
                  onRename={handleRename}
                  onFork={handleFork}
                  titleRefs={titleRefs}
                  animatingConversationId={animatingConversationId}
                  onAddItemReady={(addItem: (item: ChatListItem) => void) => {
                    agentAddItemRefs.current.set(agent.name, addItem);
                  }}
                />
              ))}
            </Accordion>
          )}
        </TabsContent>

        <TabsContent value="recents">
          <RecentsConversationList
            selectedChatId={selectedChatId}
            isActive={activeTab === 'recents'}
            onRename={handleRename}
            onFork={handleFork}
            titleRefs={titleRefs}
            animatingConversationId={animatingConversationId}
            onAddItemReady={(addItem) => {
              recentsAddItemRef.current = addItem;
            }}
          />
        </TabsContent>
        </Tabs>
      </div>
      <ForkConversationDialog
        conversationId={forkDialogConversationId || ''}
        conversationTitle={forkDialogTitle}
        agentName={forkDialogAgentName}
        open={forkDialogOpen}
        onOpenChange={setForkDialogOpen}
        onForked={handleForked}
      />
    </div>
  );
}

// Component for individual agent conversation list with infinite scroll
function AgentConversationItem({
  agent,
  selectedChatId,
  isOpen,
  onRename,
  onFork,
  titleRefs,
  animatingConversationId,
  onAddItemReady,
}: {
  agent: AgentWithCount;
  selectedChatId: string | null;
  isOpen: boolean;
  onRename: (conversationId: string) => void;
  onFork: (conversationId: string, title: string, agentName: string) => void;
  titleRefs: React.MutableRefObject<Map<string, ConversationTitleRef>>;
  animatingConversationId: string | null;
  onAddItemReady: (addItem: (item: ChatListItem) => void) => void;
}) {
  const navigate = useNavigate();

  const handleNewConversation = useCallback((e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent accordion from toggling
    navigate(`/chat/new?agent=${agent.name}`);
  }, [navigate, agent.name]);
  const {
    items: conversations,
    initialLoading,
    loadingMore,
    hasMore,
    loadMore,
    addItem,
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

  // Store addItem function in ref for parent to use
  useEffect(() => {
    if (addItem && isOpen && onAddItemReady) {
      onAddItemReady(addItem as (item: ChatListItem) => void);
    }
  }, [addItem, isOpen, onAddItemReady]);

  return (
    <AccordionItem value={agent.name} className="border-b-0">
      <AccordionTrigger
        className="group gap-2 mb-1 py-1 px-1 hover:bg-paper-deep cursor-pointer select-none rounded-md"
        arrowPosition="left"
      >
        <div className="flex-1 flex gap-x-2 items-center">
          <ChatAvatar variant="listing_ai" color={agent.agent_color || undefined}>
            {getInitials(agent.agent_name)}
          </ChatAvatar>
          <span className="text-sm font-medium truncate text-steel group-hover:text-ink transition-colors">
            {agent.agent_name}
          </span>
        </div>
        <span className="text-[10px] min-w-6 text-steel-soft bg-paper-deep px-1.5 py-0.5 rounded-full border border-line ml-auto">
          {agent.conversationCount}
        </span>
        <Button 
          size="icon" 
          variant="ghost" 
          className="h-fit w-fit opacity-0 group-hover:opacity-100 p-1 hover:bg-paper-deep rounded text-steel-soft hover:text-ink transition-all ml-1"
          onClick={handleNewConversation}
        >
          <Plus className="w-3.5 h-3.5" />
          <span className="sr-only">New Conversation</span>
        </Button>
      </AccordionTrigger>

      <AccordionContent className="space-y-0.5 ml-3 pl-3 border-l border-line overflow-hidden transition-all duration-300 opacity-100">
        {initialLoading ? (
          <div className="space-y-2 p-2">
            <Skeleton className="h-10 w-full rounded" />
            <Skeleton className="h-10 w-full rounded" />
          </div>
        ) : conversations.length === 0 && agent.conversationCount === 0 ? (
          <div className="p-2 text-xs font-body text-steel-soft">No conversations</div>
        ) : conversations.length === 0 && agent.conversationCount > 0 ? (
          <div className="space-y-2 p-2">
            <Skeleton className="h-10 w-full rounded" />
            <Skeleton className="h-10 w-full rounded" />
          </div>
        ) : (
          <>
            {conversations.map((chat) => {
              const isSelected = selectedChatId === chat.id;
              return (
                <ConversationMenu
                  key={chat.id}
                  onRename={() => onRename(chat.id)}
                  onFork={() => onFork(chat.id, chat.title, agent.name)}
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
                      'group flex w-full text-left flex-col p-1 rounded-md cursor-pointer transition-all border-l-2',
                      isSelected
                        ? 'bg-paper-deep border-signal'
                        : 'bg-transparent border-transparent hover:bg-paper-deep hover:border-line'
                    )}
                  >
                    <ConversationTitle
                      ref={(el) => {
                        if (el) titleRefs.current.set(chat.id, el);
                        else titleRefs.current.delete(chat.id);
                      }}
                      variant="agent_list"
                      value={chat.title}
                      conversationId={chat.id}
                      animate={animatingConversationId === chat.id}
                      className={isUntitledConversationTitle(chat.title) ? 'italic text-steel-soft' : undefined}
                    />
                    <p className="ps-1 text-[10px] text-steel-soft truncate mt-0.5 group-hover:text-steel">
                      {chat.timestampLabel ?? ''}
                    </p>
                  </Link>
                </ConversationMenu>
              );
            })}
            {hasMore && (
              <Button
                type="button"
                variant="ghost"
                onClick={(e) => {
                  e.stopPropagation(); // Prevent accordion from closing
                  loadMore();
                }}
                disabled={loadingMore}
                className={cn(
                  'h-auto w-full py-2 px-2 text-center text-xs text-steel hover:bg-transparent hover:text-ink',
                  loadingMore && 'opacity-50 cursor-not-allowed'
                )}
              >
                {loadingMore ? 'Loading...' : 'Load More'}
              </Button>
            )}
          </>
        )}
      </AccordionContent>
    </AccordionItem>
  );
}

function RecentsConversationList({
  selectedChatId,
  isActive,
  onRename,
  onFork,
  titleRefs,
  animatingConversationId,
  onAddItemReady,
}: {
  selectedChatId: string | null;
  isActive: boolean;
  onRename: (conversationId: string) => void;
  onFork: (conversationId: string, title: string, agentName: string) => void;
  titleRefs: React.MutableRefObject<Map<string, ConversationTitleRef>>;
  animatingConversationId: string | null;
  onAddItemReady: (addItem: (item: ChatListItem) => void) => void;
}) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [agentColorMap, setAgentColorMap] = useState<Map<string, string | null>>(new Map());
  
  const {
    chats: conversations,
    initialLoading,
    loadingMore,
    hasMore,
    error,
    sentinelRef,
    scrollRef,
    addItem,
  } = useChatList({
    enabled: isActive, // Only load when tab is active
    refreshOnRouteChange: false, // Don't refresh on route change for this use case
  });

  // Store addItem function in ref for parent to use
  useEffect(() => {
    if (addItem && isActive && onAddItemReady) {
      onAddItemReady(addItem as (item: ChatListItem) => void);
    }
  }, [addItem, isActive, onAddItemReady]);

  // Fetch agent colors for unique agents in conversations
  useEffect(() => {
    if (!isActive || conversations.length === 0) return;

    const uniqueAgents = Array.from(new Set(conversations.map(chat => chat.agent).filter(Boolean)));
    const newColorMap = new Map<string, string | null>();

    // Fetch colors for all unique agents
    Promise.all(
      uniqueAgents.map(async (agentName) => {
        try {
          const agentData = await getAgent(agentName);
          return { name: agentName, color: agentData.agent_color || null };
        } catch (error) {
          console.error(`Failed to fetch agent color for ${agentName}:`, error);
          return { name: agentName, color: null };
        }
      })
    ).then((results) => {
      results.forEach(({ name, color }) => {
        newColorMap.set(name, color);
      });
      setAgentColorMap(newColorMap);
    });
  }, [conversations, isActive]);

  // Set the scroll ref to the parent scroll container (the main ChatListing scroll area)
  useEffect(() => {
    // Find the parent scroll container
    const parentScroll = scrollContainerRef.current?.closest('#chat-listing-scroll') as HTMLDivElement | null;
    if (parentScroll) {
      scrollRef.current = parentScroll;
    } else if (scrollContainerRef.current) {
      scrollRef.current = scrollContainerRef.current;
    }
  }, [scrollRef]);

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
      <div className="space-y-1">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={`recent-skel-${i}`} className="flex px-2 py-1.5 gap-2 items-center rounded-md">
            <Skeleton className="h-6 w-6 rounded-full shrink-0" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3 w-2/3" />
              <Skeleton className="h-2.5 w-1/3" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div ref={scrollContainerRef} className="space-y-3">
        {byRecents.every(([, items]) => items.length === 0) ? (
          <div className="p-3 text-sm font-body text-steel-soft text-center">No conversations yet</div>
        ) : (
          <>
            {byRecents.map(([label, items]) => {
              if (items.length === 0) return null;
              return (
                <div key={label}>
                  <span className="px-1 text-[10px] font-medium text-steel-soft uppercase tracking-wider">
                    {label}
                  </span>
                  <div className="mt-1 space-y-0.5">
                    {items.map((chat) => {
                      const isSelected = selectedChatId === chat.id;
                      return (
                        <ConversationMenu
                          key={chat.id}
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
                              'group flex w-full text-left px-2 py-1.5 gap-2 items-center rounded-md cursor-pointer transition-all',
                              isSelected
                                ? 'bg-panel border-l-2 border-signal'
                                : 'bg-transparent hover:bg-panel'
                            )}
                          >
                            <ChatAvatar 
                              variant="chat_ai"
                              color={agentColorMap.get(chat.agent) || undefined}
                            >
                              {getInitials(chat.agent)}
                            </ChatAvatar>
                            <div className="flex-1 min-w-0 mb-1">
                              <ConversationTitle
                                ref={(el) => {
                                  if (el) titleRefs.current.set(chat.id, el);
                                  else titleRefs.current.delete(chat.id);
                                }}
                                variant="recents_list"
                                value={chat.title}
                                conversationId={chat.id}
                                animate={animatingConversationId === chat.id}
                                className={isUntitledConversationTitle(chat.title) ? 'italic text-steel-soft' : undefined}
                              />
                              <p className="ps-1 text-xs truncate text-steel">{chat.agent}</p>
                            </div>
                            <span className="mb-1 flex-shrink-0 text-[10px] text-steel-soft flex-shrink-0 self-end">
                              {chat.timestampLabel ?? ''}
                            </span>
                          </Link>
                        </ConversationMenu>
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
              <div className="p-2 text-xs font-body text-steel-soft text-center">Loading more...</div>
            )}
          </>
        )}
    </div>
  );
}

function ChatListHeader({ 
  onAgentSelect,
  onClose,
}: { 
  onAgentSelect?: (agentId: string) => void;
  onClose?: () => void;
}) {
  const [selectedAgent, setSelectedAgent] = useState<string>('');

  const handleAgentChange = useCallback((agentId: string) => {
    setSelectedAgent(agentId);
    onAgentSelect?.(agentId);
  }, [onAgentSelect]);

  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <SidebarTrigger className="-ml-1" />
        <div className="flex flex-col leading-none">
          <span className="font-mono text-eyebrow uppercase text-steel-soft">Conversations</span>
          <h1 className="font-semibold text-sm tracking-tight text-ink">Chat</h1>
        </div>
      </div>
      <div className="flex items-center gap-1">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-steel hover:text-ink"
        >
          <Search className="w-4 h-4" />
          <span className="sr-only">Search conversations</span>
        </Button>
        {onAgentSelect && (
          <ChatAgentPicker
            value={selectedAgent}
            onValueChange={handleAgentChange}
          />
        )}
        {onClose && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-steel hover:text-ink"
            onClick={onClose}
          >
            <PanelLeftClose className="w-4 h-4" />
            <span className="sr-only">Close sidebar</span>
          </Button>
        )}
      </div>
    </div>
  );
}

const LIST_TABS = [
  {
    value: 'agent',
    label: 'By agent',
    icon: Users,
  },
  {
    value: 'recents',
    label: 'Recents',
    icon: Clock4,
  },
];
