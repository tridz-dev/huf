// Placeholder destination pages for spec section 28's chat rail rows.
// Projects and Scheduled have no backing schema yet; these exist so no rail row
// is a dead control that navigates nowhere.

import { useNavigate } from 'react-router-dom';
import { Folder, FileText, Clock } from 'lucide-react';
import { EmptyState } from '@/components/dashboard/views/EmptyState';
import { ChatShellFrame } from '@/components/chat/rail/ChatShellFrame';

export function ChatProjectsPage() {
  const navigate = useNavigate();

  return (
    <ChatShellFrame>
      <div className="flex h-full w-full items-center justify-center">
        <EmptyState
          variant="passive"
          icon={Folder}
          title="No projects yet"
          description="Projects group related conversations so they share context and files."
          secondaryAction={{
            label: 'Start a chat',
            onClick: () => navigate('/chat/new'),
          }}
        />
      </div>
    </ChatShellFrame>
  );
}

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
