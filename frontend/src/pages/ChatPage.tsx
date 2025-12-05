import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useSidebar } from '@/components/ui/sidebar';
import { ChatList } from '@/components/chat/ChatList';
import { ChatWindow } from '@/components/chat/ChatWindow';
import { findScrollableContainer } from '@/utils/htmlUtils';

export function ChatPage() {
  const navigate = useNavigate();
  const { chatId: routeChatId } = useParams<{ chatId?: string }>();
  const { setOpen } = useSidebar();
  const normalizedChatId = routeChatId && routeChatId !== 'new' ? routeChatId : null;
  const [selectedChatId, setSelectedChatId] = useState<string | null>(normalizedChatId);
  const [chatListRefreshKey, setChatListRefreshKey] = useState(0);
  const chatPageRef = useRef<HTMLDivElement>(null);
  const chatWindowRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom when page mounts and content is loaded
  useEffect(() => {
    setOpen(false);
    
    const scrollToBottom = () => {
      if (!chatWindowRef.current) 
        return;
      const container = findScrollableContainer(chatWindowRef.current);
      
      if (container === window) {
        window.scrollTo({
          top: document.documentElement.scrollHeight,
          behavior: 'smooth',
        });
      } else if (container instanceof HTMLElement) {
        container.scrollTo({
          top: container.scrollHeight,
          behavior: 'smooth',
        });
      }
    };
    scrollToBottom();
  }, [setOpen, selectedChatId]);

  useEffect(() => {
    setSelectedChatId(normalizedChatId);
  }, [normalizedChatId]);

  const handleSelectChat = (chatId: string) => {
    setSelectedChatId(chatId);
    navigate(`/chat/${chatId}`);
  };

  const handleNewChat = () => {
    setSelectedChatId(null);
    navigate('/chat/new');
  };

  return (
    <div className="flex h-screen min-h-0 w-full overflow-hidden" ref={chatPageRef}>
      <ChatList
        selectedChatId={selectedChatId}
        onSelectChat={handleSelectChat}
        onNewChat={handleNewChat}
        refreshKey={chatListRefreshKey}
      />
      <div className="flex-1 min-h-0" ref={chatWindowRef}>
        <ChatWindow
          chatId={selectedChatId}
          onConversationCreated={(conversationId) => {
            setChatListRefreshKey((prev) => prev + 1);
            handleSelectChat(conversationId);
          }}
        />
      </div>
    </div>
  );
}
