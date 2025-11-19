import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useSidebar } from '@/components/ui/sidebar';
import { ChatList, mockChats } from '@/components/chat/ChatList';
import { ChatWindow } from '@/components/chat/ChatWindow';

export function ChatPage() {
  const navigate = useNavigate();
  const { chatId: routeChatId } = useParams<{ chatId?: string }>();
  const { setOpen } = useSidebar();
  const normalizedChatId = routeChatId && routeChatId !== 'new' ? routeChatId : null;
  const [selectedChatId, setSelectedChatId] = useState<string | null>(normalizedChatId);

  // Collapse the main sidebar when chat page loads
  useEffect(() => {
    // console.log('ChatPage loaded');
    setOpen(false);
  }, []);

  useEffect(() => {
    setSelectedChatId(normalizedChatId);
  }, [normalizedChatId]);

  useEffect(() => {
    if (!routeChatId && mockChats.length > 0) {
      navigate(`/chat/${mockChats[0].id}`, { replace: true });
    }
  }, [routeChatId, navigate]);

  const handleSelectChat = (chatId: string) => {
    setSelectedChatId(chatId);
    navigate(`/chat/${chatId}`);
  };

  const handleNewChat = () => {
    setSelectedChatId(null);
    navigate('/chat/new');
  };

  return (
    <div className="flex h-screen min-h-0 w-full overflow-hidden">
      <ChatList
        selectedChatId={selectedChatId}
        onSelectChat={handleSelectChat}
        onNewChat={handleNewChat}
      />
      <div className="flex-1 min-h-0">
        <ChatWindow chatId={selectedChatId} />
      </div>
    </div>
  );
}
