import ChatWindow from '@/components/chat/ChatWindowV2';
import { useNavigate } from 'react-router-dom';

// The "App Planner" agent is created at install time (see huf/install.py).
// ChatWindowV2 with no chatId opens a new conversation and allows agent selection.
// We pass a default agentName so it starts scoped to the planner.
export default function AppPlannerPage() {
  const navigate = useNavigate();

  function handleConversationCreated(conversationId: string) {
    navigate(`/apps/new/${conversationId}`, { replace: true });
  }

  return (
    <div className="h-full">
      <ChatWindow
        chatId={null}
        defaultAgentName="App Planner"
        onConversationCreated={handleConversationCreated}
      />
    </div>
  );
}
