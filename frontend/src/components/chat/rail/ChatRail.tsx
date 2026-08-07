import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { cn } from '@/lib/utils';
import type { ChatListItem } from '@/services/chatApi';
import { getConversation } from '@/services/chatApi';
import { getAgent } from '@/services/agentApi';
import { ChatRailToolbar } from './ChatRailToolbar';
import { ChatRailNav } from './ChatRailNav';
import { ChatRailHistory } from './ChatRailHistory';
import { ChatRailFooter } from './ChatRailFooter';
import { ForkConversationDialog } from '../ForkConversationDialog';
import type { ConversationTitleRef } from '../ConversationTitle';
import {
  type ConversationTitleUpdatedDetail,
  useConversationTitleSwitchFallback,
} from '../useConversationTitleFallback';

export interface ChatRailProps {
  onToggleRail: () => void;
  className?: string;
}

export function ChatRail({ onToggleRail, className }: ChatRailProps) {
  const navigate = useNavigate();
  const { chatId: routeChatId } = useParams<{ chatId?: string }>();
  const selectedChatId = routeChatId && routeChatId !== 'new' ? routeChatId : null;

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

  // Ref to store the addItem function from ChatRailHistory
  const addItemRef = useRef<((item: ChatListItem) => void) | null>(null);

  // Stable identity: ChatRailHistory lists this in an effect's deps, so an
  // inline arrow would re-run that effect on every render of the rail.
  const handleAddItemReady = useCallback((addItem: (item: ChatListItem) => void) => {
    addItemRef.current = addItem;
  }, []);

  const handleRename = useCallback((conversationId: string) => {
    const titleRef = titleRefs.current.get(conversationId);
    if (titleRef) {
      titleRef.activateInput();
    }
  }, []);

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
      };

      addItemRef.current?.(conversationItem);
    } catch (error) {
      console.error('Error updating conversation title in list:', error);
    }
  }, [selectedChatId]);

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

  // Both this rail (handleForked, above) and ChatPageV2 (on first-message conversation
  // creation) dispatch huf:conversation-created. Without this listener a brand-new or
  // forked conversation never appears in Recents until a full page reload, since
  // ChatRailHistory mounts with refreshOnRouteChange: false.
  const applyConversationCreated = useCallback(
    async (detail: { conversationId: string; agentName?: string }) => {
      const { conversationId, agentName } = detail;

      try {
        const conversationDoc = await getConversation(conversationId);
        if (!conversationDoc) return;

        const conversationItem: ChatListItem = {
          id: conversationId,
          title: conversationDoc.title || 'Untitled Chat',
          agent: conversationDoc.agent || agentName || '',
          timestamp: conversationDoc.last_activity || conversationDoc.modified,
        };

        addItemRef.current?.(conversationItem);
      } catch (error) {
        console.error('Error adding new conversation to list:', error);
      }
    },
    []
  );

  useEffect(() => {
    const handleConversationCreated = (event: Event) => {
      const customEvent = event as CustomEvent<{ conversationId: string; agentName?: string }>;
      void applyConversationCreated(customEvent.detail);
    };

    window.addEventListener('huf:conversation-created', handleConversationCreated);
    return () => {
      window.removeEventListener('huf:conversation-created', handleConversationCreated);
    };
  }, [applyConversationCreated]);

  // The header's overflow menu cannot reach handleRename (and the row's
  // ConversationTitle ref) directly, so it dispatches this event instead.
  useEffect(() => {
    const handleRenameRequest = (event: Event) => {
      const customEvent = event as CustomEvent<{ conversationId: string }>;
      handleRename(customEvent.detail.conversationId);
    };

    window.addEventListener('huf:conversation-rename-request', handleRenameRequest);
    return () => {
      window.removeEventListener('huf:conversation-rename-request', handleRenameRequest);
    };
  }, [handleRename]);

  return (
    <>
      <aside className={cn('flex h-full w-chat-rail flex-none flex-col border-r border-line bg-paper', className)}>
        <ChatRailToolbar onToggleRail={onToggleRail} />
        <ChatRailNav />
        <ChatRailHistory
          selectedChatId={selectedChatId}
          onRename={handleRename}
          onFork={handleFork}
          titleRefs={titleRefs}
          animatingConversationId={animatingConversationId}
          onAddItemReady={handleAddItemReady}
        />
        <ChatRailFooter />
      </aside>
      <ForkConversationDialog
        conversationId={forkDialogConversationId || ''}
        conversationTitle={forkDialogTitle}
        agentName={forkDialogAgentName}
        open={forkDialogOpen}
        onOpenChange={setForkDialogOpen}
        onForked={handleForked}
      />
    </>
  );
}
