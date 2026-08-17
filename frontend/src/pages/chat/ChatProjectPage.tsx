import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { MessageSquare, MessagesSquare } from 'lucide-react';
import { ChatShellFrame } from '@/components/chat/rail/ChatShellFrame';
import { ProjectHeader } from '@/components/chat/projects/ProjectHeader';
import { EmptyState } from '@/components/dashboard/views/EmptyState';
import { Skeleton } from '@/components/ui/skeleton';
import { getProject, type HufProject } from '@/services/projectApi';
import { useChatList } from '@/components/chat/useChatList';
import { cn } from '@/lib/utils';

// Project landing page (main area, not a chat screen itself). Spec: the
// project's conversations render as one flat chronological list with a
// subtle Agent chip per row - explicitly NOT grouped/accordioned by Agent.
export default function ChatProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [project, setProject] = useState<HufProject | null>(null);
  const [projectLoading, setProjectLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    if (!projectId) return;

    setProjectLoading(true);
    getProject(projectId).then((result) => {
      if (!cancelled) {
        setProject(result ?? null);
        setProjectLoading(false);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const { chats, initialLoading, loadingMore, hasMore, error, sentinelRef } = useChatList({
    project: projectId,
  });

  function handleNewChat() {
    navigate(`/chat/new?project=${encodeURIComponent(projectId ?? '')}`);
  }

  return (
    <ChatShellFrame>
      <div className="flex h-full w-full flex-col overflow-hidden">
        <ProjectHeader project={project} loading={projectLoading} onNewChat={handleNewChat} />

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="px-6 py-4 text-[11px] font-medium tracking-wide text-steel-soft">
            RECENT CHATS
          </div>

          {error ? (
            <div className="px-6 text-[13px] text-destructive">Could not load conversations</div>
          ) : initialLoading ? (
            <div className="space-y-1 px-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={`project-chat-skel-${i}`} className="flex items-center gap-3 px-2 py-2.5">
                  <Skeleton className="h-4 w-4 rounded" />
                  <Skeleton className="h-4 w-1/3" />
                </div>
              ))}
            </div>
          ) : chats.length === 0 ? (
            <EmptyState
              variant="create"
              icon={MessagesSquare}
              title="No conversations yet."
              description="Chats you start in this project will show up here."
              action={{ label: 'Start a chat', onClick: handleNewChat }}
            />
          ) : (
            <div className="px-4 pb-4">
              {chats.map((chat) => (
                <button
                  key={chat.id}
                  type="button"
                  onClick={() => navigate(`/chat/${chat.id}`)}
                  className={cn(
                    'group flex w-full items-center gap-3 rounded-chat-row px-2 py-2.5 text-left text-[13px] transition-colors hover:bg-chat-row-hover'
                  )}
                >
                  <MessageSquare className="h-[15px] w-[15px] shrink-0 text-steel-soft" />
                  <span className="min-w-0 flex-1 truncate text-ink">{chat.title || 'Untitled Chat'}</span>
                  {chat.agent && (
                    <span className="shrink-0 rounded-full bg-paper-deep px-2 py-0.5 text-[11px] text-steel">
                      {chat.agent}
                    </span>
                  )}
                </button>
              ))}
              {hasMore && <div ref={sentinelRef} className="h-2 w-full opacity-0" aria-hidden="true" />}
              {loadingMore && (
                <div className="px-2 py-2 text-[11px] text-steel-soft">Loading more…</div>
              )}
            </div>
          )}
        </div>
      </div>
    </ChatShellFrame>
  );
}
