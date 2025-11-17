import { useEffect, useState } from 'react';
import { useSidebar } from '@/components/ui/sidebar';
import { ChatList } from '@/components/chat/ChatList';
import { ChatWindow } from '@/components/chat/ChatWindow';

export function ChatPage() {
  const { setOpen } = useSidebar();
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);

  // Collapse the main sidebar when chat page loads
  useEffect(() => {
    // console.log('ChatPage loaded');
    setOpen(false);
  }, []);

  return (
    <div className="flex h-screen min-h-0 w-full overflow-hidden">
      <ChatList selectedChatId={selectedChatId} onSelectChat={setSelectedChatId} />
      <div className="flex-1 min-h-0">
        <ChatWindow chatId={selectedChatId} />
      </div>
    </div>
  );
}
