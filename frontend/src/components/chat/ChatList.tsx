import { cn } from '@/lib/utils';
import type { ChatListItem } from '@/services/chatApi';
import { ChatListBase } from './ChatListBase';

interface ChatListProps {
  selectedChatId: string | null;
  onSelectChat: (chatId: string) => void;
  onNewChat?: () => void;
  refreshKey?: number;
  onChatSelect?: () => void;
}

export function ChatList({ selectedChatId, onSelectChat, onNewChat, refreshKey, onChatSelect }: ChatListProps) {
  const renderChatItem = (chat: ChatListItem, isSelected: boolean, onClick: () => void) => (
    <div
      onClick={onClick}
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

  return (
    <ChatListBase
      selectedChatId={selectedChatId}
      onSelectChat={onSelectChat}
      onNewChat={onNewChat}
      refreshKey={refreshKey}
      onChatSelect={onChatSelect}
      variant="standalone"
      renderItem={renderChatItem}
    />
  );
}

