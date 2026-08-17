// Placeholder destination pages for spec section 28 chat rail rows.
// Scheduled has no backing schema yet; Artifacts has a real global feed
// (see A9+) that has not landed here yet either. These exist so no rail
// row is a dead control that navigates nowhere.
// (ChatProjectsPage moved to its own file - ./ChatProjectsPage.tsx - once
// it grew beyond a placeholder; see A7.)

import { useNavigate } from 'react-router-dom';
import { FileText, Clock } from 'lucide-react';
import { EmptyState } from '@/components/dashboard/views/EmptyState';
import { ChatShellFrame } from '@/components/chat/rail/ChatShellFrame';

export function ChatArtifactsPage() {
  const navigate = useNavigate();

  return (
    <ChatShellFrame>
      <div className="flex h-full w-full items-center justify-center">
        <EmptyState
          variant="passive"
          icon={FileText}
          title="No artifacts yet"
          description="Documents and files an agent produces are collected here."
          secondaryAction={{
            label: 'Start a chat',
            onClick: () => navigate('/chat/new'),
          }}
        />
      </div>
    </ChatShellFrame>
  );
}

export function ChatScheduledPage() {
  const navigate = useNavigate();

  return (
    <ChatShellFrame>
      <div className="flex h-full w-full items-center justify-center">
        <EmptyState
          variant="passive"
          icon={Clock}
          title="Nothing scheduled"
          description="Conversations set to run on a schedule will appear here."
          secondaryAction={{
            label: 'Start a chat',
            onClick: () => navigate('/chat/new'),
          }}
        />
      </div>
    </ChatShellFrame>
  );
}
