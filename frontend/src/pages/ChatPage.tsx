import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useSidebar } from '@/components/ui/sidebar';
import { ChatList } from '@/components/chat/ChatList';
import { ChatWindow } from '@/components/chat/ChatWindow';
import { findScrollableContainer } from '@/utils/htmlUtils';
import { useIsMobile } from '@/hooks/use-mobile';

export function ChatPage() {
  const navigate = useNavigate();
  const { chatId: routeChatId } = useParams<{ chatId?: string }>();
  const { setOpen } = useSidebar();
  const isMobile = useIsMobile();
  const normalizedChatId = routeChatId && routeChatId !== 'new' ? routeChatId : null;
  const [selectedChatId, setSelectedChatId] = useState<string | null>(normalizedChatId);
  const [chatListRefreshKey, setChatListRefreshKey] = useState(0);
  const chatPageRef = useRef<HTMLDivElement>(null);
  const chatWindowRef = useRef<HTMLDivElement>(null);

  // Close sidebar on initial mount only
  useEffect(() => {
    setOpen(false);
  }, []);

  // Scroll to bottom when chat content changes
  useEffect(() => {
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
  }, [selectedChatId]);

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
      {/* Desktop: Always visible sidebar */}
      {!isMobile && (
        <div className="hidden md:block">
          <ChatList
            selectedChatId={selectedChatId}
            onSelectChat={handleSelectChat}
            onNewChat={handleNewChat}
            refreshKey={chatListRefreshKey}
          />
        </div>
      )}

      {/* Mobile: Chat list is shown in app sidebar, so we just show the chat window */}
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
