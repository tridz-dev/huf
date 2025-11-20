import { useEffect, useState } from 'react';
import { Trash2, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { getConversations } from '@/services/chatApi';
import { formatTimeAgo } from '@/utils/time';

interface Chat {
  id: string;
  title: string;
  agent: string;
  timestamp?: string;
}

interface ChatListProps {
  selectedChatId: string | null;
  onSelectChat: (chatId: string) => void;
  onNewChat?: () => void;
}

export function ChatList({ selectedChatId, onSelectChat, onNewChat }: ChatListProps) {
  const [chats, setChats] = useState<Chat[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function fetchConversations() {
      try {
        setIsLoading(true);
        const conversations = await getConversations();
        const mappedChats: Chat[] = conversations.map((conv) => ({
          id: conv.id,
          title: conv.title,
          agent: conv.agent,
          timestamp: conv.timestamp ? formatTimeAgo(conv.timestamp) : undefined,
        }));
        setChats(mappedChats);
      } catch (error) {
        console.error('Error fetching conversations:', error);
        setChats([]);
      } finally {
        setIsLoading(false);
      }
    }

    fetchConversations();
  }, []);

  const handleNewChat = () => {
    onNewChat?.();
  };

  const handleDeleteChat = (chatId: string, e: React.MouseEvent) => {
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
      <ScrollArea className="flex-1 overflow-y-auto">
        <div className="space-y-1">
          {isLoading ? (
            <div className="p-3 text-sm text-muted-foreground text-center">Loading...</div>
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
        </div>
      </ScrollArea>
    </div>
  );
}

