import { MoreVertical, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import type { HufProject } from '@/services/projectApi';

export interface ProjectHeaderProps {
  project: HufProject | null;
  loading?: boolean;
  onNewChat: () => void;
}

// Small reusable header for the project landing page: name, description, the
// primary "+ New chat" action, and an overflow menu. The overflow menu's real
// actions (rename, edit instructions, archive) belong to a later task - this
// is deliberately a stub so the control isn't a dead end without pretending
// to be more than it is yet.
export function ProjectHeader({ project, loading, onNewChat }: ProjectHeaderProps) {
  return (
    <div className="flex flex-none items-start justify-between gap-4 border-b border-line px-6 py-5">
      <div className="min-w-0">
        {loading ? (
          <>
            <Skeleton className="h-6 w-48" />
            <Skeleton className="mt-2 h-4 w-72" />
          </>
        ) : (
          <>
            <h1 className="truncate text-[17px] font-semibold text-ink">
              {project?.project_name ?? 'Untitled project'}
            </h1>
            {project?.description && (
              <p className="mt-1 max-w-2xl text-[13px] text-steel">{project.description}</p>
            )}
          </>
        )}
      </div>

      <div className="flex flex-none items-center gap-2">
        <Button size="sm" onClick={onNewChat}>
          <Plus className="mr-1.5 h-4 w-4" />
          New chat
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm">
              <MoreVertical className="h-4 w-4" />
              <span className="sr-only">Project options</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {/* Stub actions - archive/edit land in a later task. */}
            <DropdownMenuItem disabled>Edit project</DropdownMenuItem>
            <DropdownMenuItem disabled>Archive project</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
