import { useNavigate, useParams } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import type { ChatListItem } from '@/services/chatApi';
import { useSidebar } from '@/components/ui/sidebar';
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar';
import { ChatListBase } from './ChatListBase';

export function ChatSidebarContent() {
  const navigate = useNavigate();
  const { chatId: routeChatId } = useParams<{ chatId?: string }>();
  const { isMobile, setOpenMobile } = useSidebar();
  const selectedChatId = routeChatId && routeChatId !== 'new' ? routeChatId : null;

  const handleSelectChat = (chatId: string) => {
    navigate(`/chat/${chatId}`);
    if (isMobile) {
      setOpenMobile(false);
    }
  };

  const handleNewChat = () => {
    navigate('/chat/new');
    if (isMobile) {
      setOpenMobile(false);
    }
  };

  const renderChatItem = (chat: ChatListItem, isSelected: boolean, onClick: () => void) => (
    <SidebarMenuItem>
      <SidebarMenuButton
        asChild
        isActive={isSelected}
        onClick={onClick}
      >
        <div className="flex flex-col items-start gap-1 w-full">
          <div className="flex items-center justify-between gap-2 w-full">
            <p className="text-sm font-medium truncate flex-1">{chat.title}</p>
          </div>
          {chat.agent && (
            <p className="text-xs text-muted-foreground truncate w-full">
              {chat.agent}
            </p>
          )}
          {chat.timestamp && (
            <p className="text-xs text-muted-foreground">
              {chat.timestamp}
            </p>
          )}
        </div>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );

  const renderSkeleton = () => (
    <SidebarMenuItem>
      <div className="flex items-center gap-3 p-2">
        <div className="flex-1 min-w-0 space-y-2">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      </div>
    </SidebarMenuItem>
  );

  const renderLoadingMore = () => (
    <div className="px-3 py-2 space-y-2">
      {Array.from({ length: 2 }).map((_, i) => (
        <SidebarMenuItem key={`loading-more-${i}`}>
          <div className="flex items-center gap-3 p-2">
            <div className="flex-1 min-w-0 space-y-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          </div>
        </SidebarMenuItem>
      ))}
    </div>
  );

  const renderContainer = (children: React.ReactNode, scrollRef: React.RefObject<HTMLDivElement>) => (
    <SidebarGroup>
      <div className="px-2 pb-2">
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
      <SidebarGroupLabel>Conversations</SidebarGroupLabel>
      <ScrollArea ref={scrollRef} className="flex-1">
        <SidebarMenu>
          {children}
        </SidebarMenu>
      </ScrollArea>
    </SidebarGroup>
  );

  return (
    <ChatListBase
      selectedChatId={selectedChatId}
      onSelectChat={handleSelectChat}
      onNewChat={handleNewChat}
      refreshOnRouteChange={true}
      variant="sidebar"
      showNewChatButton={false}
      renderItem={renderChatItem}
      renderSkeleton={renderSkeleton}
      renderLoadingMore={renderLoadingMore}
      renderContainer={renderContainer}
    />
  );
}
